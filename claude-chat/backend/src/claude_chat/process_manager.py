"""Long-lived `claude` processes, one per active session.

Each ClaudeProcess wraps an `asyncio.subprocess.Process` running
`claude -p --input-format stream-json --output-format stream-json ...`,
with a background reader task that fans stdout events into an asyncio.Queue
and a stdin lock that serializes turns.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import time
from collections.abc import AsyncIterator
from typing import Literal

log = logging.getLogger("claude_chat.process_manager")

ProcessState = Literal["spawning", "idle", "busy", "dead"]


class ClaudeNotFoundError(RuntimeError):
    pass


def _resolve_binary(binary: str = "claude") -> str:
    path = shutil.which(binary)
    if not path:
        raise ClaudeNotFoundError(f"`{binary}` not found on PATH")
    return path


class ClaudeProcess:
    def __init__(
        self,
        *,
        session_id: str,
        cwd: str | None,
        is_resume: bool,
        permission_mode: str = "bypassPermissions",
    ) -> None:
        self.session_id = session_id
        self.cwd = cwd
        self.is_resume = is_resume
        self.permission_mode = permission_mode
        self.state: ProcessState = "spawning"
        self.last_used: float = time.monotonic()
        self._process: asyncio.subprocess.Process | None = None
        self._stdin_lock = asyncio.Lock()
        self._events: asyncio.Queue[dict] = asyncio.Queue()
        self._reader_task: asyncio.Task | None = None
        self._stderr_task: asyncio.Task | None = None

    async def start(self) -> None:
        binary = _resolve_binary()
        args = [
            binary,
            "-p",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--permission-mode",
            self.permission_mode,
        ]
        if self.is_resume:
            args.extend(["--resume", self.session_id])
        else:
            args.extend(["--session-id", self.session_id])

        log.info("spawning claude for session %s (resume=%s)", self.session_id, self.is_resume)
        import os
        env = {**os.environ, "CLAUDE_CHAT_SESSION_ID": self.session_id}
        self._process = await asyncio.create_subprocess_exec(
            *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd or None,
            env=env,
        )
        self.state = "idle"
        self._reader_task = asyncio.create_task(self._read_stdout(), name=f"reader-{self.session_id}")
        self._stderr_task = asyncio.create_task(self._drain_stderr(), name=f"stderr-{self.session_id}")

    async def _read_stdout(self) -> None:
        assert self._process is not None and self._process.stdout is not None
        try:
            while True:
                line = await self._process.stdout.readline()
                if not line:
                    log.info("stdout EOF for session %s", self.session_id)
                    self.state = "dead"
                    await self._events.put({"type": "process_died", "reason": "stdout_eof"})
                    return
                raw = line.decode("utf-8", errors="replace").strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError:
                    event = {"type": "raw", "text": raw}
                await self._events.put(event)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("reader task crashed for session %s", self.session_id)
            self.state = "dead"
            await self._events.put({"type": "process_died", "reason": f"reader_error: {e}"})

    async def _drain_stderr(self) -> None:
        assert self._process is not None and self._process.stderr is not None
        try:
            while True:
                line = await self._process.stderr.readline()
                if not line:
                    return
                log.warning("claude[%s] stderr: %s", self.session_id, line.decode(errors="replace").rstrip())
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("stderr drain crashed for session %s", self.session_id)

    async def send_prompt(self, text: str) -> AsyncIterator[dict]:
        """Send a user prompt and yield events until the turn completes."""
        async with self._stdin_lock:
            if self.state == "dead" or self._process is None or self._process.stdin is None:
                yield {"type": "error", "message": "process is dead"}
                return

            self.state = "busy"
            self.last_used = time.monotonic()
            msg = {
                "type": "user",
                "message": {
                    "role": "user",
                    "content": [{"type": "text", "text": text}],
                },
            }
            try:
                self._process.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
                await self._process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as e:
                self.state = "dead"
                yield {"type": "process_died", "reason": f"stdin_write: {e}"}
                return

            while True:
                event = await self._events.get()
                yield event
                etype = event.get("type")
                if etype == "result":
                    self.state = "idle"
                    self.last_used = time.monotonic()
                    return
                if etype == "process_died":
                    self.state = "dead"
                    return

    async def kill(self) -> None:
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
        if self._stderr_task and not self._stderr_task.done():
            self._stderr_task.cancel()
        if self._process and self._process.returncode is None:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=3)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
            except ProcessLookupError:
                pass
        self.state = "dead"
        log.info("killed claude process for session %s", self.session_id)


class ProcessManager:
    def __init__(self, *, max_processes: int = 5, idle_timeout_s: float = 600.0) -> None:
        self.max_processes = max_processes
        self.idle_timeout_s = idle_timeout_s
        self._processes: dict[str, ClaudeProcess] = {}
        self._lock = asyncio.Lock()
        self._reaper_task: asyncio.Task | None = None

    async def get_or_spawn(
        self,
        *,
        session_id: str,
        cwd: str | None,
        is_resume: bool,
    ) -> ClaudeProcess:
        async with self._lock:
            existing = self._processes.get(session_id)
            if existing is not None and existing.state != "dead":
                existing.last_used = time.monotonic()
                return existing

            if existing is not None and existing.state == "dead":
                self._processes.pop(session_id, None)

            # Evict the LRU if at cap.
            if len(self._processes) >= self.max_processes:
                lru_id = min(self._processes, key=lambda k: self._processes[k].last_used)
                lru = self._processes.pop(lru_id)
                log.info("evicting LRU session %s to make room", lru_id)
                await lru.kill()

            proc = ClaudeProcess(session_id=session_id, cwd=cwd, is_resume=is_resume)
            await proc.start()
            self._processes[session_id] = proc
            return proc

    async def kill(self, session_id: str) -> None:
        async with self._lock:
            proc = self._processes.pop(session_id, None)
        if proc:
            await proc.kill()

    def status(self) -> list[dict]:
        now = time.monotonic()
        return [
            {
                "session_id": sid,
                "state": p.state,
                "idle_for_s": round(now - p.last_used, 1),
            }
            for sid, p in self._processes.items()
        ]

    async def start_reaper(self) -> None:
        if self._reaper_task is not None:
            return
        self._reaper_task = asyncio.create_task(self._reap_loop(), name="process-reaper")

    async def _reap_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(30)
                now = time.monotonic()
                async with self._lock:
                    expired = [
                        sid
                        for sid, p in self._processes.items()
                        if p.state == "idle" and (now - p.last_used) > self.idle_timeout_s
                    ]
                for sid in expired:
                    log.info("reaping idle session %s", sid)
                    await self.kill(sid)
        except asyncio.CancelledError:
            return

    async def shutdown(self) -> None:
        if self._reaper_task:
            self._reaper_task.cancel()
        async with self._lock:
            procs = list(self._processes.values())
            self._processes.clear()
        for p in procs:
            try:
                await p.kill()
            except Exception:  # noqa: BLE001
                log.exception("error killing %s during shutdown", p.session_id)


_manager: ProcessManager | None = None


def get_manager() -> ProcessManager:
    global _manager
    if _manager is None:
        _manager = ProcessManager()
    return _manager

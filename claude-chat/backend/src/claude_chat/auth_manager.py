"""OAuth login via the official `claude auth login` CLI (same flow as /login in Claude Code)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import uuid
from dataclasses import dataclass, field
from typing import Literal

from claude_chat.process_manager import ClaudeNotFoundError

log = logging.getLogger("claude_chat.auth_manager")

OAUTH_URL_RE = re.compile(r"https://claude\.ai/oauth/authorize\?[^\s]+")
VISIT_URL_RE = re.compile(r"visit:\s*(https://\S+)")


LoginStatus = Literal["starting", "awaiting_code", "completed", "failed", "cancelled"]


@dataclass
class LoginSession:
    id: str
    process: asyncio.subprocess.Process
    status: LoginStatus = "starting"
    url: str | None = None
    error: str | None = None
    output_lines: list[str] = field(default_factory=list)
    url_ready: asyncio.Event = field(default_factory=asyncio.Event)
    done: asyncio.Event = field(default_factory=asyncio.Event)
    _reader_task: asyncio.Task | None = None


def _resolve_binary(binary: str = "claude") -> str:
    path = shutil.which(binary)
    if not path:
        raise ClaudeNotFoundError(f"`{binary}` not found on PATH")
    return path


def _login_env() -> dict[str, str]:
    # Avoid opening a browser on the server; the web UI shows the link instead.
    env = {**os.environ, "BROWSER": "/usr/bin/true"}
    if not os.path.isfile(env["BROWSER"]):
        env["BROWSER"] = "true"
    return env


class AuthManager:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._login: LoginSession | None = None

    async def get_status(self) -> dict:
        binary = _resolve_binary()
        proc = await asyncio.create_subprocess_exec(
            binary,
            "auth",
            "status",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        raw = stdout.decode("utf-8", errors="replace").strip()
        if proc.returncode == 0 and raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = {}
            return {
                "logged_in": bool(data.get("loggedIn")),
                "email": data.get("email"),
                "org_name": data.get("orgName"),
                "auth_method": data.get("authMethod"),
                "subscription_type": data.get("subscriptionType"),
            }
        err = stderr.decode("utf-8", errors="replace").strip()
        return {
            "logged_in": False,
            "email": None,
            "org_name": None,
            "auth_method": None,
            "subscription_type": None,
            "error": err or None,
        }

    async def start_login(self) -> dict:
        async with self._lock:
            await self._cancel_unlocked()
            binary = _resolve_binary()
            proc = await asyncio.create_subprocess_exec(
                binary,
                "auth",
                "login",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=_login_env(),
            )
            session = LoginSession(id=str(uuid.uuid4()), process=proc)
            session._reader_task = asyncio.create_task(
                self._read_login_output(session), name=f"auth-login-{session.id}"
            )
            self._login = session

        try:
            await asyncio.wait_for(session.url_ready.wait(), timeout=20.0)
        except asyncio.TimeoutError:
            log.info("auth login: URL not seen within 20s for %s", session.id)

        return self._login_snapshot(session)

    async def get_login(self, login_id: str) -> dict | None:
        async with self._lock:
            session = self._login
            if session is None or session.id != login_id:
                return None
            return self._login_snapshot(session)

    async def submit_code(self, login_id: str, code: str) -> dict:
        code = code.strip()
        if not code:
            raise ValueError("empty code")

        async with self._lock:
            session = self._login
            if session is None or session.id != login_id:
                raise LookupError("login session not found")
            if session.status in ("completed", "failed", "cancelled"):
                return self._login_snapshot(session)
            proc = session.process
            if proc.stdin is None:
                session.status = "failed"
                session.error = "login process has no stdin"
                session.done.set()
                return self._login_snapshot(session)

        try:
            proc.stdin.write((code + "\n").encode("utf-8"))
            await proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as e:
            async with self._lock:
                session.status = "failed"
                session.error = f"could not send code: {e}"
                session.done.set()
            return self._login_snapshot(session)

        try:
            await asyncio.wait_for(session.done.wait(), timeout=120.0)
        except asyncio.TimeoutError:
            async with self._lock:
                if session.status not in ("completed", "failed", "cancelled"):
                    session.status = "failed"
                    session.error = "login timed out after submitting code"
                await self._cancel_unlocked()

        status = await self.get_status()
        async with self._lock:
            if status.get("logged_in"):
                session.status = "completed"
                session.error = None
            elif session.status == "awaiting_code":
                session.status = "failed"
                session.error = session.error or "login failed — check the code and try again"
            await self._cancel_unlocked()

        snap = self._login_snapshot(session)
        snap["logged_in"] = status.get("logged_in", False)
        if status.get("logged_in"):
            snap["email"] = status.get("email")
        return snap

    async def cancel_login(self, login_id: str) -> None:
        async with self._lock:
            session = self._login
            if session is None or session.id != login_id:
                return
            await self._cancel_unlocked()

    async def logout(self) -> dict:
        async with self._lock:
            await self._cancel_unlocked()
        binary = _resolve_binary()
        proc = await asyncio.create_subprocess_exec(
            binary,
            "auth",
            "logout",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
        return await self.get_status()

    def _login_snapshot(self, session: LoginSession) -> dict:
        return {
            "login_id": session.id,
            "status": session.status,
            "url": session.url,
            "error": session.error,
            "output": session.output_lines[-20:],
        }

    async def _read_login_output(self, session: LoginSession) -> None:
        proc = session.process
        assert proc.stdout is not None
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if not text:
                    continue
                session.output_lines.append(text)
                log.info("claude auth login: %s", text)

                if session.url is None:
                    visit = VISIT_URL_RE.search(text)
                    oauth = OAUTH_URL_RE.search(text)
                    url = visit.group(1) if visit else (oauth.group(0) if oauth else None)
                    if url:
                        session.url = url
                        session.status = "awaiting_code"
                        session.url_ready.set()

                if "paste code" in text.lower() or "Paste code" in text:
                    session.status = "awaiting_code"
                    session.url_ready.set()
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("auth login reader failed")
            session.error = str(e)
        finally:
            rc = await proc.wait()
            if session.status == "starting" and session.url:
                session.status = "awaiting_code"
            if rc != 0 and session.status not in ("completed", "cancelled"):
                if not session.error:
                    tail = "\n".join(session.output_lines[-5:])
                    session.error = tail or f"claude auth login exited with code {rc}"
                session.status = "failed"
            session.done.set()
            session.url_ready.set()

    async def _cancel_unlocked(self) -> None:
        session = self._login
        if session is None:
            return
        session.status = "cancelled"
        session.done.set()
        session.url_ready.set()
        if session._reader_task and not session._reader_task.done():
            session._reader_task.cancel()
            try:
                await session._reader_task
            except asyncio.CancelledError:
                pass
        proc = session.process
        if proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=3.0)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
            except ProcessLookupError:
                pass
        self._login = None


_manager: AuthManager | None = None


def get_auth_manager() -> AuthManager:
    global _manager
    if _manager is None:
        _manager = AuthManager()
    return _manager

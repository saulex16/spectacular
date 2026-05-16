from __future__ import annotations

import asyncio
import os
from pathlib import Path

from pydantic_ai import RunContext

from claude_chat.agent.deps import AgentDeps
from claude_chat.config import get_settings


def _resolve_path(cwd: Path, rel: str) -> Path:
    target = (cwd / rel).resolve()
    cwd_resolved = cwd.resolve()
    if target != cwd_resolved and cwd_resolved not in target.parents:
        raise ValueError(f"path escapes session cwd: {rel}")
    return target


def register_tools(agent) -> None:  # noqa: ANN001
    @agent.tool
    async def read_file(ctx: RunContext[AgentDeps], path: str) -> str:
        """Read a text file relative to the session working directory."""
        fp = _resolve_path(ctx.deps.cwd, path)
        if not fp.is_file():
            raise ValueError(f"not a file: {path}")
        return fp.read_text(encoding="utf-8", errors="replace")

    @agent.tool
    async def write_file(ctx: RunContext[AgentDeps], path: str, content: str) -> str:
        """Write content to a file relative to the session working directory."""
        fp = _resolve_path(ctx.deps.cwd, path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content, encoding="utf-8")
        return f"wrote {len(content)} bytes to {path}"

    @agent.tool
    async def list_directory(ctx: RunContext[AgentDeps], path: str = ".") -> str:
        """List files and directories under path (relative to session cwd)."""
        dp = _resolve_path(ctx.deps.cwd, path)
        if not dp.is_dir():
            raise ValueError(f"not a directory: {path}")
        entries = sorted(dp.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
        lines = []
        for e in entries[:200]:
            kind = "dir" if e.is_dir() else "file"
            lines.append(f"{kind}\t{e.name}")
        if len(entries) > 200:
            lines.append(f"... and {len(entries) - 200} more")
        return "\n".join(lines) if lines else "(empty)"

    @agent.tool
    async def run_bash(ctx: RunContext[AgentDeps], command: str) -> str:
        """Run a shell command in the session working directory. Use with care."""
        timeout = get_settings().bash_timeout_s
        proc = await asyncio.create_subprocess_shell(
            command,
            cwd=str(ctx.deps.cwd),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env={**os.environ},
        )
        try:
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()
            raise ValueError(f"command timed out after {timeout}s") from None
        out = (stdout or b"").decode("utf-8", errors="replace")
        code = proc.returncode or 0
        prefix = f"exit {code}\n" if code != 0 else ""
        return prefix + out

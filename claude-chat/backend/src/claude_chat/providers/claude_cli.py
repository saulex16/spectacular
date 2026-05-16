from __future__ import annotations

from collections.abc import AsyncIterator

from claude_chat.process_manager import get_manager
from claude_chat.providers.events import CanonicalEvent, text_delta


def _extract_stream_delta(event: dict) -> str:
    if event.get("type") != "stream_event":
        return ""
    inner = event.get("event") or {}
    if inner.get("type") != "content_block_delta":
        return ""
    delta = inner.get("delta") or {}
    if delta.get("type") != "text_delta":
        return ""
    return delta.get("text") or ""


def _extract_assistant_text(event: dict) -> str:
    if event.get("type") != "assistant":
        return ""
    message = event.get("message") or {}
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if b.get("type") == "text")
    return ""


def cli_event_to_canonical(event: dict) -> list[CanonicalEvent]:
    """Map a raw CLI JSON event to zero or more canonical events."""
    out: list[CanonicalEvent] = []
    delta = _extract_stream_delta(event)
    if delta:
        out.append(text_delta(delta))
        return out

    if event.get("type") == "assistant":
        message = event.get("message") or {}
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                out.append(
                    {
                        "type": "tool_use",
                        "tool_call_id": block.get("id", ""),
                        "name": block.get("name", "tool"),
                        "input": block.get("input"),
                    }
                )
        return out

    if event.get("type") == "user":
        message = event.get("message") or {}
        content = message.get("content")
        if not isinstance(content, list):
            return out
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            raw = block.get("content")
            if isinstance(raw, str):
                text = raw
            elif isinstance(raw, list):
                text = "".join(
                    b.get("text", "")
                    for b in raw
                    if isinstance(b, dict) and b.get("type") == "text"
                )
            else:
                text = ""
            out.append(
                {
                    "type": "tool_result",
                    "tool_call_id": block.get("tool_use_id", ""),
                    "content": text,
                    "is_error": bool(block.get("is_error")),
                }
            )
        return out

    if event.get("type") in ("process_died", "error"):
        return [event]  # type: ignore[list-item]

    return out


class ClaudeCliProvider:
    provider_id = "claude_cli"
    supports_tools = True
    supports_subagents = True

    async def stream_turn(
        self,
        *,
        session_id: str,
        prompt: str,
        model: str | None,  # noqa: ARG002
        cwd: str | None,
        history: list,  # noqa: ARG002
        is_resume: bool,
    ) -> AsyncIterator[dict]:
        """Yield raw CLI events (for subagent routing) plus canonical where applicable."""
        manager = get_manager()
        proc = await manager.get_or_spawn(
            session_id=session_id,
            cwd=cwd,
            is_resume=is_resume,
        )
        async for event in proc.send_prompt(prompt):
            yield event

    def extract_assistant_text(self, event: dict) -> str:
        return _extract_assistant_text(event)


def extract_task_invocations(event: dict) -> list[dict]:
    if event.get("type") != "assistant":
        return []
    message = event.get("message") or {}
    content = message.get("content")
    if not isinstance(content, list):
        return []
    out: list[dict] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_use":
            continue
        if block.get("name") not in ("Task", "Agent"):
            continue
        inp = block.get("input") or {}
        out.append(
            {
                "tool_use_id": block.get("id", ""),
                "name": inp.get("description") or "subagent",
                "prompt": inp.get("prompt") or "",
                "subagent_type": inp.get("subagent_type") or "",
            }
        )
    return out


def extract_tool_results(event: dict) -> list[dict]:
    if event.get("type") != "user":
        return []
    message = event.get("message") or {}
    content = message.get("content")
    if not isinstance(content, list):
        return []
    out: list[dict] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "tool_result":
            continue
        raw = block.get("content")
        if isinstance(raw, str):
            text = raw
        elif isinstance(raw, list):
            text = "".join(
                b.get("text", "")
                for b in raw
                if isinstance(b, dict) and b.get("type") == "text"
            )
        else:
            text = ""
        out.append(
            {
                "tool_use_id": block.get("tool_use_id", ""),
                "content": text,
                "is_error": bool(block.get("is_error")),
            }
        )
    return out

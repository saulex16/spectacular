from __future__ import annotations

from typing import Any

from pydantic_ai.messages import (
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    PartDeltaEvent,
    TextPartDelta,
    ToolReturnPart,
)

from claude_chat.providers.events import CanonicalEvent, text_delta, tool_result, tool_use


def map_stream_event(event: Any) -> list[CanonicalEvent]:
    out: list[CanonicalEvent] = []
    if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
        if event.delta.content_delta:
            out.append(text_delta(event.delta.content_delta))
        return out
    if isinstance(event, FunctionToolCallEvent):
        part = event.part
        args: Any = part.args
        if hasattr(args, "model_dump"):
            args = args.model_dump()
        out.append(
            tool_use(
                tool_call_id=part.tool_call_id,
                name=part.tool_name,
                input=args,
            )
        )
        return out
    if isinstance(event, FunctionToolResultEvent):
        part = event.part
        if isinstance(part, ToolReturnPart):
            content = str(getattr(part, "content", ""))
            out.append(
                tool_result(
                    tool_call_id=part.tool_call_id,
                    content=content,
                    is_error=False,
                )
            )
        return out
    return out

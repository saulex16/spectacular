from __future__ import annotations

from typing import Any, Literal, TypedDict


class TextDeltaEvent(TypedDict):
    type: Literal["text_delta"]
    text: str


class ToolUseEvent(TypedDict):
    type: Literal["tool_use"]
    tool_call_id: str
    name: str
    input: Any


class ToolResultEvent(TypedDict):
    type: Literal["tool_result"]
    tool_call_id: str
    content: str
    is_error: bool


class ReadyEvent(TypedDict, total=False):
    type: Literal["ready"]
    state: str


class TurnCompleteEvent(TypedDict):
    type: Literal["turn_complete"]


class ErrorEvent(TypedDict):
    type: Literal["error"]
    message: str


class ProcessDiedEvent(TypedDict, total=False):
    type: Literal["process_died"]
    reason: str


class UserMessageSavedEvent(TypedDict):
    type: Literal["user_message_saved"]


class SubagentStartedEvent(TypedDict):
    type: Literal["subagent_started"]
    subagent: dict[str, Any]


class SubagentCompletedEvent(TypedDict):
    type: Literal["subagent_completed"]
    subagent: dict[str, Any]


class SubagentEventEvent(TypedDict):
    type: Literal["subagent_event"]
    subagent_id: int
    event: dict[str, Any]


class AssistantTextEvent(TypedDict):
    """Internal: full assistant text chunk for persistence (CLI path)."""

    type: Literal["_assistant_text"]
    text: str


CanonicalEvent = dict[str, Any]


def canonical_to_json(event: CanonicalEvent) -> dict[str, Any]:
    return event


def text_delta(text: str) -> TextDeltaEvent:
    return {"type": "text_delta", "text": text}


def tool_use(*, tool_call_id: str, name: str, input: Any) -> ToolUseEvent:
    return {
        "type": "tool_use",
        "tool_call_id": tool_call_id,
        "name": name,
        "input": input,
    }


def tool_result(*, tool_call_id: str, content: str, is_error: bool = False) -> ToolResultEvent:
    return {
        "type": "tool_result",
        "tool_call_id": tool_call_id,
        "content": content,
        "is_error": is_error,
    }

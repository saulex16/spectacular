from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from pathlib import Path

from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart

from claude_chat.agent.coding_agent import build_coding_agent, default_model_id
from claude_chat.agent.deps import AgentDeps
from claude_chat.credential_vault import get_vault
from claude_chat.providers.events import CanonicalEvent, text_delta
from claude_chat.providers.pydantic_ai_mapper import map_stream_event

log = logging.getLogger("claude_chat.pydantic_ai_provider")

API_PROVIDERS = frozenset({"anthropic", "openai", "google"})


class ChatMessage:
    __slots__ = ("role", "content")

    def __init__(self, role: str, content: str) -> None:
        self.role = role
        self.content = content


def build_message_history(messages: list[ChatMessage]) -> list[ModelRequest | ModelResponse]:
    history: list[ModelRequest | ModelResponse] = []
    for m in messages:
        if m.role == "user":
            history.append(ModelRequest(parts=[UserPromptPart(content=m.content)]))
        elif m.role == "assistant":
            history.append(ModelResponse(parts=[TextPart(content=m.content)]))
    return history


class PydanticAiProvider:
    provider_id: str
    supports_tools = True
    supports_subagents = False

    def __init__(self, provider_id: str) -> None:
        if provider_id not in API_PROVIDERS:
            raise ValueError(f"unsupported api provider: {provider_id}")
        self.provider_id = provider_id

    async def stream_turn(
        self,
        *,
        session_id: str,
        prompt: str,
        model: str | None,
        cwd: str | None,
        history: list[ChatMessage],
    ) -> AsyncIterator[CanonicalEvent]:
        vault = get_vault()
        api_key = await vault.get_api_key(self.provider_id)
        if not api_key:
            yield {"type": "error", "message": f"no API key configured for {self.provider_id}"}
            return

        model_id = (model or "").strip() or default_model_id(self.provider_id)
        if not model_id:
            yield {"type": "error", "message": f"no model configured for {self.provider_id}"}
            return

        work = Path(cwd).expanduser().resolve() if cwd else Path.cwd()
        work.mkdir(parents=True, exist_ok=True)

        agent = build_coding_agent(
            provider=self.provider_id,
            model_id=model_id,
            api_key=api_key,
        )
        deps = AgentDeps(cwd=work, session_id=session_id)
        msg_history = build_message_history(history)

        try:
            async with agent.run_stream_events(
                prompt,
                deps=deps,
                message_history=msg_history,
            ) as stream:
                async for event in stream:
                    for mapped in map_stream_event(event):
                        yield mapped
        except Exception as e:  # noqa: BLE001
            log.exception("pydantic ai turn failed for session %s", session_id)
            yield {"type": "error", "message": str(e)}

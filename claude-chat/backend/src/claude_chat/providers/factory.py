from __future__ import annotations

from claude_chat.models import Session
from claude_chat.providers.claude_cli import ClaudeCliProvider
from claude_chat.providers.pydantic_ai_provider import API_PROVIDERS, PydanticAiProvider


class ProviderFactory:
    def for_session(self, session: Session) -> ClaudeCliProvider | PydanticAiProvider:
        if session.provider == "claude_cli":
            return ClaudeCliProvider()
        if session.provider in API_PROVIDERS:
            return PydanticAiProvider(session.provider)
        raise ValueError(f"unknown session provider: {session.provider}")


_factory: ProviderFactory | None = None


def get_provider_factory() -> ProviderFactory:
    global _factory
    if _factory is None:
        _factory = ProviderFactory()
    return _factory

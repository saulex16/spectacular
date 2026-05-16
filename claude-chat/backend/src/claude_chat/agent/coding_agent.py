from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.google import GoogleProvider
from pydantic_ai.providers.openai import OpenAIProvider

from claude_chat.agent.deps import AgentDeps
from claude_chat.agent.tools import register_tools

DEFAULT_MODELS: dict[str, str] = {
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o",
    "google": "gemini-2.0-flash",
}

MODEL_CATALOG: dict[str, list[dict[str, str]]] = {
    "anthropic": [
        {"id": "claude-sonnet-4-20250514", "label": "Claude Sonnet 4"},
        {"id": "claude-3-5-haiku-20241022", "label": "Claude 3.5 Haiku"},
    ],
    "openai": [
        {"id": "gpt-4o", "label": "GPT-4o"},
        {"id": "gpt-4o-mini", "label": "GPT-4o mini"},
    ],
    "google": [
        {"id": "gemini-2.0-flash", "label": "Gemini 2.0 Flash"},
        {"id": "gemini-2.5-pro-preview-05-06", "label": "Gemini 2.5 Pro Preview"},
    ],
}

SYSTEM_PROMPT = """You are a helpful coding assistant with access to the local filesystem
and shell in the session working directory. Use tools to read, write, and explore files.
Prefer small, focused changes. Explain what you are doing briefly."""


def default_model_id(provider: str) -> str:
    return DEFAULT_MODELS.get(provider, "")


def _build_model(provider: str, model_id: str, api_key: str):
    if provider == "anthropic":
        return AnthropicModel(model_id, provider=AnthropicProvider(api_key=api_key))
    if provider == "openai":
        return OpenAIChatModel(model_id, provider=OpenAIProvider(api_key=api_key))
    if provider == "google":
        return GoogleModel(model_id, provider=GoogleProvider(api_key=api_key))
    raise ValueError(f"unsupported provider: {provider}")


def build_coding_agent(*, provider: str, model_id: str, api_key: str) -> Agent[AgentDeps, str]:
    model = _build_model(provider, model_id, api_key)
    agent: Agent[AgentDeps, str] = Agent(
        model,
        deps_type=AgentDeps,
        system_prompt=SYSTEM_PROMPT,
        end_strategy="exhaustive",
    )
    register_tools(agent)
    return agent

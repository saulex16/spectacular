from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SessionCreate(BaseModel):
    title: str | None = None
    cwd: str | None = None
    provider: str = "claude_cli"
    model: str = ""


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    cwd: str
    provider: str
    model: str
    created_at: datetime
    updated_at: datetime


class ProviderInfo(BaseModel):
    id: str
    label: str
    configured: bool
    hint: str | None = None


class ProviderSettingsRead(BaseModel):
    providers: list[ProviderInfo]


class CredentialHint(BaseModel):
    configured: bool
    hint: str | None = None


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    role: str
    content: str
    created_at: datetime


class SubagentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    tool_use_id: str
    name: str
    subagent_type: str
    prompt: str
    result: str
    status: str
    created_at: datetime
    completed_at: datetime | None

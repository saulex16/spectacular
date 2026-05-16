from datetime import datetime

from pydantic import BaseModel, ConfigDict


class SessionCreate(BaseModel):
    title: str | None = None
    cwd: str | None = None


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    cwd: str
    created_at: datetime
    updated_at: datetime


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


class AuthStatusRead(BaseModel):
    logged_in: bool
    email: str | None = None
    org_name: str | None = None
    auth_method: str | None = None
    subscription_type: str | None = None
    error: str | None = None


class LoginSessionRead(BaseModel):
    login_id: str
    status: str
    url: str | None = None
    error: str | None = None
    output: list[str] = []
    logged_in: bool | None = None
    email: str | None = None


class LoginCodeSubmit(BaseModel):
    code: str

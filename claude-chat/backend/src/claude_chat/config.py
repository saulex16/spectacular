from __future__ import annotations

import base64
import logging
import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger("claude_chat.config")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    credentials_encryption_key: str | None = None
    bash_timeout_s: float = 60.0


@lru_cache
def get_settings() -> Settings:
    return Settings()


def resolve_encryption_key() -> bytes:
    """Return Fernet key bytes; generate ephemeral key in dev if unset."""
    raw = get_settings().credentials_encryption_key or os.environ.get("CREDENTIALS_ENCRYPTION_KEY")
    if raw:
        return base64.urlsafe_b64decode(raw.encode("utf-8"))
    key = os.urandom(32)
    encoded = base64.urlsafe_b64encode(key)
    log.warning(
        "CREDENTIALS_ENCRYPTION_KEY not set; using ephemeral key for this process: %s",
        encoded.decode("ascii"),
    )
    return key

from __future__ import annotations

import json
import logging
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from claude_chat.config import resolve_encryption_key
from claude_chat.db import SessionLocal
from claude_chat.models import ProviderCredential

log = logging.getLogger("claude_chat.credential_vault")

API_PROVIDERS = frozenset({"anthropic", "openai", "google"})


class CredentialVault:
    def __init__(self) -> None:
        self._fernet = Fernet(base64_urlsafe_key())

    async def get_api_key(self, provider: str) -> str | None:
        if provider not in API_PROVIDERS:
            return None
        async with SessionLocal() as db:
            row = await db.get(ProviderCredential, provider)
            if row is None:
                return None
            try:
                payload = json.loads(
                    self._fernet.decrypt(row.encrypted_payload.encode("ascii")).decode("utf-8")
                )
            except (InvalidToken, json.JSONDecodeError):
                log.exception("failed to decrypt credentials for %s", provider)
                return None
            key = payload.get("api_key")
            return str(key) if key else None

    async def set_api_key(self, provider: str, api_key: str) -> None:
        if provider not in API_PROVIDERS:
            raise ValueError(f"unknown provider: {provider}")
        token = self._fernet.encrypt(json.dumps({"api_key": api_key}).encode("utf-8")).decode("ascii")
        async with SessionLocal() as db:
            row = await db.get(ProviderCredential, provider)
            if row is None:
                row = ProviderCredential(provider=provider, encrypted_payload=token)
                db.add(row)
            else:
                row.encrypted_payload = token
            await db.commit()

    async def delete(self, provider: str) -> bool:
        async with SessionLocal() as db:
            row = await db.get(ProviderCredential, provider)
            if row is None:
                return False
            await db.delete(row)
            await db.commit()
            return True

    async def is_configured(self, provider: str) -> bool:
        key = await self.get_api_key(provider)
        return bool(key)

    async def hint(self, provider: str) -> str | None:
        key = await self.get_api_key(provider)
        if not key:
            return None
        if len(key) <= 4:
            return "****"
        return f"…{key[-4:]}"

    async def list_status(self) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for p in sorted(API_PROVIDERS):
            configured = await self.is_configured(p)
            out[p] = {
                "configured": configured,
                "hint": await self.hint(p) if configured else None,
            }
        return out


def base64_urlsafe_key() -> bytes:
    import base64

    return base64.urlsafe_b64encode(resolve_encryption_key())


_vault: CredentialVault | None = None


def get_vault() -> CredentialVault:
    global _vault
    if _vault is None:
        _vault = CredentialVault()
    return _vault


async def load_all_configured(db: AsyncSession | None = None) -> dict[str, str]:
    keys: dict[str, str] = {}
    vault = get_vault()
    for p in API_PROVIDERS:
        k = await vault.get_api_key(p)
        if k:
            keys[p] = k
    return keys

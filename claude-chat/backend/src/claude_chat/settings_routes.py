from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from claude_chat.agent.coding_agent import MODEL_CATALOG
from claude_chat.credential_vault import API_PROVIDERS, get_vault
from claude_chat.schemas import CredentialHint, ProviderInfo, ProviderSettingsRead

router = APIRouter(prefix="/settings", tags=["settings"])


class CredentialUpsert(BaseModel):
    api_key: str = Field(min_length=1)


@router.get("/providers", response_model=ProviderSettingsRead)
async def get_providers() -> ProviderSettingsRead:
    vault = get_vault()
    status = await vault.list_status()
    providers = [
        ProviderInfo(
            id=p,
            label=p.capitalize(),
            configured=status[p]["configured"],
            hint=status[p].get("hint"),
        )
        for p in sorted(API_PROVIDERS)
    ]
    return ProviderSettingsRead(providers=providers)


@router.put("/credentials/{provider}", response_model=CredentialHint)
async def upsert_credential(provider: str, body: CredentialUpsert) -> CredentialHint:
    if provider not in API_PROVIDERS:
        raise HTTPException(400, "unknown provider")
    vault = get_vault()
    await vault.set_api_key(provider, body.api_key.strip())
    hint = await vault.hint(provider)
    return CredentialHint(configured=True, hint=hint or "****")


@router.delete("/credentials/{provider}", status_code=204)
async def delete_credential(provider: str) -> None:
    if provider not in API_PROVIDERS:
        raise HTTPException(400, "unknown provider")
    vault = get_vault()
    if not await vault.delete(provider):
        raise HTTPException(404, "credentials not found")


@router.get("/models")
async def list_models(provider: str) -> dict:
    if provider not in API_PROVIDERS:
        raise HTTPException(400, "unknown provider")
    return {"provider": provider, "models": MODEL_CATALOG.get(provider, [])}

import base64
import os

import pytest

from claude_chat.credential_vault import CredentialVault, base64_urlsafe_key
from claude_chat.config import get_settings


@pytest.fixture
def vault(monkeypatch: pytest.MonkeyPatch) -> CredentialVault:
    key = base64.urlsafe_b64encode(os.urandom(32)).decode()
    monkeypatch.setenv("CREDENTIALS_ENCRYPTION_KEY", key)
    get_settings.cache_clear()
    return CredentialVault()


@pytest.mark.asyncio
async def test_roundtrip(vault: CredentialVault) -> None:
    await vault.set_api_key("openai", "sk-test-secret-key")
    assert await vault.get_api_key("openai") == "sk-test-secret-key"
    assert await vault.is_configured("openai")
    hint = await vault.hint("openai")
    assert hint is not None and hint.endswith("key")


@pytest.mark.asyncio
async def test_delete(vault: CredentialVault) -> None:
    await vault.set_api_key("anthropic", "sk-ant-test")
    assert await vault.delete("anthropic")
    assert await vault.get_api_key("anthropic") is None


def test_base64_urlsafe_key_length() -> None:
    os.environ["CREDENTIALS_ENCRYPTION_KEY"] = base64.urlsafe_b64encode(os.urandom(32)).decode()
    get_settings.cache_clear()
    k = base64_urlsafe_key()
    assert len(k) == 44

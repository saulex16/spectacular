from __future__ import annotations

import logging

from sqlalchemy import text

from claude_chat.db import engine

log = logging.getLogger("claude_chat.migrate")

SESSION_COLUMNS = [
    ("provider", "VARCHAR(32) NOT NULL DEFAULT 'claude_cli'"),
    ("model", "VARCHAR(120) NOT NULL DEFAULT ''"),
]


async def run_migrations() -> None:
    async with engine.begin() as conn:
        await _ensure_provider_credentials(conn)
        await _ensure_session_columns(conn)


async def _table_exists(conn, name: str) -> bool:
    result = await conn.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name},
    )
    return result.scalar() is not None


async def _columns(conn, table: str) -> set[str]:
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    return {row[1] for row in result.fetchall()}


async def _ensure_provider_credentials(conn) -> None:
    if await _table_exists(conn, "provider_credentials"):
        return
    await conn.execute(
        text(
            """
            CREATE TABLE provider_credentials (
                provider VARCHAR(32) PRIMARY KEY,
                encrypted_payload TEXT NOT NULL,
                metadata_json TEXT NOT NULL DEFAULT '{}',
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
    )
    log.info("created provider_credentials table")


async def _ensure_session_columns(conn) -> None:
    if not await _table_exists(conn, "sessions"):
        return
    existing = await _columns(conn, "sessions")
    for col, ddl in SESSION_COLUMNS:
        if col in existing:
            continue
        await conn.execute(text(f"ALTER TABLE sessions ADD COLUMN {col} {ddl}"))
        log.info("added sessions.%s", col)

from __future__ import annotations

import asyncio
import json
import uuid
import uuid as uuid_mod
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# In-memory intercept store
# ---------------------------------------------------------------------------
_pending: dict[str, dict] = {}          # intercept_id → intercept record
_intercept_events: dict[str, asyncio.Event] = {}  # intercept_id → resolved event

from claude_chat.db import SessionLocal, get_session
from claude_chat.models import Message, Session, Subagent
from claude_chat.process_manager import get_manager
from claude_chat.providers.claude_cli import (
    ClaudeCliProvider,
    cli_event_to_canonical,
    extract_task_invocations,
    extract_tool_results,
)
from claude_chat.providers.claude_cli import (
    _extract_assistant_text as cli_extract_assistant_text,
)
from claude_chat.providers.factory import get_provider_factory
from claude_chat.providers.pydantic_ai_provider import ChatMessage, PydanticAiProvider
from claude_chat.schemas import MessageRead, SessionCreate, SessionRead, SubagentRead

router = APIRouter()

DB = Annotated[AsyncSession, Depends(get_session)]


async def _has_user_messages(session_id: str) -> bool:
    async with SessionLocal() as db:
        existing = await db.scalar(
            select(Message.id)
            .where(Message.session_id == session_id, Message.role == "user")
            .limit(1)
        )
        return existing is not None


async def _user_message_count(session_id: str) -> int:
    async with SessionLocal() as db:
        n = await db.scalar(
            select(func.count())
            .select_from(Message)
            .where(Message.session_id == session_id, Message.role == "user")
        )
        return int(n or 0)


async def _load_chat_history(session_id: str) -> list[ChatMessage]:
    async with SessionLocal() as db:
        result = await db.execute(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at)
        )
        rows = result.scalars().all()
    return [ChatMessage(role=m.role, content=m.content) for m in rows]


@router.get("/sessions", response_model=list[SessionRead])
async def list_sessions(db: DB) -> list[Session]:
    result = await db.execute(select(Session).order_by(Session.updated_at.desc()))
    return list(result.scalars().all())


@router.post("/sessions", response_model=SessionRead)
async def create_session(payload: SessionCreate, db: DB) -> Session:
    provider = payload.provider or "claude_cli"
    if provider not in ("claude_cli", "anthropic", "openai", "google"):
        raise HTTPException(400, "invalid provider")
    session = Session(
        id=str(uuid.uuid4()),
        title=payload.title or "New session",
        cwd=payload.cwd or "",
        provider=provider,
        model=payload.model or "",
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


@router.get("/sessions/{session_id}", response_model=SessionRead)
async def get_session_by_id(session_id: str, db: DB) -> Session:
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(404, "session not found")
    return session


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, db: DB) -> None:
    session = await db.get(Session, session_id)
    if not session:
        raise HTTPException(404, "session not found")
    if session.provider == "claude_cli":
        await get_manager().kill(session_id)
    await db.delete(session)
    await db.commit()


@router.get("/sessions/{session_id}/messages", response_model=list[MessageRead])
async def list_messages(session_id: str, db: DB) -> list[Message]:
    result = await db.execute(
        select(Message).where(Message.session_id == session_id).order_by(Message.created_at)
    )
    return list(result.scalars().all())


@router.get("/sessions/{session_id}/subagents", response_model=list[SubagentRead])
async def list_subagents(session_id: str, db: DB) -> list[Subagent]:
    result = await db.execute(
        select(Subagent)
        .where(Subagent.session_id == session_id)
        .order_by(Subagent.created_at)
    )
    return list(result.scalars().all())


@router.get("/sessions/{session_id}/intercept/pending")
async def get_pending_intercept(session_id: str) -> dict | None:
    for rec in _pending.values():
        if rec["session_id"] == session_id and rec["status"] == "pending":
            return rec
    return None


@router.post("/intercept")
async def create_intercept(payload: dict = Body(...)) -> dict:
    """Called by the interceptor hook script. Long-polls until UI resolves it (max 30s)."""
    iid = str(uuid_mod.uuid4())
    rec = {
        "id": iid,
        "session_id": payload.get("session_id", "unknown"),
        "tool_name": payload.get("tool_name", ""),
        "original_input": payload.get("tool_input", {}),
        "modified_input": payload.get("tool_input", {}),
        "status": "pending",
    }
    _pending[iid] = rec
    ev = asyncio.Event()
    _intercept_events[iid] = ev
    try:
        await asyncio.wait_for(ev.wait(), timeout=30.0)
    except asyncio.TimeoutError:
        rec["status"] = "approved"
    finally:
        _pending.pop(iid, None)
        _intercept_events.pop(iid, None)
    return rec


@router.put("/intercept/{intercept_id}")
async def resolve_intercept(
    intercept_id: str,
    payload: dict = Body(...),
) -> dict:
    rec = _pending.get(intercept_id)
    if rec is None:
        raise HTTPException(404, "intercept not found or already resolved")
    rec["status"] = payload.get("status", "approved")
    if "prompt" in payload:
        rec["modified_input"] = {**rec["original_input"], "prompt": payload["prompt"]}
    ev = _intercept_events.get(intercept_id)
    if ev:
        ev.set()
    return rec


@router.get("/processes")
async def list_processes() -> list[dict]:
    return get_manager().status()


async def _safe_send(websocket: WebSocket, payload: dict) -> bool:
    """Send a JSON event, return False if the socket is no longer writable."""
    try:
        await websocket.send_json(payload)
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False


async def _persist_subagent_start(session_id: str, inv: dict) -> dict | None:
    """Insert a new Subagent row if we haven't seen this tool_use_id."""
    async with SessionLocal() as db:
        existing = await db.scalar(
            select(Subagent).where(Subagent.tool_use_id == inv["tool_use_id"])
        )
        if existing is not None:
            return None
        sub = Subagent(
            session_id=session_id,
            tool_use_id=inv["tool_use_id"],
            name=inv["name"],
            subagent_type=inv["subagent_type"],
            prompt=inv["prompt"],
            status="running",
        )
        db.add(sub)
        await db.commit()
        await db.refresh(sub)
        return {
            "id": sub.id,
            "session_id": sub.session_id,
            "tool_use_id": sub.tool_use_id,
            "name": sub.name,
            "subagent_type": sub.subagent_type,
            "prompt": sub.prompt,
            "result": sub.result,
            "status": sub.status,
            "created_at": sub.created_at.isoformat(),
            "completed_at": None,
        }


async def _persist_subagent_complete(res: dict) -> dict | None:
    async with SessionLocal() as db:
        sub = await db.scalar(
            select(Subagent).where(Subagent.tool_use_id == res["tool_use_id"])
        )
        if sub is None:
            return None
        sub.result = res["content"]
        sub.status = "failed" if res["is_error"] else "done"
        sub.completed_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(sub)
        return {
            "id": sub.id,
            "session_id": sub.session_id,
            "tool_use_id": sub.tool_use_id,
            "name": sub.name,
            "subagent_type": sub.subagent_type,
            "prompt": sub.prompt,
            "result": sub.result,
            "status": sub.status,
            "created_at": sub.created_at.isoformat(),
            "completed_at": sub.completed_at.isoformat() if sub.completed_at else None,
        }


async def _persist_turn(
    session_id: str,
    user_prompt: str,
    assistant_buf: list[str],
) -> None:
    async with SessionLocal() as db:
        if assistant_buf:
            db.add(
                Message(
                    session_id=session_id,
                    role="assistant",
                    content="".join(assistant_buf),
                )
            )
        session_obj = await db.get(Session, session_id)
        if session_obj and session_obj.title == "New session":
            session_obj.title = user_prompt[:80]
        await db.commit()


@router.websocket("/ws/sessions/{session_id}")
async def chat_ws(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()

    async with SessionLocal() as db:
        session = await db.get(Session, session_id)
        if not session:
            await websocket.send_json({"type": "error", "message": "session not found"})
            await websocket.close()
            return
        cwd = session.cwd or None
        model = session.model or None

    factory = get_provider_factory()
    try:
        provider = factory.for_session(session)
    except ValueError as e:
        await websocket.send_json({"type": "error", "message": str(e)})
        await websocket.close()
        return

    if isinstance(provider, ClaudeCliProvider):
        is_resume = await _has_user_messages(session_id)
        try:
            proc = await get_manager().get_or_spawn(
                session_id=session_id, cwd=cwd, is_resume=is_resume
            )
        except Exception as e:  # noqa: BLE001
            await websocket.send_json({"type": "error", "message": f"failed to spawn claude: {e}"})
            await websocket.close()
            return
        await websocket.send_json({"type": "ready", "state": proc.state})
    else:
        await websocket.send_json({"type": "ready", "state": "api"})

    try:
        while True:
            payload = await websocket.receive_text()
            try:
                data = json.loads(payload)
            except json.JSONDecodeError:
                await websocket.send_json({"type": "error", "message": "invalid json"})
                continue

            prompt = (data.get("prompt") or "").strip()
            if not prompt:
                await websocket.send_json({"type": "error", "message": "empty prompt"})
                continue

            async with SessionLocal() as db:
                db.add(Message(session_id=session_id, role="user", content=prompt))
                await db.commit()
            await _safe_send(websocket, {"type": "user_message_saved"})

            assistant_buf: list[str] = []
            ws_alive = True

            if isinstance(provider, PydanticAiProvider):
                history = await _load_chat_history(session_id)
                # Exclude the message we just added (last user) from history for this turn
                if history and history[-1].role == "user" and history[-1].content == prompt:
                    history = history[:-1]
                async for event in provider.stream_turn(
                    session_id=session_id,
                    prompt=prompt,
                    model=model,
                    cwd=cwd,
                    history=history,
                ):
                    etype = event.get("type")
                    if etype == "text_delta":
                        assistant_buf.append(event.get("text", ""))
                    if ws_alive:
                        ws_alive = await _safe_send(websocket, event)
                    if etype == "error":
                        break
            else:
                assert isinstance(provider, ClaudeCliProvider)
                cli_resume = (await _user_message_count(session_id)) > 1
                if proc.state == "dead":
                    proc = await get_manager().get_or_spawn(
                        session_id=session_id, cwd=cwd, is_resume=cli_resume
                    )
                active_sub: dict[str, int] = {}
                async for raw_event in provider.stream_turn(
                    session_id=session_id,
                    prompt=prompt,
                    model=None,
                    cwd=cwd,
                    history=[],
                    is_resume=cli_resume,
                ):
                    closed: set[int] = set()
                    for res in extract_tool_results(raw_event):
                        tid = res["tool_use_id"]
                        if tid in active_sub:
                            sub_id = active_sub.pop(tid)
                            closed.add(sub_id)
                            sub_payload = await _persist_subagent_complete(res)
                            if sub_payload and ws_alive:
                                ws_alive = await _safe_send(
                                    websocket,
                                    {"type": "subagent_completed", "subagent": sub_payload},
                                )

                    if active_sub:
                        current_sub_id = next(reversed(active_sub.values()))
                        if ws_alive:
                            for canon in cli_event_to_canonical(raw_event):
                                ws_alive = await _safe_send(
                                    websocket,
                                    {
                                        "type": "subagent_event",
                                        "subagent_id": current_sub_id,
                                        "event": canon,
                                    },
                                )
                        continue

                    if closed:
                        continue

                    for canon in cli_event_to_canonical(raw_event):
                        if ws_alive:
                            ws_alive = await _safe_send(websocket, canon)
                        if canon.get("type") == "text_delta":
                            assistant_buf.append(canon.get("text", ""))

                    text = cli_extract_assistant_text(raw_event)
                    if text and not any(
                        c.get("type") == "text_delta" for c in cli_event_to_canonical(raw_event)
                    ):
                        assistant_buf.append(text)

                    for inv in extract_task_invocations(raw_event):
                        sub_payload = await _persist_subagent_start(session_id, inv)
                        if sub_payload:
                            active_sub[inv["tool_use_id"]] = sub_payload["id"]
                            if ws_alive:
                                ws_alive = await _safe_send(
                                    websocket,
                                    {"type": "subagent_started", "subagent": sub_payload},
                                )

                    if raw_event.get("type") == "process_died" and ws_alive:
                        ws_alive = await _safe_send(websocket, raw_event)

            await _persist_turn(session_id, prompt, assistant_buf)

            if not ws_alive:
                return
            await _safe_send(websocket, {"type": "turn_complete"})

    except WebSocketDisconnect:
        return

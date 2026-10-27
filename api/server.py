"""Authenticated multi-user HTTP and Gemini Live WebSocket API."""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.api_key_validator import normalize_gemini_api_key, validate_gemini_api_key
from core.tenant import tenant_scope
from memory.memory_manager import format_memory_for_prompt, load_memory

from .auth import WEBSOCKET_PROTOCOL, get_current_user, websocket_user
from .config import settings
from .database import SessionLocal, get_db, init_db
from .gemini_errors import gemini_http_error
from .models import User
from .rate_limit import limiter
from .retention import purge_expired_user_data
from .repositories import add_chat_message, recent_chat_messages
from .schemas import (
    ChatRequest,
    ChatResponse,
    GeminiKeyRequest,
    LoginRequest,
    SessionView,
    UserCreate,
    UserView,
)
from .secret_service import (
    delete_user_secret,
    get_user_secret,
    has_user_secret,
    set_user_secret,
)
from .security import create_access_token, hash_password, verify_password, verify_unknown_account
from .websocket_client import WebSocketClient


logger = logging.getLogger(__name__)

WS_CLOSE_SERVICE_RESTART = 1012
WS_CLOSE_UNAUTHORIZED = 4401
WS_CLOSE_GEMINI_KEY_REQUIRED = 4403
WS_CLOSE_SESSION_REPLACED = 4409
WS_CLOSE_RATE_LIMITED = 4429


class LiveSessionRegistry:
    def __init__(self):
        self._sessions: dict[str, tuple[Any, WebSocketClient, asyncio.Task]] = {}
        self._lock = asyncio.Lock()

    async def replace(self, user_id: str, engine, client: WebSocketClient, task: asyncio.Task) -> None:
        async with self._lock:
            previous = self._sessions.pop(user_id, None)
            self._sessions[user_id] = (engine, client, task)
        if previous:
            engine, client, task = previous
            client._emit({
                "type": "error",
                "code": "session_replaced",
                "message": "ARGUS was opened in another window.",
            })
            await client.close(code=WS_CLOSE_SESSION_REPLACED)
            engine.request_shutdown()
            task.cancel()

    async def remove(self, user_id: str, task: asyncio.Task) -> None:
        async with self._lock:
            current = self._sessions.get(user_id)
            if current and current[2] is task:
                self._sessions.pop(user_id, None)

    def status(self, user_id: str) -> dict:
        current = self._sessions.get(user_id)
        if not current:
            return {"state": "OFFLINE", "connected": False}
        engine, client, task = current
        return {
            "state": client.state,
            "connected": not task.done(),
            "voice": engine._get_current_voice(),
            "cloud_safe": True,
        }

    async def close_all(self) -> None:
        async with self._lock:
            sessions = list(self._sessions.values())
            self._sessions.clear()
        for engine, client, task in sessions:
            engine.request_shutdown()
            task.cancel()
            await client.close(code=WS_CLOSE_SERVICE_RESTART)


live_sessions = LiveSessionRegistry()


async def _retention_loop() -> None:
    while True:
        await asyncio.sleep(24 * 60 * 60)
        try:
            await asyncio.to_thread(
                purge_expired_user_data,
                settings.data_retention_days,
            )
        except Exception as exc:
            print(f"[Retention] Cleanup failed: {exc}")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_production()
    if settings.auto_create_tables:
        await asyncio.to_thread(init_db)
    try:
        await asyncio.to_thread(
            purge_expired_user_data,
            settings.data_retention_days,
        )
    except Exception as exc:
        print(f"[Retention] Initial cleanup failed: {exc}")
    await limiter.connect()
    retention_task = asyncio.create_task(_retention_loop())
    try:
        yield
    finally:
        retention_task.cancel()
        await asyncio.gather(retention_task, return_exceptions=True)
        await live_sessions.close_all()
        await limiter.close()


app = FastAPI(
    title="ARGUS Cloud API",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


def _user_view(user: User, db: Session) -> UserView:
    return UserView(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        gemini_configured=has_user_secret(db, user.id, "gemini_api_key"),
    )


@app.get("/health")
def health() -> dict:
    return {"ok": True, "service": "argus-api"}


def _client_ip(request: Request) -> str:
    # uvicorn --proxy-headers already resolves X-Forwarded-For into client.host.
    return request.client.host if request.client else "unknown"


@app.post("/auth/signup", response_model=SessionView, status_code=201)
async def signup(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> SessionView:
    await limiter.consume(_client_ip(request), "signup_ip", 10, 3600)
    await limiter.consume(payload.email.lower(), "signup", 5, 3600)
    user = User(
        email=payload.email.lower().strip(),
        display_name=payload.display_name.strip(),
        password_hash=hash_password(payload.password),
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="An account already exists for this email") from exc
    db.refresh(user)
    return SessionView(
        access_token=create_access_token(user.id, user.session_version),
        user=_user_view(user, db),
    )


@app.post("/auth/login", response_model=SessionView)
async def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> SessionView:
    ip = _client_ip(request)
    await limiter.consume(ip, "login_ip", 50, 300)
    # Keyed by email and IP so one address cannot lock everyone out of an account.
    await limiter.consume(f"{payload.email.lower()}|{ip}", "login", 10, 300)
    user = db.scalar(select(User).where(User.email == payload.email.lower().strip()))
    if user is None:
        verify_unknown_account(payload.password)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect")
    return SessionView(
        access_token=create_access_token(user.id, user.session_version),
        user=_user_view(user, db),
    )


@app.get("/auth/me", response_model=UserView)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserView:
    return _user_view(user, db)


@app.post("/auth/logout", status_code=204)
def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    """End every session of this account by invalidating issued tokens."""
    user.session_version += 1
    db.commit()


@app.post("/me/gemini-key")
async def save_gemini_key(
    payload: GeminiKeyRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    await limiter.consume(user.id, "secret", 8, 3600)
    key = normalize_gemini_api_key(payload.api_key)
    if payload.verify_key:
        validation = await asyncio.to_thread(validate_gemini_api_key, key)
        if not validation.valid:
            raise HTTPException(status_code=422, detail=validation.message)
    set_user_secret(db, user.id, "gemini_api_key", key)
    return {"configured": True}


@app.delete("/me/gemini-key", status_code=204)
def remove_gemini_key(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    delete_user_secret(db, user.id, "gemini_api_key")


@app.get("/status")
def get_status(user: User = Depends(get_current_user)) -> dict:
    return live_sessions.status(user.id)


@app.get("/actions")
def get_actions(_: User = Depends(get_current_user)) -> dict:
    from main import get_tool_declarations

    tools = get_tool_declarations(cloud_safe=True)
    return {
        "actions": [
            {"name": item["name"], "description": item.get("description", "")}
            for item in tools
        ]
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(
    payload: ChatRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    await limiter.consume(user.id, "chat", 30, 60)
    api_key = get_user_secret(db, user.id, "gemini_api_key")
    if not api_key:
        raise HTTPException(status_code=409, detail="Add a Gemini API key before starting ARGUS")

    with tenant_scope(user.id):
        history = recent_chat_messages(user.id, limit=12)
        memory = format_memory_for_prompt(load_memory())

        def generate() -> str:
            from google import genai
            from google.genai import types
            from main import _load_system_prompt

            client = genai.Client(
                api_key=api_key,
                http_options=types.HttpOptions(
                    timeout=int(settings.chat_timeout_seconds * 1000),
                ),
            )
            context = "\n".join(
                f"{message.role.title()}: {message.content}" for message in history
            )
            prompt = (
                f"Recent conversation:\n{context}\n\n"
                f"Current user message: {payload.message}"
            )
            response = client.models.generate_content(
                model=settings.chat_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=_load_system_prompt() + "\n\n" + memory,
                ),
            )
            return str(response.text or "").strip()

        try:
            response_text = await asyncio.to_thread(generate)
        except Exception as exc:
            logger.warning("Gemini chat failed for user %s: %r", user.id, exc)
            raise gemini_http_error(exc) from exc
        if not response_text:
            raise HTTPException(status_code=502, detail="Gemini returned an empty response")
        # Store the turn only once Gemini answers, so failures leave no
        # orphaned user message in the history sent with the next request.
        add_chat_message(user.id, "user", payload.message)
        add_chat_message(user.id, "assistant", response_text)
    return ChatResponse(response=response_text)


# Browser microphone chunks are ~8 KiB of 16 kHz PCM; anything far larger is abuse.
MAX_AUDIO_CHUNK_BYTES = 64 * 1024
MAX_LIVE_TEXT_CHARS = 12000


class LiveFrameError(ValueError):
    """A client frame that is rejected without ending the live session."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def _parse_live_event(raw: str) -> dict:
    try:
        event = json.loads(raw)
    except json.JSONDecodeError:
        event = None
    if not isinstance(event, dict):
        raise LiveFrameError("invalid_frame", "Text frames must be JSON objects.")
    return event


def _check_audio_size(size: int) -> None:
    if size > MAX_AUDIO_CHUNK_BYTES:
        raise LiveFrameError(
            "audio_too_large",
            f"Audio chunks must be at most {MAX_AUDIO_CHUNK_BYTES} bytes.",
        )


def _decode_live_audio(data: Any) -> bytes:
    if not isinstance(data, str):
        raise LiveFrameError("invalid_audio", "Audio data must be base64 text.")
    # Reject before decoding so oversized frames never allocate the payload;
    # this is the base64 length of a MAX_AUDIO_CHUNK_BYTES chunk.
    if len(data) > (MAX_AUDIO_CHUNK_BYTES + 2) // 3 * 4:
        _check_audio_size(MAX_AUDIO_CHUNK_BYTES + 1)
    try:
        audio = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise LiveFrameError("invalid_audio", "Audio data must be base64 text.") from exc
    _check_audio_size(len(audio))
    return audio


async def _refuse_live_socket(websocket: WebSocket, close_code: int, code: str, message: str, **extra) -> None:
    await websocket.send_json({"type": "error", "code": code, "message": message, **extra})
    await websocket.close(code=close_code)


@app.websocket("/ws")
async def live_socket(websocket: WebSocket) -> None:
    from main import ArgusLive

    # Accept before refusing: a socket closed during the handshake reaches
    # the browser as HTTP 403 / close code 1006, hiding the reason.
    offered = websocket.scope.get("subprotocols", [])
    await websocket.accept(subprotocol=WEBSOCKET_PROTOCOL if WEBSOCKET_PROTOCOL in offered else None)
    with SessionLocal() as db:
        try:
            user = websocket_user(websocket, db)
        except HTTPException as exc:
            await _refuse_live_socket(websocket, WS_CLOSE_UNAUTHORIZED, "unauthorized", str(exc.detail))
            return
        try:
            await limiter.consume(user.id, "websocket", 12, 60)
        except HTTPException as exc:
            await _refuse_live_socket(
                websocket,
                WS_CLOSE_RATE_LIMITED,
                "rate_limited",
                str(exc.detail),
                retry_after=int((exc.headers or {}).get("Retry-After", 60)),
            )
            return
        api_key = get_user_secret(db, user.id, "gemini_api_key")

    if not api_key:
        await _refuse_live_socket(
            websocket,
            WS_CLOSE_GEMINI_KEY_REQUIRED,
            "gemini_key_required",
            "Add a Gemini API key before starting ARGUS.",
        )
        return

    client = WebSocketClient(websocket, user.id)
    engine = ArgusLive(
        client,
        cloud_safe=True,
        api_key=api_key,
        external_audio=True,
    )
    sender_task = asyncio.create_task(client.send_events())
    with tenant_scope(user.id):
        engine_task = asyncio.create_task(engine.run())
    await live_sessions.replace(user.id, engine, client, engine_task)
    client._emit({
        "type": "ready",
        "state": "CONNECTING",
        "audio": {"input_rate": 16000, "output_rate": 24000, "encoding": "pcm_s16le"},
    })

    async def handle_frame(message: dict) -> bool:
        """Apply one client frame; return False when the client asked to close."""
        if message.get("bytes") is not None:
            _check_audio_size(len(message["bytes"]))
            await engine.send_audio_chunk(message["bytes"])
            return True
        raw = message.get("text")
        if raw is None:
            return True
        event = _parse_live_event(raw)
        event_type = event.get("type")
        if event_type == "text":
            content = str(event.get("content", ""))
            if len(content) > MAX_LIVE_TEXT_CHARS:
                raise LiveFrameError(
                    "text_too_long",
                    f"Messages must be at most {MAX_LIVE_TEXT_CHARS} characters.",
                )
            await limiter.consume(user.id, "live_text", 60, 60)
            with tenant_scope(user.id):
                await engine.send_text(content)
        elif event_type == "audio":
            await engine.send_audio_chunk(
                _decode_live_audio(event.get("data", "")),
                str(event.get("mime_type") or "audio/pcm;rate=16000"),
            )
        elif event_type == "mute":
            client.muted = bool(event.get("muted", True))
            client.set_state("MUTED" if client.muted else "LISTENING")
        elif event_type == "ping":
            client._emit({
                "type": "pong",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        elif event_type == "close":
            return False
        else:
            raise LiveFrameError("unknown_event", "This event type is not supported.")
        return True

    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            try:
                if not await handle_frame(message):
                    break
            except LiveFrameError as exc:
                client._emit({"type": "error", "code": exc.code, "message": exc.message})
            except HTTPException as exc:
                if exc.status_code != status.HTTP_429_TOO_MANY_REQUESTS:
                    raise
                client._emit({"type": "error", "code": "rate_limited", "message": exc.detail})
    except (WebSocketDisconnect, asyncio.CancelledError):
        pass
    except Exception:
        logger.exception("Live session failed for user %s", user.id)
        # Queued behind pending events; the sender flushes it before closing.
        client._emit({
            "type": "error",
            "code": "internal_error",
            "message": "The live session stopped unexpectedly. Please reconnect.",
        })
    finally:
        engine.request_shutdown()
        engine_task.cancel()
        await asyncio.gather(engine_task, return_exceptions=True)
        await live_sessions.remove(user.id, engine_task)
        await client.close()
        try:
            await sender_task
        except (Exception, asyncio.CancelledError):
            pass
        try:
            await websocket.close()
        except (RuntimeError, WebSocketDisconnect):
            pass

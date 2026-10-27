"""Authenticated multi-user HTTP and Gemini Live WebSocket API."""

from __future__ import annotations

import asyncio
import base64
import importlib
import binascii
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from core.api_key_validator import normalize_gemini_api_key, validate_gemini_api_key
from core.tenant import disable_hosted_mode, enable_hosted_mode, tenant_scope
from memory.memory_manager import format_memory_for_prompt, load_memory

from .auth import WEBSOCKET_PROTOCOL, get_current_user, websocket_user
from .config import settings
from .database import SessionLocal, get_db, init_db
from .errors import api_error
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

WS_CLOSE_INTERNAL_ERROR = 1011
WS_CLOSE_SERVICE_RESTART = 1012
WS_CLOSE_SESSION_ENDED = 4000
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

    async def end(self, user_id: str, close_code: int, code: str, message: str) -> None:
        """Close the user's live session, if any, telling the client why."""
        async with self._lock:
            current = self._sessions.pop(user_id, None)
        if current:
            engine, client, task = current
            client._emit({"type": "error", "code": code, "message": message})
            await client.close(code=close_code)
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
        except Exception:
            logger.exception("Retention cleanup failed")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.validate_production()
    enable_hosted_mode()
    # Importing the engine takes ~0.5 s; doing it here keeps the first /ws
    # from freezing every other connection while it loads.
    await asyncio.to_thread(importlib.import_module, "main")
    if settings.auto_create_tables:
        await asyncio.to_thread(init_db)
    try:
        await asyncio.to_thread(
            purge_expired_user_data,
            settings.data_retention_days,
        )
    except Exception:
        logger.exception("Initial retention cleanup failed")
    await limiter.connect()
    retention_task = asyncio.create_task(_retention_loop())
    try:
        yield
    finally:
        retention_task.cancel()
        await asyncio.gather(retention_task, return_exceptions=True)
        await live_sessions.close_all()
        await limiter.close()
        disable_hosted_mode()


app = FastAPI(
    title="ARGUS Cloud API",
    version="0.1.0",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Pydantic's list of errors becomes the usual shape plus the field names.
    errors = exc.errors()
    fields = sorted({
        str(error["loc"][-1])
        for error in errors
        if error.get("loc") and error["loc"][0] == "body" and len(error["loc"]) > 1
    })
    first = errors[0].get("msg", "Invalid request") if errors else "Invalid request"
    message = f"{fields[0]}: {first}" if fields else str(first)
    return JSONResponse(
        status_code=422,
        content={"detail": {"code": "invalid_request", "message": message, "fields": fields}},
    )


class UnexpectedErrorMiddleware:
    """Turn unhandled exceptions into the usual JSON error.

    An exception handler for Exception runs in Starlette's outermost
    middleware, outside CORS, so browsers saw a CORS failure instead of the
    500 body. This middleware sits inside CORSMiddleware.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        response_started = False

        async def tracking_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            logger.error("Unhandled error on %s %s", scope.get("method"), scope.get("path"), exc_info=exc)
            if response_started:
                raise
            response = JSONResponse(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                content={"detail": {
                    "code": "internal_error",
                    "message": "Something went wrong on our side. Please try again.",
                }},
            )
            await response(scope, receive, send)


# Added last so CORS wraps everything, including the 500 responses above.
app.add_middleware(UnexpectedErrorMiddleware)
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


LOGIN_FAILURES_PER_ACCOUNT = 30
LOGIN_FAILURE_WINDOW = 15 * 60


def _client_ip(request: Request) -> str:
    if settings.client_ip_header:
        value = request.headers.get(settings.client_ip_header, "").strip()
        if value:
            return value
    if settings.trusted_proxy_hops > 0:
        hops = [
            hop.strip()
            for hop in request.headers.get("x-forwarded-for", "").split(",")
            if hop.strip()
        ]
        # Only the rightmost hops were written by our proxies; the rest is
        # whatever the client sent.
        if len(hops) >= settings.trusted_proxy_hops:
            return hops[-settings.trusted_proxy_hops]
    return request.client.host if request.client else "unknown"


@app.post("/auth/signup", response_model=SessionView, status_code=201)
async def signup(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
) -> SessionView:
    await limiter.consume(_client_ip(request), "signup_ip", 10, 3600)
    await limiter.consume(payload.email.lower(), "signup", 5, 3600)
    return await asyncio.to_thread(_create_account, db, payload)


# scrypt costs ~25 ms of CPU and the ORM is synchronous; both run in worker
# threads so one sign-in cannot stall every live session on the event loop.
def _create_account(db: Session, payload: UserCreate) -> SessionView:
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
        raise api_error(409, "account_exists", "An account already exists for this email") from exc
    db.refresh(user)
    return SessionView(
        access_token=create_access_token(user.id, user.session_version),
        user=_user_view(user, db),
    )


def _authenticate(db: Session, account: str, password: str) -> SessionView | None:
    user = db.scalar(select(User).where(User.email == account))
    if user is None:
        verify_unknown_account(password)
        return None
    if not verify_password(password, user.password_hash):
        return None
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
    account = payload.email.lower().strip()
    await limiter.consume(ip, "login_ip", 50, 300)
    # Keyed by email and IP so one address cannot lock everyone out of an account.
    await limiter.consume(f"{account}|{ip}", "login", 10, 300)
    # Caps guessing spread over many addresses; only failures count.
    failures = await limiter.count(account, "login_failures", LOGIN_FAILURE_WINDOW)
    if failures >= LOGIN_FAILURES_PER_ACCOUNT:
        raise api_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limited",
            "Too many failed sign-in attempts. Please try again later.",
            headers={"Retry-After": str(LOGIN_FAILURE_WINDOW)},
        )
    session = await asyncio.to_thread(_authenticate, db, account, payload.password)
    if session is None:
        await limiter.record(account, "login_failures", LOGIN_FAILURE_WINDOW)
        raise api_error(401, "invalid_credentials", "Email or password is incorrect")
    return session


@app.get("/auth/me", response_model=UserView)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserView:
    return _user_view(user, db)


@app.post("/auth/logout", status_code=204)
async def logout(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    """End every session of this account by invalidating issued tokens."""
    await asyncio.to_thread(_revoke_sessions, db, user)
    # The live socket authenticated once at connect; close it too.
    await live_sessions.end(user.id, WS_CLOSE_UNAUTHORIZED, "unauthorized", "You signed out.")


def _revoke_sessions(db: Session, user: User) -> None:
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
    # The schema checks length before normalization strips spaces and
    # zero-width characters, so check again on what will be stored.
    if len(key) < 20:
        raise api_error(422, "gemini_key_invalid", "Paste the raw API key created in Google AI Studio.")
    if payload.verify_key:
        validation = await asyncio.to_thread(validate_gemini_api_key, key)
        if not validation.valid and validation.retryable:
            raise api_error(503, "gemini_unavailable", validation.message)
        if not validation.valid:
            raise api_error(422, "gemini_key_invalid", validation.message)
    await asyncio.to_thread(set_user_secret, db, user.id, "gemini_api_key", key)
    # Restart a running live session so the engine and its tools use one key.
    await live_sessions.end(
        user.id,
        WS_CLOSE_SERVICE_RESTART,
        "session_restarted",
        "Your Gemini API key changed; reconnecting.",
    )
    return {"configured": True}


@app.delete("/me/gemini-key", status_code=204)
async def remove_gemini_key(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    await asyncio.to_thread(delete_user_secret, db, user.id, "gemini_api_key")
    # The live engine holds the key it connected with; stop using it.
    await live_sessions.end(
        user.id,
        WS_CLOSE_GEMINI_KEY_REQUIRED,
        "gemini_key_required",
        "Your Gemini API key was removed.",
    )


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
    api_key = await asyncio.to_thread(get_user_secret, db, user.id, "gemini_api_key")
    if not api_key:
        raise api_error(409, "gemini_key_required", "Add a Gemini API key before starting ARGUS")

    with tenant_scope(user.id):
        history = await asyncio.to_thread(recent_chat_messages, user.id, limit=12)
        memory = format_memory_for_prompt(await asyncio.to_thread(load_memory))

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
            raise api_error(502, "gemini_empty_response", "Gemini returned an empty response")
        # Store the turn only once Gemini answers, so failures leave no
        # orphaned user message in the history sent with the next request.
        await asyncio.to_thread(_store_chat_turn, user.id, payload.message, response_text)
    return ChatResponse(response=response_text)


def _store_chat_turn(user_id: str, message: str, reply: str) -> None:
    add_chat_message(user_id, "user", message)
    add_chat_message(user_id, "assistant", reply)


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


# Close codes and events for an engine that stopped on its own.
_TERMINAL_CLOSE_CODES = {
    "gemini_key_rejected": WS_CLOSE_GEMINI_KEY_REQUIRED,
    "gemini_quota_exceeded": WS_CLOSE_RATE_LIMITED,
}


def _engine_finished(task: asyncio.Task, client: WebSocketClient) -> None:
    """Close the socket when the engine stops without the server asking it to."""
    if task.cancelled():
        return  # The handler, a newer session or shutdown already closed it.
    error = task.exception()
    if error is not None:
        logger.error("Live engine failed for user %s", client.user_id, exc_info=error)
        client._emit({
            "type": "error",
            "code": "live_unavailable",
            "message": "ARGUS could not keep the live session running. Please try again later.",
        })
        close_code = WS_CLOSE_INTERNAL_ERROR
    elif client.terminal_error is not None:
        # report_error already sent the event; just pick the matching code.
        close_code = _TERMINAL_CLOSE_CODES.get(client.terminal_error[0], WS_CLOSE_INTERNAL_ERROR)
    else:
        client._emit({"type": "error", "code": "session_ended", "message": "ARGUS ended the session."})
        close_code = WS_CLOSE_SESSION_ENDED
    client.closing_task = asyncio.get_running_loop().create_task(client.close(code=close_code))


def _error_message(exc: HTTPException) -> str:
    detail = exc.detail
    return str(detail.get("message", "")) if isinstance(detail, dict) else str(detail)


def _live_session_owner(websocket: WebSocket) -> tuple[User, str | None]:
    """Authenticate the socket and load the user's key in one short DB session."""
    with SessionLocal() as db:
        user = websocket_user(websocket, db)
        return user, get_user_secret(db, user.id, "gemini_api_key")


@app.websocket("/ws")
async def live_socket(websocket: WebSocket) -> None:
    from main import ArgusLive

    # Accept before refusing: a socket closed during the handshake reaches
    # the browser as HTTP 403 / close code 1006, hiding the reason.
    offered = websocket.scope.get("subprotocols", [])
    await websocket.accept(subprotocol=WEBSOCKET_PROTOCOL if WEBSOCKET_PROTOCOL in offered else None)
    try:
        user, api_key = await asyncio.to_thread(_live_session_owner, websocket)
    except HTTPException as exc:
        await _refuse_live_socket(websocket, WS_CLOSE_UNAUTHORIZED, "unauthorized", _error_message(exc))
        return
    try:
        await limiter.consume(user.id, "websocket", 12, 60)
    except HTTPException as exc:
        await _refuse_live_socket(
            websocket,
            WS_CLOSE_RATE_LIMITED,
            "rate_limited",
            _error_message(exc),
            retry_after=int((exc.headers or {}).get("Retry-After", 60)),
        )
        return

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
    engine_task.add_done_callback(lambda task: _engine_finished(task, client))
    client._emit({
        "type": "ready",
        "state": "CONNECTING",
        "audio": {"input_rate": 16000, "output_rate": 24000, "encoding": "pcm_s16le"},
    })

    async def handle_frame(message: dict) -> bool:
        """Apply one client frame; return False when the client asked to close."""
        if message.get("bytes") is not None:
            _check_audio_size(len(message["bytes"]))
            if not client.muted:
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
            if not content.strip():
                raise LiveFrameError("invalid_frame", "Messages cannot be empty.")
            await limiter.consume(user.id, "live_text", 60, 60)
            if getattr(engine, "session", True) is None:
                raise LiveFrameError("not_ready", "ARGUS is still connecting. Try again in a moment.")
            # Spoken turns are stored from their transcript; typed ones here,
            # before sending, so the turn precedes the reply in the history.
            client._store_history("user", content)
            with tenant_scope(user.id):
                sent = await engine.send_text(content)
            if not sent:
                raise LiveFrameError("not_ready", "ARGUS is still connecting. Try again in a moment.")
        elif event_type == "audio":
            audio = _decode_live_audio(event.get("data", ""))
            if not client.muted:
                await engine.send_audio_chunk(
                    audio,
                    str(event.get("mime_type") or "audio/pcm;rate=16000"),
                )
        elif event_type == "mute":
            muted = event.get("muted", True)
            if not isinstance(muted, bool):
                raise LiveFrameError("invalid_frame", "muted must be true or false.")
            client.muted = muted
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
                client._emit({"type": "error", "code": "rate_limited", "message": _error_message(exc)})
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

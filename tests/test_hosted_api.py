import asyncio
import ipaddress
import random
import base64
import threading
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from api.database import SessionLocal, init_db
from api.models import (
    AnswerCacheEntry,
    ChatMessage,
    MemoryEntry,
    TaskRecord,
    User,
    UserConfig,
    UserSecret,
)
from api.security import create_access_token, decode_access_token, hash_password, verify_password
from api.server import app
from api.websocket_client import WebSocketClient
from core.tenant import tenant_scope
from memory.memory_manager import load_memory, update_memory


TEST_ADDRESS_HEADER = "X-Test-Client-IP"


def _from(address):
    return {TEST_ADDRESS_HEADER: address}


def _random_address():
    """A fresh client IP, so rate-limit buckets never carry over between runs."""
    return str(ipaddress.IPv4Address(random.getrandbits(32)))


class FakeLiveEngine:
    """Stand-in for ArgusLive that echoes text and records audio chunks."""

    def __init__(self, client, **_kwargs):
        self.client = client
        self.stopped = threading.Event()
        self.audio = []

    async def run(self):
        self.client.set_state("LISTENING")
        while not self.stopped.is_set():
            await asyncio.sleep(0.01)

    async def send_text(self, text):
        self.client.write_log(f"Argus: Echo: {text}")
        return True

    async def send_audio_chunk(self, data, _mime_type="audio/pcm;rate=16000"):
        self.audio.append(data)
        return True

    def request_shutdown(self):
        self.stopped.set()

    def _get_current_voice(self):
        return "puck"


class HostedApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import dataclasses
        import api.server

        init_db()
        # Tests pick their client address with a header instead of separate
        # TestClients: each TestClient runs its own event loop, and the shared
        # Redis connection only works on the loop that opened it.
        cls.address_patch = patch.object(
            api.server,
            "settings",
            dataclasses.replace(api.server.settings, client_ip_header=TEST_ADDRESS_HEADER),
        )
        cls.address_patch.start()
        cls.client = TestClient(app)
        cls.context = cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)
        cls.address_patch.stop()

    def setUp(self):
        self.email = f"operator-{uuid.uuid4().hex}@example.com"
        # Each test signs up from its own address so per-IP signup limits never trip.
        response = self.client.post("/auth/signup", headers=_from(_random_address()), json={
            "email": self.email,
            "password": "correct-horse-battery-staple",
            "display_name": "Morgan",
        })
        self.assertEqual(response.status_code, 201, response.text)
        session = response.json()
        self.user_id = session["user"]["id"]
        self.access_token = session["access_token"]
        self.headers = {"Authorization": f"Bearer {session['access_token']}"}

    def tearDown(self):
        with SessionLocal.begin() as db:
            for model in (
                AnswerCacheEntry, TaskRecord, ChatMessage, UserConfig,
                MemoryEntry, UserSecret,
            ):
                db.execute(delete(model).where(model.user_id == self.user_id))
            db.execute(delete(User).where(User.id == self.user_id))

    def test_password_hash_and_jwt_round_trip(self):
        encoded = hash_password("correct-horse-battery-staple")
        self.assertNotIn("correct-horse", encoded)
        self.assertTrue(verify_password("correct-horse-battery-staple", encoded))
        self.assertFalse(verify_password("incorrect-password", encoded))
        token = create_access_token(self.user_id)
        self.assertEqual(decode_access_token(token)["sub"], self.user_id)

    def _login_from(self, address, password="wrong-password-123"):
        return self.client.post(
            "/auth/login",
            headers=_from(address),
            json={"email": self.email, "password": password},
        )

    def test_failed_logins_from_one_address_do_not_lock_out_others(self):
        attacker = _random_address()
        for _ in range(10):
            self.assertEqual(self._login_from(attacker).status_code, 401)
        self.assertEqual(self._login_from(attacker).status_code, 429)
        response = self._login_from(_random_address(), "correct-horse-battery-staple")
        self.assertEqual(response.status_code, 200, response.text)

    def test_unknown_emails_still_pay_for_a_password_check(self):
        import api.server

        with patch.object(
            api.server, "verify_unknown_account", wraps=api.server.verify_unknown_account,
        ) as check:
            response = self.client.post(
                "/auth/login",
                headers=_from(_random_address()),
                json={"email": f"ghost-{uuid.uuid4().hex}@example.com", "password": "whatever-123"},
            )
        self.assertEqual(response.status_code, 401)
        check.assert_called_once_with("whatever-123")

    def test_logout_revokes_issued_tokens(self):
        self.assertEqual(self.client.get("/auth/me", headers=self.headers).status_code, 200)
        self.assertEqual(self.client.post("/auth/logout", headers=self.headers).status_code, 204)
        self.assertEqual(self.client.get("/auth/me", headers=self.headers).status_code, 401)

        response = self._login_from(_random_address(), "correct-horse-battery-staple")
        self.assertEqual(response.status_code, 200, response.text)
        fresh = {"Authorization": f"Bearer {response.json()['access_token']}"}
        self.assertEqual(self.client.get("/auth/me", headers=fresh).status_code, 200)

    def test_production_requires_redis_unless_opted_out(self):
        import os
        from api.config import Settings

        with patch.dict(os.environ, {"ARGUS_ENV": "production"}):
            os.environ.pop("REDIS_REQUIRED", None)
            self.assertTrue(Settings().redis_required)
            os.environ["REDIS_REQUIRED"] = "0"
            self.assertFalse(Settings().redis_required)
        with patch.dict(os.environ, {"ARGUS_ENV": "development"}):
            os.environ.pop("REDIS_REQUIRED", None)
            self.assertFalse(Settings().redis_required)

    def test_production_refuses_weak_secrets_and_local_origins(self):
        import dataclasses
        from api.config import Settings

        good = dataclasses.replace(
            Settings(),
            environment="production",
            jwt_secret="j" * 32,
            encryption_key="e" * 32,
            database_url="postgresql://argus@db/argus",
            cors_origins=("https://app.example.com",),
        )
        good.validate_production()
        for change in (
            {"jwt_secret": "short"},
            {"encryption_key": "short"},
            {"encryption_key": "j" * 32},
            {"cors_origins": ()},
            {"cors_origins": ("http://localhost:3000",)},
        ):
            with self.assertRaises(RuntimeError, msg=change):
                dataclasses.replace(good, **change).validate_production()

    def test_unexpected_errors_return_json_without_internals(self):
        import api.server

        client = TestClient(app, raise_server_exceptions=False)
        with patch.object(
            api.server.live_sessions, "status", side_effect=RuntimeError("redis at 10.0.0.5"),
        ):
            response = client.get("/status", headers=self.headers)
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["detail"]["code"], "internal_error")
        self.assertNotIn("10.0.0.5", response.text)

    def _client_ip_for(self, headers, address="10.1.2.3", **overrides):
        import dataclasses
        import api.server
        from starlette.requests import Request

        overrides.setdefault("client_ip_header", "")
        request = Request({
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": (address, 50000),
        })
        with patch.object(api.server, "settings", dataclasses.replace(api.server.settings, **overrides)):
            return api.server._client_ip(request)

    def test_client_ip_ignores_forwarded_headers_by_default(self):
        self.assertEqual(self._client_ip_for({"X-Forwarded-For": "6.6.6.6"}), "10.1.2.3")

    def test_client_ip_uses_the_configured_platform_header(self):
        headers = {"Fly-Client-IP": "198.51.100.8", "X-Forwarded-For": "6.6.6.6"}
        self.assertEqual(self._client_ip_for(headers, client_ip_header="Fly-Client-IP"), "198.51.100.8")

    def test_client_ip_takes_the_hop_added_by_trusted_proxies(self):
        headers = {"X-Forwarded-For": "6.6.6.6, 198.51.100.8"}
        self.assertEqual(self._client_ip_for(headers, trusted_proxy_hops=1), "198.51.100.8")
        self.assertEqual(self._client_ip_for({}, trusted_proxy_hops=1), "10.1.2.3")

    def test_failed_logins_are_capped_per_account_across_addresses(self):
        from api.server import LOGIN_FAILURES_PER_ACCOUNT

        for _ in range(LOGIN_FAILURES_PER_ACCOUNT):
            self.assertEqual(self._login_from(_random_address()).status_code, 401)
        response = self._login_from(_random_address(), "correct-horse-battery-staple")
        self.assertEqual(response.status_code, 429, response.text)

    def test_login_rejects_oversized_passwords(self):
        response = self._login_from(_random_address(), "x" * 201)
        self.assertEqual(response.status_code, 422)

    def test_signups_are_limited_per_address(self):
        address = _random_address()
        created = []
        try:
            for index in range(11):
                response = self.client.post("/auth/signup", headers=_from(address), json={
                    "email": f"bulk-{index}-{uuid.uuid4().hex}@example.com",
                    "password": "correct-horse-battery-staple",
                    "display_name": "Bulk",
                })
                if response.status_code == 201:
                    created.append(response.json()["user"]["id"])
            self.assertEqual(len(created), 10)
            self.assertEqual(response.status_code, 429)
        finally:
            with SessionLocal.begin() as db:
                db.execute(delete(User).where(User.id.in_(created)))

    def test_gemini_key_is_encrypted_and_user_status_updates(self):
        raw_key = "AIza" + "A" * 35
        response = self.client.post(
            "/me/gemini-key",
            headers=self.headers,
            json={"api_key": raw_key, "validate": False},
        )
        self.assertEqual(response.status_code, 200, response.text)
        with SessionLocal() as db:
            row = db.scalar(select(UserSecret).where(UserSecret.user_id == self.user_id))
            self.assertIsNotNone(row)
            self.assertNotIn(raw_key, row.encrypted_value)
        me = self.client.get("/auth/me", headers=self.headers)
        self.assertTrue(me.json()["gemini_configured"])

        from actions.presentation_maker import _api_key

        with tenant_scope(self.user_id):
            self.assertEqual(_api_key(), raw_key)

    def _chat_with_gemini(self, outcome):
        """Send /chat while Gemini answers with ``outcome`` (text or exception)."""
        response = self.client.post(
            "/me/gemini-key",
            headers=self.headers,
            json={"api_key": "AIza" + "C" * 35, "validate": False},
        )
        self.assertEqual(response.status_code, 200, response.text)
        created = []

        class FakeModels:
            def generate_content(self, **_kwargs):
                if isinstance(outcome, BaseException):
                    raise outcome
                return SimpleNamespace(text=outcome)

        class FakeClient:
            def __init__(self, **kwargs):
                created.append(kwargs)
                self.models = FakeModels()

        with patch("google.genai.Client", FakeClient):
            response = self.client.post(
                "/chat", headers=self.headers, json={"message": "hello there"},
            )
        return response, created

    def _stored_chat(self):
        with SessionLocal() as db:
            return [
                (row.role, row.content)
                for row in db.scalars(
                    select(ChatMessage)
                    .where(ChatMessage.user_id == self.user_id)
                    .order_by(ChatMessage.created_at)
                )
            ]

    def test_chat_stores_both_turns_and_bounds_the_gemini_call(self):
        response, created = self._chat_with_gemini("General Kenobi")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["response"], "General Kenobi")
        self.assertEqual(
            self._stored_chat(),
            [("user", "hello there"), ("assistant", "General Kenobi")],
        )
        self.assertGreater(created[0]["http_options"].timeout, 0)

    def test_chat_reports_a_rejected_gemini_key(self):
        from google.genai import errors

        response, _ = self._chat_with_gemini(errors.ClientError(400, {"error": {
            "code": 400,
            "message": "API key not valid. Please pass a valid API key.",
            "status": "INVALID_ARGUMENT",
        }}))
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(response.json()["detail"]["code"], "gemini_key_rejected")
        self.assertEqual(self._stored_chat(), [])

    def test_chat_reports_gemini_quota_limits(self):
        from google.genai import errors

        response, _ = self._chat_with_gemini(errors.ClientError(429, {"error": {
            "code": 429, "message": "Quota exceeded", "status": "RESOURCE_EXHAUSTED",
        }}))
        self.assertEqual(response.status_code, 429, response.text)
        self.assertEqual(response.json()["detail"]["code"], "gemini_quota_exceeded")
        self.assertIn("Retry-After", response.headers)
        self.assertEqual(self._stored_chat(), [])

    def test_chat_reports_gemini_outages_and_timeouts(self):
        import httpx
        from google.genai import errors

        response, _ = self._chat_with_gemini(errors.ServerError(503, {"error": {
            "code": 503, "message": "overloaded", "status": "UNAVAILABLE",
        }}))
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(response.json()["detail"]["code"], "gemini_unavailable")

        response, _ = self._chat_with_gemini(httpx.ReadTimeout("timed out"))
        self.assertEqual(response.status_code, 504, response.text)
        self.assertEqual(response.json()["detail"]["code"], "gemini_timeout")
        self.assertEqual(self._stored_chat(), [])

    def test_chat_hides_unexpected_gemini_failures(self):
        response, _ = self._chat_with_gemini(RuntimeError("socket at 10.0.0.7 reset"))
        self.assertEqual(response.status_code, 502, response.text)
        self.assertEqual(response.json()["detail"]["code"], "gemini_failed")
        self.assertNotIn("10.0.0.7", response.text)
        self.assertEqual(self._stored_chat(), [])

    def test_memory_is_scoped_by_tenant(self):
        with tenant_scope(self.user_id):
            update_memory({"identity": {"name": {"value": "Morgan"}}})
            self.assertEqual(load_memory()["identity"]["name"]["value"], "Morgan")

        other_id = str(uuid.uuid4())
        with SessionLocal.begin() as db:
            db.add(User(
                id=other_id,
                email=f"other-{uuid.uuid4().hex}@example.com",
                display_name="Other",
                password_hash=hash_password("another-secure-password"),
            ))
        try:
            with tenant_scope(other_id):
                self.assertNotIn("name", load_memory()["identity"])
        finally:
            with SessionLocal.begin() as db:
                db.execute(delete(User).where(User.id == other_id))

    def test_status_and_cloud_actions_are_authenticated(self):
        self.assertEqual(self.client.get("/status").status_code, 401)
        status_response = self.client.get("/status", headers=self.headers)
        self.assertEqual(status_response.json()["state"], "OFFLINE")
        actions = self.client.get("/actions", headers=self.headers).json()["actions"]
        names = {action["name"] for action in actions}
        self.assertIn("web_search", names)
        self.assertIn("code_generator", names)
        self.assertNotIn("open_app", names)
        self.assertNotIn("code_helper", names)

    def test_cloud_action_worker_keeps_tenant_context(self):
        import main
        from core.tenant import get_current_user_id

        argus = main.ArgusLive.__new__(main.ArgusLive)
        argus.cloud_safe = True
        argus.ui = SimpleNamespace(
            set_state=lambda _state: None,
            muted=False,
        )
        call = SimpleNamespace(id="tenant-call", name="web_search", args={"query": "test"})

        with patch.object(main, "web_search_action", side_effect=lambda **_kwargs: get_current_user_id()):
            with tenant_scope(self.user_id):
                response = asyncio.run(argus._execute_tool(call))

        self.assertEqual(response.response["result"], self.user_id)

    def test_cloud_code_generator_keeps_tenant_context(self):
        import main
        from core.tenant import get_current_user_id

        argus = main.ArgusLive.__new__(main.ArgusLive)
        argus.cloud_safe = True
        argus.ui = SimpleNamespace(
            set_state=lambda _state: None,
            muted=False,
        )
        call = SimpleNamespace(
            id="tenant-code-call",
            name="code_generator",
            args={"description": "print hello", "language": "Rust"},
        )

        with patch.object(
            main,
            "code_generator",
            side_effect=lambda **_kwargs: f"tenant={get_current_user_id()}",
        ):
            with tenant_scope(self.user_id):
                response = asyncio.run(argus._execute_tool(call))

        self.assertEqual(response.response["result"], f"tenant={self.user_id}")

    def _open_live_socket(self):
        response = self.client.post(
            "/me/gemini-key",
            headers=self.headers,
            json={"api_key": "AIza" + "D" * 35, "validate": False},
        )
        self.assertEqual(response.status_code, 200, response.text)
        import main

        patcher = patch.object(main, "ArgusLive", FakeLiveEngine)
        patcher.start()
        self.addCleanup(patcher.stop)
        socket = self.client.websocket_connect("/ws", subprotocols=self._live_protocols()).__enter__()
        self.addCleanup(socket.__exit__, None, None, None)
        received = [socket.receive_json(), socket.receive_json()]
        self.assertEqual({event["type"] for event in received}, {"ready", "status"})
        return socket

    def _assert_session_alive(self, socket):
        socket.send_json({"type": "text", "content": "still there?"})
        message = socket.receive_json()
        self.assertEqual(message["type"], "message")
        self.assertEqual(message["content"], "Echo: still there?")

    def test_websocket_rejects_malformed_frames_without_closing(self):
        socket = self._open_live_socket()
        for frame, code in (
            ("not json", "invalid_frame"),
            ("[1, 2]", "invalid_frame"),
            ('{"type": "audio", "data": "***"}', "invalid_audio"),
            ('{"type": "audio", "data": 42}', "invalid_audio"),
            ('{"type": "teleport"}', "unknown_event"),
        ):
            socket.send_text(frame)
            error = socket.receive_json()
            self.assertEqual((error["type"], error["code"]), ("error", code), frame)
        self._assert_session_alive(socket)

    def test_websocket_limits_live_input_size(self):
        from api.server import MAX_AUDIO_CHUNK_BYTES, MAX_LIVE_TEXT_CHARS

        socket = self._open_live_socket()
        socket.send_bytes(b"\x00" * (MAX_AUDIO_CHUNK_BYTES + 1))
        self.assertEqual(socket.receive_json()["code"], "audio_too_large")
        oversized = base64.b64encode(b"\x00" * (MAX_AUDIO_CHUNK_BYTES + 3)).decode()
        socket.send_json({"type": "audio", "data": oversized})
        self.assertEqual(socket.receive_json()["code"], "audio_too_large")
        largest = base64.b64encode(b"\x00" * MAX_AUDIO_CHUNK_BYTES).decode()
        socket.send_json({"type": "audio", "data": largest})
        socket.send_json({"type": "text", "content": "x" * (MAX_LIVE_TEXT_CHARS + 1)})
        self.assertEqual(socket.receive_json()["code"], "text_too_long")
        self._assert_session_alive(socket)

    def test_websocket_keeps_the_session_when_text_is_rate_limited(self):
        from api.rate_limit import limiter

        socket = self._open_live_socket()
        real_consume = limiter.consume

        async def consume(user_id, bucket, limit, window):
            if bucket == "live_text":
                limit = 0
            await real_consume(user_id, bucket, limit, window)

        with patch.object(limiter, "consume", consume):
            socket.send_json({"type": "text", "content": "too fast"})
            self.assertEqual(socket.receive_json()["code"], "rate_limited")
        self._assert_session_alive(socket)

    def test_websocket_hides_internal_failures(self):
        socket = self._open_live_socket()
        with patch.object(
            FakeLiveEngine, "send_text", side_effect=RuntimeError("db at 10.0.0.9 down"),
        ):
            socket.send_json({"type": "text", "content": "boom"})
            error = socket.receive_json()
        self.assertEqual(error["code"], "internal_error")
        self.assertNotIn("10.0.0.9", error["message"])
        self.assertEqual(socket.receive()["type"], "websocket.close")

    def _live_protocols(self, token=None):
        return ["argus.v1", f"bearer.{token or self.access_token}"]

    def _rejected_socket_url(self, url):
        from starlette.websockets import WebSocketDisconnect

        with self.client.websocket_connect(url) as socket:
            event = socket.receive_json()
            with self.assertRaises(WebSocketDisconnect) as closed:
                socket.receive_json()
        return event, closed.exception.code

    def _rejected_socket(self, protocols):
        """Connect to a socket the server refuses; return its error event and close code."""
        from starlette.websockets import WebSocketDisconnect

        with self.client.websocket_connect("/ws", subprotocols=protocols) as socket:
            event = socket.receive_json()
            with self.assertRaises(WebSocketDisconnect) as closed:
                socket.receive_json()
        return event, closed.exception.code

    def test_websocket_rejects_missing_or_bad_tokens_with_4401(self):
        for protocols in (["argus.v1"], self._live_protocols("not-a-token")):
            event, code = self._rejected_socket(protocols)
            self.assertEqual((event["type"], event["code"]), ("error", "unauthorized"), protocols)
            self.assertEqual(code, 4401, protocols)

    def test_websocket_ignores_tokens_in_the_query_string(self):
        event, code = self._rejected_socket_url(f"/ws?token={self.access_token}")
        self.assertEqual((event["code"], code), ("unauthorized", 4401))

    def test_websocket_selects_the_argus_subprotocol(self):
        socket = self._open_live_socket()
        self.assertEqual(socket.accepted_subprotocol, "argus.v1")

    def test_websocket_reports_rate_limits_with_4429(self):
        from api.rate_limit import limiter

        real_consume = limiter.consume

        async def consume(user_id, bucket, limit, window):
            await real_consume(user_id, bucket, 0 if bucket == "websocket" else limit, window)

        with patch.object(limiter, "consume", consume):
            event, code = self._rejected_socket(self._live_protocols())
        self.assertEqual(event["code"], "rate_limited")
        self.assertEqual(event["retry_after"], 60)
        self.assertEqual(code, 4429)

    def test_websocket_requires_a_gemini_key_with_4403(self):
        event, code = self._rejected_socket(self._live_protocols())
        self.assertEqual(event["code"], "gemini_key_required")
        self.assertEqual(code, 4403)

    def test_a_new_live_session_closes_the_previous_one(self):
        from starlette.websockets import WebSocketDisconnect

        first = self._open_live_socket()
        second = self.client.websocket_connect("/ws", subprotocols=self._live_protocols()).__enter__()
        self.addCleanup(second.__exit__, None, None, None)

        event = first.receive_json()
        self.assertEqual((event["type"], event["code"]), ("error", "session_replaced"))
        with self.assertRaises(WebSocketDisconnect) as closed:
            first.receive_json()
        self.assertEqual(closed.exception.code, 4409)

        received = [second.receive_json(), second.receive_json()]
        self.assertEqual({event["type"] for event in received}, {"ready", "status"})
        self._assert_session_alive(second)

    def test_authenticated_websocket_streams_engine_events(self):
        raw_key = "AIza" + "B" * 35
        response = self.client.post(
            "/me/gemini-key",
            headers=self.headers,
            json={"api_key": raw_key, "validate": False},
        )
        self.assertEqual(response.status_code, 200, response.text)

        import main

        with patch.object(main, "ArgusLive", FakeLiveEngine):
            with self.client.websocket_connect("/ws", subprotocols=self._live_protocols()) as socket:
                received = [socket.receive_json(), socket.receive_json()]
                self.assertEqual({event["type"] for event in received}, {"ready", "status"})
                socket.send_json({"type": "text", "content": "status report"})
                message = socket.receive_json()
                self.assertEqual(message["type"], "message")
                self.assertEqual(message["content"], "Echo: status report")
                socket.send_json({"type": "close"})
                self.assertEqual(socket.receive()["type"], "websocket.close")

        with SessionLocal() as db:
            stored = db.scalars(
                select(ChatMessage)
                .where(ChatMessage.user_id == self.user_id)
                .order_by(ChatMessage.created_at)
            ).all()
        self.assertEqual(
            [(row.role, row.content) for row in stored],
            [("assistant", "Echo: status report")],
        )


class FakeWebSocket:
    def __init__(self):
        self.events = []

    async def send_json(self, event):
        self.events.append(event)


class WebSocketAdapterTests(unittest.TestCase):
    def test_adapter_serializes_status_text_and_audio(self):
        async def run():
            socket = FakeWebSocket()
            client = WebSocketClient(socket)
            sender = asyncio.create_task(client.send_events())
            client.set_state("LISTENING")
            client.write_log("Argus: Online.")
            client.send_audio(b"\x01\x02")
            await asyncio.sleep(0)
            await client.close()
            await sender
            return socket.events

        events = asyncio.run(run())
        self.assertEqual([event["type"] for event in events], ["status", "message", "audio"])
        self.assertEqual(events[-1]["data"], "AQI=")

    def test_adapter_strips_speaker_prefixes_without_losing_text(self):
        async def run():
            socket = FakeWebSocket()
            client = WebSocketClient(socket)
            sender = asyncio.create_task(client.send_events())
            client.write_log("You: Hello")
            client.write_log("Argus: Online.")
            client.write_log("Research finished")
            await asyncio.sleep(0)
            await client.close()
            await sender
            return socket.events

        events = asyncio.run(run())
        self.assertEqual(
            [(event["role"], event["content"]) for event in events],
            [("user", "Hello"), ("assistant", "Online."), ("system", "Research finished")],
        )


if __name__ == "__main__":
    unittest.main()

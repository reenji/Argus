import asyncio
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
        init_db()
        cls.client = TestClient(app)
        cls.context = cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        self.email = f"operator-{uuid.uuid4().hex}@example.com"
        response = self.client.post("/auth/signup", json={
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
        socket = self.client.websocket_connect(f"/ws?token={self.access_token}").__enter__()
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
        socket.send_json({"type": "text", "content": "x" * (MAX_LIVE_TEXT_CHARS + 1)})
        self.assertEqual(socket.receive_json()["code"], "text_too_long")
        self._assert_session_alive(socket)

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
            with self.client.websocket_connect(f"/ws?token={self.access_token}") as socket:
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

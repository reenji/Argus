"""ArgusLive behaviour that the hosted live socket depends on."""

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import main


class RecordingClient:
    def __init__(self):
        self.muted = False
        self.current_file = None
        self.on_text_command = None
        self._voice_combo = None
        self.errors = []

    def __getattr__(self, _name):
        return lambda *args, **kwargs: None

    def report_error(self, code, message):
        self.errors.append(code)


def _failing_connect(error):
    class Connect:
        async def __aenter__(self):
            raise error

        async def __aexit__(self, *_exc):
            return False

    return lambda **_kwargs: Connect()


def _client_raising(error):
    return SimpleNamespace(aio=SimpleNamespace(live=SimpleNamespace(connect=_failing_connect(error))))


class LiveEngineTests(unittest.TestCase):
    def _engine(self):
        engine = main.ArgusLive(RecordingClient(), cloud_safe=True, api_key="test-key", external_audio=True)
        engine._build_config = lambda: None
        return engine

    def _run(self, engine, error):
        with patch.object(main.genai, "Client", return_value=_client_raising(error)), \
                patch.object(main, "pick_live_model", return_value="models/live-test"), \
                patch.object(engine, "_wait_before_reconnect") as wait:
            async def no_wait(delay):
                waits.append(delay)
                if len(waits) >= 3:
                    engine.request_shutdown()

            waits = []
            wait.side_effect = no_wait
            asyncio.run(asyncio.wait_for(engine.run(), timeout=5))
        return waits

    def test_a_rejected_key_stops_reconnecting_and_is_reported(self):
        from google.genai import errors

        engine = self._engine()
        waits = self._run(engine, errors.ClientError(400, {"error": {
            "code": 400, "message": "API key not valid.", "status": "INVALID_ARGUMENT",
        }}))
        self.assertEqual(waits, [])
        self.assertEqual(engine.ui.errors, ["gemini_key_rejected"])

    def test_transient_failures_back_off_before_reconnecting(self):
        engine = self._engine()
        waits = self._run(engine, ConnectionResetError("connection reset by peer"))
        self.assertEqual(waits, [1.0, 2.0, 4.0])
        self.assertEqual(engine.ui.errors, [])

    def test_audio_is_dropped_instead_of_blocking_when_the_queue_is_full(self):
        engine = self._engine()

        async def scenario():
            engine.session = object()
            engine.out_queue = asyncio.Queue(maxsize=1)
            first = await engine.send_audio_chunk(b"\x01")
            second = await asyncio.wait_for(engine.send_audio_chunk(b"\x02"), timeout=1)
            return first, second

        self.assertEqual(asyncio.run(scenario()), (True, False))


if __name__ == "__main__":
    unittest.main()

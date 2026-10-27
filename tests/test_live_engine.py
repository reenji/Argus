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
        self.states = []
        self.interruptions = 0

    def __getattr__(self, _name):
        return lambda *args, **kwargs: None

    def report_error(self, code, message):
        self.errors.append(code)

    def set_state(self, state):
        self.states.append(state)

    def interrupt_audio(self):
        self.interruptions += 1


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


class LiveAudioTests(unittest.TestCase):
    def _engine(self):
        return main.ArgusLive(RecordingClient(), cloud_safe=True, api_key="test-key", external_audio=True)

    def test_speaking_state_is_sent_once_per_change(self):
        engine = self._engine()
        for value in (True, True, True, False, False):
            engine.set_speaking(value)
        self.assertEqual(engine.ui.states, ["SPEAKING", "LISTENING"])

    def test_an_interruption_drops_queued_reply_audio(self):
        engine = self._engine()

        def response(**server_content):
            return SimpleNamespace(
                data=None,
                server_content=SimpleNamespace(
                    output_transcription=None, input_transcription=None,
                    turn_complete=False, model_turn=None, **server_content,
                ),
                tool_call=None,
            )

        class Session:
            async def receive(self):
                yield response(interrupted=True)
                engine.request_shutdown()

        async def scenario():
            engine.session = Session()
            engine.audio_in_queue = asyncio.Queue()
            for chunk in (b"a", b"b", b"c"):
                engine.audio_in_queue.put_nowait(chunk)
            engine._turn_done_event = asyncio.Event()
            await asyncio.wait_for(engine._receive_audio(), timeout=5)

        asyncio.run(scenario())
        self.assertTrue(engine.audio_in_queue.empty())
        self.assertEqual(engine.ui.interruptions, 1)


if __name__ == "__main__":
    unittest.main()

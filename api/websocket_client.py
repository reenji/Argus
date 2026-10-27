"""ArgusClient adapter that emits engine events as WebSocket JSON frames."""

from __future__ import annotations

import asyncio
import base64
import logging
from concurrent.futures import Future, ThreadPoolExecutor
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket


logger = logging.getLogger(__name__)

_SPEAKER_PREFIXES = (("You: ", "user"), ("Argus: ", "assistant"))

class WebSocketClient:
    def __init__(self, websocket: WebSocket, user_id: str | None = None):
        self.websocket = websocket
        self.user_id = user_id
        self.on_text_command: Callable[[str], None] | None = None
        self.muted = False
        self.current_file: str | None = None
        self._voice_combo = None
        self.state = "CONNECTING"
        self._loop = asyncio.get_running_loop()
        self._events: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=256)
        self._close_code: int | None = None
        # Set by the engine when it stops for a reason reconnecting cannot fix.
        self.terminal_error: tuple[str, str] | None = None
        # One writer thread keeps transcript inserts in order and off the
        # event loop that carries every user's audio.
        self._history_writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="argus-history")

    def _enqueue(self, event: dict[str, Any] | None) -> None:
        if self._events.full():
            try:
                self._events.get_nowait()
            except asyncio.QueueEmpty:
                pass
        self._events.put_nowait(event)

    def _emit(self, event: dict[str, Any]) -> None:
        event.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        self._loop.call_soon_threadsafe(self._enqueue, event)

    def write_log(self, text: str) -> None:
        role = "system"
        content = str(text)
        for prefix, speaker in _SPEAKER_PREFIXES:
            if content.startswith(prefix):
                role, content = speaker, content.removeprefix(prefix)
                break
        if self.user_id and role in {"user", "assistant"}:
            self._store_history(role, content)
        self._emit({"type": "message", "role": role, "content": content})

    def _store_history(self, role: str, content: str) -> None:
        from . import repositories

        try:
            job = self._history_writer.submit(repositories.add_chat_message, self.user_id, role, content)
        except RuntimeError:
            return  # The session already closed; late engine output is dropped.
        job.add_done_callback(_log_history_failure)

    def report_error(self, code: str, message: str) -> None:
        self.terminal_error = (code, message)
        self._emit({"type": "error", "code": code, "message": message})

    def set_state(self, state: str) -> None:
        self.state = str(state).upper()
        self._emit({"type": "status", "state": self.state})

    def show_subtitle(self, text: str) -> None:
        self._emit({"type": "transcript", "content": str(text), "final": False})

    def clear_subtitle(self) -> None:
        self._emit({"type": "transcript_clear"})

    def set_theme(self, theme_key: str) -> None:
        self._emit({"type": "preference", "name": "theme", "value": theme_key})

    def set_graphics_quality(self, quality: str) -> None:
        self._emit({"type": "preference", "name": "graphics_quality", "value": quality})

    def sync_voice_display(self, voice_name: str) -> None:
        self._emit({"type": "preference", "name": "voice", "value": voice_name})

    def handle_ui_command(self, action: str) -> None:
        self._emit({"type": "ui_command", "action": action})

    def show_research_progress(self, question: str) -> None:
        self._emit({"type": "progress", "kind": "research", "label": question, "percent": 0, "phase": "Queued"})

    def update_research_progress(self, question: str, percent: int, phase: str, artifacts=None, warnings=None) -> None:
        self._emit({"type": "progress", "kind": "research", "label": question, "percent": percent, "phase": phase, "artifacts": artifacts or [], "warnings": warnings or []})

    def finish_research_progress(self, state: str, detail: str) -> None:
        self._emit({"type": "progress_end", "kind": "research", "state": state, "detail": detail})

    def hide_research_progress(self) -> None:
        self._emit({"type": "progress_hide", "kind": "research"})

    def show_presentation_progress(self, title: str, visible: bool = False) -> None:
        self._emit({"type": "progress", "kind": "presentation", "label": title, "percent": 0, "phase": "Queued", "visible": visible})

    def update_presentation_progress(self, title: str, percent: int, phase: str, visible: bool = False, artifacts=None, warnings=None) -> None:
        self._emit({"type": "progress", "kind": "presentation", "label": title, "percent": percent, "phase": phase, "visible": visible, "artifacts": artifacts or [], "warnings": warnings or []})

    def finish_presentation_progress(self, state: str, detail: str) -> None:
        self._emit({"type": "progress_end", "kind": "presentation", "state": state, "detail": detail})

    def hide_presentation_progress(self) -> None:
        self._emit({"type": "progress_hide", "kind": "presentation"})

    def send_audio(self, data: bytes, mime_type: str = "audio/pcm;rate=24000") -> None:
        self._emit({
            "type": "audio",
            "mime_type": mime_type,
            "data": base64.b64encode(data).decode("ascii"),
        })

    async def send_events(self) -> None:
        while True:
            event = await self._events.get()
            try:
                if event is None:
                    if self._close_code is not None:
                        await self.websocket.close(code=self._close_code)
                    return
                await self.websocket.send_json(event)
            except Exception:
                # The browser already went away; nothing left to deliver.
                return

    async def close(self, code: int | None = None) -> None:
        """Stop sending after the queued events; with a code, also close the socket."""
        self._close_code = code
        # Let queued transcript lines finish so the history is complete on close.
        await asyncio.to_thread(self._history_writer.shutdown, True)
        # Scheduled like _emit so events emitted just before still go out first.
        self._loop.call_soon_threadsafe(self._enqueue, None)


def _log_history_failure(job: Future) -> None:
    if not job.cancelled() and job.exception() is not None:
        logger.error("Could not store a live transcript line", exc_info=job.exception())

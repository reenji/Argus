"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { getToken, sessionExpired, WS_URL } from "@/lib/api";

export type ArgusState = "OFFLINE" | "CONNECTING" | "LISTENING" | "THINKING" | "SPEAKING" | "MUTED";
export type Message = { id: string; role: "user" | "assistant" | "system"; content: string; at: string };
export type Progress = { kind: string; label: string; percent: number; phase: string } | null;

type Capture = {
  context: AudioContext;
  stream: MediaStream;
  source: MediaStreamAudioSourceNode;
  processor: ScriptProcessorNode;
  sink: GainNode;
};

// Close codes sent by the /ws endpoint (api/server.py, docs/HOSTED_API.md).
const CLOSE_SESSION_ENDED = 4000;
const CLOSE_UNAUTHORIZED = 4401;
const CLOSE_GEMINI_KEY_REQUIRED = 4403;
const CLOSE_SESSION_REPLACED = 4409;
const CLOSE_RATE_LIMITED = 4429;
const ARGUS_STATES = new Set(["OFFLINE", "CONNECTING", "LISTENING", "THINKING", "SPEAKING", "MUTED"]);

/** Exponential backoff with jitter: ~1 s, 2 s, 4 s ... capped at 30 s. */
function reconnectDelay(attempt: number) {
  const base = Math.min(30_000, 1000 * 2 ** Math.max(0, attempt - 1));
  return base / 2 + Math.random() * (base / 2);
}

type SocketCallbacks = {
  /** The server says the account has no usable Gemini key. */
  onKeyRequired?: () => void;
};

function pcm16(input: Float32Array, sourceRate: number, targetRate = 16000) {
  const ratio = sourceRate / targetRate;
  const length = Math.max(1, Math.floor(input.length / ratio));
  const output = new Int16Array(length);
  for (let i = 0; i < length; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(input.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j += 1) sum += input[j];
    const value = Math.max(-1, Math.min(1, sum / Math.max(1, end - start)));
    output[i] = value < 0 ? value * 32768 : value * 32767;
  }
  return output;
}

export function useArgusSocket({ onKeyRequired }: SocketCallbacks = {}) {
  const socket = useRef<WebSocket | null>(null);
  const capture = useRef<Capture | null>(null);
  const startingMic = useRef(false);
  const playback = useRef<AudioContext | null>(null);
  const nextPlaybackAt = useRef(0);
  const scheduled = useRef(new Set<AudioBufferSourceNode>());
  const stopMicRef = useRef<(() => Promise<void>) | null>(null);
  const [state, setState] = useState<ArgusState>("CONNECTING");
  const [messages, setMessages] = useState<Message[]>([]);
  const [transcript, setTranscript] = useState("");
  const [progress, setProgress] = useState<Progress>(null);
  const [error, setError] = useState("");
  const [micActive, setMicActive] = useState(false);

  const ensurePlayback = useCallback(async () => {
    if (!playback.current) playback.current = new AudioContext({ sampleRate: 24000 });
    if (playback.current.state === "suspended") await playback.current.resume();
    return playback.current;
  }, []);

  const playAudio = useCallback(async (encoded: string, mimeType?: string) => {
    const context = await ensurePlayback();
    const binary = window.atob(encoded);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    const view = new DataView(bytes.buffer);
    const samples = new Float32Array(Math.floor(bytes.byteLength / 2));
    for (let i = 0; i < samples.length; i += 1) samples[i] = view.getInt16(i * 2, true) / 32768;
    const rate = Number(/rate=(\d+)/.exec(mimeType ?? "")?.[1]) || 24000;
    const buffer = context.createBuffer(1, samples.length, rate);
    buffer.copyToChannel(samples, 0);
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    const start = Math.max(context.currentTime + 0.02, nextPlaybackAt.current);
    source.start(start);
    nextPlaybackAt.current = start + buffer.duration;
    scheduled.current.add(source);
    source.onended = () => { scheduled.current.delete(source); };
  }, [ensurePlayback]);

  /** Silence reply audio already scheduled, e.g. when the user talks over ARGUS. */
  const clearPlayback = useCallback(() => {
    scheduled.current.forEach((source) => { try { source.stop(); } catch { /* already ended */ } });
    scheduled.current.clear();
    nextPlaybackAt.current = 0;
  }, []);

  const keyRequired = useRef(onKeyRequired);
  useEffect(() => { keyRequired.current = onKeyRequired; }, [onKeyRequired]);

  useEffect(() => {
    // Each run of this effect owns its sockets and timers; events from a
    // socket of an earlier run (React strict mode, remounts) are ignored.
    let active = true;
    let retry: ReturnType<typeof setTimeout> | undefined;
    let attempt = 0;

    function stop(message: string) {
      setError(message);
      void stopMicRef.current?.();
    }

    function connect() {
      const token = getToken();
      if (!token || !active) return;
      setState("CONNECTING");
      // The token travels as a subprotocol so it never lands in URL logs.
      const ws = new WebSocket(`${WS_URL}/ws`, ["argus.v1", `bearer.${token}`]);
      ws.binaryType = "arraybuffer";
      socket.current = ws;
      let retryAfterMs = 0;
      const current = () => active && socket.current === ws;

      ws.onmessage = (message) => {
        if (!current()) return;
        let event;
        try {
          event = JSON.parse(String(message.data));
        } catch {
          return;
        }
        if (!event || typeof event !== "object") return;
        if (event.type === "status" && ARGUS_STATES.has(event.state)) setState(event.state as ArgusState);
        if (event.type === "ready") {
          attempt = 0;
          setError("");
        }
        if (event.type === "message" && typeof event.content === "string") {
          setMessages((list) => {
            const role = (["user", "assistant", "system"].includes(event.role) ? event.role : "system") as Message["role"];
            const previous = list[list.length - 1];
            if (previous?.role === role && previous.content === event.content) return list;
            return [...list.slice(-99), { id: crypto.randomUUID(), role, content: event.content, at: event.timestamp }];
          });
        }
        if (event.type === "transcript" && typeof event.content === "string") setTranscript((value) => `${value} ${event.content}`.trim());
        if (event.type === "transcript_clear") setTranscript("");
        if (event.type === "audio" && typeof event.data === "string") {
          playAudio(event.data, event.mime_type).catch(() => setError("Audio playback needs browser permission."));
        }
        if (event.type === "audio_clear") clearPlayback();
        if (event.type === "progress" && event.visible !== false) {
          setProgress({ kind: String(event.kind), label: String(event.label), percent: Number(event.percent) || 0, phase: String(event.phase ?? "") });
        }
        if (event.type === "progress_end") {
          setProgress(null);
          if (event.state === "failed" && event.detail) setError(String(event.detail));
        }
        if (event.type === "progress_hide") setProgress(null);
        if (event.type === "error") {
          setError(typeof event.message === "string" && event.message ? event.message : "Live session error");
          if (event.retry_after > 0) retryAfterMs = event.retry_after * 1000;
        }
      };
      ws.onerror = () => { if (current()) setError("The live channel could not be reached."); };
      ws.onclose = (event) => {
        if (!current()) return;
        socket.current = null;
        setState("OFFLINE");
        // Refusals that a retry cannot fix end the reconnect loop.
        if (event.code === CLOSE_UNAUTHORIZED) {
          stop("Your session expired. Sign in again.");
          sessionExpired();
          return;
        }
        if (event.code === CLOSE_GEMINI_KEY_REQUIRED) {
          stop("Your Gemini key needs attention.");
          keyRequired.current?.();
          return;
        }
        // Reconnecting would take the session back from the other window, and so on forever.
        if (event.code === CLOSE_SESSION_REPLACED) return stop("ARGUS is open in another window. Reload to use it here.");
        if (event.code === CLOSE_SESSION_ENDED) return stop("ARGUS ended the session. Reload to start again.");
        attempt += 1;
        const delay = event.code === CLOSE_RATE_LIMITED
          ? Math.max(retryAfterMs || 60_000, reconnectDelay(attempt))
          : reconnectDelay(attempt);
        retry = setTimeout(connect, delay);
      };
    }

    connect();
    return () => {
      active = false;
      if (retry) clearTimeout(retry);
      socket.current?.close();
      socket.current = null;
    };
  }, [playAudio, clearPlayback]);

  const sendText = useCallback(async (content: string) => {
    const clean = content.trim();
    if (!clean || socket.current?.readyState !== WebSocket.OPEN) return false;
    // Unlock audio for the reply, but a blocked AudioContext must not lose the message.
    await ensurePlayback().catch(() => undefined);
    if (socket.current?.readyState !== WebSocket.OPEN) return false;
    setMessages((current) => [...current.slice(-99), { id: crypto.randomUUID(), role: "user", content: clean, at: new Date().toISOString() }]);
    socket.current.send(JSON.stringify({ type: "text", content: clean }));
    return true;
  }, [ensurePlayback]);

  const stopMic = useCallback(async () => {
    const current = capture.current;
    capture.current = null;
    setMicActive(false);
    if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify({ type: "mute", muted: true }));
    if (current) {
      current.processor.disconnect();
      current.source.disconnect();
      current.sink.disconnect();
      current.stream.getTracks().forEach((track) => track.stop());
      await current.context.close().catch(() => undefined);
    }
  }, []);
  useEffect(() => { stopMicRef.current = stopMic; }, [stopMic]);

  const startMic = useCallback(async () => {
    // A second click while the permission prompt is open must not open a second capture.
    if (capture.current || startingMic.current) return;
    startingMic.current = true;
    let stream: MediaStream | null = null;
    let context: AudioContext | null = null;
    try {
      await ensurePlayback();
      stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      context = new AudioContext();
      const sampleRate = context.sampleRate;
      const source = context.createMediaStreamSource(stream);
      const processor = context.createScriptProcessor(4096, 1, 1);
      const sink = context.createGain();
      sink.gain.value = 0;
      processor.onaudioprocess = (event) => {
        if (socket.current?.readyState !== WebSocket.OPEN) return;
        const encoded = pcm16(event.inputBuffer.getChannelData(0), sampleRate);
        socket.current.send(encoded.buffer);
      };
      source.connect(processor);
      processor.connect(sink);
      sink.connect(context.destination);
      capture.current = { context, stream, source, processor, sink };
      setMicActive(true);
      if (socket.current?.readyState === WebSocket.OPEN) socket.current.send(JSON.stringify({ type: "mute", muted: false }));
    } catch (reason) {
      // Release whatever was opened so the browser's recording indicator turns off.
      stream?.getTracks().forEach((track) => track.stop());
      await context?.close().catch(() => undefined);
      setError(reason instanceof Error ? reason.message : "Microphone access was denied.");
    } finally {
      startingMic.current = false;
    }
  }, [ensurePlayback]);

  useEffect(() => () => { void stopMic(); void playback.current?.close(); }, [stopMic]);

  return { state, messages, transcript, progress, error, micActive, sendText, startMic, stopMic };
}

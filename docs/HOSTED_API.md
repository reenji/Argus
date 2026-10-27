# Hosted API errors

How the FastAPI service (`api/server.py`) reports failures to clients.

## HTTP

Errors use FastAPI's `{"detail": ...}` body. Most `detail` values are a
message string; `/chat` failures from Gemini use `{"code", "message"}`:

| Status | `code` | Meaning |
|---|---|---|
| 409 | `gemini_key_rejected` | Gemini rejected the saved API key. |
| 429 | `gemini_quota_exceeded` | The key's Gemini quota is used up (`Retry-After` is set). |
| 503 | `gemini_unavailable` | Gemini returned a server error or could not be reached. |
| 504 | `gemini_timeout` | Gemini did not answer within `ARGUS_CHAT_TIMEOUT_SECONDS`. |
| 502 | `gemini_failed` | Any other Gemini failure; details are only in the server log. |

Rate-limited requests answer 429 with a `Retry-After` header. Unexpected
server errors answer 500 with `{"code": "internal_error", "message": ...}`;
the stack trace is only in the server log.

## Live WebSocket (`/ws`)

Problems with a single frame produce an event and the session continues:

```json
{"type": "error", "code": "invalid_audio", "message": "Audio data must be base64 text."}
```

| `code` | Cause |
|---|---|
| `invalid_frame` | A text frame that is not a JSON object. |
| `invalid_audio` | Audio `data` that is not base64 text. |
| `audio_too_large` | An audio chunk over 64 KiB. |
| `text_too_long` | A text message over 12000 characters. |
| `unknown_event` | An unsupported `type`. |
| `rate_limited` | Too many text messages; wait and resend. |

When the server refuses or ends a session it sends an `error` event first
(except on restart) and then closes the socket with one of these codes. Each
account has one live session at a time:

| Close code | `code` | Client should |
|---|---|---|
| 4401 | `unauthorized` | Sign in again; do not reconnect with the same token. |
| 4403 | `gemini_key_required` | Ask the user to add a Gemini API key. |
| 4409 | `session_replaced` | Stop; the same account opened ARGUS in another window. |
| 4429 | `rate_limited` | Reconnect after `retry_after` seconds. |
| 1012 | — | The server is restarting; reconnect shortly. |
| 1000 | `internal_error` | Reconnect; the failure is in the server log. |

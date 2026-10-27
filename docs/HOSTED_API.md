# Hosted API

How the FastAPI service (`api/server.py`) authenticates clients, reports
failures and runs in production.

Endpoints: `POST /auth/signup`, `POST /auth/login`, `GET /auth/me`,
`POST /auth/logout`, `POST|DELETE /me/gemini-key`, `GET /status`, `GET /actions`,
`POST /chat`, `GET /health` and the live WebSocket `/ws`. Authenticated routes
take `Authorization: Bearer <token>`.

## HTTP

Every error answers with the same body:

```json
{"detail": {"code": "gemini_key_required", "message": "Add a Gemini API key before starting ARGUS"}}
```

Validation errors also list the offending body fields in `detail.fields`.

| Status | `code` | Meaning |
|---|---|---|
| 401 | `unauthorized` | Missing, invalid, expired or revoked (after logout) token. |
| 401 | `invalid_credentials` | Wrong email or password. |
| 409 | `account_exists` | Signup with an email that already has an account. |
| 409 | `gemini_key_required` | `/chat` without a saved Gemini key. |
| 409 | `gemini_key_rejected` | Gemini rejected the saved API key. |
| 422 | `invalid_request` | The body failed validation; see `fields`. |
| 422 | `gemini_key_invalid` | The submitted key is malformed or Gemini rejected it. |
| 429 | `rate_limited` | Our own request limits; `Retry-After` is set. |
| 429 | `gemini_quota_exceeded` | The key's Gemini quota is used up; `Retry-After` is set. |
| 502 | `gemini_empty_response` | Gemini answered with no text. |
| 502 | `gemini_failed` | Any other Gemini failure; details are only in the server log. |
| 503 | `gemini_unavailable` | Gemini returned a server error or could not be reached. |
| 504 | `gemini_timeout` | Gemini did not answer within `ARGUS_CHAT_TIMEOUT_SECONDS`. |
| 500 | `internal_error` | Unexpected server error; the stack trace is only in the server log. |

## Live WebSocket (`/ws`)

Browsers cannot set headers on a WebSocket, so the token travels as a
subprotocol next to `argus.v1`, which the server selects:

```js
new WebSocket(`${API}/ws`, ["argus.v1", `bearer.${token}`]);
```

Non-browser clients may send `Authorization: Bearer <token>` instead. Tokens in
the query string are not accepted.

Problems with a single frame produce an event and the session continues:

```json
{"type": "error", "code": "invalid_audio", "message": "Audio data must be base64 text."}
```

| `code` | Cause |
|---|---|
| `invalid_frame` | A text frame that is not a JSON object, empty text, or a non-boolean `muted`. |
| `not_ready` | Text sent before the engine connected to Gemini; resend shortly. |
| `invalid_audio` | Audio `data` that is not base64 text. |
| `audio_too_large` | An audio chunk over 64 KiB. |
| `text_too_long` | A text message over 12000 characters. |
| `unknown_event` | An unsupported `type`. |
| `rate_limited` | Too many text messages; wait and resend. |

When the server refuses or ends a session it sends an `error` event first
(except on server shutdown) and then closes the socket with one of these
codes. Each account has one live session at a time on a server instance:

| Close code | `code` | Client should |
|---|---|---|
| 4401 | `unauthorized` | Sign in again; sent for a bad token and after logout. |
| 4403 | `gemini_key_required`, `gemini_key_rejected` | Ask the user to add or replace their Gemini API key. |
| 4409 | `session_replaced` | Stop; the same account opened ARGUS in another window. |
| 4429 | `rate_limited`, `gemini_quota_exceeded` | Reconnect after `retry_after` seconds (60 when absent). |
| 4000 | `session_ended` | Stop; ARGUS ended the session (for example, the user asked it to quit). |
| 1011 | `live_unavailable` | The engine failed; reconnect with backoff. |
| 1012 | `session_restarted` or none | Reconnect shortly; the key changed or the server is restarting. |
| 1000 | `internal_error` or none | Without an error event this is a normal close (the client sent `close`); with `internal_error`, reconnect. |

## Tools in the hosted app

The hosted engine runs with `cloud_safe=True` and offers only tools that do not
touch the server's files, desktop or network on the user's behalf:

| Tool | Hosted restrictions |
|---|---|
| `web_search` | Uses the user's own Gemini key. |
| `code_generator` | Returns code as text; nothing is written to disk. |
| `deep_research` | Runs in the background; reports can be read aloud but not saved (`output_path` is not accepted). |
| `create_presentation` | Runs in the background; source files, source URLs, templates, `output_path` and `open_after_create` are not accepted. |

Email, flights, YouTube and every computer-control tool are desktop-only. Tools
never fall back to the operator's `GEMINI_API_KEY` for a signed-in user, and
tool arguments are not written to the server log.

## Scaling

Run **one API process on one machine**. The registry of live sessions (one per
account, `session_replaced`, `/status`), the task queue and pending research
and presentation results live in that process's memory; with several machines
or uvicorn workers a second window would not replace the first and results
could be looked up on the wrong instance. `scripts/start_web_api.sh` starts a
single worker; on Fly keep `fly scale count 1`. Rate limits are already shared
through Redis.

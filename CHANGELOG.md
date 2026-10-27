# Changelog

All notable changes are recorded here. Versions follow Semantic Versioning.

## [Unreleased]

### Changed

- The live WebSocket takes the token as a `bearer.<token>` subprotocol next to
  `argus.v1`; tokens in the query string are no longer accepted.
- Every hosted API error answers `{"detail": {"code", "message"}}`; validation
  errors also list `fields`. See `docs/HOSTED_API.md`.
- Logout revokes every token of the account (`users.session_version`,
  migration `20261026_0002`) and closes the live session.
- Email, flights and YouTube are desktop-only; hosted presentation and
  research tools no longer accept server paths, URLs or visible mode.
- Production requires Redis, 32+ character distinct secrets and https
  `CORS_ORIGINS`; rate limits read the client address from `CLIENT_IP_HEADER`
  or `TRUSTED_PROXY_HOPS`.
- Dev start-up runs the Alembic migrations instead of `create_all`.

### Added

- `ARGUS_CHAT_TIMEOUT_SECONDS` and Gemini error codes for `/chat`.
- Live close codes 4000, 4401, 4403, 4409, 4429, 1011 and 1012, with an error
  event explaining each.
- Per-account cap on failed logins and per-address signup limits.
- Retention indexes (migration `20261027_0003`).

### Fixed

- Assistant messages sent over the hosted WebSocket and saved to chat history
  no longer lose their first character.
- The backend CI job runs its tests (it failed importing PortAudio since the
  first commit).
- Malformed live frames, a full audio queue or a failing engine no longer hang
  or silently kill the session; reconnects to Gemini back off.
- Sign-in, scrypt and database work run off the event loop.
- Concurrent saves no longer fail on unique constraints, and hosted memory
  keeps entry dates and concurrent updates.
- The web client returns to sign-in on a revoked session, offers to replace
  the Gemini key, reconnects with backoff and releases the microphone.
- Next.js updated to 16.4.3 for GHSA-2464-fhr4-w9xw, GHSA-673q-mjm6-r5xr and
  GHSA-p3m5-59mp-jv5r.

## [0.1.0] - 2026-10-02

- Establish the initial Argus version and rename the desktop, web client, CLI,
  configuration, and documentation.
- Configure Windows, macOS, and Linux desktop packaging from tagged builds.
- Keep source installation available alongside binary releases.

This entry describes the initial project version. A GitHub release is created
only after the `v0.1.0` tag is pushed and the release workflow succeeds.

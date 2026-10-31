---
name: verify
description: Verify that a change to Argus really works before claiming completion — runs the same backend and web checks CI runs and reports only what was actually proven.
---

# Verify

Use this skill when a feature, fix, or refactor needs evidence that it works.

## Goal
Turn "it should work" into concrete evidence.

## Workflow
1. Name the exact behavior that must be proven.
2. Prefer existing tests first (`tests/`), then add the narrowest test that is missing.
3. Run the checks below that cover the files you touched.
4. If automation is not enough, describe the manual steps and gather observable evidence.
5. Report only what was actually verified.

## Argus checks (mirror `.github/workflows/ci.yml`)

Backend — Python 3.11+, SQLite and in-memory rate limits unless `DATABASE_URL` / `REDIS_URL` are set:

```sh
pip install -r requirements.txt
alembic upgrade head
xvfb-run -a python -m unittest -v \
  tests.test_phase1_decoupling tests.test_hosted_api tests.test_core_resilience \
  tests.test_qa_system tests.test_api_key_validation tests.test_action_helpers \
  tests.test_cloud_tools tests.test_live_engine tests.test_data_layer \
  tests.test_tenant_isolation
```

Desktop modules need PortAudio, an X display and Qt's EGL runtime just to
import; without `xvfb-run` and those libraries, run a single module
(`python -m unittest -v tests.test_<area>`) and say which ones were skipped.

Web (`web/`):

```sh
cd web && npm ci && npm run typecheck && npm run lint && npm run build
```

Order: existing tests → typecheck/build → narrow direct commands → manual validation.

## Rules
- Do not say a change is complete without evidence.
- If a check fails, include the failure clearly.
- Changes to tenant isolation, auth, secrets or the live audio protocol need the matching test module green (`test_tenant_isolation`, `test_hosted_api`, `test_live_engine`).
- If no realistic verification path exists (hardware, Gemini quota, real microphone), say so instead of bluffing.
- Prefer concise evidence over noisy logs.

## Output
- What was verified
- Which commands/tests were run
- What passed
- What failed or remains unverified

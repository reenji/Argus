---
name: debug
description: Diagnose a failing Argus behavior (desktop app, FastAPI service, web client, Gemini Live session) from logs, tests and a focused reproduction before proposing a fix.
---

# Debug

Use this skill when something in Argus is broken or behaving confusingly.

## Goal
Find the real failure signal quickly and name the smallest corrective step.

## Workflow
1. Read the issue description carefully and decide which surface fails: desktop (`main.py`, `ui.py`, `actions/`), agent loop (`agent/`), hosted API (`api/`), or web client (`web/`).
2. Inspect the most relevant evidence first: the failing test or command, tracebacks, API error envelopes (`api/errors.py`), and Gemini errors (`api/gemini_errors.py`).
3. Reproduce narrowly — a failing unit test in `tests/` beats a theory.
4. Separate symptoms from root cause.
5. Recommend the smallest next fix or verification step.

## Rules
- Prefer real evidence over guesses.
- If the cause is external (Gemini quota, missing system library, network policy), say so plainly instead of patching around it.
- Do not prescribe broad rewrites before isolating the failure.
- Tag temporary debug output `[DEBUG-<4hex>]` so cleanup is a single grep.
- Redact API keys, tokens and user data from logs before they leave the session.
- A bug fix lands with the test that reproduces it (see `tdd`).

## Output
- Observed failure
- Root-cause hypothesis
- Evidence for that hypothesis
- Smallest next action

---
name: review
description: Evaluate a finished Argus diff for defects, risk and simplification before it ships — correctness first, then security/tenant isolation, then reuse; findings ranked by severity.
---

# Review

Use this skill to evaluate work that already exists. Review never authors the
change it is judging.

## Goal
Find what is actually wrong, ranked by severity, with enough detail to act on.

## Workflow
1. Establish what changed (`git diff origin/main...HEAD`) and what it was meant to do.
2. Read the change against that intent.
3. Check correctness first, then risk, then simplification.
4. Verify each candidate finding before reporting it.
5. Report findings most-severe first.

## What to check
- **Correctness** — logic defects, edge cases, error paths, asyncio/thread interaction (blocking calls on the event loop)
- **Risk** — tenant isolation, auth, secret handling (`core/secret_store.py`, `api/secret_service.py`), destructive desktop actions, data integrity
- **Contract** — API error envelope (`api/errors.py`) and the live audio protocol stay compatible with `web/`
- **Reuse** — existing utilities or patterns the change should have used
- **Simplification** — code that could be deleted or collapsed
- **Coverage** — behavior that ships untested

## Two axes for large diffs
Review a substantial diff in two separate passes and report them separately:
- **Standards** — against `CONTRIBUTING.md`, `SECURITY.md`, `DESIGN.md` and existing conventions; skip what tooling already enforces.
- **Intent** — against the task or issue: requirements missing or partial, behavior nobody asked for.

A small diff stays one pass.

## Rules
- Verify before reporting. A plausible finding that does not reproduce is noise.
- State severity honestly; do not pad the list.
- "No findings" is a valid result.
- Advisory by default; security and destructive-operation concerns are stated as blocking.

## Output
- Findings, most-severe first, each with file, line and a concrete failure scenario
- What was checked and found clean
- Anything that could not be assessed

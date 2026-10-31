---
name: execute
description: Carry an agreed Argus task through to working, verified code — small reversible diffs, existing patterns reused, evidence collected with the verify skill.
---

# Execute

Use this skill when the work is understood and the job is to build it.

## Goal
Take a task from agreed intent to working code, with evidence that it works.

## Workflow
1. Confirm the task is clear enough to build. If it is not, ask or research first.
2. Break the work into independent units; run genuinely independent units in parallel.
3. Implement the smallest correct change per unit, reusing existing utilities and patterns.
4. Verify as you go, not only at the end (`verify`).
5. Report what changed, what was verified, and what remains.

## Rules
- Prefer deletion over addition when behavior is preserved.
- Do not add dependencies (`requirements.txt`, `web/package.json`) without an explicit request.
- Keep diffs small and reversible — one feature or fix per PR (`CONTRIBUTING.md`).
- Hosted code paths must stay tenant-scoped: never fall back to shared local files when a request has no user (see `docs/HOSTED_API.md`).
- Schema changes go through an Alembic migration in `alembic/`.
- User-visible changes update `README.md` / `README.pt-BR.md` or `docs/`.
- No workarounds: a skipped check, hard-coded value or manual step is fixed or flagged before more work lands on top of it.
- Placeholder TODOs, skipped tests and stub tests are blockers, not progress.
- Authoring and approval are separate passes — hand off to `review` or `verify`, do not self-approve.

## Completion
Before claiming done:
- No pending units
- Tests pass, or failures are reported plainly
- Verification evidence collected

## Output
- Files changed
- What was implemented
- Evidence it works
- What is still open

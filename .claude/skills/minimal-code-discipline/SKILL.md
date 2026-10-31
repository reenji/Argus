---
name: minimal-code-discipline
description: YAGNI-ladder discipline for Argus changes — existence first, reuse before writing, standard library before new dependencies, shortest correct diff, without minimizing away validation, security or tenant isolation.
---

# Minimal Code Discipline

Apply while planning and writing code to keep diffs small and obviously correct.

## When to use
- The user asks for a minimal, lean or smallest-possible change
- A plan or change is growing beyond the stated request
- New code where reinvented helpers or speculative generality are likely

Do not use when the user explicitly asks for a broad build, or when minimizing would touch the non-negotiables.

## The discipline
- **Existence first.** Skip work that only serves a speculative future need.
- **Reuse before writing.** Search `core/`, `api/`, `actions/` and `web/src/` for an existing helper before writing one; never copy one that lives a few files away.
- **Dependency ladder.** Standard library → platform capability → an already-installed dependency → hand-written code. No new dependency without approval.
- **Understand before minimizing.** Follow the execution path first, then ship the shortest correct diff.
- **Boring over clever.**
- **Mark the ceiling.** A deliberate simplification gets a short comment naming the limit and what would justify replacing it.
- **Root cause, not symptoms.** Fix the shared cause, not each caller.

## Non-negotiables
Never minimize away:
- validation where a trust boundary is crossed (HTTP, WebSocket, desktop actions)
- per-user isolation in hosted code paths
- error handling that guards against data loss
- security controls and secret handling
- accessibility fundamentals in `web/` and the desktop UI
- scope the user explicitly requested

## Before reporting completion
- Every added line earns its place
- The diff is the shortest one that solves the stated problem
- Non-negotiables are intact
- Tests still pass (`verify`)

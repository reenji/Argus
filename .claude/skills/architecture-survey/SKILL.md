---
name: architecture-survey
description: Read-only survey of where Argus is getting harder to change — ranked deepening candidates (shallow modules, single-caller seams, logic behind the wrong boundary) with evidence. Never edits code.
argument-hint: "[optional directory or area to survey]"
disable-model-invocation: true
---

# Architecture Survey

Find where the repo is getting harder to change, report it with evidence, and stop.

## When to survey
- After a batch of PRs lands.
- When edits start touching more files than they should, interfaces grow for one caller, or unrelated tests must change in lockstep.

An optional argument narrows the survey to a directory; otherwise survey the whole repo.

## The survey
1. Read the repo's principles: `DESIGN.md`, `PRODUCT.md`, `docs/HOSTED_API.md`, `SECURITY.md`.
2. Read a good stretch of `git log` and let the areas that keep changing steer the walk.
3. Walk the module graph — `main.py`/`ui.py`, `agent/`, `actions/`, `core/`, `memory/`, `api/`, `web/src/` — and look for:
   - **Shallow modules** — wide interface, thin behavior; callers know more than the module hides.
   - **Hypothetical seams** — a boundary crossed by exactly one adapter with no second caller.
   - **Logic behind the wrong seam** — behavior living on the far side of a boundary that does not own its data (e.g. desktop-only assumptions inside hosted code).

Apply the **demolition test**: if the module were removed, would its complexity vanish (pass-through) or reappear across its callers (load-bearing)? Only load-bearing shallowness is a finding.

## The report
Rank candidates by leverage against risk. Each carries:
- **Evidence** — file:line for the interface, its callers and the behavior
- **The deepening move** — one sentence
- **Risk** — what the move touches and what could break
- **Severity / confidence / actionable** — survey findings are heuristic, so confidence is low by default

End with the **top recommendation**: the one candidate to deepen first, and why.

## Non-goals
- No code edits, not even "while it's fresh".
- Not a gate; nothing blocks on the report.

Done when the report exists with evidence, ranking and risk for every finding, and no file was modified.

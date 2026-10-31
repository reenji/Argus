---
name: research
description: Investigate an open question about Argus or a dependency (Gemini, FastAPI, Next.js, PyQt) and return grounded, sourced findings without changing code.
---

# Research

Use this skill when the next step depends on something not yet known.
Research answers questions; it does not implement.

## Goal
Replace assumptions with evidence, and say plainly what remains uncertain.

## Workflow
1. State the question precisely enough to know when it is answered.
2. Search the repo and its docs first (`README.md`, `docs/`, `DESIGN.md`, `PRODUCT.md`, `SECURITY.md`) — local evidence outranks recollection.
3. For external SDKs and APIs, consult official documentation.
4. Sweep more than one way when the answer could hide: by file, by symbol, by caller, by git history.
5. Synthesize findings, each tied to where it came from.

## Scale
- **Narrow lookup** — answer it directly.
- **Several independent questions** — investigate in parallel.
- **Unknown-size discovery** — keep going until more passes surface nothing new.

## Rules
- Cite the source: file and line, or the document consulted.
- Distinguish what was verified from what was inferred.
- Report contradicting evidence rather than picking the tidier story.
- Do not implement as a side effect of researching.

## Output
- The question
- Findings, each with its source
- What remains unknown or unverifiable
- Recommended next step, if one follows

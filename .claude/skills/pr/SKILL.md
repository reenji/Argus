---
name: pr
description: Draft an Argus pull request body from evidence already collected — one-line claim with the smallest visual that proves it, before/after checks from verify, and a reversibility note.
---

# PR Body

The PR body is the one artifact a reviewer outside the session reads. Assemble
it from what was already established; add nothing new.

## Template

```markdown
## Summary
<one-line claim, then the smallest visual that proves it>

## Evidence
- **Before:** <failing check or output>
  **After:** <passing check or output>

## Reversibility
<Rollback: cheap via <mechanism> | expensive because <reason>>
<Blast radius: one line>
```

## Summary
One sentence, then the smallest view that makes the point:
- logic → pseudocode
- control flow → call tree
- UI structure → component tree
- broad refactor → shallow file tree
- data flow between desktop, API and web → Mermaid diagram
- the delta itself → a diff shaped like the change

One visual usually suffices.

## Evidence
Quote the `verify` output: the exact check that failed before and passes after.
For UI changes prefer a screenshot. Never claim evidence that was not produced.

## Reversibility
Ask: hard to reverse? surprising without context? a real trade-off? All no →
cheap rollback (revert the merge). Any yes → say why. Database migrations,
stored-data format changes and deploy config (`fly.toml`, `render.yaml`,
`web/vercel.json`) are usually one-way doors — say so explicitly.

## Output
- The PR body, ready to paste
- Pointers to the evidence it relies on

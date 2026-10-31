---
name: tdd
description: Test-first work on Argus — one failing test, one implementation, repeat; expected values from an independent source; substitutes only at agreed boundaries (Gemini, network, desktop I/O).
---

# TDD

Red-green in small steps, at seams agreed with the user before the first test exists.

## The loop
1. Write the next test at a seam (`tests/test_<area>.py`, `unittest`). Run it. Watch it fail for the reason you expect — a test that cannot fail is not a test.
2. Implement the smallest change that turns it green.
3. Repeat. Each test is a narrow but complete path through the behavior, not a layer finished in isolation.

## Rules
- Expected values come from an independent source: a spec line, a documented output, a worked example — never from the implementation under test.
- Substitute only at the seam's boundary: the Gemini client, the network, the database URL, audio and screen devices. No mocks inside the code the test exercises.
- Refactoring is not part of the loop; do it after green, in review.
- A bug fix starts with the failing test that reproduces it.
- When proposing a seam, say in one line what it catches and what it lets through.

## When no seam fits
If the behavior cannot be tested at any agreed seam, stop and report the missing seam as a finding instead of testing through internals.

## Output
- The seams used, with what each catches and misses
- Red/green evidence — the failing run and the passing run
- Any missing-seam findings

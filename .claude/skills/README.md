# Argus development skills

Claude Code skills for working on this repository. They load automatically in
Claude Code sessions opened in the repo; invoke one with `/<name>` or let the
model pick it from its description.

| Skill | Use it to |
|-------|-----------|
| `execute` | Carry an agreed task through to working, verified code |
| `verify` | Prove a change works, with the same checks CI runs |
| `debug` | Find the real failure signal and the smallest next fix |
| `research` | Answer an open question with sourced findings, no code changes |
| `tdd` | Red/green test-first work at agreed seams |
| `review` | Evaluate a finished diff for defects, risk and simplification |
| `minimal-code-discipline` | Keep a change to the shortest correct diff |
| `pr` | Draft a PR body from the evidence already collected |
| `architecture-survey` | Report where the code is getting harder to change (read-only) |

Adapted from [oh-my-claudecode](https://github.com/Yeachan-Heo/oh-my-claudecode)
(MIT, see `LICENSE-oh-my-claudecode`). The originals depend on the OMC runtime
(`omc` CLI, `.omc/` state, launch pipeline); these versions drop that coupling
and point at Argus's own checks and docs.

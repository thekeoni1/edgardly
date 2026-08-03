# Edgardly v2 progress

Running state for the v2 build. docs/V2_PLAN.md is the plan and the single source of truth.
docs/SESSIONS.md holds the session prompts. This file records what actually happened.

## Decisions log

Settled decisions. A later session should not re-litigate these; if one turns out to be
wrong, change it here with a dated note saying why.

| Date | Decision | Detail |
| --- | --- | --- |
| 2026-08-03 | Plug rows are explicit derived formulas | Where tagged components do not sum to the reported total, the scaffold writes a visible plug row such as "Other current assets (plug to reported total)" as a live Excel formula. Never a filled number, never a silent guess. Any plug whose absolute value exceeds 10 percent of its statement total raises a flag saying this filer's XBRL is too sparse for a reliable scaffold. |
| 2026-08-03 | Test suite is restored to the public repo | Commit 4e1d457 removed app/tests and app/pytest.ini in June 2026 with no stated rationale, and git history was the only surviving copy. Every later phase is gated on tests, so the suite lives with the code. |

## Session log

One entry per work session. Record what shipped, the xfail count after the session, and any
open questions the next session needs to know about.

| Date | Session | Shipped | xfails | Open questions |
| --- | --- | --- | --- | --- |
| 2026-08-03 | Setup | Folded the planning output into the repo: risk register R1 through R10 as V2_PLAN Part 8, decisions log as Part 9, tasks 2.2b and 2.5 added to Phase 2, docs/SESSIONS.md created, this file created. Documentation only, no code changes. | n/a | None |

## Open questions

Nothing outstanding.

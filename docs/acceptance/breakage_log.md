# Scaffold breakage log

Everything the acceptance hand-check turns up, one row each, written down before
anybody decides whether it matters. A discrepancy that looks harmless at the
time it is found is exactly the kind that turns out not to be, and the log costs
one line.

Each entry ends in one of two states, and no third:

- **Fixed.** The code was wrong and now is not. The fix commit goes in the last
  column.
- **Flagged blank.** Edgardly cannot stand behind the value, so the cell shows
  as missing with the flag message and a pointer to the filing to check. This is
  a legitimate outcome, not a failure to fix something: a number nobody can
  source is worse than an admitted hole. The root cause column says why.

An entry that is neither is open, and a checklist copy with an open entry
against it is not signed off. Phase 2 is done when all three copies are signed
and this table has no open rows. An empty table is a legitimate final state and
means the hand-check found nothing, which is worth recording as such rather than
leaving the file absent.

| Date | Company | Sheet and cell | Expected | Got | Root cause | Fix commit or flag |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |

## Status

No entries yet. The hand-check has not been run.

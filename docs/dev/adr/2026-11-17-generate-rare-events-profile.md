# The rare_events profile: a row floor, cases on several rows and operations that read the row

Date: 2026-11-17. Status: accepted by the maintainer (plan Insurance V2, lot 3, Q1).

## Context

`rare_events` injects cases that must stay rare in the file: a key reused once, five future
birth dates, 500 agency codes of another branch. Counts are absolute, so a small file turns
"rare" into "frequent". Three of the report's cases cannot be written with the operations that
exist: a key reused on a second row (the case spans two rows), a postal code of another
province (the new value depends on the row) and a boundary value copied from another cell.

## Decision

- **Floor.** A scenario profile may declare `min_rows`; `build_generate_plan` refuses fewer
  rows than the floor, naming the profile, the floor and the request. The floor is validated
  at load (scenario profiles only, at least the largest count) and cannot be overridden.
  `rare_events` declares 100,000.
- **Multi-row cases.** `reuse_value` copies the clean value of one of the 1,000 rows before the
  changed row. `AnomalyEvent.related_row` carries that row; the truth writes two `relational`
  lines sharing `group_id` `<scenario>-<first row>`, and checks on the altered file that both
  cells are still equal. Metrics count cases, not rows (`applied_cases` against
  `rows_touched`), and the probability of absence of such a scenario is `null` with the reason
  `multi_row_case`, because the formula counts single-row cases.
- **Row-aware values.** A `format` value that needs the row (`postal_other_province`) is
  supplied by the package through `inject_anomalies(contextual=)`, like `canonical`. The engine
  stays free of any Insurance table; a package that supplies none refuses the value. The value
  is allowed for scenario profiles of Insurance only.
- **Kinds.** `reuse_value` and `copy_column` are scenario-profile kinds: refused in a legacy
  profile and absent from the kinds that the Computer validator accepts.
- **Valid atypical.** A `valid_atypical` scenario must declare severity `info` and detection
  `none`; its changed cells also get `valid_atypical` truth lines. It writes real events (the
  clean file keeps no exception to its rules), so the boundary cases of `rare_events` are
  injected, and their truth says they are not defects.
- **Probability.** Computed exactly with integers and rounded once (`generate_rarity`), for the
  actual number of rows; never copied from the report's table, which holds for 500,000 rows.

## Consequences

- `generation_version` is 2: `metrics.json` and `truth.csv` change for the same inputs.
- A reuse case needs both cells left as the operation wrote them: a profile that overlaps another
  scenario on the same cell fails with a message instead of describing a case that is not there.
- The boundary cases only use today's catalogue (M01, M02); lot 6 completes them with the
  rules it adds, and may need to restrict them (a contract that ends the day it starts may
  carry a claim after its end).
- Contract: `docs/dev/generate/insurance-v2.md` sections 6.1 to 6.4.

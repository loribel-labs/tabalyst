# Generate scenarios overlap only when they say so

Date: 2026-11-16. Status: accepted by the maintainer (plan Insurance V2, D7, amended).

## Context

The plan said that injection operations never overlap and that only the new profiles would
allow it. Measured on the current engine, the statement holds only for operations with an
absolute `count`: `_choose_rows` reserves their rows, so no two of them share a row. Operations
with `rate` select their rows independently. On `dirty_realistic` (3,000 rows, seed 42) 618
events fall on 574 rows and 44 rows carry several events; `test_generate_insurance.py` pins
`events == affected_rows + 44`. The report asks for explicit multiple anomalies (C01 to C04),
and an overlap that is neither requested nor labelled would make the ground truth ambiguous.

## Decision

- Legacy profiles keep their behavior byte for byte, overlap of `rate` operations included.
- A profile is a V2 profile when its operations declare `scenario_id`. A V2 profile uses `count`
  only and refuses `rate`; a mix of V2 and legacy operations is refused.
- In a V2 profile two operations never share a row by default. Both must declare
  `can_overlap: true` to share one, and `conflicts_with` (a list of scenario ids, symmetric)
  forbids it even then. `requires` lists columns that the output profile must provide: a
  scenario that cannot apply is refused, not skipped.
- Selection stays sequential in profile order. Streams of a V2 profile are keyed by
  `scenario_id` and the rank of the operation in the scenario, not by position, so adding a
  scenario at the end never changes the earlier ones. Inserting one does, and the profile
  order is part of the profile.
- With overlap, the second operation reads the row as the first left it (C02, C03, C04); the
  journal keeps both events in application order.

## Consequences

- The rule of the plan ("never two defects on one row") is true for V2 profiles and is not
  claimed for legacy ones.
- `_choose_rows` has to track claims per scenario instead of one global bytearray, with a
  memory bound of one byte per row per scenario that takes part in an overlap relation.
- `net_difference` and `injected` truth lines can differ (a change undone by a later one),
  which is intended.
- Contract: `docs/dev/generate/insurance-v2.md` section 4. Lot 1 implements and tests it.

# Near-uniqueness is a separate non-binding reading with a tolerance that grows with the square root

Date: 2026-10-24 (lot 9 of the Unique ID plan)

## Context

After row deduplication an identifier can still repeat a few times between distinct records. The
specification (cahier 13) rules out a fixed share: 1 % of 10,000 values and 1 % of a million are not the same
situation. It forbids creating a role `identifier/unique_id` from a percentage below 100 %, and forbids hiding a
residual anomaly because it is statistically rare. It proposes the family `min(p*N, a*sqrt(N), K)` without
coefficients. No real file exists in the lab to calibrate them on (only 100-row samples and recipes).

## Decision

- A separate member `near_unique` of `identifier_uniqueness`, filled only for `repeated_between_distinct_records`
  with a `complete` status. `unique`, `interpretation` and the classification do not change.
- Tolerance `T(U) = min(U // 100, isqrt(U), 1000)` on the distinct rows `U`, integers only; `R_residual <= T` is
  `near_unique`; below 100 distinct rows the signal is `population_too_small`. Fixed constants, no configuration:
  chosen by the maintainer (24 October 2026) as provisional, versioned by `NEAR_UNIQUE_VERSION`.
- Shown on the column page only, always with the sentence that it is no guarantee.

## Consequences

- A change of constant is a version bump of the model, not of the rule or of the Report revision (unpublished 5).
- The number of distinct repeated IDs and the concentration of the repetitions are not part of the reading:
  they need per-ID frequencies among the distinct rows, which no analysis holds today.
- Calibration on real files is open; a configuration surface would wait for it.
- Rejected: a fixed percentage (not a definition of rarity), a configurable model before any calibration, and a
  signal without a floor of population.

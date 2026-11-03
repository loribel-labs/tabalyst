# Stratified minimum of one row and the stratified-balanced method

Date: 2026-11-03. Status: accepted by the maintainer (specification
"Tabalyst Sample - Cahier des charges Stratified").

## Context

Until 0.7.3 `stratified` allocated rows by the largest remainder with no
minimum (STRAT-01, design O42): a rare stratum could get no row. The
specification asks for a minimum of one row per stratum and a second method,
a quota per stratum.

## Decision

- `stratified` uses `allocate_strata_with_minimum` (`scanner/stratify.py`): a
  stratum whose exact quota is under one row is held at one, the cost is taken
  from the others in proportion, repeated until stable, then the largest
  remainder with integers only (ties: the key as text). No stratum exceeds its
  population. A size under the number of strata is refused with an `InputError`
  that names the `--rows` needed; nothing is written. This reverses STRAT-01.
- `stratified-balanced` (`--per-value N`, `per_value`) keeps `min(N, N_i)` random
  rows per stratum in one reading, one reservoir of `N` rows per stratum, the
  rows written in file order. `--rows` and `--percent` are refused. The
  `--max-strata` ceiling and the Scan-based advance refusal apply to both.
- The planner advice keeps `uncovered_at_size` (strata beyond the size) and
  `size_for_every_stratum` (now the number of strata), so that the advice and the
  sample keep one rule. `allocate_strata` stays for callers of the classic rule.

## Consequences

- A sample of `stratified` made before this change can differ.
- `stratified` with a size under the strata, accepted before, is now an error.
- Memory of `stratified-balanced` is bounded by `N` times the number of strata,
  at most `--max-strata` strata.

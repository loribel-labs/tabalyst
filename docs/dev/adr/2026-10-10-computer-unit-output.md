# Present Computer measurements with optional localized units

Status: accepted on 2026-10-10 for the development package.

## Context

Computer derives prices and compatibility from numeric component capacities.
Its CSVs currently expose those numbers in named fields such as `memory_gb`.
The example also needs readable values such as `4 GB` and `4 Go`, plus a
measured quality fixture that mixes numeric and unit-bearing cells.

## Decision

Keep catalog capacities and derived values numeric. The Computer exporter
offers an explicit `unit_style: localized` request (CLI `--unit-style`) that
formats a fixed set of physical measures after derivation, per locale. The
default `numeric` preserves the existing output. `unit_columns` selects a
validated subset of measured columns and implies localized output. Separately,
the `unit_variants` anomaly profile adds GB/Go capacities to altered CSVs;
`unit_variants_extended` covers all 14 measures in the extended profile.
Both use the shared mutation pass, with logs and summaries.

## Consequences

Unitized CSV cells are text even when the field name retains a numeric unit
suffix. Callers needing numeric analysis use the default style. EN/FR CSVs
remain row-aligned, while unit suffixes differ by locale. Numeric catalog
references, selection weights, and calculations are unchanged. The explicit
request and anomaly profile keep both output choices reproducible and
auditable.

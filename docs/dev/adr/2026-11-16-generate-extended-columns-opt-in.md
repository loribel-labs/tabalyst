# Insurance gets more columns only through an output profile

Date: 2026-11-16. Status: accepted by the maintainer (plan Insurance V2, D1 and Q4).

## Context

The decision of gate G2a (2026-10-14, `docs/dev/generate/insurance-stress-cases.md` section 6)
kept Insurance at 34 columns and rejected adding columns to the package, because the number is
cited in about thirty places and every benchmark of `docs/dev/scan/benchmarks.md` is measured on
the 34-column file. The Insurance V2 report needs more columns (`date_sinistre`,
`montant_couverture`, `franchise`, `montant_indemnise`, ...) to express non-ambiguous business
rules and ML targets. The stress-case document named a generic output profile for column
packages (its option B) as the way to add columns without moving anything.

## Decision

- The default output stays the 34 columns, byte for byte, for the same seed (D1).
- `--output-profile extended` adds 10 columns after `filiale`: 44 in all. The option exists
  (`compact` for Computer); an unknown value for a package fails. Whether a request file
  can select it is settled at lot 4.
- `extended` is frozen when it is published. Further columns come in a later profile
  (`complete`, tranche B and after), so a given seed and profile never change bytes between
  releases.
- The base row of `InsuranceProvider.row()` is not touched: it draws from one sequential
  stream, so a new draw would shift every value. Each added column draws from its own stream
  after the base row, using only the base row and its own draws. The first 34 columns of an
  extended file equal the default file.
- A column enters a profile only with the rule that constrains it, the scenario that breaks it
  and the tests of both. Rules of the clean file stay strict, without exception (ADR
  2026-11-11).

## Consequences

- This amends decision 1 of gate G2a for opt-in profiles only. The default, the published
  numbers, the benchmarks and the public demo keep 34 columns.
- The injection pass reads the staged clean CSV, so the added columns are eligible for
  operations with no change to the pass.
- Public pages say which profile a statement applies to. Navigation of `tabalyst-studio` and the
  website only advertise what the README documents.
- Contract: `docs/dev/generate/insurance-v2.md` sections 4.4 and 7.

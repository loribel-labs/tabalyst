# Generate keeps the ground truth in files beside changes.csv

Date: 2026-11-16. Status: accepted by the maintainer (plan Insurance V2, D3 to D5 and D11).

## Context

`changes.csv` is the journal of the injection pass: ten fixed columns (`event_id` to `cause`,
plus `class` when a profile declares one) and digests pinned by the tests of the three
existing Insurance profiles. The Insurance V2 report asks for more: the rule a case tests,
its category and severity, its rarity level, a common cause, the canonical value of the cell,
the cells that really differ from the clean file, rule violations that no operation caused,
valid atypical cases and cases visible only across rows. A journal of operations cannot say
those things: it only knows what an operation did.

## Decision

- `changes.csv` is unchanged: no column is added, and legacy profiles write no new file.
- A V2 profile writes `truth.csv`, `rules.json`, `metrics.json` and `manifest.json` beside it
  (and `latent.csv` for the ML profiles), named `<dataset>.<profile>.<role>.<ext>`.
- `truth.csv` has one line per cell or row and per `kind` (injected, net difference, rule
  violation, valid atypical, relational, uncertain), so an evaluation reads the kind it needs.
- The latent scores of the generator (`risque_sinistre` and similar) are never columns of the
  main CSV. They go to `latent.csv`, marked as not an input variable.
- The public repository emits only the reference truth. Scores, comparisons of methods and
  multi-seed experiments live in `tabalyst-lab/benchmarks/` (D3).
- The files carry `format`, `format_version` `0.2.0` and `format_revision` 1, with a JSON
  Schema generated from Pydantic models, like the Dedup report.

## Consequences

- Existing digests, the public demo and the 3,000-row file stay valid: nothing in a legacy
  profile moves.
- The truth is verifiable alone: the rules are data in `rules.json`, evaluated by a pure
  function that the generator also uses to check its own clean file.
- More artifacts per run: atomic publication and collision protection extend to them in
  `_publish_artifacts`.
- Contract: `docs/dev/generate/insurance-v2.md` section 5. Scan and Report do not read these
  files and do not evaluate rules between columns (design, Lot 5).

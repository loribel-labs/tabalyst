---
title: Format of the report of a smart sample
description: What the JSON report written beside a smart sample contains - the plan, the rows chosen, the coverage by family and weighted, the targets missed and why - and how to read it without mistaking it for a guarantee.
---

`tabalyst sample --smart` writes `<stem>.sample.json` beside the
sample. It is the report of what the sample aimed at and what it covers. The
document has `format: "tabalyst.sample"`, `format_version: "0.2.0"` and its own
`format_revision`, which is `1`. The format is experimental while Tabalyst is in
beta. The JSON Schema is `tabalyst/schemas/tabalyst.sample.schema.json`, generated
from the same models as the document.

```console
tabalyst sample customers.csv --smart --rows 1000
```

The command also writes `<stem>.sample.html`, a page rendered from this document
alone. The page is not part of the format: it adds nothing the JSON does not say.

## What it promises, and what it does not

- `coverage.scope` is `target_catalog`: the coverage is that of the targets of
  the plan. A case that no target describes can be missing, and the report does
  not know it.
- The proportions of the sample are not those of the file: rare cases are chosen
  on purpose. Do not estimate the population from it. The `statements` member
  repeats this in codes (`catalog_not_population`, `proportions_not_population`,
  `heuristic_no_optimum`).
- The rows are chosen by a greedy cover of a bounded pool of candidates. The
  coverage is measured, no optimum is promised.

## Members

| Member | Content |
| --- | --- |
| `engine`, `source` | The engine and the source of the [scan](../scan/format.md) the sample stands on, as they were |
| `request` | `method` (`smart`), `rows` (the size asked for, from `--rows` or `--percent`), `percent` when it was given, and the `seed` of the choice |
| `output` | The CSV file written: `name`, `rows` (without the header), `columns`, `encoding`, `delimiter`, and `order: "source"` |
| `run` | `started_at`, `duration_seconds`, `timings` (`reading`, `selection`, `other`), `peak_memory_bytes`, `records_read`, `cells_read`, `source_verified` and `passes` |
| `plan` | The [smart sample plan](../scan/plan.md#smart-sample-plan) the sample followed: targets, weights, sizes, reserve, budget of candidates and the readings announced |
| `selection` | How the rows were found: `rows`, `by_cover`, `by_worst`, `by_reserve`, `shortfall`, the `reserve` and the `pool` |
| `coverage` | What the rows cover, below |
| `statements` | Codes of what a reader must not take the sample for |
| `targets` | One entry for each target of the plan, below |

`run.passes` counts the readings of the source the sample cost: `scan` is true
when no current scan was stored and the file was scanned first, and `total` adds
the selection. The source is verified: its digest, computed while it was read,
is compared with the scan's before anything is written, and a file that changed
leaves no output.

### Selection

`by_cover` rows were chosen to cover targets. `by_worst` rows are the rows that show
the most weight of anomalies at once (at most `smart.worst_rows` of them and a twentieth
of the size), kept even when their targets are covered already. `by_reserve` rows are ordinary rows,
chosen by a seeded hash of their position. `reserve.planned` is the share the plan
granted (20% of the size by default, less when mandatory targets need the room);
`reserve.taken` is what the sample holds, which is more when the targets needed
fewer rows than they were given, and `reserve.adjusted` says so. `shortfall` is
the number of rows missing from the size asked for, when the candidate rows the
budget kept were too few; it is 0 in a normal run.

`pool` tells what the reading held in memory: `per_target` candidates at most for
each target, the `candidate_rows` kept, their `peak_bytes` as source text, the
`budget_bytes` and the `refused_rows` that the budget turned away. A row is kept
whole: the sample never holds a preview or a truncated row.

### Coverage

| Member | Content |
| --- | --- |
| `defined` | The targets of the plan |
| `evaluable` | Those the sample could test on a row. The others are `not_evaluable` (such as a duplicate row, which needs a digest of every row) or `unresolved` |
| `observed` | Evaluable targets that at least one row of the source covers |
| `covered` | Evaluable targets that at least one row of the sample covers |
| `weighted` | `total` and `covered` weights of the evaluable targets, and their `share` |
| `mandatory` | The mandatory targets: `defined`, `covered`, and the ids still `missing` |
| `families` | The same counts for each family of targets |
| `missing` | The heaviest targets not covered, mandatory first, at most 20, each with its `reason`; `missing_total` counts them all |
| `verification` | The targets whose rows the plan counted exactly, against what the reading found |

The reasons a target is not covered are:

- `size`: the sample is too small, and heavier targets took the rows;
- `budget`: the budget of candidate rows turned its rows away;
- `not_observed`: no row of the source covers it. The scan could not always tell:
  a bin of equal width between the minimum and the maximum can be empty.

`verification` is the proof that the tests agree with the scan. For each target
whose frequency the plan holds exactly, the reading counts the rows that cover it.
`checked` targets were compared, `agreed` of them match, and `disagreed` lists the
ids that differ. A difference is a defect to report, not a property of your data.

### Targets

Each entry of `targets` has the `id` of a target of the plan and its `status`:

| Status | Meaning |
| --- | --- |
| `covered` | At least one row of the sample covers it |
| `not_covered` | The sample does not cover it; `reason` says why |
| `not_evaluable` | The sample cannot recognize it on a row; `reason` says why |
| `unresolved` | The plan called it ready, but what it refers to was no longer in the scan |

An entry also gives `observed` (the rows of the source that cover the target),
`candidates` (the rows held for it), and, when the plan counted it exactly,
`expected` and `agrees`.

## Changelog of the format

| Revision | Change |
| --- | --- |
| 1 | First revision, with the version 0.2.0 family: the report of a smart sample (`request`, `output`, `run`, `plan`, `selection`, `coverage`, `statements`, `targets`). It starts the family; breaking changes are allowed during the beta and are recorded here. The embedded plan has the `missing`, `remark` and `character` base weights (`plan.settings.weights.base`) and the `worst_rows` setting, and `selection` has `by_worst`, since the targets of empty cells, remarks, characters and rare values and the worst rows; the revision stays `1` while the family is unreleased. |

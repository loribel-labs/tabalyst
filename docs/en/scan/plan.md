---
title: Plan the analyses a scan could add
description: What tabalyst scan --plan shows, how the planner chooses analyses under a memory budget, the decisions and reasons in a plan, and the Python functions that return it.
---

`tabalyst scan --plan` shows which further analyses would be useful and possible
for a file, what each would cost, and which ones the scan already answers. It
runs none of them and writes nothing beside the source. The plan is experimental
in the beta: the analyses it proposes cannot be run yet, so it shows what a
later release will add.

```console
tabalyst scan customers.csv --plan
```

If the scan of the file stored by Tabalyst is current (same content, settings
and version), only the planning runs. Otherwise the first pass runs and is
stored, as `tabalyst scan` does. The plan goes to standard output; messages go to
standard error.

```text
Plan for basic.csv (plan 84f918d7e204, planner 1).
22 candidates: 5 selected, 16 already answered by the scan, 1 left out.

Selected:
  1. pattern_validation [compiled_matcher]: rows / id (up to 5.0 KiB, CPU low, automatic, not available yet)
  2. pattern_validation [compiled_matcher]: rows / name (up to 5.0 KiB, CPU low, automatic, not available yet)
  3. pattern_validation [compiled_matcher]: rows / amount (up to 5.0 KiB, CPU low, automatic, not available yet)
  4. pattern_validation [compiled_matcher]: rows / notes (up to 5.0 KiB, CPU low, automatic, not available yet)
  5. temporal_distribution [period_counts]: rows / joined (up to 1.7 KiB, CPU very_low, automatic, not available yet)

Not applicable:
  1 x the field mixes types, so a typed analysis would be unreliable

A second reading of the source is needed (30 cells, CPU very_low). Memory: 16.0 MiB to 16.0 MiB, about 16.0 MiB.
The second pass is not available in this version: the plan only shows what it would do.
```

## What the plan contains

The planner looks at the scan, never at the source. For each field it considers
the analyses that concern it:

| Analysis | What it adds |
| --- | --- |
| `exact_frequencies` | The exact count of every distinct value |
| `numeric_histogram` | The spread of the numbers, with exact median and quantiles when the integers have a small range |
| `length_distribution` | The lengths of the text |
| `exact_distinct` | The exact number of distinct values of an identifier-like field |
| `pattern_validation` | The structural patterns counted on every occurrence, not only on a sample of the distinct values |
| `temporal_distribution` | The dates counted by day, month or year |

Each candidate gets one decision:

- **selected**: asked for, or useful and cheap enough to be chosen
  automatically. Selected analyses share one reading of the source.
- **already_satisfied**: the scan already holds the answer, for example an
  enumeration of 17 values whose counts are all listed. It is never run again,
  and the plan says where the answer is.
- **rejected**: not applicable to the field (no values, a mixed type, a sensitive
  field whose values are withheld), of too little benefit, or beyond the memory
  budget. A rejection never says the analysis is impossible.

A plan contains no value from your data, and no date: the same scan gives the
same plan on any machine, whatever the number of workers.

## Memory and cost

Each analysis lists the memory it needs in three cases: at least what the scan
already proves, the likely size, and a firm maximum taken from the counts of
the scan. The budget is charged with the maximum, so a selection never exceeds
it. Memory that several analyses share is counted once, and the reading of the
source is counted once whatever the number of analyses. These figures size the
data structures of the analyses, not the whole process, and are provisional in
the beta.

## Options

`--plan` accepts the options that choose how the file is read (`-c`,
`--delimiter`, `--encoding`, `--collection`, `--workers`, `-q`, `--no-progress`).
It refuses `-o`, `-d`, `--force` and `--counters`, which write.

## Python API

```python
import tabalyst

plan = tabalyst.plan_document("customers.scan.json")
for candidate in plan.candidates:
    print(candidate.id, candidate.selection.state)

scan = tabalyst.scan("customers.csv")
plan = tabalyst.plan_analyses(
    scan,
    requests=[tabalyst.AnalysisRequest("numeric_histogram", field="age")],
)
print(plan.summary.second_pass_required)
```

`tabalyst.plan_analyses(scan)` plans from a scan result in memory.
`tabalyst.plan_document(path)` plans from a scan document; a Report is refused,
because it keeps fewer sample values than its scan. `requests` name analyses to
choose first, and `automatic=False` selects nothing else. A request for an
unknown analysis, dataset or field raises `tabalyst.ConfigurationError`.
`tabalyst.generate_plans(inputs)` plans several sources, as the command does.
`plan.model_dump(mode="json")` gives the plan as JSON.

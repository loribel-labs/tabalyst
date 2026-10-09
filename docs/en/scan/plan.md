---
title: Plan the analyses a scan could add
description: What tabalyst scan --plan shows, how the planner chooses analyses under memory, cell and CPU limits, when a run would ask for a confirmation, the decisions and reasons in a plan, and the Python functions that return it.
---

`tabalyst scan --plan` shows which further analyses would be useful and possible
for a file, what each would cost, and which ones the scan already answers. It
runs none of them and writes nothing beside the source. The plan is experimental
in the beta. Two of the analyses it proposes, the histograms of numeric fields and
the length distribution, can be run with [`tabalyst scan --deep`](deep.md); the
others cannot be run yet, so the plan also shows what a later release will add.

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
  1. pattern_validation [compiled_matcher]: rows / id (up to 6.0 KiB, CPU very_low, automatic, not available yet)
  2. pattern_validation [compiled_matcher]: rows / name (up to 6.0 KiB, CPU very_low, automatic, not available yet)
  3. pattern_validation [compiled_matcher]: rows / amount (up to 6.0 KiB, CPU very_low, automatic, not available yet)
  4. pattern_validation [compiled_matcher]: rows / notes (up to 6.0 KiB, CPU very_low, automatic, not available yet)
  5. temporal_distribution [period_counts]: rows / joined (up to 1.7 KiB, CPU very_low, automatic, not available yet)

Not applicable:
  1 x the field mixes types, so a typed analysis would be unreliable

A second reading of the source is needed (30 cells, CPU very_low). Memory: 24.0 MiB to 24.0 MiB, about 24.0 MiB.
5 of the selected analyses cannot run in this version; tabalyst scan --deep runs the others.
Estimated time: under a second (a guide from the first pass, not a promise).
Running it would not ask for a confirmation.
```

## What the plan contains

The planner looks at the scan, never at the source. For each field it considers
the analyses that concern it:

| Analysis | What it adds |
| --- | --- |
| `exact_frequencies` | The exact count of every distinct value of a field of at most 1,000 values (runs with `--deep`) |
| `numeric_histogram` | The spread of the numbers, with exact median and quantiles when the integers have a small range (runs with `--deep`) |
| `length_distribution` | The lengths of the text (runs with `--deep`) |
| `exact_distinct` | The exact number of distinct values of an identifier-like field (runs with `--deep`) |
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
data structures of the analyses, not the whole process. They come from
measures of the structures Tabalyst uses, so a set of one million 12-character
identifiers is charged about 133 MB, which is why an automatic plan leaves
such exact counts out.

Each analysis and the reading also get a CPU class, `very_low`, `low`,
`moderate` or `high`, from the work they add to each cell. The classes are
measured on the second pass for the histograms and the length distribution; the
other analyses still use estimates that the second pass will replace when they
can run. A counter of integers or a bin costs about 1 microsecond a cell, as much
as the first pass spends on a cell, which is why both are `moderate`.

## Automatic, requested and forced

What the planner chooses by itself stays within limits that keep it cheap:

| Limit | Automatic choice | Requested or forced |
| --- | --- | --- |
| Memory (firm maximum) | 128 MiB | 512 MiB, never exceeded |
| Cells of the reading | 100 million | no limit |
| CPU class | `moderate` at most | no limit |
| Expected benefit | 45 out of 100 at least | only orders the analyses |

The limits count memory in bytes and work in cells, never measured time, so the
same scan gives the same plan on any machine.

`--deep` plans the second pass as if it were forced: every analysis that
applies and fits the 512 MiB budget, whatever the automatic limits.

```console
tabalyst scan customers.csv --plan --deep
```

The selected analyses then say `forced` instead of `automatic`. The plan lists
the analyses that cannot run yet, and says so at the end; `tabalyst scan
--deep` without `--plan` [runs the second pass](deep.md) with those that can.

## Estimated time and confirmation

When a second reading is needed, the plan text ends with an estimated time, as
a range, from how long the first pass took to read the file:

```text
Estimated time: 4 s to 9 s (a guide from the first pass, not a promise).
Running it would ask for a confirmation first: its memory is above what an automatic choice may take.
```

The estimate is a guide: compression, disk cache and the width of the records
change it. It is not part of the plan, which stays the same from one machine to
another. A run would ask for a confirmation before starting when the selection
goes beyond an automatic limit, because it was requested or forced, or when the
upper end of the estimate reaches two minutes. What the planner chooses by
itself never asks. With several files, the text ends with one line for all of
them: the times add up and the memory is the largest.

## Options

`--plan` accepts the options that choose how the file is read (`-c`,
`--delimiter`, `--encoding`, `--collection`, `--workers`, `-q`, `--no-progress`).
It refuses `-o`, `-d`, `--force` and `--counters`, which write.
`--deep` shows the forced plan with `--plan`, and runs the second pass without it.

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
`tabalyst.generate_plans(inputs)` plans several sources, as the command does;
`forced=True` plans a forced second pass, and the result says whether running
the plans together would require a confirmation (`requires_confirmation`).
`plan.model_dump(mode="json")` gives the plan as JSON.

`tabalyst.plan_second_pass(scan)` returns the plan with its estimated time and
whether running it requires a confirmation. It never asks anything and runs
nothing:

```python
second = tabalyst.plan_second_pass(scan, forced=True)
print(second.estimate)
print(second.requires_confirmation, second.confirmation.reasons)
```

The reasons are `memory_over_automatic`, `cells_over_automatic`,
`cpu_over_automatic` and `time_over_threshold`. The number of bins of a
histogram comes from the `deep` settings of a [configuration
file](../reference/configuration.md#deep-settings); `plan_second_pass(scan,
deep=tabalyst.DeepSettings(bins=50))` takes them explicitly. Running a plan is
described in [the second pass](deep.md#python-api).

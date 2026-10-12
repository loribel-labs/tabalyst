---
title: Simple, Clear and Smart
description: Walk through the three steps of Tabalyst Scan on one example file, from a fast scan to a readable report to a smart sample, with the files each step writes.
---

Tabalyst works in three steps, and each one is useful on its own.

| Step | Question it answers | Command | You get |
| --- | --- | --- | --- |
| **Simple** | What does this file contain? | `tabalyst scan` | One JSON document, read once, with bounded memory. |
| **Clear** | What does that mean, and how sure is it? | `tabalyst report` | A report that labels every figure exact, estimated or limited. |
| **Smart** | What should I do next, and what would it cost? | `tabalyst scan --plan`, `--deep`, `tabalyst sample --sample-method smart` | A plan of extra analyses, exact figures, and a small file that still shows every case. |

The examples below use `examples/input/insurance-customers.csv` of the
repository: 3,000 fictional customer and contract records across 34 columns.
Their outputs are in `examples/output/insurance-customers-scan/`.

## Simple: scan the file

```console
tabalyst scan examples/input/insurance-customers.csv -o customers.scan.json
```

The scan reads the file once. It writes `customers.scan.json` and, beside it,
`customers.scan.html`, a page that shows the scan. Pass `--no-html` for the JSON
only. The scan holds, for every column, the counts, the native and inferred types,
the missing values, the distinct values and their exact counts, exact statistics,
the lengths, the patterns found, a sample of whole rows and the observations
about quality.

Without `-o`, the scan is stored in Tabalyst's local storage and reused by the
next command that needs it, as long as the source and the settings have not
changed.

Memory depends on configurable limits, not on the number of rows. Some figures
are limited or estimated because of those limits. Read
[exact, estimated and limited results](../scan/reading-results.md) before you
quote one.

## Clear: read the report

```console
tabalyst report examples/input/insurance-customers.csv
```

The report is an HTML page built from a JSON profile, and it needs nothing else
to be read. Each figure carries its quality: **exact**, **estimated**, **sample**,
**at least** or **not computed**. The page opens with an overview, then one
section per aspect of the data: types, missing values, frequencies, lengths,
patterns, dates, observations, relationships and, when a second pass ran, its
results as insights (units, shape of the numbers, parts of the dates, repeated
values, numbers by category), each figure with its accuracy. See [Read a report](../report/read-report.md).

`tabalyst report` decides by itself whether a second pass is worth its cost
(see Smart, below). It says what it added and what it left out. Pass
`--deep` to force it, or set `deep.mode` to `off` in a configuration file to
never run it.

## Smart: plan the next step

A scan is a first pass: it never reads the file twice. Ask what a second reading
could still add, and what it would cost, without running anything:

```console
tabalyst scan examples/input/insurance-customers.csv --plan
```

```text
Plan for insurance-customers.csv (plan 7a23dae6f250, planner 1).
147 candidates: 43 selected, 70 already answered by the scan, 34 left out.
...
A second reading of the source is needed (102,000 cells, CPU very_low). Memory: 27.6 MiB to 35.1 MiB, about 29.5 MiB.
Estimated time: under a second (a guide from the first pass, not a promise).
Running it would not ask for a confirmation.
```

The plan is deterministic: it depends on the scan and the settings, not on the
speed of the machine. When the estimate passes the thresholds (several minutes,
or memory beyond the budget), a command that forces the second pass asks you to
confirm first, once for a whole batch. Outside a terminal it stops with exit code
3 unless you pass `--yes`.

Run the second pass when you want exact figures:

```console
tabalyst scan examples/input/insurance-customers.csv --deep -o customers.scan.json
```

It reads the source again and writes `customers.deep.json` beside the scan:
exact distinct counts and frequencies, exact histograms and medians, patterns
counted on every occurrence, dates per period, and the relationships that the
planner chose.

### A smart sample

Ask for the plan of a sample that would cover the cases the scan knows about:

```console
tabalyst scan examples/input/insurance-customers.csv --plan --smart --sample-size 150
```

```text
Targets: 347 (146 mandatory, 201 optional), 11 the sample cannot recognize yet.
  Low cardinality: 146 targets, 146 mandatory
  Structured strings: 57 targets, 0 mandatory
  Numeric: 53 targets, 0 mandatory
  Dates: 67 targets, 0 mandatory
  Quality: 24 targets, 0 mandatory
```

Then create it:

```console
tabalyst sample examples/input/insurance-customers.csv --sample-method smart --rows 150 --seed 42
```

```text
Targets:       335 of 336 covered (weighted 99.8%); 347 defined
Mandatory:     146 of 146 covered
Reserve:       49 ordinary rows; the proportions are not those of the population
Readings:      2 of the source (first pass and selection)
```

The command writes the sample (`insurance-customers.sample.csv`), its report
(`insurance-customers.sample.json`) and a page that shows the report
(`insurance-customers.sample.html`). The page says what the sample covers,
what it does not, and why, and which exact counts of the plan the reading
confirmed.

A smart sample is not a random sample. Rare cases are chosen on purpose, so its
proportions are not those of the file. The coverage is that of the targets the
scan knows about: a case that no target describes can be missing. Read
[the sample format](../sample/format.md) and
[the three kinds of samples](../scan/reading-results.md#three-kinds-of-samples).

## Where to go next

- [Tabalyst Scan](../scan/index.md): the commands and the documents.
- [Plan the analyses](../scan/plan.md): what a plan holds, with
  `--stratify` for advice on stratified sampling.
- [Add histograms and exact medians](../scan/deep.md): the second pass.
- [Tabalyst Sample](../sample/index.md): first, last, random, stratified and
  smart samples.

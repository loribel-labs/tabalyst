---
title: Create your first report
description: Tutorial that profiles a five-row CSV file with tabalyst report, opens the HTML report and reads the problems Tabalyst found.
---

In this tutorial you create a small CSV file, run `tabalyst report` on it, open
the HTML report and read the problems Tabalyst detects. It takes about five
minutes. You need Tabalyst installed and up to date: see
[Install Tabalyst](install.md). If it is already installed, update it
first, since the output shown here comes from the latest release:

```console
pip install --upgrade tabalyst
```

## 1. Create a CSV file

In your working folder, create a file named `orders.csv` with this content:

```text
id,name,amount,joined,active,notes
001,Alice,12.50,2026-01-01,true,First order
002,Bob,,2026-02-01,false,
003,Charlie,25.00,2026-03-01,true,"Two items, one order"
003,Charlie,25.00,2026-03-01,true,"Two items, one order"
004,Dana,not available,2026-04-01,true,Pending review
```

This file contains deliberate problems: a repeated row, empty cells and a text
value in a numeric column.

## 2. Run the report

```console
tabalyst report orders.csv
```

Tabalyst prints a summary and the location of the report:

```text
Analyzed 5 rows and 6 columns.
Report: C:\work\orders.html
Second pass (automatic): 7 analyses, 7 computed, 0 reused.
```

The second pass is an extra step that Tabalyst runs by itself when it finds an
analysis useful and cheap. The line says what it did.

Three files now sit beside `orders.csv`:

```text
orders.csv
orders.html        the interactive report
orders.json        the JSON profile, for scripts and other tools
executions.json    the history of the runs in this folder
```

## 3. Open the report

Open `orders.html` in your web browser, by double-clicking it or from the
terminal:

```console
start orders.html      # Windows
open orders.html       # macOS
xdg-open orders.html   # Linux
```

The report works offline. Add `--details` to the command to create an
independent HTML page per column under `orders/`. The **Columns** table then
links to those pages. In each column page, **Overview** shows the stored values
with counts and all detected formats directly. The files contain values from
your data: share them accordingly.

## 4. Read what Tabalyst found

The report is organized in numbered sections, listed in the bar at the top:
**Overview**, **Summary**, **Observations**, **Columns**, **Transformations**,
**Dates**, **Strings**, **Detectors**, **Patterns**, **Insights**, **Second pass**,
**Data sample** and **Analysis settings**. A section appears only when the data
has something to show: a file with a numeric column also gets **Numeric**, and a
**Limits** section appears when the scan stopped a measure at a limit.

### Overview

The **Overview** section sums up the file: 5 rows, 6 columns, 2 missing cells
(6.67 %) and 1 duplicate row. Under it:

- **Column quality** counts the columns by what Tabalyst found in them: 0 with
  errors, 2 with issues, 4 with no finding. A column with errors counts under
  errors even when it also has issues.
- **Signals** has one tile per kind of finding. Here there are two, both Issues:
  **ID repetitions** (1 value repeated beyond its first occurrence, in `id`) and
  **Mixed types** (1 value outside the closest type, in `amount`). The
  [tile catalogue](../report/read-report.md#signal-tiles) lists the others.
- **Column types** counts the columns by family and type.

An **Error** is a value that a rule proves invalid, such as a date that does not
exist. An **Issue** is an ambiguity or a deviation worth a look. Nothing here is an
Error: no rule proves a value invalid in this file.

### Summary

The **Summary** table has one row per column, with its type, a sentence about its
values, the missing share and its **Errors** and **Issues**. In `orders.csv`:

| Column | Type | What the row says |
| --- | --- | --- |
| `id` | Identifier, ID | 4 distinct values; an Issue: 1 repetition beyond the first (`003`) |
| `name` | Text, Very short | Median length of 5 characters, no finding |
| `amount` | Other, Mixed | Numbers and text together; an Issue: 1 value outside the closest type (`not available`); 1 missing |
| `joined` | Temporal, Date | Dates from 2026-01-01 to 2026-04-01, in one format |
| `active` | Categorical, Boolean | `true` holds 80 % of the values |
| `notes` | Text, Short | Median length of 17 characters; 1 missing |

Click an Issue to see what it counts, out of how many values, how exact the count
is and a few examples.

### Observations

**Observations** lists what the scan found from its facts: the repeated row
(record 4 repeats record 3 exactly), the mixed column `amount`, and the two empty
cells (`amount` and `notes`, record 2), which are remarks and not problems.

Look at the types too:

- `id` is an **identifier**, not an integer: values such as `001` have leading
  zeros, so Tabalyst keeps them as text and reads the column as an ID.
- `joined` is a **date** in the `YYYY-MM-DD` format.
- `active` is a **boolean** (`true` / `false`).

Types are descriptive hints: Tabalyst never modifies your CSV file.

## 5. Run it again

Run the same command a second time:

```console
tabalyst report orders.csv
```

Tabalyst refuses to replace the existing report:

```text
Error: Report output already exists. Use --force to replace it:
  orders.html
  orders.json
```

Add `--force` when replacing the report is intentional:

```console
tabalyst report orders.csv --force
```

`executions.json` is not replaced: each run adds an entry to it.

## What you learned

- `tabalyst report FILE.csv` creates an HTML report and a JSON profile beside
  the source file.
- The report shows detected types, missing values, duplicates and other
  problems, without changing your data.
- Existing reports are protected unless you pass `--force`.

## Next steps

- Choose the output name with `-o`, or process several files at once with
  `tabalyst report *.csv -d reports/`. Run `tabalyst report --help` for all
  options.
- Use the [JSON profile](../report/json-profile.md) in your own scripts.
- Adapt the analysis with a [configuration file](../reference/configuration.md).

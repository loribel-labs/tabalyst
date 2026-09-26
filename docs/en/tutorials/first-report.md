---
title: Create your first report
description: Tutorial that profiles a five-row CSV file with tabalyst report, opens the HTML report and reads the problems Tabalyst found.
---

In this tutorial you create a small CSV file, run `tabalyst report` on it, open
the HTML report and read the problems Tabalyst detects. It takes about five
minutes. You need Tabalyst installed and up to date: see
[Install Tabalyst](../how-to/install.md). If it is already installed, update it
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
```

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

The report is a single self-contained file. It works offline and can be sent to
someone else, but it contains values from your data: share it accordingly.

## 4. Read what Tabalyst found

The report is organized in sections: **Dataset overview**, **Columns**,
**Transformations**, **Numeric analysis**, **Date analysis**,
**String analysis**, **Data sample** and **Analysis settings**.

In **Dataset overview**, the **Quality observations** card lists the problems in
`orders.csv`. Warnings come first; the two whitespace observations are
informational and are always listed, here with a count of 0.

| Problem | Where | Why |
| --- | --- | --- |
| 1 duplicate row | Record 4 | It repeats record 3 exactly |
| 2 missing cells | `amount` and `notes`, record 2 | The cells are empty |
| 1 column with mixed types | `amount` | Three numbers and the text `not available` |

Look at the columns too:

- `id` is detected as **text**, not integer: values such as `001` have leading
  zeros, so Tabalyst keeps them as text.
- `joined` is detected as a **date** in the `YYYY-MM-DD` format.
- `active` is detected as a **boolean** (`true` / `false`).

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
- Use the [JSON profile](../reference/json-profile.md) in your own scripts.
- Adapt the analysis with a [configuration file](../reference/configuration.md).

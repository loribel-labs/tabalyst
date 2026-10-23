---
title: "CLI: tabalyst dedup"
description: Every option of tabalyst dedup, the summary it prints, the files it writes, its exit codes and examples for one file, a batch, an output folder, a forced run and a content check.
---

```console
tabalyst dedup INPUT... [OPTIONS]
```

The simplest use:

```console
tabalyst dedup customers.csv
```

Finds the rows that occur more than once in each CSV source and writes, beside
it or in the folder of `-d`, up to three CSV files and a JSON report:
`<stem>.unique.csv`, `<stem>.duplicates.csv`, `<stem>.duplicates_all.csv` and
`<stem>.dedup.json`. A pattern or several inputs also write
`dedup.summary.json`. The source is never modified. See
[Tabalyst Dedup](../../dedup/index.md).

## Options

| Option | Description |
| --- | --- |
| `INPUT...` | One or more CSV files or non-recursive glob patterns (required). Quote a pattern so that Tabalyst expands it |
| `-d`, `--output-dir PATH` | Folder for the outputs and the batch report, created if needed. Default: beside each source |
| `-c`, `--config PATH` | JSON [configuration file](../configuration.md#dedup-settings) |
| `--max-rows N` | Most data records a source may hold; more fails that source with `row_limit_exceeded` (default 10,000,000, at least 1) |
| `--delimiter TEXT` | One-character CSV delimiter |
| `--encoding TEXT` | CSV text encoding |
| `--memory-budget-mb N` | Memory in MiB that the rows may take before the run continues on disk (default 512, at least 1) |
| `--temp-dir PATH` | Folder for the temporary store used when the budget is reached. Default: the system temporary folder |
| `-f`, `--force` | Process again the sources that are already processed, and replace output files that Dedup did not write. A source is never replaced |
| `--verify-content` | Decide that a source is already processed from the SHA-256 of the source and of its outputs, not from size and modification time. An error with `--force` |
| `--quiet` | Print only the final status, and the errors. Hides the progress. An error with `--verbose` and with `--no-progress` |
| `--verbose` | Add the storage mode, the passes, the durations and the memory peak, and list the excluded files. Measuring the memory peak makes the first pass two to four times slower |
| `--no-progress` | Hide the progress line. It is also hidden outside a terminal |
| `--help` | Show the options and exit |

There is no `-o` option (a source has up to four outputs) and no `--yes`:
Dedup never asks a question, in a terminal or outside one.
`--delimiter` and `--encoding` also apply to the CSV files written.

## What it prints

The result goes to standard output, the progress and the errors to standard
error. One explicit file prints a block:

```text
Tabalyst Dedup
---------------------------------------------------------------
File:         customers.csv
Source rows:  6
Distinct:     3
Groups:       2
Extra copies: 3

Duplicate records found.
CSV files generated:
  customers.unique.csv
  customers.duplicates.csv
  customers.duplicates_all.csv
Report: customers.dedup.json
Status: COMPLETE
```

A pattern or several inputs print a table, also for one source:

```text
Tabalyst Dedup
---------------------------------------------------------------
File              Status    Rows       Extra copies  Outputs
---------------------------------------------------------------
customers.csv     DONE            6    3             3
orders.csv        DONE            4    1             2
products.csv      DONE            3    0             0
---------------------------------------------------------------
Eligible files:       3
Processed:            3
Already processed:    0
Failed:               0
New CSV files:        5
JSON reports:         3 available (3 updated)
Batch report:         dedup.summary.json
Result:               COMPLETE
```

| Status | Meaning |
| --- | --- |
| `DONE` | The source was processed in this run |
| `SKIPPED` | The source was already processed and has not changed; nothing was written. `0 new` in the table means no CSV was created by this run |
| `FAILED` | The source failed; `-` replaces its counts. The reason is on standard error |
| `EXCLUDED` | A derived file that a pattern found; listed by `--verbose`, counted on the `Excluded:` line |

The result of the batch is `COMPLETE`, `PARTIAL` when some source failed, or
`FAILED` when every source did. A source that fails prints one line on
standard error before the table: `Error [bad.csv]: message (reason)`. The
message is a fixed sentence with no cell. A refusal before any work prints
`Error: message`.

`--quiet` prints only the last line (`Status: COMPLETE` for one file,
`Result: COMPLETE` for a batch). `--verbose` adds a block of measures
(`Storage:`, `Passes:`, `First pass:`, `Second pass:`, `Memory peak:` and
`Duration:`) or, for a batch, a `Details` list.

## Examples

One file, and a batch:

```console
tabalyst dedup customers.csv
tabalyst dedup "*.csv"
tabalyst dedup customers.csv orders.csv
```

Choose the output folder, which keeps the source folder clean:

```console
tabalyst dedup "data/*.csv" -d deduped
```

A source that is already processed is skipped, which the summary says:

```text
Tabalyst Dedup
---------------------------------------------------------------
File:         products.csv
Source rows:  3
Distinct:     3
Groups:       0
Extra copies: 0

Already processed, verified by metadata.
No CSV files generated.
Report: products.dedup.json
Status: COMPLETE
```

Process again, or check the content of the files instead of their size and
date:

```console
tabalyst dedup customers.csv --force
tabalyst dedup "*.csv" --verify-content
```

A large file with a larger memory budget and a roomy temporary folder:

```console
tabalyst dedup big.csv --memory-budget-mb 2048 --temp-dir D:/tmp
```

A CSV with another delimiter or encoding, or a configuration file:

```console
tabalyst dedup data.csv --delimiter ";" --encoding cp1252
tabalyst dedup "*.csv" -c tabalyst.json
```

Dedup accepts CSV files only.

## Exit codes

| Code | When |
| --- | --- |
| `0` | Nothing failed. A skipped or excluded file is not a failure |
| `1` | At least one failure that is not an input error (storage, an output that cannot be written, an output to replace without `--force`, a defect), or a batch report that cannot be written |
| `2` | Invalid option or configuration, such as `--quiet` with `--verbose`, `--force` with `--verify-content` or a value below 1 |
| `4` | A source is missing, or every failure is an input error: invalid CSV, a decoding error, the row limit, a source that changed while it was read, an output that is a source or a folder |

Code `3` is not used: Dedup asks no confirmation. When a batch has both kinds
of failure, `1` wins over `4`. A source that fails does not stop the others.

```text
Error: --force and --verify-content cannot be used together: a forced run reprocesses every source, so there is nothing to verify.
```

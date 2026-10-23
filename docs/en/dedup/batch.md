---
title: Batch and already processed files
description: How tabalyst dedup processes several CSV files, which files it skips, when a file counts as already processed, and when it refuses to replace an existing file.
---

`tabalyst dedup` takes one or more CSV files or non-recursive wildcard patterns.
Each file is processed on its own, in the order found, and a file that fails
does not stop the others. Quote a pattern so that Tabalyst expands it itself,
which works the same in PowerShell, `cmd` and POSIX shells:

```console
tabalyst dedup "*.csv"
tabalyst dedup "data/*.csv" -d deduped
tabalyst dedup customers.csv orders.csv
```

Tabalyst does not search subfolders, and `**` is refused. Two patterns that
find the same file process it once. A pattern that matches no file is an input
error (exit code `4`).

## Output folder

By default the outputs are written beside each source. With `-d` they go to one
folder, which is created when needed. Each source has four possible output
names, built from the name of the file without its extension:

| Name | Content |
| --- | --- |
| `<stem>.unique.csv` | The distinct rows |
| `<stem>.duplicates.csv` | Each repeated row once |
| `<stem>.duplicates_all.csv` | Every occurrence of the repeated rows |
| `<stem>.dedup.json` | The [report](format.md) of the source |

## Files that a pattern skips

Running the same pattern twice must not read the results of the first run. A
file found by a pattern is skipped, never an error, in these cases:

| Reason | The file |
| --- | --- |
| `derived_csv` | Ends with `.sample.csv`, `.unique.csv`, `.duplicates.csv` or `.duplicates_all.csv`, in any case |
| `dedup_output` | Ends with `.dedup.json`, or is `dedup.summary.json` |
| `inspect_file`, `lock_file` | Is an Inspect file or a lock file |
| `output_directory` | Is in the output folder, which the pattern reached through a wildcard in its folder part, such as `"*/*.csv" -d out` |

A file you name yourself is never skipped for its suffix: `tabalyst dedup
customers.unique.csv` processes that file. The skipped files appear in the
`--verbose` output and in the batch report, with their reason. A pattern that
matches only skipped files is not an error: the command reports that no file
is left to process and exits with `0`.

## Already processed files

A source is **skipped**, with the status `SKIPPED` and the reason
`already_processed`, when everything shows that the last run is still valid:

1. A report `<stem>.dedup.json` exists, is complete and was written by this
   format of Tabalyst Dedup.
2. The CSV settings (delimiter and encoding) are the same, and the report does
   not hold more records than `--max-rows` allows.
3. The source has the same name and size, and the same modification time. When
   only the modification time differs, Tabalyst reads the file and compares its
   SHA-256 with the one in the report.
4. The output files that the report lists all exist and have the recorded size.
   No other managed file exists.

A skipped source writes nothing, not even its report. The summary says how far
the check went:

```text
Already processed, verified by metadata.
```

`metadata` means that size and modification time were compared. `digest` means
that the SHA-256 of the source, and of the outputs, was compared. If any
condition fails, the source is processed again. This is the case when you
change the source, the delimiter, the encoding or a lowered `--max-rows`, or
delete an output.

A source without duplicate has no CSV: its report alone proves it was
processed.

A copy of a file made with a new modification time is read and hashed at every
run until it is processed again.

### Example

Three files, run twice. The first run processes them:

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

The second run finds the folder as the first one left it. Its pattern now also
finds the five CSV files of the first run, which are skipped:

```text
Tabalyst Dedup
---------------------------------------------------------------
File              Status    Rows       Extra copies  Outputs
---------------------------------------------------------------
customers.csv     SKIPPED         6    3             0 new
orders.csv        SKIPPED         4    1             0 new
products.csv      SKIPPED         3    0             0 new
---------------------------------------------------------------
Eligible files:       3
Excluded:             5
Processed:            0
Already processed:    3
Failed:               0
New CSV files:        0
JSON reports:         3 available (0 updated)
Batch report:         dedup.summary.json
Result:               COMPLETE
```

`0 new` means that this run created no CSV file for the source, not that the
source has no duplicate: the `Extra copies` column says that. If you change
`orders.csv` and run again, only `orders.csv` is processed.

### Check the content: `--verify-content`

By default, the size and the modification time decide. A tool that rewrites a
file with the same size and the same modification time would go unnoticed.
Pass `--verify-content`, or set `dedup.verify_content_on_skip` to `true` in the
[configuration](../reference/configuration.md#dedup-settings), to decide from
the SHA-256 of the source and of the outputs. It reads every file again, so it
is slower on large files. It is refused with `--force`, which already
reprocesses everything.

### Process again: `--force`

`--force` skips the check and processes every source again. It also allows
replacing a file under an output name that Tabalyst did not write (see below).
It never replaces a source.

## What Tabalyst refuses to replace

Tabalyst never modifies or replaces a source, with or without `--force`. The
whole batch is checked before any file is read, and nothing is written when:

- an output name is the path of one of the sources (exit code `4`);
- two sources would write the same output name, such as `data.csv` and
  `data.tsv`, or two folders with `-d` (exit code `1`);
- an output name is a folder (exit code `4`);
- a file with an output name exists and no Dedup report proves that Tabalyst
  wrote it (exit code `1`). A file whose size was changed by hand is such a
  file.

```text
Error: Dedup output already exists and no Tabalyst Dedup report proves it is one of its results. Use --force to allow replacing it:
  customers.unique.csv
```

The check covers all four names of a source, also the ones this run would not
write. Only `--force` allows replacing a file that Tabalyst did not write, and
it never deletes one it does not replace. A `dedup.summary.json` that is not a
Tabalyst batch report follows the same rule.

## When a source fails

A source can fail without stopping the batch: invalid CSV, more records than
`--max-rows`, a source that changed while it was read, or a storage problem.
The source gets a report with `status` `failed` and the `reason`, and its
earlier outputs are deleted, because they no longer describe the source.

```text
Error [customers.csv]: The file has more than 3 data records. (row_limit_exceeded)
Tabalyst Dedup
---------------------------------------------------------------
File:         customers.csv

Failed: row_limit_exceeded. No CSV files generated.
Report: customers.dedup.json
Status: FAILED
```

The other sources are processed, and the exit code is `4` when every failure
is an input error and `1` as soon as one is not. The reasons are listed in
[the report format](format.md#failed-report).

The CSV files are written to temporary files first and published only when the
whole set is valid, then the report is written last. A complete report proves
that the whole set was published. If a run is interrupted, for example with
Ctrl-C, the next run repairs the state; it also deletes the temporary files of
the interrupted run, and only those.

## The batch report

When you give a pattern or several inputs, `tabalyst dedup` also writes
`dedup.summary.json`, the [batch report](format.md#batch-report), in the output
folder, otherwise beside the sources if they share one folder, otherwise in the
current folder. One explicit file writes none. An existing file of that name
is replaced only if it is a Tabalyst batch report, or with `--force`.

## Two runs at the same time

Tabalyst does not lock the outputs. Do not run two `tabalyst dedup` commands
on the same files or the same output folder at once: they are not protected
against each other. The check just before each source narrows the window and
the recovery after an interruption keeps the state repairable, but neither is
a lock.

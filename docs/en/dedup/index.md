---
title: Tabalyst Dedup
description: Find the exact duplicate rows of CSV files and write the unique rows, the repeated rows and every occurrence of them to new CSV files, with a JSON report, without changing the source.
---

Use `tabalyst dedup` to find the rows that occur more than once in a CSV file
and to get a copy without the repeats. Two rows are the same only when all
their cells are identical. The source file is never modified.

```console
tabalyst dedup customers.csv
```

For this `customers.csv`:

```text
id,name
101,Alice
102,Bob
101,Alice
103,Charlie
101,Alice
102,Bob
```

the command prints:

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

It writes the CSV files and the JSON report beside the source, or in the
folder of `-d`. A result with `Status: COMPLETE` is exact: Tabalyst never
approximates a count. If the memory, the disk or the time is not enough, the
command fails with a reason instead (see
[Exactness, memory and limits](limits.md)).

## The three outputs

| File | Rows | Use it to |
| --- | --- | --- |
| `<stem>.unique.csv` | Every distinct row once, at the place of its first occurrence | Continue with data without repeats |
| `<stem>.duplicates.csv` | Each repeated row once, in the order of its first occurrence | See which rows are repeated |
| `<stem>.duplicates_all.csv` | Every occurrence of the repeated rows, first ones included | See every copy of a repeated row, as soon as a row occurs three times or more |
| `<stem>.dedup.json` | One JSON report | Read the counts in a script, see [the report format](format.md) |

Every CSV keeps the header, the order of the columns and the order of the
source. Nothing is sorted. The first occurrence of a row is the one kept.

The three CSV files are not three separate parts of the source: a repeated row
is in `unique.csv`, in `duplicates.csv` and in `duplicates_all.csv`.

For the example above, `customers.unique.csv` holds rows 1, 2 and 4:

```text
id,name
101,Alice
102,Bob
103,Charlie
```

`customers.duplicates.csv` holds the two repeated rows:

```text
id,name
101,Alice
102,Bob
```

`customers.duplicates_all.csv` holds the five occurrences of those two rows,
in the order of the source:

```text
id,name
101,Alice
102,Bob
101,Alice
101,Alice
102,Bob
```

## When a CSV is written

Tabalyst writes only the files that carry information. The criterion is the
highest number of occurrences of one row.

| The source has | CSV files written | JSON report |
| --- | --- | --- |
| No repeated row | None | Yes |
| Repeated rows, none more than twice | `unique` and `duplicates` | Yes |
| A row three times or more | `unique`, `duplicates` and `duplicates_all` | Yes |

When two copies are the most there is, `duplicates_all.csv` would repeat
every row of `duplicates.csv` and is not written. A file without duplicate
gets its report only, and `outputs.csv_files_created` is `0` in it:

```text
No duplicate records found.
No CSV files generated.
```

A file that holds only a header is valid: it has no record and no CSV is
written.

## The counts

The command and the report use the same counts, which always add up.

| Count | Meaning | Example |
| --- | --- | --- |
| Source rows (`records.total`) | Data records, the header excluded | 6 |
| Distinct (`records.distinct`) | Different rows; also the rows of `unique.csv` | 3 |
| Groups (`records.duplicate_groups`) | Rows that occur at least twice; also the rows of `duplicates.csv` | 2 |
| Extra copies (`records.extra_copies`) | Occurrences after the first of their row | 3 |
| Group occurrences (`records.duplicate_group_occurrences`) | Groups plus extra copies; also the rows of `duplicates_all.csv` | 5 |

Source rows equal distinct rows plus extra copies. The first occurrence is not
an extra copy: a row that occurs 3 times has 2 extra copies. A row that
occurs once is a singleton (`records.singletons`), and distinct rows equal
singletons plus groups.

## What counts as the same row

A row is the list of the cells decoded from the CSV file. Two rows are the same
when they have the same number of cells and the same cells in the same order.
Tabalyst changes nothing before it compares:

- `Alice` and `alice` are two rows, as are `Alice` and `Alice ` (a trailing
  space), and `007` and `7`.
- Quoting does not matter: `"Alice"` and `Alice` are the same cell.
- A cell that holds a comma, a quote or a line break is a single cell.
- A letter with an accent written in two Unicode forms is two cells.

The header is not part of any row. The identity used is named
`full_decoded_csv_row_v1` in the report.

## Several files

`tabalyst dedup` takes files and wildcard patterns, and processes each file on
its own. A file that is already processed and has not changed is skipped. See
[Batch and already processed files](batch.md).

```console
tabalyst dedup "*.csv" -d deduped
```

## Compared with the Scan

[Tabalyst Scan](../scan/index.md) and [Tabalyst Report](../report/index.md)
count the duplicate rows of a file as part of their analysis. That count is
bounded: past `scan.limits.max_tracked_records` it is a lower bound such as
`≥ 12`. Use Dedup when you need the exact count, or the rows themselves. Under
the Scan limit the two numbers agree. Dedup never starts a Scan.

## Pages

- [Batch and already processed files](batch.md): patterns, skipped files,
  `--force`, `--verify-content` and what Tabalyst refuses to overwrite.
- [Exactness, memory and limits](limits.md): the memory budget, the disk, the
  10,000,000 rows limit and the measures.
- [Format of the Dedup reports](format.md) and its
  [changelog](format-changelog.md).
- [`tabalyst dedup` command reference](../reference/cli/dedup.md) and
  [Python API: Dedup](../reference/python-api/dedup.md).
- [Configuration](../reference/configuration.md#dedup-settings): the `dedup`
  settings.

Dedup reads CSV files only. It does not modify the lines of the source, and it
does not look for near duplicates, for duplicates on some columns only, or
after a normalization.

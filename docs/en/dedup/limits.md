---
title: Exactness, memory and limits
description: Why a complete Dedup result is exact, how the memory budget and the disk fallback work, the limit of 10,000,000 records, the space the temporary files and the outputs take, and measured times.
---

A Dedup result with `Status: COMPLETE` is exact: the counts and the CSV files
are those of a comparison of every cell of every row. Tabalyst never gives an
approximate duplicate count in Dedup. When something is not enough to be exact
(memory, disk, a changed source) the source fails with a `reason` and
publishes no CSV, instead of publishing a result that might be wrong.

The numbers on this page were measured on one machine (a 24-thread laptop
processor, 31 GB of memory, an NVMe disk, Windows 11, Python 3.12). They show
the order of magnitude; they are not guarantees, and they may change before
Tabalyst 1.0.

## How Dedup stays exact

- **Whole rows.** The identity of a row is its list of decoded cells. Dedup
  keeps the full identity of every distinct row in a store and compares it with
  each new row. It never decides that two rows are equal because a short
  digest or a hash matches.
- **Two readings.** Dedup reads the source once to count, and a second time to
  write the CSV files, only when there is a duplicate. A source without
  duplicate is read once.
- **A stable source.** Size and modification time are compared at the start and
  at the end of each reading, and the SHA-256 of the two readings must be
  equal. A source that changes while Dedup works fails with `source_changed`
  and publishes nothing.
- **Checked counts.** The rows of each output are counted against the counts of
  the first reading before the files are published. A disagreement stops the
  run with `unexpected_error`.

## Row limit

A source may hold 10,000,000 data records by default; the header is not
counted. `--max-rows` (or `dedup.max_rows`) changes the limit, which must be at
least 1. Exactly `max_rows` records are allowed. At the next record the source
fails with `row_limit_exceeded`: no CSV is published, and the failed report
records the limit and `records_read`, with `certified` set to `false`. The other
files of the batch go on. Counts of a failed source are not given, since they
would not be complete.

A record is a CSV record, not a line: a cell with a line break is one record.
A cell longer than 131,072 characters, the limit of the `csv` module Tabalyst
reads with, makes the source fail with `invalid_csv`, as it does for
`tabalyst sample`.

## Memory budget

Dedup keeps the rows it has seen in memory, and moves to disk when they take
too much. `--memory-budget-mb` (or `dedup.memory_budget_mb`) sets the budget in
MiB, 512 by default and at least 1. It counts the bytes of the stored rows plus
a fixed cost per row, never the memory of the process, so the same file makes
the same choice on any machine. Rows with few columns stay in memory up to
about 2.5 to 3.3 million distinct rows with the default budget.

When the budget is reached the command says so, for example `memory budget
reached at record 3,100,000, continuing on disk`, and goes on without losing a
row. The report records `run.storage_mode` `disk` instead of `memory`. The
result does not depend on the mode. The disk path takes 1.6 to 2.7 times as
long as the memory path on the same file.

The working memory of a run stays under the budget plus about 150 MiB, in memory
and on disk. A budget of 1 MiB runs in about 70 MiB. To keep files of up to
about 9 million distinct short rows in memory, which is faster, give more:

```console
tabalyst dedup big.csv --memory-budget-mb 2048
```

The memory is only used when the file needs it. If you give a budget that the
machine does not have, the system decides, not Tabalyst.

## Temporary disk

The disk path uses a temporary SQLite database in a private folder of the
system temporary folder. Use `--temp-dir` to put it on a volume with room. The
folder is deleted when the run ends, is interrupted or fails, before the
second reading starts.

Plan for about the size of the distinct rows plus 20 to 50 bytes for each,
and keep 64 MiB free: 0.7 GiB for 10 million distinct rows of 4 cells, 2.7 GiB
for 10 million rows of 20 cells. Before the move and after every commit,
Dedup checks the free space. If there is not enough, or if the folder is
missing, unreadable or a file, the source fails with `insufficient_disk_space`
or `storage_unavailable`, the temporary files are deleted and nothing is
published.

## Disk for the outputs

The CSV files are written next to the source (or in `-d`). They take at most
about twice the size of the source for the three files together, and less when
there are few duplicates. The outputs are written to temporary files in that
folder first, so plan for them to exist twice at the moment of the
replacement of an earlier result.

Dedup does not check the space for the outputs before it starts. If the
volume fills up during the second reading, the source fails with
`insufficient_disk_space` and publishes nothing, which can happen after the
first reading has taken minutes on a very large file.

## Measured times

Rows of 4 cells (about 50 bytes), the default budget, 25 % of extra copies.
`Mode` is the storage mode of the first reading.

| Records | Mode | Time | Peak working set | Source | Outputs |
| ---: | --- | ---: | ---: | ---: | ---: |
| 100,000 | memory | 0.3 s | 75 MiB | 5 MiB | 6 MiB |
| 1,000,000 | memory | 3.5 s | 210 MiB | 50 MiB | 68 MiB |
| 5,000,000 | disk | 34 s | 527 MiB | 264 MiB | 361 MiB |
| 10,000,000 | disk | 96 s | 596 MiB | 535 MiB | 733 MiB |

Wider rows cost more per record: 10 million records of 20 cells (3.0 GiB)
took 3.5 minutes. The second reading is the more expensive one for wide rows
and long texts, because writing three CSV files costs more than reading.
Timings vary by about 40 % between identical runs.

A source that is already processed is decided in about a second, even a large
one, because only its size and modification time are compared. With
`--verify-content` the source and the outputs are read and hashed, so the time
grows with their size.

## `--verbose`

`--verbose` adds the storage mode, the passes, the durations and the memory peak
to the summary. The memory peak is measured by tracing every Python allocation,
which makes the first reading two to four times slower and doubles the memory
used. Use it to understand a run, not to time one. The measured peak is in
`run.memory_peak_bytes` of the report, `null` otherwise.

## What the numbers are not

- They are not a promise of time. Tabalyst decides with budgets of bytes and
  records, never with a clock, and an estimated time only feeds messages.
- The memory budget is not a limit of the memory of the process: it does not
  count the interpreter, the buffers or the two bit arrays that mark the
  records (about 2.5 MB for 10 million records).
- Dedup reads CSV files only.

# Scan benchmarks

Reproducible measurements for Tabalyst Scan. Phase 0 records the baseline of
the current pandas report engine; phase 6 adds the scan engine and decides
targets (O19). Numbers are only comparable on the same machine and data.

## Protocol

Generate deterministic synthetic data (fictional values, 20 columns mixing
identifiers, contacts, postal codes, province variants, ISO and DMY dates, dot
and comma decimals, booleans, enumerations, free text and a mixed column; the
JSON form adds nested orders, null addresses and a late optional field):

```powershell
.\.venv\Scripts\python.exe benchmarks\generate_data.py --rows 100000 -o benchmarks\data\synthetic-100k.csv
.\.venv\Scripts\python.exe benchmarks\generate_data.py --rows 1000000 -o benchmarks\data\synthetic-1m.csv
```

`benchmarks/data/` is ignored by Git. Measure, one fresh interpreter per run:

```powershell
.\.venv\Scripts\python.exe benchmarks\run_baseline.py examples\input\insurance-customers.csv benchmarks\data\synthetic-100k.csv --repeat 3
.\.venv\Scripts\python.exe benchmarks\run_baseline.py benchmarks\data\synthetic-1m.csv
```

Tasks:

- `csv-read`: iterate every record with `csv.reader`, the lower bound for any
  Python streaming reader.
- `report-engine`: `tabalyst.analyze_csv()` with default settings, which reads
  and analyzes the CSV (no HTML rendering). It measured the pandas engine in the
  baseline; since lot 5a it measures the report built on Tabalyst Scan.
- `scan` (lot 6): `tabalyst.scan()` with default settings, so with worker
  processes for sources of 16 MiB or more.
- `scan-single` (lot 6): `tabalyst.scan(workers=1)`, in one process.
- `pandas-engine`: the former pandas engine, measured in the tables below
  until lot 5c removed it with the task.

Reported memory is the peak resident set (peak working set on Windows) of the
measuring process, plus the peak of each worker process since lot 6: an upper
bound of the memory used at once. Growth subtracts the resident memory after
imports. Time is the best of the repeats. Close memory-heavy applications first: the 1M-row
report engine needs about 4.6 GB.

## Baseline, 2026-09-26

| File | Rows | Size (MB) | Task | Best time (s) | Rows/s | Peak memory (MB) | Growth (MB) |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| insurance-customers.csv | 3,000 | 0.8 | csv-read | 0.01 | 542,594 | 17 | 0 |
| insurance-customers.csv | 3,000 | 0.8 | report-engine | 0.77 | 3,872 | 91 | 15 |
| synthetic-100k.csv | 100,000 | 28.8 | csv-read | 0.17 | 577,207 | 17 | 0 |
| synthetic-100k.csv | 100,000 | 28.8 | report-engine | 8.83 | 11,331 | 525 | 450 |
| synthetic-1m.csv | 1,000,000 | 290.0 | csv-read | 1.72 | 580,086 | 17 | 0 |
| synthetic-1m.csv | 1,000,000 | 290.0 | report-engine | 108.57 | 9,211 | 4,567 | 4,492 |

Environment: Tabalyst 0.3.0 (commit 9d9f5fb), CPython 3.12.14, pandas 3.0.6,
Windows 11 (10.0.26200), Intel Core Ultra 9 275HX (24 logical CPUs), 32 GB RAM.
Three repeats for the first two files, one for the 1M-row file.

## Observations

- The current engine's memory grows linearly at about 16 times the CSV size:
  10 million rows (about 2.9 GB of CSV) would need about 45 GB and cannot run on
  this 32 GB machine. This is the limit Scan removes (ET05).
- Throughput is about 9,000 to 11,000 rows per second for 20 columns, dominated
  by per-distinct-value Python work rather than by pandas reading.
- A plain `csv.reader` pass reads the same rows about 60 times faster (580,000
  rows per second). A Python streaming engine therefore has a large budget:
  matching the current throughput with bounded memory is a realistic first
  target for phase 6, to be confirmed by measurements.

## Lot 5a, 2026-09-27

Indicative single runs after the report moved onto Tabalyst Scan (commit
24730ee plus the lot 5a changes, same machine as the baseline):

| File | Rows | Size (MB) | Task | Best time (s) | Rows/s | Peak memory (MB) | Growth (MB) |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| insurance-customers.csv | 3,000 | 0.8 | pandas-engine | 0.79 | 3,788 | 95 | 15 |
| insurance-customers.csv | 3,000 | 0.8 | report-engine | 0.85 | 3,549 | 91 | 12 |
| synthetic-100k.csv | 100,000 | 28.8 | pandas-engine | 9.07 | 11,028 | 529 | 450 |
| synthetic-100k.csv | 100,000 | 28.8 | report-engine | 13.17 | 7,593 | 269 | 189 |

The report on Scan takes about 45% more time than the pandas engine on
100,000 rows, with about 40% of its memory growth; the detector work of lot 3
dominates. Lot 6 sets the targets.

## Lot 6, 2026-09-28

The engine after the batches, column reading and workers of lot 6 (commit
fce27be plus the lot 6 changes, same machine as the baseline, at most 8
workers). Three repeats for the first two files, one for the others; the JSON
file is `generate_data.py --rows 100000` with a `.json` output.

| File | Rows | Size (MB) | Task | Best time (s) | Rows/s | Peak memory (MB) | Growth (MB) |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| insurance-customers.csv | 3,000 | 0.8 | csv-read | 0.01 | 566,626 | 18 | 0 |
| insurance-customers.csv | 3,000 | 0.8 | report-engine | 0.57 | 5,285 | 52 | 15 |
| insurance-customers.csv | 3,000 | 0.8 | scan | 0.18 | 16,470 | 51 | 13 |
| insurance-customers.csv | 3,000 | 0.8 | scan-single | 0.18 | 16,317 | 51 | 13 |
| synthetic-100k.csv | 100,000 | 28.8 | csv-read | 0.16 | 613,938 | 18 | 0 |
| synthetic-100k.csv | 100,000 | 28.8 | report-engine | 2.14 | 46,809 | 826 | 788 |
| synthetic-100k.csv | 100,000 | 28.8 | scan | 2.17 | 46,056 | 827 | 789 |
| synthetic-100k.csv | 100,000 | 28.8 | scan-single | 4.80 | 20,813 | 233 | 196 |
| synthetic-1m.csv | 1,000,000 | 290.0 | report-engine | 11.45 | 87,324 | 740 | 702 |
| synthetic-1m.csv | 1,000,000 | 290.0 | scan | 11.99 | 83,434 | 739 | 702 |
| synthetic-1m.csv | 1,000,000 | 290.0 | scan-single | 38.36 | 26,067 | 230 | 192 |
| synthetic-100k.json | 100,000 | 64.9 | report-engine | 8.48 | 11,789 | 864 | 827 |
| synthetic-100k.json | 100,000 | 64.9 | scan | 8.12 | 12,318 | 864 | 826 |
| synthetic-100k.json | 100,000 | 64.9 | scan-single | 10.77 | 9,287 | 277 | 240 |

The same scans with Tabalyst 0.4.1 before lot 6's second session (single
runs, fresh process, same method):

| File | Rows | Scan time (s) | Peak memory (MB) |
| --- | ---: | ---: | ---: |
| insurance-customers.csv | 3,000 | 0.41 | 47 |
| synthetic-100k.csv | 100,000 | 11.16 | 226 |
| synthetic-100k.json | 100,000 | 22.38 | 290 |
| synthetic-1m.csv | 1,000,000 | 147.05 | 232 |

- One million rows take 12 s instead of 147 s (0.4.1) and 109 s (the pandas
  engine of the baseline, with 4.6 GB of memory). In one process, the scan
  takes 38 s with the memory of 0.4.1.
- Workers cost memory, not results: each holds an interpreter with Tabalyst
  (about 60 to 80 MB) and the values of its fields. The gain stops at 4 to 8
  workers on these 20 columns (1M rows: 18.1 s with 2 workers, 11.5 s with
  4, 11.4 s with 8, 11.3 s with 16), where the scan process becomes the
  bottleneck: reading about 1.8 s per million rows, counting columns about 2
  s, duplicate digests about 1 s, sending values to workers about 0.6 s.
- Per distinct value, the analysis went from about 10 microseconds (13
  `classify` calls and 13 tally updates) to 2 to 5 for the costliest fields
  (amounts with decimal commas, phones, dates), and a fraction of a
  microsecond for fields whose detectors are skipped.
- JSON is bound by its reader and the per-observation engine: the reader
  alone takes 3 s for these 100,000 records (2.9 million observations).

## JSON Inspect

The costs of JSON Inspect, of the interpretation resolver and of the JSON and JSONL
parcours (hash, event pass, Scan, report with a stored scan) are in
`docs/dev/inspect/benchmarks.md` (lot JI-8).

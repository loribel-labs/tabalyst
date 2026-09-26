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
  and analyzes the CSV (no HTML rendering).

Reported memory is the peak resident set (peak working set on Windows) of the
measuring process; growth subtracts the resident memory after imports. Time is
the best of the repeats. Close memory-heavy applications first: the 1M-row
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

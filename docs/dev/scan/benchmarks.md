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

## Baseline of the Scan and JSON work, lot 0, 2026-10-06

The reference for the lots that follow (`design.md` sections 18 to 21). Engine
0.6.2 at commit `0acf126` (format revision 2 of the Scan), CPython 3.12.14,
Windows 11, Intel Core Ultra 9 275HX (24 logical CPUs), default workers (at
most 8). Each run is a fresh interpreter, three repeats, median and range.
Files: the reference folder `D:/GIT.test/tabalyst/csv/` (the combined insurance
file, 1,000,000 rows by 34 columns, 276,086,860 bytes, and its three extractions)
and `benchmarks/data/synthetic-1m.csv` (1,000,000 rows by 20 columns). Script:

```powershell
.\.venv\Scripts\python.exe benchmarks\scan_json_baseline.py D:\GIT.test\tabalyst\csv\insurance-combined.csv benchmarks\data\synthetic-1m.csv --repeat 3
```

It writes `results.json` (every run, with the phases of `run.timings`, the
limited measures and the size of the documents) and `results.md` under
`D:\GIT.test\tabalyst\artifacts\scan-json-lot0\`. Tasks: `csv-read` (the floor of
any Python reader, PERF-04), `scan`, `scan-single` (`workers=1`), `scan-t10000`
(`limits.max_distinct_per_field` 10,000: the lower tracking limit first
proposed for the work, measured to decide O28), `report` (from the source, scan included) and `report-from-scan` (the
report of an existing Scan document: reading, profile and rendering only, no
source). Peak memory adds the peak of every worker to the one of the process.

| File | Rows | Size (MB) | Task | Median (s) | Range (s) | Rows/s | Peak memory (MB) |
| --- | ---: | ---: | --- | ---: | --- | ---: | ---: |
| insurance-combined.csv | 1,000,000 | 263.3 | csv-read | 1.88 | 1.87-1.95 | 530,596 | 20 |
| insurance-combined.csv | 1,000,000 | 263.3 | scan | 12.03 | 11.91-12.23 | 83,106 | 715 |
| insurance-combined.csv | 1,000,000 | 263.3 | scan-single | 26.04 | 25.84-27.84 | 38,406 | 199 |
| insurance-combined.csv | 1,000,000 | 263.3 | scan-t10000 | 15.05 | 14.11-15.73 | 66,467 | 536 |
| insurance-combined.csv | 1,000,000 | 263.3 | report | 16.12 | 15.95-16.47 | | 715 |
| insurance-combined.csv | 1,000,000 | 263.3 | report-from-scan | 0.64 | 0.58-0.74 | | 716 |
| synthetic-1m.csv | 1,000,000 | 290.0 | csv-read | 1.69 | 1.68-1.69 | 593,074 | 20 |
| synthetic-1m.csv | 1,000,000 | 290.0 | scan | 11.44 | 11.28-12.04 | 87,384 | 796 |
| synthetic-1m.csv | 1,000,000 | 290.0 | scan-single | 48.47 | 46.19-48.58 | 20,629 | 235 |
| synthetic-1m.csv | 1,000,000 | 290.0 | scan-t10000 | 11.87 | 11.76-12.34 | 84,251 | 546 |
| synthetic-1m.csv | 1,000,000 | 290.0 | report | 14.74 | 14.38-14.80 | | 797 |
| synthetic-1m.csv | 1,000,000 | 290.0 | report-from-scan | 0.23 | 0.22-0.26 | | 796 |
| insurance-principal.csv | 727,273 | 185.4 | scan | 10.39 | 10.02-10.43 | 69,968 | 688 |
| insurance-principal.csv | 727,273 | 185.4 | scan-single | 17.84 | 17.77-19.06 | 40,761 | 186 |
| insurance-quebec.csv | 181,818 | 46.5 | scan | 2.87 | 2.86-2.88 | 63,304 | 627 |
| insurance-quebec.csv | 181,818 | 46.5 | scan-single | 4.15 | 4.06-4.18 | 43,806 | 127 |
| insurance-ontario.csv | 90,909 | 22.5 | scan | 1.93 | 1.88-1.97 | 47,202 | 673 |
| insurance-ontario.csv | 90,909 | 22.5 | scan-single | 2.59 | 2.55-2.62 | 35,155 | 142 |

Phases of the default scan (`run.timings`, median seconds): the combined file
reads in 3.99, analyzes in 6.85, finalizes in 0.44 and spends 0.69 on setup and
assembly; `synthetic-1m.csv` 3.72, 6.37, 0.49 and 0.69. In one process the
analysis takes 20.64 and 42.34 seconds. The main process peaks at 177 MB (the
combined file) and 190 MB; workers add the rest of the total peak. The Scan
document of the combined file is 1,277,597 bytes and its Report profile 470,385.
The `insurance-principal`, `quebec` and `ontario` rows, with their `report` and
`report-from-scan` timings, are in `results.md`.

### What the baseline shows

- **The floor.** Reading and parsing alone take 1.9 s for the combined file
  (530,000 rows per second); `run.timings.reading` is 4 s, because it also
  hashes the source and builds the records. The first pass is 6 times the
  floor with workers and 14 times in one process.
- **Run-to-run drift is as large as the regression threshold.** The same code
  and configuration measured 12.03 s in the first session and 14.47 s (five
  repeats, interleaved with `scan-t10000` at 13.84 s) in a second one
  later the same day: a drift of 20% between sessions, with 3% to 10% spread inside one.
  The first `scan-t10000` of the combined file (+25%) was this drift, not a
  cost of the tracking limit. **Rule:** a lot compares itself with the baseline
  commit measured in the same session, interleaved (`git worktree` of
  `0acf126`, same script), never with the figures above, which only give the
  order of magnitude.
- **Tracking limit of 10,000 (first version of O28, not retained).** Time is not worse (the combined file
  13.84 s against 14.47 s in the same session; `synthetic-1m` +4%, the three extractions -5% to -15%) and
  the peak memory falls from 715 to 536 MB, since fewer tables are kept. The
  cost is exactness, not time. With T = 10,000, columns with 10,000 to
  100,000 distinct values lose their exact cardinality, complete frequencies,
  stage cardinalities and variant groups, and exact medians when numeric:

  | File | Columns between 10,000 and 100,000 distinct values |
  | --- | --- |
  | insurance-combined | `date_naissance` (65,020) |
  | insurance-principal | `date_naissance` (25,095), `montant_reclamation` (83,858) |
  | insurance-quebec | `date_naissance`, `code_postal`, `montant_reclamation` |
  | insurance-ontario | `id_client`, `courriel` and `id_contrat` (90,909 each), `date_naissance`, `code_postal`, `prime_annuelle`, `montant_reclamation` |
  | synthetic-1m | `birth_date` (23,725), `score` (81,610), `code` (99,893) |

  A file of fewer than 100,000 rows loses the exact distinct count of its
  identifiers (`insurance-ontario`: 7 columns). Exact counts come back only
  with the second pass (lot 7b), which `tabalyst scan` never starts by itself.
  For this reason T keeps its default of 100,000 and only the size K of the
  bottom-k sample is 10,000 (O28, amended 2026-10-07).
- **Workers.** Workers cut the first pass in half (26.0 to 12.0 s for the
  combined file, 48.5 to 11.4 s for the synthetic one) and multiply the peak
  memory by 3.6 and 3.4. The planner and the sampler must not make the main
  process the bottleneck: `analysis` is already the largest phase at 57%.
- **The report on top of the scan.** `report` takes the scan time plus about 4
  s (16.12 against 12.03 s). Rebuilding the report from a Scan document takes
  0.2 to 0.6 s for 1,000,000 rows, so presentation changes are cheap and a
  second pass added to `report` must be judged against the scan, not against
  this figure.

### Regression thresholds (PERF-06) and hash refusal

- A lot touching the hot path is blocked when the median first pass of the
  realistic file (`insurance-combined.csv`) is more than 20% slower than the
  baseline commit measured in the same session, or more than 10% slower with
  the diagnostics disabled. The worst-width file (30 columns including 5
  unique identifiers, to generate at lot 2a with `generate_data.py`) allows
  35%.
- Memory: the analytical memory plateau must not depend on the number of rows
  (PERF-05); the peak of the combined file stays within 10% of 715 MB.
- The hash of the bottom-k (design 18.8) is refused above these costs. The
  micro-benchmark of the candidates is lot 2a.

## Bottom-k hash (lot 2a)

Script `benchmarks/bottomk_hash.py`, same machine and interpreter as the
baseline above; results under `D:\GIT.test\tabalyst\artifacts\scan-json-lot2a\`
(`micro.json`, `engine-1.json`, `engine-auto.json`). The decision is in
[design.md](design.md) 18.8.

```powershell
.\.venv\Scripts\python.exe benchmarks\bottomk_hash.py micro
.\.venv\Scripts\python.exe benchmarks\generate_data.py --rows 1000000 --layout worst-width -o D:\GIT.test\tabalyst\bench\worst-width-1m.csv
.\.venv\Scripts\python.exe benchmarks\bottomk_hash.py engine D:\GIT.test\tabalyst\csv\insurance-combined.csv D:\GIT.test\tabalyst\bench\worst-width-1m.csv --repeat 5 --workers auto
```

**Cost per key** (nanoseconds, best of five over 200,000 distinct keys, the
encoding of the key included; identifiers of 12 characters, then words of 25 and
hexadecimal strings of 32):

| Function | Bits | 12 characters | 25 | 32 |
| --- | ---: | ---: | ---: | ---: |
| BLAKE2b, seeded state copied (retained) | 128 | 319 | 442 | 413 |
| BLAKE2b, seed as prefix | 128 | 404 | 583 | 491 |
| BLAKE2s | 128 | 374 | 502 | 385 |
| SHA-256 cut to 128 | 128 | 621 | 682 | 642 |
| SHA-1 cut to 128 | 128 | 633 | 852 | 688 |
| MD5 | 128 | 659 | 737 | 669 |
| SHAKE-128 | 128 | 911 | 1,027 | 904 |
| CRC-32 twice (refused) | 64 | 237 | 283 | 351 |
| builtin `hash()` (unstable, floor) | 64 | 71 | 75 | 73 |

**Quality.** KMV error on 50,000 sequential identifiers, K = 256, 12 seeds
(model RSE 6.3%): the RMS error is 4.4% (BLAKE2b state copied), 6.3% (salt), 7.6%
(BLAKE2s), 5.4% (SHA-256), 6.6% (SHA-1), 5.1% (MD5), 9.7% (SHAKE-128), all within
what 12 draws allow. The test does not separate the 128-bit candidates.

**The sampler itself.** Fed like the engine (batches of 4,096 distinct keys,
K = 10,000), five columns of one million unique identifiers take 3.8 s of
sampler time, 760 ns per occurrence (hash 320 to 440, the rest is the
dictionary lookup, the rank comparison and the compactions). `from_exact` on the
table of 100,001 keys of a released field: 116 ms. Memory at K = 10,000: 5.3 MB
per field, 550 bytes per entry.

**Effect on the first pass** (prototype of lot 2b: `ValueProcessor` patched in
every process to feed a sampler, K = 10,000, every released field and every
complete table of more than K keys; interleaved with the unpatched scan, one
fresh interpreter per run, median; the prototype converts keys and builds an
intermediate table, which the engine of lot 2b will not):

| File | Rows | Workers | Without (s) | With (s) | Overhead |
| --- | ---: | --- | ---: | ---: | ---: |
| insurance-combined.csv | 1,000,000 | default | 13.63 | 14.09 | +3.4% |
| worst-width-1m.csv (30 columns, 5 unique identifiers) | 1,000,000 | default | 16.87 | 17.77 | +5.3% |
| insurance-ontario.csv | 90,909 | default | 2.01 | 2.08 | +3.4% |
| insurance-combined.csv | 1,000,000 | 1 | 34.22 | 42.77 | +25.0% |
| worst-width-1m.csv | 1,000,000 | 1 | 59.02 | 87.04 | +47.5% |
| insurance-ontario.csv | 90,909 | 1 | 2.69 | 3.66 | +36.2% |

Five repeats for the default mode, three in one process. Variance is large in
one process (the combined file ran 33.3 to 43.2 s with the prototype), so those
three rows are an order of magnitude. A parallel scan hashes in the workers, so
the default mode is the reference of the thresholds (20% and 35%, design 18.8):
it passes with a wide margin. In one process the prototype exceeds them; lot 2b
brings it down and measures it again. The worst-width file is generated by
`generate_data.py --layout worst-width` (378,957,474 bytes, seed 42).

## JSON Inspect

The costs of JSON Inspect, of the interpretation resolver and of the JSON and JSONL
parcours (hash, event pass, Scan, report with a stored scan) are in
`docs/dev/inspect/benchmarks.md` (lot JI-8).

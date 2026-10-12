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

## Bottom-k in the engine (lot 2b)

Same method as lot 2a: the working tree against a `git worktree` of the base
commit (`b33f62d`, no sampler in the engine), alternated in one session, one
fresh interpreter per run, three series, median
(`benchmarks/scan_json_baseline.py`, tasks `scan` and `scan-single`). Memory is
the peak working set of the process plus the peak of each worker (an upper
bound of what is used at once).

| File | Mode | Base (s) | With (s) | Overhead | Peak base (MB) | Peak with (MB) |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| insurance-combined.csv | default | 13.94 | 14.44 | +3.6% | 796 | 934 |
| worst-width-1m.csv | default | 15.64 | 18.18 | +16.2% | 877 | 1,053 |
| insurance-ontario.csv | default | 2.26 | 2.19 | -3.1% | 776 | 893 |
| insurance-combined.csv | 1 process | 24.93 | 27.49 | +10.3% | 233 | 330 |
| worst-width-1m.csv | 1 process | 48.22 | 55.60 | +15.3% | 293 | 399 |
| insurance-ontario.csv | 1 process | 2.88 | 3.45 | +19.8% | 169 | 225 |

All rows are under the thresholds of design 18.8 (20% for the realistic file,
35% for the worst-width file); the small file in one process is 0.6 s over 2.9 s
and within the noise of the machine (the base itself ran 2.65 to 3.31 s). Run
to run the base moved by up to 20% (the worst-width file in one process ran 46.8
to 56.0 s), so a single pair of runs says little.

The first integration, which fed the sampler with generic keys, cost +31% on the
combined file and +32% on the worst-width file in one process. What brought it
down:

- A field of at most K distinct values pays no hash: a dictionary of original
  keys, in first-seen order (selection `all`), until K is exceeded.
- `update_strings` and `from_exact_strings` take the texts of a field of
  strings, hash them in a tight loop and build a key only for a text that can
  enter the sample. Once the sample is full a text above the limit is rejected
  with no tuple and no lookup, which is almost every text (K of a million).
- `from_exact` finds the K-th smallest priority first and ranks only the keys
  at or below it, instead of sorting every key of a table of T + 1.
- `Samples` validates plain dictionaries for its entries: that is 1.5
  microseconds an entry, against 2.5 for the model and 3 for `model_construct`.

Not changed, and worth knowing: the hash costs 0.27 microseconds a key, the
generic `update` 0.66 and `update_strings` about 0.43 once the sample is full.

**Weight of the Scan.** The three members added to each entry (`id`,
`count_accuracy`, `identity_accuracy`) make the indented document of the
combined file 31.3 MB (17.2 MB before the lot), and `insurance-ontario` 23.7 MB
(13.3). The number of entries did not change (up to K per field). The Report
built from a scan takes 1.8 s instead of 1.4 to 1.6 s (reading and ranking the
heavier scan). The compact `[value, count]` writing of Q1 is the lever if the
weight matters.

## Long texts and the memory budget (lot 2c)

Same method as lots 2a and 2b: the working tree against a `git worktree` of the
base commit (`e16eb51`, lot 2b), alternated in one session, one fresh interpreter
per run, three series (`benchmarks/scan_json_baseline.py`, tasks `scan` and
`scan-single`; driver and logs under `D:/GIT.test/tabalyst/artifacts/scan-json-lot2c/`).
The machine was about twice as slow as in lot 2b (the same base ran 26 s on the
combined file against 14 s), and it went to sleep during the series, so one run
of the working tree took 7 hours by the clock and one worst-width run took 50 s
instead of 24 s. Each series is therefore read as a pair, and the table gives the
median of the three paired ratios (with the raw pairs, outliers included).

| File | Mode | Paired ratios (with / base - 1) | Median |
| --- | --- | --- | ---: |
| insurance-combined.csv | default | -0.6%, +0.2%, -15.1% | -0.6% |
| worst-width-1m.csv | default | -0.3%, -0.1%, +109% (a 50 s run, noise) | -0.1% |
| insurance-ontario.csv | default | +0.6%, -3.9%, -4.0% | -3.9% |
| long-text-60k.csv | default | -2.7%, -6.4%, -1.8% | -2.7% |
| insurance-combined.csv | 1 process | -0.3%, (clock jump), +0.1% | +0.1% |
| worst-width-1m.csv | 1 process | +2.0%, +17.9%, +0.7% | +2.0% |
| insurance-ontario.csv | 1 process | -6.2%, +3.4%, -7.8% | -6.2% |
| long-text-60k.csv | 1 process | +8.8%, +7.7%, +13.4% | +8.8% |

All medians are under the thresholds of design 18.8 (20% for the realistic file,
35% for the worst-width file). The cost added to the hot path is one `len` per
new streamed value, a `max` of the lengths per column batch of a streamed
field, and counters that move only on admission, hit and compaction. Peak memory
is unchanged (937 against 938 MB on the combined file); the long-text file falls
from 757 to 713 MB, since long values no longer wait in 4,096-value batches.
The long-text file in one process costs +8.8% because the base did not hash its
long values (60,000 rows, 36,143 and 7,269 long occurrences in two columns; 158 MB
of text hashed in 43,412 distinct texts).

`long-text-60k.csv` is written by `generate_data.py --layout long-text` (205,679,978
bytes at 60,000 rows, seed 42): `description` (200 to 8,000 characters, a
common 400-character prefix, unique for 70% of the rows), `summary` (unique,
about 200 to 1,000 characters) and four short columns. The scan with the lot
keeps 100 long texts per column, scans in 5.5 s with workers and reports an
estimate of 59,297 distinct `summary` values for the 60,000 rows.

**Plateau of memory (PERF-05).** A scan of unique 4,000-character texts took
memory proportional to the number of rows: 7.7, 14 and 25 MB at 1,500, 3,000 and
6,000 rows, since a CSV batch held up to 4,096 rows whatever their size and the
streaming batch up to 4,096 values. Both batches are now closed by size
(`BATCH_BYTES` and `PENDING_CHARS`, 8 MiB), and
`test_memory_does_not_grow_with_unique_long_texts` checks that 4 times the rows
cost no more than 10% memory with small limits.

**Cost model of the samples.** A full bottom-k of 10,000 strings measures 540
bytes an entry at its peak (380 once compacted), whatever the length of the text,
since the strings are shared with the table they came from. The model counts 600
bytes plus two per character of the mean stored value (`memory.sample_entry_bytes`),
checked against `tracemalloc` by a test; the default budget of 512 MiB covers 34
columns of 10,000 values of 40 characters each (about 7 MB a column).

## Samples by length (lot 3a)

Same method as lots 2a to 2c: the working tree against a `git worktree` of the base
commit (`a7ce56f`, lot 2c), alternated in one session (the first tree alternates
from one series to the next), one fresh interpreter per run, three series
(`benchmarks/scan_json_baseline.py`, tasks `scan` and `scan-single`; driver and logs
under `D:/GIT.test/tabalyst/artifacts/scan-json-lot3a/`). Medians of the paired
ratios (new / base - 1). `insurance-ontario.csv` has two series only (its first was
a probe).

| File | Mode | Paired ratios | Median |
| --- | --- | --- | ---: |
| insurance-combined.csv | default | +5.1%, -2.8%, +3.4% | +3.4% |
| worst-width-1m.csv | default | +5.9%, +3.9%, +12.1% | +5.9% |
| insurance-ontario.csv | default | +0.2%, -0.3% | -0.0% |
| long-text-60k.csv | default | +4.4%, -7.5%, +0.1% | +0.1% |
| many-lengths-500k.csv | default | +8.5%, -3.9%, +0.8% | +0.8% |
| insurance-combined.csv | 1 process | -4.1%, -3.6%, +5.7% | -3.6% |
| worst-width-1m.csv | 1 process | +2.4%, -3.9%, -2.0% | -2.0% |
| insurance-ontario.csv | 1 process | +4.2%, +4.2% | +4.2% |
| long-text-60k.csv | 1 process | -2.4%, +19.5%, -0.9% | -0.9% |
| many-lengths-500k.csv | 1 process | +9.4%, +9.4%, +8.7% | +9.4% |

All medians are under the thresholds (20%, 35% for the worst-width file). The
added work per distinct key of a `bottom_k` field is a `len`, a dictionary lookup
and a comparison with the admission limit of the stratum; the priority is computed
once for the sample and its strata (`bottomk.string_priorities`), and only the keys
that can enter a stratum are handed to it. The worst-width file barely changes
because its identifiers all have one length. The peak memory moves by +0.1% to
+9% (combined 987 to 988 MB; the stress file 211 to 230 MB in one process); the
indented Scan grows by 0.1 MB (combined), 0.9 MB (worst width) and 2.8 MB
(long texts), the pool of values that the sample does not hold.

`many-lengths-500k.csv` (177,725,201 bytes) is a stress file written for this lot:
500,000 rows, `name` (3 to 40 characters), `comment` (10 to 200), `code` (6 to 12),
`wide` (1 to 400, so more lengths than the 64 tracked), a unique `id` and a
37-value `label`, random content. The file measured came from a one-off script of the same
distribution (seed 7, LF line ends); `generate_data.py --layout many-lengths` now
writes an equivalent one. It exercises the slow path of untracked lengths (`other`).

**Plateau of memory (PERF-05).** `test_memory_does_not_grow_with_the_number_of_lengths_met`
scans 8,000 and 32,000 rows with 40 lengths in cycle: the peak is within 10% (2.20
MB against 2.20 MB measured), once 30 strata of 20 values are full.

## Row sample (lot 3b)

**Priority of a position** (`benchmarks/rowsample_priority.py`, 1,000,000 positions, 64 bits
each, all distinct): a BLAKE2b call per position 0.27 to 0.29 s, a splitmix64 mix in Python
0.27 s, and the choice of the row sample, one BLAKE2b-512 call for a block of eight positions
and the eight little-endian words of its digest, 0.07 to 0.08 s. A hash that does not look at
the cells is what the row sample needs (ROW-05), and the block makes it 3.5 times cheaper.
Isolated sampler, 34 columns: 0.084 microseconds per row for the CSV batches (1,003,520 rows
in 0.084 s), 0.96 microseconds per record once the middle is full for single records (against
tens of microseconds of reading a JSON record).

**First pass.** Same method as lots 2a to 3a: the working tree against a `git worktree` of
the base, alternated in one session (the first tree alternates from one series to the next),
one fresh interpreter per run, three series (`benchmarks/scan_json_baseline.py`, tasks `scan`
and `scan-single`; driver and logs under `D:/GIT.test/tabalyst/artifacts/scan-json-lot3b/`).
The base is the state of lot 3a (commit `a7ce56f` plus the uncommitted lot 3a), so the figures
are the cost of the row sample alone. Medians of the paired ratios (new / base - 1):

| File | Mode | Paired ratios | Median |
| --- | --- | --- | ---: |
| insurance-combined.csv | default | +4.5%, +12.2%, -3.3% | +4.5% |
| worst-width-1m.csv | default | +2.6%, +8.9%, +5.8% | +5.8% |
| insurance-ontario.csv | default | -8.6%, -0.8%, +7.2% | -0.8% |
| long-text-60k.csv | default | -6.6%, -8.9%, -4.5% | -6.6% |
| insurance-combined.csv | 1 process | +2.0%, +4.5%, +12.8% | +4.5% |
| worst-width-1m.csv | 1 process | +25.1%, +1.7%, +4.7% | +4.7% |
| insurance-ontario.csv | 1 process | -0.0%, -5.0%, +6.6% | -0.0% |
| long-text-60k.csv | 1 process | -0.0%, +4.4%, -8.9% | -0.0% |
| synthetic-100k.jsonl (68 MB) | default | +2.7%, -7.2%, +5.2% | +2.7% |
| synthetic-100k.json (68 MB) | default | +5.2%, +9.0%, +3.3% | +5.2% |

All medians are under the thresholds (20%, 35% for the worst-width file). The +25.1% of the
first worst-width series in one process is the base's own variance: the same base took 56.8 s
in that series and 75.0 and 74.5 s in the next two, while the new tree took 71.1, 76.3 and
78.1 s (the paired ratio of the last two is +1.7% and +4.7%). The peak memory moves by +0.1% to
+1.3%. The CSV path stays the batch path: the row sample takes the rows of a batch as they
are, once per batch, and projects only the 50 first rows, the rows admitted to the middle
(a few thousand for a million rows) and the 50 last. The indented Scan (`json.dumps(indent=2)`, the figure the
script reports) grows by 2.8 MB (combined), 2.6 MB (worst width), 2.7 MB (ontario), 1.1 MB (long
texts) and 2.0 MB (JSONL). As written (`dump_json`), the Scan of insurance-ontario grows from
10.4 to 11.2 MB compact (the default) and from 13.6 to 14.5 MB with `output.json_indent`, where
each row takes one line.

**Model of the memory.** `rowsample.TABLE_ROW_BYTES` and the other constants are checked against
`tracemalloc` by tests: for rows of 5, 30 and 100 columns the model is 0.98 to 1.15 times the
measure (table rows) and 1.02 to 1.37 times (records). The plateau test feeds 5,000 and 40,000
rows through a sample of 200: the retained memory is the same within 10%.

## Pattern inference (lot 4a)

The inference runs once after `finalize`, reads the samples (at most about 16,000 distinct
values per field with the default sizes) and never the source, so its cost does not grow with
the number of rows. It is measured by the scan itself (`run.timings.derived`), in the default
mode, one fresh interpreter per run, three runs per file (script and log under
`D:/GIT.test/tabalyst/artifacts/scan-json-lot4a/`). Because the inference runs after the pass,
it is compared with the duration of the same run and no alternation with a base is needed:

| File | Scan | Inference (3 runs) | Share |
| --- | ---: | ---: | ---: |
| insurance-combined.csv (1 M rows, 34 columns) | 16.1 to 16.3 s | 0.09 to 0.10 s | 0.6% |
| insurance-ontario.csv | 2.3 to 2.5 s | 0.14 to 0.15 s | 6.3% |
| long-text-60k.csv | 2.8 s | 0.08 s | 2.9% |
| many-lengths-500k.csv | 4.7 to 4.9 s | 0.43 to 0.54 s | 10.2% |

All shares are under the threshold of 20%. The share is higher on smaller scans (the cost is
constant and the scan is short) and on `many-lengths-500k.csv`, where the text columns have
very many structures and the generalization ladder tokenizes their values three times. The
patterns of a 34-column scan weigh about 27 KB compact (25 KB for `insurance-ontario`), 83 KB
indented, against 6 MB for the whole indented Scan of the 3,000-row example.

## Observations and adaptive normalization (lot 4b)

The observations are built once after the patterns, from the counters of the finished datasets
and without the samples, so their cost is a function of the number of fields. The adaptive
normalization is decided at finalization from counters that exist already. No hot path is
touched. Compared with the commit of the lot 4a (`647bac6`, a `git worktree` under
`D:/GIT.test/tabalyst/worktrees/base-4b`), one fresh interpreter per run, alternating, three
series, medians (script and results under `D:/GIT.test/tabalyst/artifacts/scan-json-lot4b/`):

| File | Scan duration | `finalize` | `derived` (patterns + observations) | Observations alone |
| --- | ---: | ---: | ---: | ---: |
| insurance-combined.csv (1 M rows, 34 columns) | 14.16 to 14.18 s (+0.1%) | -2.0% | 0.088 to 0.107 s | 0.011 s |
| insurance-ontario.csv | 2.36 to 2.31 s (-2.0%) | -0.5% | 0.135 to 0.142 s | 0.006 s |
| many-lengths-500k.csv | 4.56 to 4.39 s (-3.7%) | -8.6% | 0.455 to 0.475 s | 0.003 s |
| long-text-60k.csv | 2.75 to 2.64 s (-3.9%) | -2.0% | 0.070 to 0.073 s | 0.002 s |
| worst-width-1m.csv (30 columns) | 17.77 to 17.64 s (-0.7%) | -2.3% | 0.537 to 0.545 s | 0.009 s |

All differences are inside the dispersion between sessions (about 20%, lot 0) and under the
threshold of 20%. The first version of the walker of `limited` envelopes entered the lists of
samples (up to 10,000 entries per field) and cost 0.17 to 0.49 s; it now enters only the stages
of the normalization, which took the observations from 0.49 s to 0.011 s on the combined file. The
`observations` member weighs 1.8 to 8 KB compact (6.5 KB for the combined file, with
16 observations and 24 limits), against 1.3 to 14 MB for the Scan.

## The report reads the findings (lot 5)

Lot 5 touches the Report and the HTML, and removes `records.preview` from the Scan: the
collection of the first records disappears from the hot path of `RecordFacts.add` and
`add_batch`, nothing is added to it. Compared with the commit of the lot 4b (`38d5353`, a
`git worktree` under `D:/GIT.test/tabalyst/worktrees/lot5-head`), one fresh interpreter per
run, alternating, three series, medians (script `D:/GIT.test/tabalyst/artifacts/lot5_perf.py`,
`tabalyst scan` then `tabalyst report --scan`, the HTML and JSON of the second):

| File | Scan | Report from the scan | HTML | JSON |
| --- | ---: | ---: | ---: | ---: |
| insurance-ontario.csv (90,909 rows) | 3.33 to 3.20 s (-3.9%) | 1.35 to 1.33 s (-1.5%) | 500 to 615 KB (+23%) | 750 to 761 KB (+1.5%) |
| insurance-combined.csv (1 M rows) | 15.49 to 15.31 s (-1.2%) | 1.48 to 1.51 s (+2.0%) | 542 to 644 KB (+19%) | 763 to 765 KB (+0.2%) |

The Scan is not slower. The report builds its views (observations, limits, patterns, rows,
distinct count) in a fraction of its time and prints a bounded page (`DISPLAY_LIMITS`): the HTML
grows by the three sections it adds (observations, patterns, 30 rows of 34 cells), not with the
size of the file. The JSON loses `issues`, `preview` and `limits` and gains 30 rows instead of 10.

## Planner (lot 6a)

Lot 6a adds no code to the first pass: `scanner/api.py`, the engine, the value processors and the
readers are unchanged (`git diff --stat` of the lot touches `scanner/identity.py` only, where
`facts_sha256` moved from `scan_document.py`). The Scan is therefore not compared with an earlier
commit; what is measured is the planner, which runs after a scan and reads the finished document
(script `D:/GIT.test/tabalyst/artifacts/lot6a_perf_plan.py`, best of three calls in
one process):

| File | Fields | Facts of the fields | `facts_sha256` | `plan_analyses` | Plan JSON |
| --- | ---: | ---: | ---: | ---: | ---: |
| insurance-combined.csv (1 M rows) | 34 | 0.1 ms | 8.4 ms | 16.6 ms | 82 KB |

The plan has 126 candidates for the 34 fields (33 selected, 76 already answered by the Scan, 17
left out) and a firm memory maximum of 216.5 MB of the 256 MiB budget: the exact distinct sets of
the identifier-like fields are charged with the number of values read, which is why the maximum
is far above the expected 160 MB. Planning cost is linear in the number of fields (a few
candidates each, no value read); `facts_sha256` is the largest part and is the same function the
Report already pays. The thresholds and the size constants are provisional until lot 6b.

## Costs and budgets of the planner (lot 6b)

Lot 6b touches no file of the first pass (`git diff --stat` of the lot has nothing under
`scanner/` but `planner/`), so the Scan is not compared with an earlier commit. What is
measured is the cost model, with `benchmarks/planner_costs.py` (results under
`D:/GIT.test/tabalyst/artifacts/`), and the planner on the finished Scan of the combined file.

```powershell
.\.venv\Scripts\python.exe benchmarks\planner_costs.py structures --entries 1000000
.\.venv\Scripts\python.exe benchmarks\planner_costs.py reader D:\GIT.test\tabalyst\csv\insurance-ontario.csv
.\.venv\Scripts\python.exe benchmarks\planner_costs.py cpu --cells 1000000
```

**Bytes an entry holds** (`tracemalloc`, 200,000 and 1,000,000 entries, held at rest and peak
while growing): a set of texts of 8, 12, 24, 48 and 64 characters 82.6 to 90.9, 86.6 to 94.9,
98.6 to 106.9, 122.6 to 130.9 and 138.6 to 146.9 bytes (41 of header and terminator, the
characters, and a slot of 25.5 at one million entries to 34 at 200,000), peak up to 104.6 for 12
characters at 200,000 entries; a set of integers 65.6 to 73.9, peak 88.1; a table of counts
98 to 101 for a key of 10 characters; a dense counter 8 bytes. The slot of a set lies between 27
bytes (60% of load) and 53 (30%, right after it grew), and the old and the new table coexist
while it grows: the model takes 27, 37 and 80 bytes for its minimum, expected and maximum.
`EXACT_ENTRY_BYTES` of lot 6a (64) was 30% too low for a set of identifiers; `MATCHER_BYTES`
(a compiled matcher measures 2.2 to 4.4 KB) went from 4,096 to 5,120.

**Reading the source once** (peak traced memory while the reader yields and drops every item):
7.3 MB for `insurance-ontario.csv` and `insurance-quebec.csv`, 8.2 MB for `worst-width-1m.csv`,
4.2 MB for `synthetic-100k.json`, 19.0 MB for `long-text-60k.csv` (texts of up to 8,000
characters). The reserve for the parser, counted once whatever the number of analyses, went from
16 to 24 MiB.

**Work added to a cell** (nanoseconds, loop overhead removed, values already parsed, one
million cells, a machine busy with the test suite for the last run): a dense counter 15, a
length 22, a bin 42, a period of a date 35, a table of counts 43, a set of unique texts 127 to
154, a compiled matcher 98 per candidate. For comparison the first pass spends about 600 ns a
cell in one process (20.6 s for 34 million cells) and reads at 8.5 million cells a second
(4.0 s). The constants (`NS_PER_CELL`) round these up; they are proxies, replaced by the
executor's own measures at lot 7a.

**The planner on the combined file** (1,000,000 rows by 34 columns, 34 million cells, Scan
stored by `tabalyst`, best of three, script `lot6b_perf_plan.py`):

| Plan | Time | Candidates | Selected | Memory min, expected, max | Estimated time | Confirmation |
| --- | ---: | ---: | ---: | --- | --- | --- |
| Automatic | 11 ms | 126 (76 satisfied, 20 left out) | 30 | 31, 34 and 39 MiB | 3.9 to 7.8 s | no |
| Forced | 11 ms | 126 (76 satisfied, 17 left out) | 33 | 54, 217 and 416 MiB | 4.2 to 9.0 s | yes, `memory_over_automatic` |

With the model of lot 6a the automatic plan chose 33 analyses with a firm maximum of 216.5 MB;
with the corrected sizes the three identifiers of a million values (127 to 129 MiB each) no
longer fit the 128 MiB of an automatic choice and wait for `--deep`, which asks first. The
estimates come from a reading phase of 5.6 s on the stored Scan (the baseline measured 4.0 s);
the planner's own cost is unchanged by the lot and stays linear in the number of fields.

The costs of JSON Inspect, of the interpretation resolver and of the JSON and JSONL
parcours (hash, event pass, Scan, report with a stored scan) are in
`docs/dev/inspect/benchmarks.md` (lot JI-8).

## Second pass (lot 7a)

The first pass is untouched: the lot moves `_open_reader` and `_peak_memory_bytes` out of
`scanner/api.py` (to `readers/factory.py` and `scanner/process.py`) without changing the
loop, so the Scan is not compared with the earlier commit. What is measured is the
executor, with `benchmarks/planner_costs.py executor` (best of two or three runs, results
under `D:/GIT.test/tabalyst/artifacts/`), and a real `tabalyst scan --deep`.

```powershell
.\.venv\Scripts\python.exe benchmarks\planner_costs.py executor D:\GIT.test\tabalyst\csv\insurance-combined.csv --repeat 2
.\.venv\Scripts\python.exe benchmarks\planner_costs.py executor D:\GIT.test\tabalyst\csv\insurance-ontario.csv --repeat 3
$env:TABALYST_HOME = "D:\GIT.test\tabalyst\home-7a-bench"
.\.venv\Scripts\python.exe -m tabalyst scan D:\GIT.test\tabalyst\csv\insurance-combined.csv --deep -v
```

**Cost of a cell** (the analysis time of the run divided by the cells handed to the
analyses; the reading, which is shared, is separate). `insurance-combined.csv`, 1,000,000
rows by 34 columns, 34 million cells:

| Analysis | Cells handled | Reading | Analysis | Per cell | Model (firm bytes) | Peak traced |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Counters of integers (2 columns) | 2,000,000 | 3.44 s | 1.68 s | 841 ns | 0.60 MB | 8.3 MB |
| Bins of decimals (2 columns) | 2,000,000 | 3.12 s | 3.32 s | 1,661 ns | 0.57 MB | 9.4 MB |
| Lengths (22 text columns, Scan's histogram turned off) | 22,000,000 | 3.28 s | 4.54 s | 207 ns | 5.83 MB | 9.2 MB |

`insurance-ontario.csv` (90,909 rows) gives 666 and 1,658 ns for counters and bins, and 8.2
and 9.3 MB at the peak: the memory held does not depend on the number of records (PERF-05).
It is the reader (7 to 8 MB, 24 MiB reserved by the model) and the states, far under their
firm bounds. The cost of a counter or a bin is mostly what is done to a cell before it is
counted, the same as in the first pass (profile of the bins on the Ontario file: the reader 36%,
the replay of the cells 49%, of which the number detector 23%, the counting and the
placement in a bin 6%); lengths are cheaper
because they need no number and the strings of a text column repeat. The reading phase of
the second pass (3.1 to 3.4 s) is 0.72 to 0.79 of the `run.timings.reading` of the first
(4.3 s), above the 0.6 that the estimate takes as its lowest share.

**The constants.** `NS_PER_CELL` takes 900 ns for a counter of integers, 1,800 for a bin and
250 for a length (rounded up from 841, 1,661 and 207), where lot 6b had proxies of 20, 50 and
30 on values already parsed. The CPU class limits move from 50, 200 and 800 ns to 100, 600 and
2,400 (the first pass spends about 600 ns on a cell), so a counter and a bin are `moderate` and
a length is `low`; with the old limits a bin of a decimal would have been `high` and never
chosen by the Report. `COST_MODEL_VERSION` is 2. The memory model adds the cells remembered per
field (1,024 strings at 250 bytes) and 280 bytes per edge of a bin; it stays far over what the
runs held (conservative by a factor of 3 or more).

**A real run** (`tabalyst scan --deep` on the combined file, Scan stored by the first call):

| Run | Result |
| --- | --- |
| Forced, with what the executor can run | 4 analyses (two counters, two bins), 4,000,000 cells, 7.6 s (reading 3.3 s, analysis 4.3 s), estimated 4 to 11 s; `deep.json` of 317 KB; no confirmation |
| Again | 1.0 s in all: every result is stored, the source is not read, the file is not rewritten |
| `scan --plan --deep` (all analyzers) | 33 selected, 54 to 417 MiB, estimated 5 to 14 s, confirmation `memory_over_automatic`; 29 of them cannot run yet |

Planner on the finished Scan (best of three): automatic 11 ms, 30 selected, 31 to 40 MiB,
estimated 4.7 to 12.8 s; forced for the executor's analyzers 9 ms, 4 selected, 24 to 25 MiB,
estimated 4.3 to 11.3 s, no confirmation. The medians of the two integer columns are exact
(5,002 and 500); those of the two decimal columns are estimates with bounds.

## Exact distinct and exact frequencies (lot 7b)

The first pass is untouched (`git diff --stat` of the lot has nothing in `scanner/` but
`planner/` and `secondpass/`), so the Scan is not compared with an earlier commit. What is
measured is the exact set, with `benchmarks/planner_costs.py` (`exact` and `executor`,
results under `D:/GIT.test/tabalyst/artifacts/`), and a real `tabalyst scan --deep`.

```powershell
.\.venv\Scripts\python.exe benchmarks\planner_costs.py exact --entries 1000000
.\.venv\Scripts\python.exe benchmarks\planner_costs.py executor D:\GIT.test\tabalyst\csv\insurance-combined.csv --repeat 2
.\.venv\Scripts\python.exe benchmarks\planner_costs.py executor D:\GIT.test\tabalyst\csv\exact-table-1m.csv --repeat 2 --max-samples 100
$env:TABALYST_HOME = "D:\GIT.test\tabalyst\home-7b-bench"
.\.venv\Scripts\python.exe -m tabalyst scan D:\GIT.test\tabalyst\csv\insurance-combined.csv --deep --yes -v
```

**Which key.** Candidates measured on one million distinct identifiers (a script outside the
repository, `tracemalloc`, then the same without it for the time of a batch of 4,096 distinct
values):

| Representation | Bytes an entry (at rest) | ns a distinct value |
| --- | ---: | ---: |
| set of strings of 12 characters (key 53 + slot 34) | about 87 | 69 |
| set of integers, one set per length (strings of digits) | 66 | 237 (with `isdigit`, `isascii` and the length) |
| set of integers, ASCII packed with a sentinel | 74 | 241 |
| open-addressing table in two `array('Q')`, 128-bit keys | 36 at rest, 70 at the peak | about 15,000 |

Only the digit strings get the compact key (ADR `2026-10-09-exact-distinct-keys.md`).

**The exact set** (`planner_costs.py exact`, 1,000,000 distinct values, the strings are built
inside the trace): bytes an entry held, peak, and the bytes the executor charges to its pool.

| Identifiers | Held | Peak | Charged | ns a value (with the generation of the string) |
| --- | ---: | ---: | ---: | ---: |
| 8 digits | 61.5 | 68.3 | 65.6 | 417 |
| 10 digits | 65.5 | 70.9 | 65.6 | 352 |
| 12 digits | 65.5 | 70.9 | 65.6 | 355 |
| 8 characters, letters and digits | 82.6 | 82.7 | 82.6 | 500 |
| 10 characters | 84.6 | 84.7 | 84.6 | 552 |
| 12 characters | 86.6 | 86.7 | 86.6 | 549 |

The charge is the measure, so a limit is met at the bytes the plan stated. The firm bound of
the plan for a 12-character identifier is 133 MB for a million values (41 + 12 + 80 bytes, plus
27 for the first 50,000), 1.5 times what is held.

**Cost of a cell** (the analysis time of the run divided by the cells handed to the analyses,
the reading separate; `insurance-combined.csv` 1,000,000 rows by 34 columns, and
`exact-table-1m.csv`, 1,000,000 rows of four fields of 300, 500, 700 and 900 values and a
sequence):

| Analysis | Cells handled | Reading | Analysis | Per cell | Model (firm bytes) | Peak traced |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Exact sets (4 fields of up to one million values) | 4,000,000 | 3.30 s | 1.49 s | 373 ns | 416.6 MB | 201.9 MB |
| Exact set (1 identifier field of 1,000,000 values) | 1,000,000 | 0.90 s | 0.32 s | 317 ns | 128.4 MB | 77.6 MB |
| Tables of frequencies (4 fields) | 4,000,000 | 0.79 s | 0.43 s | 108 ns | 1.39 MB | 4.0 MB |

The counters, bins and lengths of lot 7a, run again in the same session on a machine that was
not otherwise idle, gave 956, 1,516 and 182 ns, against 841, 1,661 and 207: the constants of
the model (900, 1,800, 250) are kept. `NS_PER_CELL` takes 400 ns for a key of an exact set and
120 for an entry of the table (rounded up), both class `low`. `COST_MODEL_VERSION` is 3.

**A real run** (`tabalyst scan --deep --yes` on the combined file, Scan stored by the first
call): 8 analyses (two counters, two bins, four exact sets), 7,000,000 cells, 10.6 s (reading
3.6 s, analysis 7.0 s; estimated 5 to 14 s); the plan asked first (`memory_over_automatic`,
firm bound 443 MB); the process peak is 438 MB; `deep.json` is 360 KB. The exact numbers of
distinct values: `id_client` 1,000,000 (unique), `id_contrat` 1,000,000 (unique, the KMV
estimate of the Scan said 984,843), `code_postal` 130,082 (131,022), `montant_reclamation`
115,667 (115,800). Run again: 0.9 s, the source is not read.

## Patterns, dates and the second pass of the Report (lot 7c)

Machine: the one of lots 7a and 7b, not idle during the measures (the counters of integers took
1,142 to 1,252 ns a cell against 841 at lot 7a, so the figures below are 30 to 50% above a quiet
machine). Both commands read the combined file of lot 0 (1,000,000 rows by 34 columns).

**Cost of a cell** (`planner_costs.py executor --max-samples 1000`: the Scan keeps a sample of
1,000 values, so the patterns need the source; the analysis time of the run divided by the cells
handed to the analyses, the reading separate):

| Analysis | Cells handled | Per cell | Model | Peak traced |
| --- | ---: | ---: | ---: | ---: |
| Pattern validation (3 fields, 5 candidates), token loop only | 3,000,000 | 1,788 ns (1,073 a candidate) | | |
| Pattern validation, compiled regular expressions for ASCII values | 3,000,000 | 633 to 722 ns (380 to 430 a candidate) | 800 + 100 a candidate | 7.4 MB |
| Dates per period, the memory of 1,024 strings of the other analyses | 5,000,000 | 1,700 to 1,964 ns | | 9.2 MB |
| Dates per period, 16,384 strings remembered (`PERIOD_MEMO_ENTRIES`) | 5,000,000 | 674 ns | 800 | 23.5 MB (firm 34.4 MB) |

A value of an ASCII text is read by a possessive regular expression, `{low,high}+` for every
repeat (the semantics of the greedy matcher of the grammar, no backtracking); the token loop,
kept for the other values, cost about 2.8 times more on these fields. The date detector is the
expensive part of a date: a column of days repeats the same strings from one batch to the next,
and a memory of 1,024 strings, enough for the other analyses, read the same dates again every
time (2,658 distinct dates in `date_debut`). `NS_PER_CELL` is 800 ns for the field of a pattern
validation plus 100 for each candidate (`matcher_base`, `matcher`) and 800 for a period, all
class `moderate`; `COST_MODEL_VERSION` is 4. The planner estimates the plan of the combined file
at 12 to 41 s before the dates were remembered (30 analyses, 13 of them reading the source).

**Overhead of the Report** (`benchmarks/report_overhead.py`, each case in its own storage, wall
time of `tabalyst report` including the interpreter and the files):

| Case | Wall time | Scan | Second pass | Reading of the second pass | Analyses | Peak (process) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `off` (`deep.mode` off, no second pass) | 20.9 s | 18.5 s | none | none | 0 | 355 MB |
| `auto` (the planner decides) | 38.3 s | 19.2 s | 16.7 s | 4.5 s | 30 (13 read the source) | 400 MB |
| `warm` (`auto` again on the same storage) | 1.8 s | reused | 0.0003 s | none | 30 reused | 266 MB |
| `forced` (`--deep --yes`) | 39.6 s | 18.4 s | 18.7 s | 5.1 s | 33 | 459 MB |

The automatic second pass adds 17.4 s to a report of 20.9 s, 84%: above the 50% I proposed as the
point from which the overhead is worth a decision, and it reads 12 million cells, a tenth of the
100 million that an automatic choice may take (decision O36). It was 23.8 s (+105%) before the
dates were remembered. The estimate of the plan (12 to 41 s) holds the measure. The JSON grows
from 0.76 to 1.19 MB (the embedded second-pass document, with the plan of 126 candidates), the
HTML from 0.65 to 0.76 MB. On `examples/input/insurance-customers.csv` (3,000 rows) the report
takes 1.8 s against 1.7 s without it (the second pass is 0.07 s of 29 analyses). The lever, if the overhead is too much, is the automatic
budget of 20.2, which is deterministic and recorded in the plan.

## Pairs of numeric columns (lot 8a)

`benchmarks/planner_costs.py executor` on the combined file (1,000,000 x 34, one reading,
`pearson` among the analyses of a forced plan):

| Measure | Value |
| --- | ---: |
| Planning of the forced plan, exploration of the pairs included | 0.021 s |
| Pairs run | 2 (3,000,000 cells handled: 3 columns, each converted once) |
| Reading | 4.9 s |
| Analysis (conversion of the columns and the co-moments) | 5.9 s |
| Per cell of a column of a pair, shared columns counted for every pair | 1,467 ns |
| Firm bound of the model | 1.16 MB |
| Peak traced | 7.95 MB (the reading included, which the model counts apart) |

`NS_PER_CELL["pearson"]` is 1,500 ns, class `moderate`, rounded up from 1,467; a column shared by
several pairs is read once, so the estimate of a plan with shared columns is an upper bound.
`COST_MODEL_VERSION` is 5. The exploration of the row sample is bounded by
`deep.pearson.max_columns` (50) and `max_work` (1,000,000 pairs times rows), and costs well
under a second: 21 ms here.

**Overhead of the Report with pairs** (`benchmarks/report_overhead.py`, same file and cases as lot 7c): `off` 19.8 s,
`auto` 36.4 s (second pass 16.2 s, 30 analyses, 12 million cells read, no pair reached the automatic bound on this
file), `warm` 1.85 s. The pairs add nothing here to the +84% measured at lot 7c, which stays to be decided by the
maintainer; the planning of the pairs costs 21 ms.

## Tables of a category against a feature (lot 8b)

`benchmarks/planner_costs.py executor` on the combined file (1,000,000 x 34, one reading per kind
of analysis, two repeats; the machine was not idle: the counters of integers took 1,470 ns a cell
against 841 at lot 7a). Tables chosen by the exploration of a forced plan, which share their columns:

| Feature | Tables | Cells handed (a shared column counted once) | Per cell handed | Per cell of each table | Model |
| --- | ---: | ---: | ---: | ---: | ---: |
| Pattern | 5 | 7,000,000 | 445 ns | 312 ns | 600 ns |
| Length | 5 | 8,000,000 | 412 ns | 330 ns | 500 ns |
| Prefix | 10 | 14,000,000 | 230 ns | 161 ns | 300 ns |

The planner charges each table both its columns, so its estimate is an upper bound for tables that
share one (a column of the combined file served up to five tables). The three are class `low`.
`NS_PER_CELL["crosstab_pattern"]`, `["crosstab_length"]` and `["crosstab_prefix"]` are rounded up from
the measure; `COST_MODEL_VERSION` is 6. The plan of the forced second pass, exploration of the tables
and of the pairs included, took 0.156 s (21 ms at lot 8a for the pairs alone). The firm bound of the
model is 3.6 to 7.1 MB for 5 to 10 tables, the traced peak 7.7 to 8.1 MB with the reading.

The refactor of `PatternAccumulator` (the classifier is shared with the tables) kept the loop of the
validation inline: calling `PatternClassifier.classify` for each distinct value costs 80 ns more on a
column of identifiers (296 against 215 ns, 300,000 distinct values, one candidate), so the loop is
repeated in `add_strings` and the figures of lot 7c still hold (221 against 214 ns).

On `examples/input/insurance-customers.csv` (3,000 rows, 34 columns) the exploration of the tables
costs a fraction of the 0.12 s of the whole second pass of the Report (44 analyses, 8 of them tables).

**Overhead of the Report with tables** (`benchmarks/report_overhead.py`, same file and cases as lots 7c and 8a):

| Case | Wall time | Scan | Second pass | Reading of the second pass | Analyses | Cells read | Peak (process) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `off` | 20.8 s | 18.6 s | none | none | 0 | none | 356 MB |
| `auto` | 43.0 s | 18.7 s | 22.0 s | 5.1 s | 38 | 25 million | 402 MB |
| `warm` | 1.9 s | reused | 0.0003 s | none | 38 reused | none | 267 MB |
| `forced` (`--deep --yes`) | 51.5 s | 18.9 s | 29.8 s | 4.9 s | 55 | 37 million | 464 MB |

The automatic second pass now adds 22.2 s to a report of 20.8 s, **+107%** (+84% at lots 7c and 8a, 38.3 s and
36.4 s). The planner picks eight tables by itself on this file (`automatic_tables`), which add 8 analyses, 13 million
cells and about 5 s to the second pass; the estimate stays within `low`. The JSON grows from 1.19 to 1.28 MB and the HTML
from 0.76 to 0.87 MB. The levers, if the overhead is too much, are `deep.crosstab.automatic_tables` (a default of 8) and
the automatic budget of 20.2 (decision O36); both are deterministic.

## Selection of a smart sample (lot 10b)

`tabalyst sample --sample-method smart` on the reference files, with the Scan stored (one reading). The machine
was slower than at lot 0 (the first pass of `insurance-combined.csv` took 20 s against 10.5 s at the baseline).

| File | Rows | Targets (tested columns) | Selection | Peak, process | Pool |
| --- | ---: | ---: | ---: | ---: | ---: |
| `insurance-ontario.csv` | 90,909 | 256 | 1.8 s (20 us a row) | 225 MB | 0.5 MB, 2,040 rows |
| `insurance-combined.csv` | 1,000,000 | 345 (31) | 35.0 s (35 us a row) | 259 MB | 1.4 MB, 5,035 rows |

On the combined file the Scan loaded takes 254 MB and the selection adds 5 MB: the memory of the selection does
not depend on the number of rows (PERF-05). The first version took 2.4 s and 37.7 s: the profile showed the numeric
targets (ten bins, one test each) placing every number ten times and the offer of every row to every target it
covers; the numbers are now placed once and a row that cannot beat the worst candidate of a full target is
skipped before the call. What is left is the first pass's reading of the cells (dates and numbers of the columns
that have a test, remembered per distinct string) and the csv parsing. `SELECT_NS_PER_CELL` (600) and
`SELECT_NS_PER_ROW` (2,000) put the model at 35 s at its centre for the combined file, in a range of 23 to 65 s.
All the 260 exact counts of the plan on the combined file were found again by the reading (`verification`).

## Final matrix, limited profile (lot 11, F07)

The matrix of the specification (17.2) was run in a **limited profile**, by decision of the maintainer: at most
1,000,000 rows and 100 columns, two repeats, medians. The complete matrix (2,000,000 rows, 500 and 1,000 columns, three
repeats of every task) is deferred to the end of the plan. Engine 0.6.2 at commit `810e701` plus the changes of the lot,
the same machine as lot 0 (24 logical CPUs), default workers. Script:

```powershell
.\.venv\Scripts\python.exe benchmarks\final_matrix.py --root D:\GIT.test\tabalyst\bench\matrix --out D:\GIT.test\tabalyst\artifacts\lot11-matrix --repeat 2 --existing D:\GIT.test\tabalyst\csv\insurance-combined.csv D:\GIT.test\tabalyst\bench\worst-width-1m.csv D:\GIT.test\tabalyst\bench\many-lengths-500k.csv D:\GIT.test\tabalyst\bench\long-text-60k.csv
```

The new files are written by `benchmarks/matrix_layouts.py` (deterministic, seed 42, under `D:\GIT.test\tabalyst\bench\matrix`).
Tasks of `scan_json_baseline.py`: `scan`, `report-off` (`deep.mode` off), `report` (the second pass the planner chooses)
and `smart-sample` (0.5% of the rows, the Scan made first and not timed, the selection timed alone). Phases are those of
`run.timings`, the second pass and the selection are separate documents with their own times (PERF-01). Peak memory adds
the peak of every worker to the one of the process.

| Case (rows) | Scan (s) | Peak (MB) | Report without / with second pass (s) | Smart selection (s) | Matrix risk |
| --- | ---: | ---: | --- | ---: | --- |
| low-cardinality (1,000,000 x 11) | 4.31 | 569 | 4.52 / 7.00 | 5.78 | lookups and counters |
| transition K-1, K, K+1 (200,000 x 3, 9,999 to 10,001 distinct) | 1.00, 1.03, 1.08 | 115 | 1.36, 1.35, 1.45 / 1.59, 1.64, 1.71 | 0.80 to 0.88 | exact to estimated at K |
| transition T (100,000 distinct) | 1.30 | 141 | 1.62 / 1.96 | 0.94 | exact to limited at T |
| high-cardinality (1,000,000 x 8) | 10.62 | 941 | 10.92 / 23.11 | 31.64 | hash, heap, memory after overflow |
| short-ids (1,000,000 x 7, 8 to 12 characters) | 6.68 | 836 | 7.88 / 19.21 | 18.79 | compact exact set |
| worst-width (1,000,000 x 30, 5 unique identifiers) | 21.26 | 1,190 | 22.46 / 58.35 | 57.01 | shared budget |
| long-text (60,000 x 6) | 3.19 | 817 | 3.56 / 4.50 | 2.27 | bounded previews, hashing |
| many-lengths (500,000 x 6) | 5.48 | 815 | 6.16 / 11.67 | 9.04 | states of the strata |
| realistic insurance (1,000,000 x 34) | 19.74 | 1,019 | 20.64 / 43.23 | 23.80 | reference |
| repeated (550,000 x 20, half of the rows repeated) | 9.71 | 1,043 | 10.61 / 31.03 | 25.72 | fixed cost against distinct values |
| wide-100 (200,000 x 100) | 22.83 | 1,722 | 27.65 / 35.91 | 42.04 | row sample, pairs |
| growth 250k, 500k (x 8, high-cardinality layout) | 4.48, 6.26 | 872, 895 | 4.99, 6.75 / 9.12, 13.05 | 7.36, 14.88 | plateau |
| growth 1M (the high-cardinality row above) | 10.62 | 941 | 10.92 / 23.11 | 31.64 | plateau |
| normalization without effect (500,000 x 4) | 2.54 | 567 | 3.09 / 3.96 | 3.15 | cost of unused normalization |
| normalization with late effect (500,000 x 4) | 2.55 | 572 | 3.08 / 4.10 | 3.12 | exactness of the impacts |

What it shows:

- **Plateau of memory (PERF-05).** Rows 250,000, 500,000 and 1,000,000 of the same layout peak at 872, 895 and 941 MB:
  4 times the rows add 8%, and what grows is the tables the limits bound, not a function of N.
- **Transition around K and T.** The first pass costs the same at 9,999, 10,000 and 10,001 distinct values (1.00, 1.03,
  1.08 s). Crossing T = 100,000 adds 0.2 to 0.3 s, the release of the table.
- **The selection of a smart sample** reads the source once. Its time is the reading of the cells that have a test,
  and the reading of a cell is remembered per distinct string, so it depends on how many distinct values the tested
  columns hold: 0.7 us a cell on the realistic file, 2.6 us on short identifiers, 3.7 us on nearly all distinct
  columns. Its memory is the Scan loaded plus a bounded pool (`verification` found the exact counts of the plan on every
  file that was run).
- **Overhead of the second pass of the Report** (PERF-07), `report` against `report-off`: +2.5 s (low cardinality),
  +12 s (high-cardinality), +11 s (short identifiers), +21 s on the realistic file, +36 s on the worst-width file,
  +8 s on a hundred columns. It is time the second pass reads and counts, published beside the Scan.

### Against the base commit, in the same session (PERF-06)

`0acf126` (the baseline of lot 0) in a `git worktree`, the head, alternated three times, task `scan`, default workers:

| File | Base (s), three runs | Head (s), three runs | Median | Peak memory (MB) |
| --- | --- | --- | --- | --- |
| insurance-combined.csv | 16.68, 16.41, 15.93 | 18.64, 19.14, 18.67 | **+13.7%** (threshold 20%) | 719 to 1,019 |
| worst-width-1m.csv | 18.35, 18.20, 17.69 | 20.83, 20.86, 20.08 | **+14.5%** (threshold 35%) | 804 to 1,188 |
| insurance-ontario.csv | 1.89, 1.88, 1.89 | 2.42, 2.46, 2.47 | +30.2% (0.57 s) | 678 to 973 |

The thresholds hold for the two files they were set for. The 90,909-row file is over 20% for 0.57 s: it pays the fixed
cost of what the work added (derived blocks, row sample, patterns, observations) on a few thousand distinct values.
**Memory is above the guard-rail of lot 0** (the peak of the realistic file within 10% of 715 MB): it is +42%, the sum
of the peaks of the main process and the workers, from the bottom-k samples of 10,000 values per column (lot 2b measured
796 to 934 MB) and the row sample; the memory does not depend on the number of rows. The maintainer is to rule on it at
the gate D.

### Calibration of the estimate of the selection

The model of lot 10b (600 ns a tested cell, 2,000 ns a row) gave 35 s for the realistic file and was 4 to 5 times too
low on columns that are nearly all distinct (a million rows of the high-cardinality layout measured 31.6 s for an
estimate of 7 s). The cell cost is now `SELECT_NS_PER_CELL` 600 plus `SELECT_NS_PER_DISTINCT_CELL` 3,000 times the average
distinct share of the tested columns, read from the Scan (a limited count counts as all distinct). The estimate
(low to high) now brackets the measures: high-cardinality 26 to 100 s (measured 31.6), short identifiers 19 to 75 (18.8),
repeated 17 to 65 (25.7), wide-100 30 to 117 (42.0), growth 500k 12 to 46 (14.9), low-cardinality 6.3 to 23 (5.8).

### The lever of the overhead of the Report (`automatic_tables`)

`insurance-combined.csv`, `report` with `deep.crosstab.automatic_tables` at 0, 2, 4 and 8 (fresh storage each time):

| `automatic_tables` | Wall (s) | Second pass (s) | Analyses | Tables | Cells read (millions) |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 36.1 | 16.0 | 30 | 0 | 12 |
| 2 | 36.7 | 17.1 | 32 | 2 | 16 |
| 4 | 39.2 | 18.7 | 34 | 4 | 20 |
| 8 (default) | 39.8 | 19.8 | 38 | 8 | 25 |

Each table costs about 0.5 s of the second pass on this file. Going from 8 to 0 tables saves 3.8 s out of 39.8 (-10%):
the overhead of the Report is mostly the other 30 analyses (16 s of a 20 s first pass), which the planner picks as
cheap and useful. The lever of the tables is small; the lever of the whole second pass is `deep.mode` and the automatic
budget of 20.2.

## Memory, overhead of the Report and the full matrix (lot 12)

Lot 12 treats the two points that the maintainer accepted at lot 11 and left for later: the memory of the first pass
(+42%, 719 to 1,019 MB on the realistic file against `0acf126`) and the overhead of the Report (+107%, the second pass
adding 22 s to a Report of 21 s). Engine 0.6.2 at commit `338fd44` plus the changes of the lot, CPython 3.12.14, Windows 11,
Intel Core Ultra 9 275HX (24 logical CPUs), 32 GB. The interleaved comparisons and the matrix ran on a quiet machine (no
other session scanning); the machine was faster than at lot 11 (the first pass of the combined file took 11.7 s against 19.7
s), so **only ratios taken in one session are compared**, never the figures of two sections.

### Where the memory came from

The peak of a parallel scan is the sum of the peaks of the main process and of each worker (`insurance-combined.csv`, one
scan, `benchmarks/interleave.py` and a driver reading the peak of each process):

| Scan | Main process | Workers | Sum |
| --- | ---: | ---: | ---: |
| `0acf126` | 177 MB | 8 of about 67 MB | 719 MB |
| Lot 11 (K = 10,000) | 340 MB | 8 of 71 to 93 MB | 1,017 MB |
| Lot 11 with K = 100 (`limits.max_samples`) | 187 MB | 8 of 57 to 91 MB | 825 MB |

- **The main process (+153 MB)** holds the bottom-k samples of the Scan: with `tracemalloc`, `insurance-ontario.csv` retains 99
  MB of result at K = 10,000 against 9 MB at K = 100, about 450 bytes an entry (a `SampleEntry` is a pydantic model: an object, its
  dictionary, its set of fields set and the text). The row sample and the patterns weigh about 10 MB.
- **The workers (+140 MB in all)** imported the whole `tabalyst` package, 498 modules (services, planner, Report, `jinja2`,
  `yaml`), 50 MB before any value; they need 35 MB. K = 10,000 adds only 5 MB to a worker.

### The levers and what they gave

No lever touches the per-value loop of the first pass, reduces what is computed or changes a result.

| Lever | What it does | Effect |
| --- | --- | --- |
| M2, lazy package | `tabalyst` and `tabalyst.scanner` resolve their public names on first use (PEP 562) | A worker loads 280 modules instead of 498: 35 MB instead of 50 MB at rest, about 15 MB less in each |
| M1, at most 6 workers | `MAX_WORKERS` 8 to 6 | The time is that of 8 workers on every file (below), and 2 workers fewer are 130 to 170 MB less |
| R1, second pass in workers | the routes of the fields of a CSV file run in workers (design 20.18) | The second pass of the Report takes 9 s instead of 15 s on the realistic file |
| M3, compact sample entries | not done | Would take about 110 to 150 MB from the main process, at the price of changing the type of `Samples.listed`; not needed |

**The number of workers** (interleaved, `TABALYST_BENCH_WORKERS`, `benchmarks/interleave.py`; the first column is the scan with
the lazy package and 8 workers). Median of the runs in seconds, then the peak memory:

| File | `0acf126` | 8 workers | 6 workers | 4 workers | 3 workers |
| --- | ---: | ---: | ---: | ---: | ---: |
| insurance-combined (3 series) | 11.46 s, 719 MB | 12.80 s, 900 MB | 13.13 s, 769 MB | 13.17 s, 641 MB | 13.74 s, 576 MB |
| worst-width-1m (2 series) | | 16.23 s, 1,072 MB | 16.50 s, 916 MB | 18.38 s, 779 MB | 19.96 s, 696 MB |
| wide-100 (2 series) | | 18.66 s, 1,605 MB | 19.10 s, 1,437 MB | 20.13 s, 1,278 MB | 20.98 s, 1,193 MB |

Four workers are enough for 34 columns (within 3% of the time of 8, 641 MB) but cost 8% to 13% on the files whose columns are heavy or
numerous; six cost 2% on all three and bring the realistic file to 769 MB, 7% above the baseline. The cap is 6. The lazy
package alone takes the realistic file from 1,019 to 900 MB.

### Against the base commit, in the same session (PERF-06, PERF-05)

`0acf126` in a `git worktree`, the head, alternated three times, task `scan`, default workers:

| File | Base (s), three runs | Head (s), three runs | Median | Threshold | Peak memory (MB) |
| --- | --- | --- | --- | --- | --- |
| insurance-combined.csv | 10.97, 10.53, 10.36 | 11.96, 12.05, 12.10 | **+14.5%** | 20% | 719 to 769 (**+7%**, guard-rail 10%) |
| worst-width-1m.csv | 13.12, 12.54, 12.83 | 15.50, 14.91, 15.25 | **+18.8%** | 35% | 804 to 917 |
| insurance-ontario.csv | 1.89, 1.84, 1.89 | 1.97, 2.02, 2.02 | +7.3% | | 680 to 734 |

The 90,909-row file was at +30% at lot 11 (the fixed cost of starting 8 workers that each import the package): it is now +7%. All the
thresholds and the guard-rail of lot 0 (peak of the realistic file within 10% of 715 MB) hold.

### The overhead of the Report, before and after R1

`benchmarks/report_overhead.py` on `insurance-combined.csv`, the lot 11 tree in a `git worktree` against the head, alternated
twice (wall time of `tabalyst report`, interpreter and files included):

| Case | Lot 11 | Lot 12 | Second pass, lot 11 | Second pass, lot 12 |
| --- | ---: | ---: | ---: | ---: |
| `off` (no second pass) | 16.7 s, 17.2 s | 16.7 s, 16.3 s | none | none |
| `auto` (the planner decides, 38 analyses, 25 million cells) | 32.8 s, 34.2 s | 26.3 s, 26.0 s | 15.3 s, 16.6 s | 9.3 s, 9.0 s |
| `warm` (again on the same storage) | 2.0 s | 1.8 s | 0.0003 s | 0.0003 s |
| `forced` (`--deep --yes`, 55 analyses, 37 million cells) | 40.7 s, 39.3 s | 35.6 s, 36.2 s | 22.8 s, 22.3 s | 18.6 s, 19.0 s |

The automatic second pass adds 9.2 s to a Report of 16.5 s, **+59%** instead of +99% in the same session (+107% at lot 11).
What is left is the reading of the source (4 s, in the process that asks), the exact sets and the pairs and tables of
columns, which stay in the process, and the pickling of the columns (0.8 s). Moving the tables to the workers would save at
most 2 s of 9; the reading is the floor. Starting the workers costs about 0.5 s, so the second pass of a source under 16 MiB
stays in one process. The planner's estimate of time (20.2) still counts one process and is an upper bound.

### The full matrix (PERF-05 to PERF-08, F07)

`benchmarks/final_matrix.py --profile full --repeat 3` (all four tasks, three repeats, medians). The new cases are the
growth family at 2,000,000 rows and the wide family at 500 and 1,000 columns, written by `benchmarks/matrix_layouts.py`
(seed 42, under `D:\GIT.test\tabalyst\bench\matrix`):

```powershell
.\.venv\Scripts\python.exe benchmarks\final_matrix.py --profile full --root D:\GIT.test\tabalyst\bench\matrix --out D:\GIT.test\tabalyst\artifacts\lot12\matrix-full --repeat 3 --existing D:\GIT.test\tabalyst\csv\insurance-combined.csv D:\GIT.test\tabalyst\bench\worst-width-1m.csv D:\GIT.test\tabalyst\bench\many-lengths-500k.csv D:\GIT.test\tabalyst\bench\long-text-60k.csv
```

| Case | Rows | Size (MB) | Scan (s) | Peak (MB) | Report without (s) | Report with (s) | Second pass adds | Smart selection (s) | Spread of the three runs |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| insurance-combined | 1,000,000 | 263 | 11.71 | 770 | 12.65 | 19.91 | +7.3 s (+57%) | 19.96 | 2% |
| worst-width-1m | 1,000,000 | 361 | 14.97 | 918 | 15.69 | 27.27 | +11.6 s (+74%) | 38.18 | 3% |
| many-lengths-500k | 500,000 | 169 | 3.67 | 625 | 4.09 | 6.22 | +2.1 s (+52%) | 6.22 | 3% |
| long-text-60k | 60,000 | 196 | 2.33 | 621 | 2.75 | 3.61 | +0.9 s (+31%) | 1.91 | 2% |
| low-cardinality | 1,000,000 | 80 | 3.23 | 378 | 3.50 | 4.77 | +1.3 s (+36%) | 3.69 | 2% |
| transition-K-1 | 200,000 | 4 | 0.97 | 112 | 1.31 | 1.52 | +0.2 s (+16%) | 0.77 | 3% |
| transition-K | 200,000 | 4 | 0.97 | 111 | 1.30 | 1.52 | +0.2 s (+16%) | 0.78 | 3% |
| transition-K+1 | 200,000 | 4 | 1.02 | 113 | 1.32 | 1.61 | +0.3 s (+22%) | 0.76 | 5% |
| transition-T | 200,000 | 4 | 1.24 | 136 | 1.54 | 1.81 | +0.3 s (+18%) | 0.93 | 3% |
| high-cardinality | 1,000,000 | 130 | 10.29 | 718 | 10.79 | 13.89 | +3.1 s (+29%) | 20.42 | 2% |
| short-ids | 1,000,000 | 59 | 4.54 | 646 | 5.03 | 7.71 | +2.7 s (+53%) | 12.14 | 2% |
| repeated-550k | 550,000 | 159 | 7.17 | 829 | 7.81 | 17.22 | +9.4 s (+121%) | 16.38 | 2% |
| wide-100 | 200,000 | 166 | 17.50 | 1,438 | 20.05 | 23.29 | +3.2 s (+16%) | 27.98 | 9% |
| growth-250k | 250,000 | 32 | 3.72 | 648 | 4.28 | 5.82 | +1.5 s (+36%) | 4.80 | 2% |
| growth-500k | 500,000 | 65 | 5.88 | 673 | 6.40 | 8.13 | +1.7 s (+27%) | 9.76 | 2% |
| normalization-clean | 500,000 | 17 | 1.97 | 379 | 2.29 | 2.87 | +0.6 s (+25%) | 2.05 | 3% |
| normalization-effect | 500,000 | 17 | 1.99 | 384 | 2.37 | 2.94 | +0.6 s (+24%) | 2.03 | 3% |
| growth-2M | 2,000,000 | 260 | 19.11 | 810 | 19.86 | 26.05 | +6.2 s (+31%) | 42.21 | 1% |
| low-cardinality-2M | 2,000,000 | 160 | 6.51 | 473 | 6.80 | 9.40 | +2.6 s (+38%) | 8.06 | 1% |
| wide-500 | 200,000 | 832 | 87.60 | 1,819 | 94.98 | 107.43 | +12.5 s (+13%) | 145.69 | 4% |
| wide-1000 | 200,000 | 1,667 | 209.12 | 2,164 | 226.18 | 227.62 | +1.4 s (+1%) | 326.46 | 27% |

The peaks are those of the scan. The Report peaks above it, since it keeps the Scan and builds the profile and the page: 47 MB
above on the realistic file without a second pass and 323 MB with one, 615 MB above on `wide-500` without one. The smart
selection loads the Scan and the targets of every column: 6% above the scan on the realistic file, 32% to 71% on the wide
files (`wide-1000` at 3,692 MB). The spread is the largest range of the four tasks over its median; the 27% of
`wide-1000` is one slow run of the Report (228 to 288 s) and of the selection (310 to 398 s), not a trend.

- **Plateau of memory (PERF-05).** The growth family peaks at 648, 673, 718, 810 MB for 250,000, 500,000, 1,000,000 and
  2,000,000 rows, and at 805 MB for 4,000,000. What grows is the table of digests of the rows that detects exact duplicates,
  which `limits.max_tracked_records` bounds at 2,000,000 entries (about 190 MB at its limit): with `records.duplicates`
  off, 500,000 and 2,000,000 rows both peak at 620 to 624 MB (main process 161 MB). The plateau is the limit, and it is reached
  at 2,000,000 rows. Before lot 12 the same rows peaked at 872, 895 and 941 MB.
- **Transition around K and T.** 9,999, 10,000 and 10,001 distinct values scan in 0.97, 0.97 and 1.02 s; 100,000 distinct
  values in 1.24 s (release of the table), as at lot 11.
- **Columns (PERF-08).** 100, 500 and 1,000 columns of 200,000 rows scan in 17.5, 87.6 and 209 s: 0.88, 0.88 and 1.05
  microseconds a cell, so the time is proportional to the cells. The memory is not: 1,438, 1,819 and 2,164 MB, because the
  samples share one budget (`limits.max_sample_memory`, 512 MiB) and the sample of a column shrinks as columns are
  discovered (design 18.10). No case ran out of memory and the budgets held. On `wide-1000` the Report's second pass reads
  nothing (250 analyses answered from the Scan's samples, 0.01 s).
- **The second pass of the Report** adds 13% to 74% to the Report without it, and 121% on `repeated-550k` (18 analyses and 6.6
  million cells in 9.3 s, 1.4 microseconds a cell: its exact sets, which run in the process, are the cost). It adds
  nothing to the first pass.
- **The smart selection** reads the source once; its time is the reading of the cells that have a test (design 20.16), 0.8 to
  326 s on these files.

**What was not run.** Two million rows with 500 or 1,000 columns: 1 and 2 billion cells, 7 and 17 GB of CSV, and about 15 and
35 minutes for a Scan alone at the measured rate, 6 and 12 hours for the four tasks in three repeats. The wide cases keep
200,000 rows, since the memory and the time per cell do not depend on the rows (PERF-05, above). The decision was taken
with the maintainer on 2026-10-10.

## Ambiguous numbers read by the evidence of the column (Insight lot 17d.2a)

The first pass keeps the ambiguous numbers (`1,234`) and the strict decimals `d.ddd` as integers and decides their reading at
the finalization of the field (design 20.27). `76eb1c6` (a copy of the tree, `lot17d/base`) against the head, alternated three
times in one session, task `scan`, default workers (`benchmarks/interleave.py`, outputs under
`D:/GIT.test/tabalyst/artifacts/lot17d2a/il/`):

| File | Base (s), three runs | Head (s), three runs | Median | Threshold | Peak memory (MB) |
| --- | --- | --- | --- | --- | --- |
| insurance-combined.csv (1 M x 34, realistic) | 13.03, 12.72, 12.71 | 12.51, 12.40, 12.55 | **-2.5%** | 20% | 780 to 778 (guard-rail 10%) |
| worst-width-1m.csv | 16.08, 15.69, 15.96 | 15.48, 15.56, 15.82 | **-0.8%** | 35% | 926 to 925 |
| dd3.csv (500,000 rows of `d.ddd`) | 3.63, 3.57, 3.60 | 3.81, 3.33, 3.35 | -6.8% | | 626 to 626 |
| amb-s30.csv (500,000 rows, 30% ambiguous) | 4.05, 4.00, 4.61 | 4.64, 4.14, 4.10 | +3.5% | | 630 to 627 |
| amb-s100.csv (500,000 rows, about 100% ambiguous) | 4.07, 3.98, 4.09 | 4.13, 4.23, 4.23 | +3.3% | | 627 to 626 |
| amb-s100-n100k.csv (100,000 rows, complete tables) | 4.23, 3.59, 3.62 | 3.99, 3.88, 3.93 | +8.0% | | 198 to 248 |
| amb-s100-n2m.csv (2 M rows, released tables) | 12.83, 12.18, 13.46 | 15.75, 13.03, 13.70 | +7.0% | | 767 to 763 |

The thresholds hold, and the memory plateau does not depend on the rows: 626 MB at 500,000 rows and 763 MB at 2 M (627 and
767 for the base). The Scan document of the realistic file is the base's but for the two new settings of the four number
detectors and `config_sha256`. The only memory step is the synthetic worst case, four columns entirely ambiguous with 100,000
distinct values each and complete tables (+25%): the resolved numbers enter the exact median like any number; the same file
written without commas costs the same (lot 17d.1 note). The sessions of 17d.1 and 17d.2a measured the base 3 to 4 points
apart, so differences of that size are noise.

## Values with a unit read by the evidence of the column (Insight lot 17d.2b)

The second pass reads the ambiguous numbers of `measure_extraction` in the convention the plan decides from the Scan (design
20.28); the first pass is not touched, so no interleaved Scan comparison applies. The cost of the extraction was measured with
`measure_costs.py` of lot 14 on `measures-1m.csv` (1 M rows, five columns, one process), the base `ecad208` (a copy of the tree,
`lot17d2b/base`) against the head, alternated twice in one session (`D:/GIT.test/tabalyst/artifacts/lot17d2b/`):

| Subset | Base (ns per cell), two runs | Head (ns per cell), two runs | Change |
| --- | --- | --- | --- |
| all five columns | 1,458 and 1,376 | 1,434 and 1,450 | +1.8% |
| price (about 1,100 distinct) | 1,112 and 1,115 | 1,170 and 1,204 | +6.6% |
| amount (1 M distinct, grid) | 4,733 and 4,766 | 4,875 and 5,017 | +4.1% |
| discount, size, weight | 147 and 145, 417 and 432, 437 and 434 | 149 and 151, 432 and 458, 448 and 467 | +2.7% to +5.3% |

The traced peak is the same (23 MB for the five columns). The differences are of the size of the drift between runs of one
session (3 to 4 points, above), so the tiers of `NS_PER_CELL` and `COST_MODEL_VERSION` (11) stay as they are: the reading adds one
comparison per matched value under `comma`, and a column that resolves ambiguous values holds more numbers in its table.

## The matrix replayed, the cost model reviewed (Insight lot 20)

Lot 20 replays the full matrix of lot 12 (`benchmarks/final_matrix.py --profile full`, all four tasks, two repeats, outputs
under `D:/GIT.test/tabalyst/artifacts/lot20/`) with the analyzers of lots 13 to 17d, on `1072f3d` (Tabalyst 0.7.0, branch
`scan-json/e`), and compares it with the table of lot 12 (`lot12/matrix-full`, three repeats). The machine is the same, and
drifts: the Scan of the same file takes 9% to 17% more than in lot 12 in every case, which the interleaved comparison below
shows is the machine and not the code.

### The first pass, against the 0.7.0 base in the same session (PERF-06)

`a024b8f` (the release preparation, a copy of the tree) against the head, task `scan`, three alternated series,
`benchmarks/interleave.py`:

| File | Base, three runs (s) | Head, three runs (s) | Paired change | Peak (MB), base then head |
| --- | --- | --- | ---: | --- |
| insurance-combined (1 M rows, 34 columns) | 13.44, 13.59, 13.18 | 13.31, 13.48, 13.38 | -0.8% | 776, 778 |
| worst-width-1m (1 M rows, worst width) | 17.09, 16.82, 17.20 | 16.81, 17.21, 17.14 | -0.4% | 922, 925 |

Lots 13 to 17d together stay far inside the guardrails (+20%, +35%, +10% of memory): the first pass costs what it cost in 0.7.0.

### The matrix

Every task of every case against lot 12 (medians, seconds; the Scan column is the drift of the machine):

| Case | Scan | Report without second pass | Report (automatic) | Smart sample | Peak, Report |
| --- | ---: | ---: | ---: | ---: | ---: |
| insurance-combined | +13.9% | +15.7% | +37.7% | +12.6% | +2.7% |
| worst-width-1m | +11.9% | +13.8% | +16.5% | +12.3% | +2.3% |
| many-lengths-500k | +12.3% | +10.8% | +12.4% | +12.5% | +2.6% |
| long-text-60k | +9.0% | +8.0% | +14.4% | +9.4% | +2.1% |
| high-cardinality | +10.5% | +12.0% | +12.8% | +8.2% | +2.2% |
| short-ids | +12.3% | +14.3% | +15.8% | +14.7% | +3.1% |
| repeated-550k | +15.8% | +15.1% | +14.2% | +8.5% | +2.2% |
| wide-100 (200,000 rows) | +7.3% | +9.8% | +15.4% | +5.4% | +4.8% |
| wide-500 | +8.9% | +12.1% | +13.3% | +7.2% | +0.2% |
| wide-1000 | +17.2% | +9.8% | +10.2% | +7.9% | +0.6% |
| growth-2M | +11.5% | +11.4% | +8.3% | +7.8% | +1.2% |
| low-cardinality-2M | +5.8% | +5.6% | +5.1% | +11.5% | +3.6% |

(the other cases, `transition-*`, `growth-250k` and `-500k`, `normalization-*`, `low-cardinality`, lie in the same bands; the full table is
`lot20/matrix-full/results.md`). The memory of the Scan moves by +0.4% to +4.8%, with the plateau independent of the rows
(`growth-2M` 816 MB against 810). The one outlier is the second pass of the realistic file (7.18 s then, 12.80 s now, 78% more,
56% once the drift is taken out): it is the five pairs of `category_stats` that the Report picks by itself (lot 16c noted it,
`automatic_stats` 8).

### The levers

| Question | Measure (realistic file, one scan, alternated runs of the executor, median of three) | Decision |
| --- | --- | --- |
| `deep.stats.automatic_stats` 0, 2, 4, 8 | second pass 10.7, 11.8, 15.3 and 15.4 s (the plan holds 5 pairs, so 4 and 8 choose almost the same) | 2 (maintainer, 2026-10-12): the second pass of the Report goes to 8.86 s (23.01 s the Report, against 27.42 s with 8) |
| Ceiling of the tiers of the shape and of the parts (2,400 ns) | a forced plan is estimated between 61 and 239 s and takes 25 s (the model counts one process; the workers share the reading); with the measured costs (4,300 and 3,700 ns) the estimate is 67 to 261 s and the plan becomes `high`, so `--deep` asks for a confirmation | stays |
| `pearson` 1,500 ns (measured 2,340 to 2,690 in lot 16) | same reasoning: it decides the class `moderate` of the pair, the estimate is already above the real time | stays |
| Utility 40 of `numeric_shape` and `datetime_parts` | at 50 for the tiers few and mid: 49 and 57 analyses instead of 48, the second pass 15.19 and 15.77 s against 15.30 s (+3.0% for all), same peak memory (328 MB) | stays 40 (maintainer, 2026-10-12) |

After the change of `automatic_stats` the two heaviest cases again, same session, two repeats: insurance-combined Report 23.01 s
(second pass 8.86 s, peak 1,127 MB), worst-width-1m Report 31.26 s (second pass 13.37 s, peak 1,209 MB). `COST_MODEL_VERSION`
stays 11 (no cost changes, a budget of the plan changes).

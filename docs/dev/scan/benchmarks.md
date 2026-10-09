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

## JSON Inspect

The costs of JSON Inspect, of the interpretation resolver and of the JSON and JSONL
parcours (hash, event pass, Scan, report with a stored scan) are in
`docs/dev/inspect/benchmarks.md` (lot JI-8).

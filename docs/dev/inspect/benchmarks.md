# Inspect benchmarks (lot JI-8)

Costs of JSON Inspect and of the parcours that Inspect added to Scan and
Report. The design records the parameters decided from earlier measurements
(`design.md` section 15); this page confirms them on the finished code and
measures the whole parcours. Numbers are only comparable on the same machine
and data.

## Protocol

`benchmarks/run_baseline.py` gained tasks for the JI-8 measurements (the
default tasks are unchanged). Each measurement runs in a fresh interpreter;
`resolve-*` and `report-*` use an empty temporary storage (`TABALYST_HOME`), so
no cache is inherited. Data are the synthetic records of
`benchmarks/generate_data.py`, which now also writes JSONL (20 columns, nested
`address` and `orders`, null addresses, a late optional field; about 650 bytes
per record). `benchmarks/data/` is ignored by Git.

```powershell
.\.venv\Scripts\python.exe benchmarks\generate_data.py --rows 100000 -o benchmarks\data\synthetic-100k.json
.\.venv\Scripts\python.exe benchmarks\generate_data.py --rows 100000 -o benchmarks\data\synthetic-100k.jsonl
.\.venv\Scripts\python.exe benchmarks\run_baseline.py benchmarks\data\synthetic-100k.json --task sha256 --task events --task inspect --task resolve-cold --task resolve-warm --task scan --task report-cold --task report-reuse --repeat 3
.\.venv\Scripts\python.exe benchmarks\run_baseline.py benchmarks\data\synthetic-100k.jsonl --task sha256 --task inspect --task resolve-cold --task resolve-warm --task scan --task report-cold --task report-reuse --task jsonl-parse-hook --task jsonl-parse-plain --repeat 3
```

Tasks:

- `sha256`: full SHA-256 of the file (`scan_reuse.file_sha256`).
- `events`: the `ijson` event pass of the Scan reader (`JsonEvents`), which
  includes its own hash and the check for long digit runs. JSON only.
- `inspect`: `inspect_source()` (event pass, hash, candidates, bounded
  observation, selection).
- `resolve-cold`: `resolve_interpretation()` with an empty storage: automatic
  inspection, writing `inspect.json`.
- `resolve-warm`: the same call once the cache exists: only the cache is read
  and the source is hashed to validate it.
- `scan`: `tabalyst.scan()` with defaults (the engine alone, with workers).
- `report-cold`: `generate_reports()` on an empty storage: resolution, Scan,
  report files.
- `report-reuse`: the same call again on the same storage: the stored scan is
  reused and only the report is rebuilt. Time is that second call; memory is
  the peak of the process, which includes the first call.
- `jsonl-parse-hook`, `jsonl-parse-plain`: `json.loads` on each line with
  `Decimal` floats, with and without the duplicate-key hook of the JSONL
  reader.

## Results

Environment: Tabalyst 0.4.4 (commit `22d75c0` plus the JI-8 working tree),
CPython 3.12.14, Windows 11 (10.0.26200), Intel Core Ultra 9 275HX (24 logical
CPUs), `ijson` compiled backend. Best of 3 for 100,000 records, one run for
1,000,000. Seconds.

| Task | JSON 100 k (65 MB) | JSONL 100 k (65 MB) | JSON 1 M (652 MB) | JSONL 1 M (651 MB) |
| --- | ---: | ---: | ---: | ---: |
| `sha256` | 0.04 | 0.04 | 0.36 | 0.37 |
| `events` | 0.66 | - | 7.06 | - |
| **`inspect`** | **0.77** | **0.67** | **8.22** | **6.42** |
| `resolve-cold` | 0.79 | 0.00 | 7.79 | 0.00 |
| `resolve-warm` | 0.04 | 0.00 | 0.37 | 0.00 |
| `scan` | 9.19 | 7.64 | 67.83 | 61.04 |
| `report-cold` | 9.65 | 8.64 | 75.91 | 68.93 |
| `report-reuse` | 0.33 | 0.35 | 0.65 | 0.70 |
| `jsonl-parse-hook` | - | 0.58 | - | 6.22 |
| `jsonl-parse-plain` | - | 0.50 | - | 5.19 |

Peak memory: Inspect grows by 2 to 4 MB whatever the size. A Scan grows by
770 to 862 MB (parent and workers) on these files.

Reading:

- **Hash.** About 1.8 GB/s: 0.36 s for 650 MB, 0.5% of a Scan. Always computing
  it in full (DP-D, EF-28) is cheap next to everything else.
- **Inspect pass.** 1.1 to 1.2 times the bare event pass (JSON), about 8 to 12%
  of a Scan. A JSONL source is faster to inspect than a JSON one (6.4 s against
  8.2 s for 1 M records) (the cause was not isolated).
- **Resolver.** Without a cache a JSON source pays one Inspect (7.8 s on
  652 MB, the same as `inspect`); with the cache it pays only the validation
  hash (0.37 s). JSONL has no automatic Inspect (design 9.4), so the resolver
  is free.
- **Report.** The first report costs a Scan plus 5 to 13% (report files and the
  cache). With the scan stored, the report is rebuilt in 0.3 to 0.7 s whatever
  the source size: the source is hashed (0.04 to 0.37 s) and the scan document
  is read, not the source.
- **Duplicate-key hook (JSONL).** 16% to 20% more parse time on these records
  (0.58 s against 0.50 s; 6.22 s against 5.19 s), against about 40% on the
  dense lines measured in JI-4. Accepted again: the extra second on 1 M records is under 2% of a
  Scan, and the hook is what makes an ambiguous
  object an exclusion instead of a silent choice.

## `RECORDS_OBSERVED` confirmed

`inspect_source` on `synthetic-100k.json` (65 MB, 100,000 records, 30 fields
of which one, `loyalty_tier`, only appears in the last 10% of the records),
best of 3:

| `RECORDS_OBSERVED` | Time (s) | Fields observed |
| ---: | ---: | ---: |
| 10 | 0.75 | 29 |
| 100 | 0.80 | 29 |
| **1,000** | **0.84** | 29 |
| 10,000 | 0.87 | 29 |
| all | 1.18 | 30 |

The bound costs 0.09 s over 10 records and observing everything adds 40% to
the pass: the same conclusion as JI-5. The late field is not described by any
bound that stops before it, and the Scan finds it (CA-11,
`test_a_field_after_the_observed_records_is_found_by_the_scan`). `K` = 1,000
stays: the cost is not what limits it, the description of the structure is
partial by design (D15). No change.

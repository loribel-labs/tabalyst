# The memory of the first pass and the overhead of the Report are cut without computing less

Status: accepted on 2026-10-10 (maintainer, lot 12 of the Scan and JSON work).

## Context

Lot 11 measured two costs of the work against the commit `0acf126`: the sum of the peaks of the process and its
workers went from 719 to 1,019 MB on the realistic file (+42%), and the second pass of `tabalyst report` added 22 s to
a Report of 21 s (+107%). The maintainer accepted both for the time being, on condition that nothing already done is
reduced and no exact measure regresses (P1, EVOL-05).

## Decision

- A scan worker imports the engine and not the services of the package: `tabalyst` and `tabalyst.scanner` resolve
  their public names on first use (PEP 562). Each worker is 15 MB lighter.
- The first pass starts at most 6 workers instead of 8. The time is the one of 8 on every file measured (+2%), and four
  workers cost 8% to 13% on wide files.
- The routes of the fields of a CSV file in the second pass run in worker processes (`secondpass/parallel.py`, design
  20.18). A route is independent of the others, so a worker that receives its column of every batch in reading order
  counts what the process would; the results do not depend on the number of workers. The routes with an exact set (one
  memory pool for the run, MEM-06) and the pairs and tables of columns stay in the process. `--workers` applies to both
  passes.
- Not done: compact sample entries in the result (a change of the type of `Samples.listed` for 110 to 150 MB, not
  needed once the two levers above are in), and the tables in the workers (2 s of 9, the reading of the source is the
  floor).

## Consequences

- Realistic file: 719 to 769 MB (+7%, inside the guard-rail of 10%), first pass +14.5% (threshold 20%); the Report
  adds 9 s instead of 15 s to a Report of 16.5 s (+59% instead of +99% in the same session).
- A second pass that fails in a worker stops with `SecondPassWorkerError`: an automatic one is left out of the Report
  and said so, a forced one fails. Workers that cannot start leave the pass in one process.
- The time estimate of a plan (20.2) counts one process and is an upper bound for a CSV file of 16 MiB or more.
- A file of 500 and 1,000 columns does not run out of memory (1.8 and 2.2 GB for the scan, 2.7 and 2.9 GB for the Report) because the samples share
  one budget; the limit of 2,000,000 tracked records bounds the memory of the row digests.

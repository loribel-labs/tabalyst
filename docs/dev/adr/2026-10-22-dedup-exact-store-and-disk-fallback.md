# The exact row store keeps whole keys, in memory first and on disk past the budget

Status: accepted on 2026-10-22 (maintainer, lot 0 of Tabalyst Dedup, decisions D6 and
D7 of the plan), SQLite included as the first disk realization. The measured
parameters are fixed at gate 3 (after lot 3).

## Context

`tabalyst dedup` must tell, exactly, which records of a CSV of up to 10 million
records are identical (design: `docs/dev/dedup/design.md`, section 5). The
specification forbids deciding on a digest alone (FR-IDENT-02) and any `complete`
result that is approximate (S10.2, S20). The Scan's duplicate tracking is not a model:
it holds a 128-bit BLAKE2b digest and 80 bytes per distinct row up to
`limits.max_tracked_records` (2 million), and then reports a lower bound.

An exact in-memory table keeps the whole key of every distinct row. A Python
dictionary of `bytes` keys costs the key, the `bytes` object header (33 bytes), the
slot of the table and the value (a count and a first position). The plan estimates
100 to 250 bytes per distinct narrow row, so 1 to 2.5 GB at 10 million distinct rows,
against a default budget of 512 MiB. Wide rows cost more. These are estimates, to be
measured in lots 2 and 3. If they hold, the in-memory path alone cannot carry the
guarantee at the stated size, and the disk path is a blocking part of the first
priority of the specification (S17, P0).

## Decision

1. **One interface, `ExactRowStore`**, whose single operation of the first pass is
   `observe(key, position) -> Occurrence(count, first_position)`. The counters of the
   groups follow from the count transitions, so the store is never scanned.
2. **The key is the canonical encoding of the row** (design 5.2): the count of cells,
   then the length and the UTF-8 bytes of each cell, with unsigned LEB128 integers. It
   is injective, so equal keys are equal rows and different rows never share a key.
3. **Equality always compares the whole key.** The memory realization is a dictionary
   keyed by `bytes`. The disk realization is a SQLite table
   `rows(key BLOB PRIMARY KEY, count INTEGER, first INTEGER) WITHOUT ROWID` in a
   temporary database under `--temp-dir`, updated by an upsert that returns the new
   count (`INSERT ... ON CONFLICT(key) DO UPDATE SET count = count + 1 RETURNING`;
   two statements when the SQLite library is older than 3.35). A digest may be added
   later as an index prefix to speed up comparison, never as the decision, and its
   function is then a parameter so that a test can inject collisions (T20).
4. **A tiered store** starts in memory and migrates to SQLite when the accounted
   bytes (the sum of `len(key) + ENTRY_OVERHEAD` of the entries) pass
   `--memory-budget-mb` (default 512 MiB). The accounting is deterministic and does not
   read the RSS, so the same file and budget choose the same mode on any machine
   (project rule: budgets in bytes, not wall-clock time). The migration copies every
   entry in batches into the database, then drops the dictionary, then continues; no
   group is lost, and the mode is named in the progress and recorded in the report
   (`run.storage_mode`).
5. **Failure rather than approximation.** If the temporary folder is unusable, the
   disk is full or the free space is below the estimate, the source fails with a
   stable reason and publishes nothing. The temporary database is deleted in every
   case, including after an error.
6. **SQLite is the first disk realization** because it is in the standard library,
   needs no dependency and is crash-safe enough for a disposable file (journal off,
   synchronous off, one transaction per batch). It is a choice of the realization
   behind the interface and can change without changing anything else.

## Alternatives considered

- **Digest-only set (as the Scan).** Rejected: not exact (FR-IDENT-02).
- **Digest index plus keys on disk, compared on a match.** Exact, but two structures
  and a lookup per hit; it is the possible optimization of decision 3, not the first
  realization.
- **External partitioning.** Route each key by digest to one of `P` temporary files
  (with its position), then count each partition in memory with full-key comparison.
  Exact, no database, sequential I/O. It needs the partition files to be written and
  read once more, and a bound on a partition that does not fit the budget. It stays the
  documented replacement if SQLite is too slow at 10 million (the plan's lot 3 note):
  in that case a new ADR replaces this one before lot 4 starts.
- **An embedded key-value store (dbm, LMDB, RocksDB).** Rejected: a dependency or a
  platform-dependent format for the same job as SQLite.
- **DuckDB**, already a runtime dependency (project catalog). Rejected for the first
  pass: it is built for bulk loads and group-by queries, not for one keyed upsert per
  record from Python, and the answer to each record is needed immediately (the
  transition of the count marks the bit arrays). It stays a candidate for a bulk
  "group by the whole row" if lot 3 finds that SQLite is too slow, which would change
  the algorithm (a pass that writes the keys, then one query) and need a new ADR.
- **External sort of the keys.** Exact and bounded in memory, but it destroys the
  record order that the two bit arrays rely on and costs a sort of the whole file.
- **Dictionary only.** Rejected for the default budget, as measured above (to be
  confirmed by lot 2).

## Consequences

- The correctness of the engine does not depend on the speed or the size of the store.
  Any realization can be tested against the same inputs and the same expected counts.
- Lot 2 measures the real bytes per distinct row of the dictionary and fixes
  `ENTRY_OVERHEAD`. Lot 3 measures SQLite at 1, 5 and 10 million rows with 0, 25 and
  90 percent of extra copies and writes the table of results into the plan. Gate 3
  passes if the exact path holds in the budgets of memory and disk the maintainer
  accepts after reading those numbers; otherwise this ADR is replaced (partitioning,
  another budget or another default limit) before going on.
- The first pass keeps only two bit arrays (about 2.5 MB at 10 million records) after
  the store is closed, so the second pass never needs the store.
- The disk path needs free space about the size of the keys times a factor measured in
  lot 3; the estimate is checked before the migration and during the run.
- The temporary files are private to the run and are always deleted; an interrupted run
  leaves nothing that a later run could take for a result.

# A report proves the ownership of the outputs, and a recovery report survives an interruption

Status: accepted on 2026-10-22 (maintainer, lot 0 of Tabalyst Dedup, decisions D2, D9
and D10 of the plan; the recovery report is new).

## Context

A source gives up to four files: three CSV and a JSON report (design 6.1). The
specification wants three things that pull against each other:

- a source that changed is reprocessed and its old outputs are replaced without
  `--force` (S9.4), yet an existing file must never be overwritten without proof that
  it belongs to the previous processing;
- the JSON report published last is the marker of a finished processing (S11.5), and a
  source whose report is `complete` and whose outputs are intact is skipped (S9.2);
- renaming several files is not one atomic operation (S11.5).

The plan fixes the base: the report keeps, for every output, `file`, `rows`,
`size_bytes` and `sha256` (D10); a name without a matching inventory is foreign; a
failure replaces the previous report with a `failed` one and deletes the managed
outputs (D2); `--force` allows replacing a foreign output that is not a source (D9).

The gap: during a replacement the first CSV is published before the report changes.
If the process stops then, a `complete` report describes the old outputs while a new
file sits under one of the names. On the next run that file matches no inventory, so it
is foreign, and the run is refused without `--force`; or, worse, the old report is
trusted over a changed set. D10 alone does not survive an interruption between the
files.

## Decision

1. **Ownership.** A file under a managed name is *owned* when the report beside it
   (`complete` or `in_progress`) lists the name and the file on disk has the recorded
   size (the recorded SHA-256 too when the content is verified). Everything else under a
   managed name is *foreign*. Foreign files are never deleted; they are replaced only
   with `--force` and only when the run writes that name (design 7.4 and 11.4).
2. **Recovery report.** Before the first change to the outputs of a source, the report
   `<stem>.dedup.json` is replaced atomically by a report with `status "in_progress"`
   that records the inventory of the previous outputs and the inventory of the planned
   ones (names, sizes, SHA-256 of the files already staged and validated). From that
   instant, a file under a managed name is owned if it matches either inventory.
3. **Order of a publication.** Stage and validate every CSV in temporary files next to
   the destination; write the recovery report; publish the CSV with `os.replace`;
   delete the previous owned outputs that are no longer part of the set; replace the
   recovery report by the `complete` report. The same order, with an empty planned set,
   serves a failure (D2): recovery report, deletion of the owned outputs, `failed`
   report.
4. **The recovery report is never a result.** The cache does not reuse it. After an
   interruption the next run finds it, proves ownership with it, deletes the stale
   `.<managed name>.*.tmp` of its source, reprocesses the source and publishes a
   complete set. Nothing the interrupted run published is lost track of, and no
   `complete` report ever covers a changed set.
5. **The window is short and late.** The recovery report is written after the two
   passes and the validation, never before: an interruption (or a failure) during a
   long pass leaves the previous result untouched. A failure that happens during the
   publication leaves the recovery report in place and is reported as a failure.
6. **No lock file** in V1. Two simultaneous runs on the same outputs are not protected
   and the documentation says so.

## Alternatives considered

- **Sentinel by name only** (any file with a managed name is owned). Rejected: it
  would let Dedup overwrite or delete a file the user made, which the specification
  forbids without proof.
- **Temporary directory published by one rename.** Atomic for a directory, but the
  outputs live beside the sources, possibly among other files, and a directory swap
  cannot replace three files in a shared folder.
- **A journal file separate from the report.** Same guarantee, one more name to manage
  and to exclude from discovery. The report that already exists and is already managed
  carries the same data.
- **Delete the old report first.** The ownership proof disappears at the moment it is
  needed.

## Consequences

- The report model has three statuses, `complete`, `failed` and `in_progress`, and the
  schema is discriminated on `status` (design 12).
- A hand edit of an output (its size changes) makes it foreign. The user gets a clear
  refusal rather than a silent overwrite; `--force` is the explicit way out.
- Recovery is a normal run: the tests of lot 7 simulate an interruption after each step
  of the publication (after the recovery report, after each `os.replace`, after each
  deletion) and check that the next run ends with a coherent complete set, and that no
  foreign file was touched.
- A failure after a success loses the old result (D2). With `--force` this is also
  true when the old result was still valid; the cost was accepted by the maintainer.

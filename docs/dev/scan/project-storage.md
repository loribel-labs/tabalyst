# Tabalyst Scan: project storage design

Design only, no contract tests yet, no code. This document turns the storage
requirements of the private specification (`tabalyst-gb`,
`drafts/202609-27-openrefine/Cahier-des-charges-Tabalyst-Scan-gestion-des-caches.md`)
into decisions, the way [design.md](design.md) cites its own private
specification for traceability. Its identifiers (`PROJ-xx`, `SCAN-xx`,
`CACHE-xx`) are reused here.

This document governs a storage layer that does not exist yet: the persisted
project state that a future Explore, and later Transform, will read instead
of re-scanning a source every time. It does not change the current
`tabalyst scan` / `tabalyst report --scan` behavior (design.md sections 16.3
and 16.6, decisions O12 and O17): a scan document written beside its source
stays a supported, simpler mode for one-shot CLI use. Project storage is an
additional, central store built from the same `tabalyst.scanner.scan()`
engine, for tools that need to reopen a dataset without a full rescan.

## 1. Status of decisions

Labels follow design.md section 1: **Proposed** decisions become accepted or
are amended at a gate before the lot that implements them starts;
**Deferred** decisions are left open on purpose, to a named later point;
**Implemented** decisions are built and tested, in the lot named.

### Decision register

| ID | Topic | Decision | Status | Section |
| --- | --- | --- | --- | --- |
| S01 | Storage layout | One relative path under a storage root, `workspaces/<workspace_id>/projects/<project_id>/`, identical in local and SaaS mode; only the root differs. | Proposed | 3 |
| S02 | Project identity | `project_id` is a generated opaque identifier (ULID), used as the project's directory name; never derived from the source path (PROJ-01). | Implemented (lot 7.storage-a) | 4 |
| S03 | Workspace and dataset identity | `workspace_id` is the fixed constant `local` in CLI/local mode. No separate `dataset_id` is introduced while one project holds one source. | Implemented (lot 7.storage-a) | 4 |
| S04 | `project.json` schema | Its own `format`, `format_version` and `format_revision`; `project_id`, `workspace_id`, `source.path`, `source.name`, `created_at`, `last_scan_at` (PROJ-02). | Implemented (lot 7.storage-a) | 5 |
| S05 | Freshness storage | `project.json` does not duplicate the source's size, modification time or SHA-256: they stay in `scan.json`'s `source` block, already required by O12 (PROJ-03). | Proposed | 5, 6 |
| S06 | Cache boundary | Everything under `cache/` is disposable at the file level; `project.duckdb` in full is project storage, never mixed with cache tables (CACHE-01). | Proposed | 7 |
| S07 | `project.duckdb` population | Loaded by a layer above `tabalyst.scanner`, through DuckDB's own readers configured from `ScanConfig`, rebuilt atomically and in full on every scan (SCAN-01, SCAN-04). | Proposed | 8 |
| S08 | Project lookup | `projects/index.json` maps a resolved source path to a `project_id`; reconstructible from `project.json` files, not authoritative (PROJ-06). | Implemented (lot 7.storage-a) | 4 |
| S09 | Relation to O12 | The freshness comparison of O12 (design.md section 16.6) is reused, not duplicated, resolving the source from `project.json`'s stored path instead of "beside the document" (PROJ-03, PROJ-04). | Proposed | 6 |
| D01 | DuckDB schema | Table layout, column naming and typing from scanner fields, and how large listings beyond `scan.json`'s limits (SCAN-04) are produced. | Deferred | 8 |
| D02 | Transform history | Storage of future correction and transformation history inside a project. | Deferred | - |
| D03 | Cache policy | TTL, size quotas, automatic cleanup, and the exact `tabalyst cache` command surface (CACHE-06, CACHE-07, specification section 7). | Deferred | 7 |
| D04 | Stale project default | The default behavior when a project's source has changed: reuse, rescan, compare or version (PROJ-04). | Deferred | 6 |
| D05 | Multi-source projects | A `dataset_id` distinct from `project_id`, if a project ever holds more than one source. | Deferred | 4 |

## 2. Principles

1. **One relative layout, two roots.** The path under the storage root is
   identical whether that root is a local per-OS user data directory or a
   future SaaS storage location; only the root resolution differs, so no
   later migration of the storage schema is needed for a SaaS deployment.
2. **Identity is not location.** A `project_id` never derives from a source
   path; a path only locates a file (PROJ-01).
3. **Project storage is exact for its declared scope; cache is disposable.**
   An artifact belongs to project storage when reconstructing it needs a new
   Scan (re-reading the source); it belongs to `cache/` when it can be
   recomputed from project storage alone (CACHE-01, CACHE-03).
4. **The scan engine stays storage-agnostic.** `tabalyst.scanner` never
   imports DuckDB, exactly as it never imports pandas (ET04, design.md
   section 3): project storage is built by a layer above it.
5. **Rebuilt, not patched.** A rescan replaces `scan.json` and
   `project.duckdb` in full, atomically; there is no incremental update.

## 3. Storage root and layout

```text
<storage root>/
  workspaces/
    <workspace_id>/
      projects/
        index.json                # reconstructible: source path -> project_id
        <project_id>/
          project.json
          scan.json
          project.duckdb
          cache/                  # optional; see section 7
```

- **Local storage root:** the platform's conventional user data directory,
  resolved once through the `platformdirs` package (a runtime dependency,
  accepted by the maintainer in lot 7.storage-a): `appname` `Tabalyst`,
  `appauthor` disabled to avoid an extra nesting level. The environment
  variable `TABALYST_HOME`, when set, replaces this directory (tests, servers).
  - Windows: `%LOCALAPPDATA%\Tabalyst`
  - macOS: `~/Library/Application Support/Tabalyst`
  - Linux: `$XDG_DATA_HOME/tabalyst`, falling back to `~/.local/share/tabalyst`
- **SaaS storage root:** a server-side configuration setting, out of scope
  for this document beyond the invariant of principle 1; its capacities and
  quotas layer (specification section 8) is not designed here.
- `workspace_id` is `local` in CLI/local mode (S03): a fixed constant, never
  generated or persisted separately, since there is exactly one workspace
  locally. A SaaS deployment uses a real `workspace_id` (anonymous or
  authenticated) under the same layout.

## 4. Project identity (S02, S03, S08)

- **`project_id` generation.** A ULID: lexicographically sortable by
  creation time (useful when listing `projects/` for debugging), filesystem-
  safe on every target OS, and opaque, so it carries no meaning that a
  rename or a copy of the source could invalidate (PROJ-01). It is generated
  once, at project creation, and used verbatim as the project's directory
  name.
- **No separate `dataset_id`.** The specification mentions a `dataset_id`
  alongside `workspace_id` (specification section 8), but "one project holds
  one source for now" (design.md's own framing) makes its shape
  undecidable today: introducing one now would guess at a distinction that
  may never be needed. If a project ever holds more than one source,
  `dataset_id` is designed then, scoped within `project_id` (D05). Until
  then, `project_id` is the only storage-level identifier; it must not be
  confused with `tabalyst.scanner`'s own internal dataset concept (one JSON
  source can produce several `ScanResult` datasets, entirely inside
  `scan.json`, design.md section 5).
- **Lookup index.** `projects/index.json` maps a normalized, resolved
  absolute source path to a `project_id`, so a command can find "the
  project for this file" without opening every `project.json` (PROJ-06,
  acceptance criterion 2). It is explicitly **not** an identity or a
  freshness proof: it is reconstructible by scanning `projects/*/project.json`
  (bounded by the number of local projects), so a missing or stale entry
  degrades to "no project found for this path" rather than to wrong data.
  Concurrency and locking for this index are not designed here: local,
  single-user CLI use does not need them yet.
- **Renamed or moved sources.** Since identity is not derived from path
  (principle 2), a moved file simply is not found by the index; adopting an
  existing project explicitly for a relocated file, versus creating a new
  one, is a user-facing choice left to the Explore lot that first needs it.

## 5. `project.json` schema (S04, S05)

```json
{
  "format": "tabalyst.project",
  "format_version": "0.1.0a",
  "format_revision": 1,
  "project_id": "01J8Z3K9QYVJ8VXW3N6R2E9F4D",
  "workspace_id": "local",
  "created_at": "2026-09-28T12:00:00Z",
  "last_scan_at": "2026-09-28T12:00:03Z",
  "source": {
    "path": "D:/GIT/tabalyst/examples/insurance-customers.csv",
    "name": "insurance-customers.csv"
  }
}
```

- `format`, `format_version` and `format_revision` version `project.json`
  itself, independently of `scan.json`'s own revision counter, following the
  repository's existing convention of one revision counter per artifact
  (AGENTS.md Versioning; `executions.json`'s `schema_version` is the
  precedent).
- `source.path` is the resolved, absolute path used only to locate the file;
  per principle 2 it is never part of the project's identity. `source.name`
  is its basename, echoing `scan.json`'s own `source.name`, kept here so a
  caller can display it without opening `scan.json`.
- **No size, modification time or SHA-256 here (S05).** PROJ-03 asks the
  project to keep at least these facts, but `scan.json`'s `source` block
  already carries them under the existing O12 contract (design.md sections
  16.1 and 16.6), validated by `scan_reuse.py`. Duplicating them in
  `project.json` would create two copies of the same fact that could
  disagree; delegating to `scan.json` avoids that, at the cost of requiring
  a project to always have a `scan.json`. That cost is already paid: project
  creation and a project's first scan are the same operation (principle 5),
  so a `project.json` without a matching `scan.json` is an incomplete write,
  handled like any other interrupted output (O17: temporary file, atomic
  replace).
- The version of the scan engine and of the scan document format
  (PROJ-02's wording) live in `scan.json`'s own `engine` and
  `format_version`/`format_revision` fields (design.md section 16.1);
  `project.json` does not repeat them.
- `last_scan_at` updates on every successful rescan; `created_at` never
  changes.
- `project.duckdb`'s own schema version is stored inside that file, kept
  independent from `project.json`'s and `scan.json`'s revision counters;
  its exact form is deferred (D01).

## 6. Freshness and O12 (S05, S09)

- `scan_reuse.check_source` (design.md section 16.6, O12) already implements
  the freshness comparison this design needs: same size and modification
  time is fresh; a differing modification time is decided by SHA-256, so a
  merely touched file stays fresh; a differing size is stale; a missing
  source is accepted, with a warning that it was not checked. Its current
  implementation assumes the scan document sits beside the source
  (`scan_path.parent / result.source.name`), which does not hold for
  project storage: `scan.json` lives in `projects/<project_id>/`, not next
  to the source.
- **Recommendation, not a refactor performed here:** extract the comparison
  decision (recorded source facts plus a location to stat, producing fresh,
  stale or missing) from the "where is it" lookup, so both the beside-source
  flow and the project-store flow share one implementation. Project storage
  resolves the location from `project.json`'s `source.path` (section 5)
  instead of "beside the document"; the decision logic itself is unchanged.
- **Default behavior on staleness is not decided here (D04).** `tabalyst
  report --scan` turns "stale" into a fatal `InputError` (exit 4) because it
  is a one-shot batch command with nothing sensible to fall back to. An
  interactive Explore session reusing a project is not bound by that
  choice, and PROJ-04 explicitly leaves the default open (reuse the old
  scan, rescan, compare versions, or create a new project version). This
  document only specifies that the same three-way fact (fresh, stale,
  missing) is available to whatever default the Explore lot picks; no
  result may be presented as describing the current source without that
  check, per PROJ-04.

## 7. Cache boundary (S06)

| Artifact | Class | Rule |
| --- | --- | --- |
| Source file | Persistent, outside the project | Never written to (SCAN-08); located via `project.json.source.path`. |
| `project.json` | Project storage | Never touched by `cache clean`/`clear`. |
| `scan.json` | Project storage | Never touched by `cache clean`/`clear`. |
| `project.duckdb` (whole file) | Project storage | Never touched by `cache clean`/`clear`, even partially: no cache table is ever mixed into it. |
| Anything under `cache/` | Cache | Disposable; rebuilt on demand from project storage alone, never from the source again. |

- The rule is deliberately file-tree-level, not DuckDB-internal: a future
  `tabalyst cache clean`/`clear` (specification section 7) can decide what
  is safe to delete by listing directories, without opening `project.duckdb`
  and inspecting its schema (CACHE-01). This settles the "exact location"
  question the specification leaves open in its section 10.
- A future Explore materialization backed by DuckDB (a filtered facet count,
  a materialized preview for a given filter state) lives in its own file
  under `cache/` (for example `cache/explore.duckdb`), never as an extra
  table inside `project.duckdb`.
- `cache/` is optional, matching the specification's own tree (marked
  "facultatif"); its absence is a normal state. Nothing in Scan or a basic
  Explore open depends on `cache/` existing beforehand (CACHE-03).
- TTL, size quotas, automatic cleanup and the exact `tabalyst cache` command
  surface are deferred (D03): the specification itself states these
  parameters are not decided (specification sections 6 and 7).

## 8. Populating `project.duckdb` (S07)

- `tabalyst.scanner` is unchanged by this design: it never imports DuckDB,
  exactly as it never imports pandas or does format-specific work (ET04,
  design.md section 3). `scan()` keeps returning an in-memory `ScanResult`;
  nothing here touches its contract.
- A new layer above it, a peer of today's `scan_service.py` rather than a
  part of `tabalyst.scanner`, performs, for one project:
  1. Run `scan()` to get a `ScanResult`; write it as `scan.json`, the same
     serialization `tabalyst scan` already produces (design.md section
     16.3).
  2. Load the source into `project.duckdb`'s base tables using DuckDB's own
     native readers (`read_csv_auto`, `read_json_auto` or equivalent),
     configured from the same `ScanConfig.csv`/`ScanConfig.json` settings
     used for the scan pass (delimiter, encoding, JSON collections), so
     both views describe the same logical dataset.
  3. Replace `project.duckdb` atomically (temporary file, then rename),
     with the same discipline as O17; a project is never left with a
     half-populated database.
- This makes `project.duckdb` a second, independent read of the source,
  through DuckDB's own reader rather than `tabalyst.scanner`'s streaming
  one. That is a deliberate trade: it keeps the scan engine free of any
  storage or SQL-engine dependency (principle 4), at the cost of reading the
  source twice per project scan. That cost already has a precedent: the
  JSON pre-pass for the `ijson` long-integer crash (design.md section 5.2,
  lot 4 note) also reads its source twice.
- **Explicitly open, not decided here (D01):**
  - The exact table layout: one table per scanner dataset, and how columns
    are named and typed from `field.id`/`path`. SCAN-03 requires that a
    DuckDB-inferred physical type never silently replaces Tabalyst's own
    semantic type, so a mapping is necessary, but its shape needs the
    detailed design D01 defers.
  - How SCAN-04's large listings, beyond `scan.json`'s own limits (for
    example every record index of a duplicate beyond
    `limits.max_listed_records`), are produced: recomputing them with SQL
    against the freshly loaded table, or asking the scanner for a second,
    unbounded pass. Both are plausible; neither is decided.
  - Whether DuckDB's own column type inference needs to be pinned from
    `ScanConfig` to avoid disagreeing with the scan's own native-type
    reading. Flagged as a risk, not resolved.

## 9. Relation to Tabalyst Scan's own dataset concept

To avoid the conflation the maintainer already flagged: `tabalyst.scanner`'s
"dataset" (one JSON source can produce several, section 5 of design.md, for
example one per discovered collection) is an internal concept of the scan
engine, entirely inside `scan.json`. It is not a storage-level identifier
and has no independent existence in `project.json`, in `projects/` directory
names, or in `workspace_id`/`project_id`. `project.duckdb`'s table layout
(section 8, D01) may need one table per scanner dataset, but that is a
consequence of the engine's own model, not a new identity to track.

## 10. Changes to this document

| Date | Change | Reason |
| --- | --- | --- |
| 2026-09-28 | Initial version. | Design of the project storage layer for a future Explore and Transform, requested by the maintainer ahead of any implementation lot. |
| 2026-09-28 | S02, S03, S04 and S08 implemented (`tabalyst.projects`); `platformdirs` accepted; `TABALYST_HOME` added; the example `project_id` corrected to a valid ULID. | Lot 7.storage-a. |

# Tabalyst Scan: project storage design

This document started as the design of the storage layer and now records its
incremental implementation. It turns the storage requirements of the private
specification (`tabalyst-gb`,
`drafts/202609-27-openrefine/Cahier-des-charges-Tabalyst-Scan-gestion-des-caches.md`)
into decisions, the way [design.md](design.md) cites its own private
specification for traceability. Its identifiers (`PROJ-xx`, `SCAN-xx`,
`CACHE-xx`) are reused here.

This document governs the persisted project state that a future Explore, and
later Transform, will read instead of re-scanning a source every time. Project
identity, `project.json`, `scan.json` and freshness are implemented;
`project.duckdb` and the public interface are not. This layer does not change
the current `tabalyst scan` / `tabalyst report --scan` behavior (design.md
sections 16.3 and 16.6, decisions O12 and O17): a scan document written beside
its source stays a supported, simpler mode for one-shot CLI use. Project
storage is an additional, central store built from the same
`tabalyst.scanner.scan()` engine, for tools that need to reopen a dataset
without a full rescan.

## 1. Status of decisions

Labels follow design.md section 1: **Proposed** decisions become accepted or
are amended at a gate before the lot that implements them starts;
**Deferred** decisions are left open on purpose, to a named later point;
**Implemented** decisions are built and tested, in the lot named.

Lot 7.storage-c completes D01 as a detailed **Proposed** design, ready for
the implementation gate, not as shipped behavior. Sections 8 and 9 specify
the target; the revision-1 layout and models of lots 7.storage-a/b still run.

### Decision register

| ID | Topic | Decision | Status | Section |
| --- | --- | --- | --- | --- |
| S01 | Storage layout | One relative path under a storage root, `workspaces/<workspace_id>/projects/<project_id>/`, identical in local and SaaS mode; only the root differs. | Proposed | 3 |
| S02 | Project identity | `project_id` is a generated opaque identifier (ULID), used as the project's directory name; never derived from the source path (PROJ-01). | Implemented (lot 7.storage-a) | 4 |
| S03 | Workspace and dataset identity | `workspace_id` is the fixed constant `local` in CLI/local mode. No separate `dataset_id` is introduced while one project holds one source. | Implemented (lot 7.storage-a) | 4 |
| S04 | `project.json` schema | Its own `format`, `format_version` and `format_revision`; `project_id`, `workspace_id`, `source.path`, `source.name`, `created_at`, `last_scan_at` (PROJ-02). | Implemented (lot 7.storage-a) | 5 |
| S05 | Freshness storage | `project.json` does not duplicate the source's size, modification time or SHA-256: they stay in `scan.json`'s `source` block, already required by O12 (PROJ-03). | Implemented (lot 7.storage-b) | 5, 6 |
| S06 | Cache boundary | Everything under `cache/` is disposable at the file level; `project.duckdb` in full is project storage, never mixed with cache tables (CACHE-01). | Proposed | 7 |
| S07 | `project.duckdb` population | A layer above `tabalyst.scanner` consumes the same Tabalyst observations as Scan; no independent DuckDB source inference. Rebuilt in full per generation. Supersedes the original second-reader proposal. | Proposed (7.storage-c) | 8.4 |
| S08 | Project lookup | `projects/index.json` maps a resolved source path to a `project_id`; reconstructible from `project.json` files, not authoritative (PROJ-06). | Implemented (lot 7.storage-a) | 4 |
| S09 | Relation to O12 | The freshness comparison of O12 (design.md section 16.6) is reused, not duplicated, resolving the source from `project.json`'s stored path instead of "beside the document" (PROJ-03, PROJ-04). | Implemented (lot 7.storage-b) | 6 |
| D01 | DuckDB schema | Detailed design completed by S10-S16; implementation and validation remain. | Proposed (7.storage-c) | 8, 9 |
| S10 | Internal format | `tabalyst.project-db`, alpha family `0.1.0a`, revision 1; physical DuckDB compatibility is separate. | Proposed (7.storage-c) | 8.1 |
| S11 | Dataset representation | Shared record and ordered-observation tables, dataset ids as values, canonical paths as identity; no inferred wide base table. | Proposed (7.storage-c) | 8.2 |
| S12 | Raw values | Native type tag plus lossless Scan canonical text; containers and null remain distinct; no automatic SQL casts. | Proposed (7.storage-c) | 8.3 |
| S13 | Large results | Persist unbounded record membership and paginate; compute value listings from stored observations with Tabalyst rules. Never overwrite bounded Scan measures. | Proposed (7.storage-c) | 8.5 |
| S14 | Publication | Immutable generation directory and one atomic revision-2 `project.json` manifest replacement; readers pin a generation. | Proposed (7.storage-c) | 9 |
| S15 | Scope and exposure | Raw local storage, exposure on every consumer; explicit structural scope, no claim of source-byte preservation. | Proposed (7.storage-c) | 8.3-8.5 |
| S16 | Acceptance | Semantic parity, failure injection and platform tests precede enabling project database consumers. | Proposed (7.storage-c) | 10 |
| D06 | DuckDB runtime and performance | Pin supported package/storage versions and ingestion batching after wheel, spill and benchmark evidence in 7.storage-d1. | Deferred | 10 |
| D07 | Rich row findings and JSON ancestry | Per-detector record attribution, exact source reconstruction and collection parent links need a richer engine/reader contract; design before Explore/Transform requires them. | Deferred | 8.5 |
| D08 | Deployment durability | Power-loss guarantees, network filesystems and SaaS writer coordination require platform evidence; first implementation supports tested local filesystems only. | Deferred | 9.3 |
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
  `scan.json` and its database representation, design.md section 5).
- **Lookup index.** `projects/index.json` maps a normalized, resolved
  absolute source path to a `project_id`, so a command can find "the
  project for this file" without opening every `project.json` (PROJ-06,
  acceptance criterion 2). It is explicitly **not** an identity or a
  freshness proof: it is reconstructible by scanning `projects/*/project.json`
  (bounded by the number of local projects), so a missing or stale entry
  degrades to "no project found for this path" rather than to wrong data.
  The future publication protocol serializes workspace writers (section 9),
  including lookup and index updates; the current implementation has no lock.
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
  handled as incomplete. Individual O17 replacements do not provide a
  multi-file transaction; section 9 specifies the future protocol.
- The version of the scan engine and of the scan document format
  (PROJ-02's wording) live in `scan.json`'s own `engine` and
  `format_version`/`format_revision` fields (design.md section 16.1);
  `project.json` does not repeat them.
- `last_scan_at` updates on every successful rescan; `created_at` never
  changes.
- `project.duckdb`'s own schema version is stored inside that file, kept
  independent from `project.json`'s and `scan.json`'s revision counters;
  its proposed form is specified in section 8.1 (D01).

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
- `scan_reuse.compare_source()` implements the comparison decision (recorded
  source facts plus a location to stat, producing `fresh`, `stale` or
  `missing`) independently of the "where is it" lookup. Both the beside-source
  flow and `projects.freshness.project_freshness()` share it. Project storage
  resolves the location from `project.json`'s `source.path` (section 5)
  instead of "beside the document"; the decision logic is unchanged.
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

## 8. Detailed database contract (D01, S07, S10-S13, S15)

### 8.1 Format and compatibility

The target is one self-contained DuckDB database per committed generation,
opened read-only by consumers. Its Tabalyst objects live only in `meta` and
`data`; no extension, source attachment, external view or cache is required
to reopen it without the source. Derived query caches remain under `cache/`.

`meta.format` has exactly one row (singleton key `id = 1`):

| Column | SQL type | Meaning |
| --- | --- | --- |
| `id` | INTEGER | Primary key, constrained to 1. |
| `format` | VARCHAR | Exactly `tabalyst.project-db`. |
| `format_version` | VARCHAR | Exactly `0.1.0a` for this family. |
| `format_revision` | INTEGER | Initially 1; increases for schema or semantic changes. |
| `project_id`, `workspace_id`, `generation_id` | VARCHAR | Binding to the manifest and immutable generation. |
| `scan_sha256` | VARCHAR | SHA-256 of the exact UTF-8 bytes of the sibling `scan.json`. |
| `duckdb_version`, `storage_compatibility` | VARCHAR | Actual writer version and explicitly selected physical storage compatibility target. |
| `loader_version`, `record_semantics_version` | INTEGER | Initially 1; observation codec and Scan-compatible record comparison contract. |

All columns are non-null. Unknown logical revisions are rejected, not guessed
from table names. No automatic alpha migration: rebuild from the source;
if unavailable, keep the old generation and report incompatibility. A physical
DuckDB open failure is distinct from an unsupported Tabalyst revision.
An engine upgrade alone does not increment the logical revision; changed
meaning or required tables do. The supported DuckDB package range and physical
storage target must be chosen and tested in d1 (D06), not invented here.
Consult DuckDB's separate
[storage compatibility contract](https://duckdb.org/docs/current/internals/storage)
when selecting that physical target; it does not version Tabalyst's schema.

`scan.json` remains authoritative for source facts, effective configuration,
engine/detector/normalization versions, field interpretation, exposure, scope
and diagnostics. Database metadata references it through `scan_sha256`,
rather than duplicating its full profile. The manifest binds both files.
The database alone supports raw queries, but is not a valid Tabalyst project
without its matching scan and manifest.

### 8.2 Tables, identities and ordering

Use **shared long tables**, not one inferred wide SQL table per dataset.
This represents heterogeneous records, repeated array observations, empty
datasets and up to the Scan field cap without requiring that many SQL columns.
Each dataset is a partition identified by the exact `dataset.id` value.
There is no new persistent source or dataset identity (D05 remains deferred).

All identifiers below are fixed ASCII, owned by Tabalyst. Source names,
dataset ids, paths and field ids are bound SQL values, never identifiers.
No sanitization, truncation or hash is used as the identity of a name, so
duplicate headers, case-only differences, Unicode, dots, brackets, quotes,
reserved SQL words and empty keys cannot collide.

In the following tables, columns are non-null unless explicitly marked `?`.
Use BIGINT for indices, ordinals and counts (positive indices, nonnegative
counts); VARCHAR for identifiers/text and BOOLEAN for flags. Counts outside
the SQL integer range fail the build explicitly; never wrap or round.
Suffix `_json` means validated UTF-8 JSON stored as VARCHAR, serialized with
sorted object keys, compact separators and `ensure_ascii=False`; array
order is retained. It avoids depending on an optional JSON SQL extension.

| Table | Columns and constraints |
| --- | --- |
| `meta.datasets` | `dataset_id` PK, `ordinal` unique (1-based result order), `kind`, `collection_path_json?`, `record_count`. One row for **every** Scan dataset, including empty or not-found collections. |
| `meta.fields` | `dataset_id`, `field_id`, `ordinal` (1-based field order), `path_json`, `name`, `display`, `parent_field_id?`, `collection_dataset_id?`. PK (`dataset_id`, `field_id`); unique (`dataset_id`, `path_json`) and (`dataset_id`, `ordinal`); dataset FK. Copy field metadata verbatim, including nullable parent and collection links. |
| `data.records` | `dataset_id`, `record_index`, `location_json`, `depth_truncated`, `observation_count`, `with_missing`, `is_empty`, `duplicate_key?` (BLOB). PK (`dataset_id`, `record_index`); dataset FK. One row per analyzed record only. |
| `data.observations` | `dataset_id`, `record_index`, `observation_index` (1-based within the record), `path_json`, `field_id?`, `native_type`, `raw_text?`, `array_length?`. PK (`dataset_id`, `record_index`, `observation_index`); record FK; non-null field ids reference `meta.fields` within that dataset. |
| `meta.listings` | `dataset_id`, `listing_id`, `status`, `record_count?`, `reason?`, `semantics_version` (INTEGER, initially 1). PK (`dataset_id`, `listing_id`); dataset FK. |
| `data.listing_records` | `dataset_id`, `listing_id`, `record_index`. Composite PK of all three; FKs to listing and analyzed record. No repeated record within a listing. |

The loader validates all constraints before publication, including constraints
not expressible as a simple SQL FK. `meta.fields` contains exactly the fields
in Scan, not an inferred superset. `field.id` is local to the generation:
JSON discovery can renumber `f<n>` on rescan. Cross-generation matching uses
(dataset id, canonical path segments), never `f<n>`, display or table order.
CSV `column_3` maps to `[{"column":3}]`, not the header text. No promise
of semantic column identity survives a source column reorder.

Every emitted observation, including root and containers, is retained in
reader order. Resolve field ids after Scan finalization by canonical path.
The root and paths beyond `max_fields` may have a null field id: keep their
path and raw observation for record comparison, but do not present them as
profiled fields. There is no unbounded in-memory registry of these paths;
repeat path text in storage and insert bounded batches.

Record indices are Scan's 1-based dataset-local indices, with gaps for
excluded records. They are not SQL row numbers or physical line numbers.
`location_json` stores exactly Scan's location (including 0-based JSON
element indices where supplied). Always order queries explicitly by record
and observation indices; SQL insertion order is not a contract.

### 8.3 Values, absence and collection semantics

| Native type | Authoritative stored payload |
| --- | --- |
| `string` | `raw_text` is the exact decoded string, including empty text and whitespace; `array_length` is SQL NULL. |
| `integer`, `number` | `raw_text` is Scan's `canonical_text` of the Python int/Decimal. No BIGINT, DOUBLE or fixed-scale DECIMAL conversion of source values. |
| `boolean` | `raw_text` is `true` or `false`, preserving its native tag. |
| `null`, `object` | Both payload columns are SQL NULL, distinguished by the native tag. |
| `array` | `raw_text` is SQL NULL; `array_length` is the observed nonnegative length, including zero. |

Validate this tagged union on write and reopen. SQL NULL payload is not an
absent field. Strings `"123"`, integers `123`, numbers `123.0`, booleans,
nulls, `""`, blanks and configured markers remain distinct. CSV values
are always strings. Technical types and detector interpretations stay in Scan;
any future typed SQL projection is derived, explicit and fallible, never a
replacement for these columns.

“Raw” means **as observed by Scan**, not original source bytes: CSV quoting,
encoding and line-ending syntax are decoded, and JSON number spelling follows
design 9.1 (`1e3` may become `1E+3`, integer `-0` becomes `0`).
Objects are container observations, not serialized source objects. The
database is not a lossless source archive or a Transform export format.

There is no synthetic absence row. For a tracked key/column field, presence
within a record is its observation count; absence is the number of object
observations at its canonical parent path minus that count. For the root,
the denominator is one analyzed record; for items paths, absence is undefined
(NULL), as in Scan. A null/missing parent is not an object and creates no
child absence. For example, `[{}, {"x":null}, {"x":""}]` has one absence,
one null and one empty string for `x`, not three SQL nulls. Repeated object
parents produce repeated opportunities; these counts need no guessed array
indices. Precise attribution to a particular parent occurrence is D07.

Keep automatic JSON document/collection separation exactly as Scan emits it.
A promoted array remains an array observation with its length in the document;
its elements occur only in the named collection dataset. Arrays inside records
remain repeated observations in that dataset. Explicit selections crossing
arrays keep one sequence of indices for each selected dataset; do not invent
a parent FK from `location.element`, which can repeat across parent arrays.
Missing collections still have metadata and zero records. Dataset events may
interleave and the document record may arrive last.

Structural limits are not removed by persistence: depth-truncated subtrees,
excluded records and unselected collections are not recoverable from this
database. Retained unprofiled paths do not make `structure.paths` complete.
Query responses identify the generation, dataset, structural limitations and
analyzed scope; “complete listing” means complete for that scope.

This file deliberately holds unmasked raw observations, including sensitive
values; masking a profile is not encryption or anonymization of project
storage. Use local project access permissions for staging and committed files.
Every Tabalyst listing/export applies Scan's exposure rules before ranking,
grouping or paging (equal masks merge; hide returns no values). Unknown-field
payloads are not exposed through profiled-field APIs. Raw SQL access is
privileged local access, not the default Explore API. The existing adaptive
sensitive-detector blind spot (design 13) remains a risk; storage does not
silently change detector behavior.

### 8.4 Loading with the effective ScanConfig (amended S07)

Resolve configuration once using the existing `resolve_scan_config()`
precedence (defaults, explicit config files in order, explicit arguments).
Pass that effective object to `scan(..., on_record=sink)`. The storage sink
is outside `tabalyst.scanner`; the scanner imports no DuckDB and no source
reader is replaced. The existing hook receives analyzed records before engine
processing, including CSV batches expanded to Records, and observes exactly
the exclusions and structural limits of the chosen Tabalyst reader.

The sink streams records/observations and record facts into a private staging
database using an explicit schema and bounded parameterized inserts. It must
not mutate Records or accumulate all source data in Python. After scan
completion, populate empty datasets, declared fields and metadata from
ScanResult and resolve the nullable field references. Sink failure aborts the
whole generation; it never merely disables storage while publishing Scan.
Use temporary ingestion tables until final metadata is available, then build
the constrained final tables and drop the ingestion tables before publication;
do not insert unresolved foreign keys into the final schema.
For CSV duplicate comparison, derive the declared table layout from the
column paths of the first analyzed record (including unprofiled columns),
then validate it against the final source header. A zero-record dataset needs
no digest. JSON always uses the ordered-observation comparison. Merely
instantiating `RecordFacts` without its CSV layout would produce wrong keys.

Use the exact effective settings for string categories, normalization and
record facts. Do not load the top-level Sample CSV settings or re-read config
files midway. Verify `config_sha256(result.config)` equals the result's
fingerprint before publication. The hook covers analyzed records only:
full excluded-record locations are **not** available from it; bounded
diagnostics cannot be expanded by guessing (D07).

The original S07 proposed an independent DuckDB reader pass. That is rejected
as the baseline: configuring a delimiter and `all_varchar` does not prove
parity for malformed records, null handling, headers, Unicode, collections,
paths and arbitrary-size numbers. DuckDB's CSV inference options and JSON
schema inference are documented separately from Tabalyst's reader contract:
[CSV reader](https://duckdb.org/docs/stable/data/csv/overview),
[JSON loading](https://duckdb.org/docs/lts/data/json/loading_json).
An accelerated native-reader path would need a later parity design and full
corpus proof; it is not a fallback on sink failure.

The same record stream supplies the scan and database, eliminating disagreement
between two parses. JSON retains its current safety pre-pass; no extra parsing
pass is introduced. Compare source identity/size/mtime before and after Scan
and abort on observable mutation/replacement. The source hash in Scan describes
the actual bytes read. These checks cannot guarantee an atomic snapshot of an
externally rewritten file whose metadata is restored; a source snapshot or
cooperating source lock requires later evidence/design, not an O12 shortcut.
On later opens, freshness still uses S09 against the manifest's generation.

### 8.5 Large listings beyond scan.json (SCAN-04)

Persist three baseline listings for each dataset: `records.with_missing`,
`records.empty` and `records.duplicates`. Their metadata status is
`complete` with a count (including zero), or `disabled` with no count when
duplicate detection is disabled. A storage computation failure prevents
publication; it is not a complete empty result.

Compute missing/empty flags with the existing record semantics (design 9.10,
`RecordContext`): only observed scalar values count. An absent field is
not a missing scalar for these record listings; a record with no scalar
values is not empty. Persist their membership without `max_listed_records`.

For duplicates, compute the same record digest as Scan in the sink, using
the shared table/ordered-observation logic and dataset-local path-token state;
retain all digests on disk instead of a bounded `_seen` set. Refactor a
shared storage-neutral helper if necessary; never implement a different SQL
row equality, sort object members or normalize strings. The digest covers
unprofiled observations too. With `records.duplicates=false`, store NULL
keys and no duplicate membership. Otherwise SQL partitions by dataset and
digest and lists every record after the minimum index in each group. This
inherits Scan's negligible 128-bit digest collision risk; it is not claimed
to be mathematical byte equality. Record-semantic version 1 pins that rule,
including canonical reconstruction tests for Decimal representations.

The persisted duplicate count can exceed a Scan `record_budget` lower bound.
Do not rewrite Scan's envelope or pretend its sampled list was exhaustive.
When Scan's count is complete, counts and its listed prefix must match.
When it is limited, its count is a lower bound and every listed record must
belong to the full database list (not necessarily its prefix).

Queries use (generation id, dataset id, listing id) as logical references,
then keyset pagination by `record_index > after`, ordered ascending. A
cursor from another generation is rejected. Page size limits transport only;
counts cover the whole scope. No change to `scan.json` is required now.
A future JSON reference API needs its own format change when implemented.

Full value frequencies and normalization variants can be computed from raw
observations without the source, even after Scan released its value tables:
run the shared Python category/normalization rules in bounded batches, then
let DuckDB group the resulting tagged keys on disk. Use design 9.1/10
populations and tie order, with exposure before listing. Use explicit binary
text comparison proven equivalent to Python ordering; no SQL lower/trim,
locale collation, inferred number or date casts. Results are separately
labelled storage-derived with their scope and semantic versions, not edits
to Scan. Persist reusable query intermediates only under `cache/`.

The database is the durable backing for these large results; query
materializations are disposable. Disk or spill exhaustion fails explicitly,
never truncates a “complete” list or requests an unbounded in-memory Scan.

**D07 remains deferred:** per-detector anomaly row lists and full exclusion
locations cannot be recovered faithfully from bounded examples, aggregated
detector results or the current record-only hook. Re-running detectors could
contradict adaptive `not_tested`, failures or field-level decisions. A future
storage-neutral attribution stream must be designed before claiming these
SCAN-04/SCAN-05 cases. Likewise defer exact JSON occurrence ancestry and
source-byte reconstruction. The three record lists and value listings above
are the initial supported scope, not a claim that every future issue exists.

## 9. Atomic generations, failure and recovery (S14)

### 9.1 Why the layout must evolve

The working-tree implementation of 7.storage-b writes `scan.json` with
`write_text_atomic()`, then calls `record_scan()`. A scan failure before
writing preserves the old project, as its tests show. However, a failure
between those two writes can leave a new scan with old project metadata.
Adding a third rename does not make the three files atomic. The current
`create_project()` also publishes metadata/index before scanning. These
are implementation gaps to fix in the next lot, not guarantees already met.

The target layout supersedes section 3's revision-1 artifact locations:

```text
<project_id>/
  project.json                     # revision 2: authoritative commit manifest
  generations/
    <generation_id>/
      scan.json
      project.duckdb
  .staging/<generation_id>/         # unpublished, writer-owned
  cache/                           # keys must include generation_id
```

Generation ids are new opaque ULIDs, unique within the project, unrelated to
dataset/field ids. Files in a published generation never change. Do not create
root-level scan/database aliases that could accidentally mix generations.

Revision-2 `project.json` retains all revision-1 identity/source/timestamp
fields and adds exactly:

```json
{
  "generation": {
    "id": "01J8Z3K9QYVJ8VXW3N6R2E9F4D",
    "scan_sha256": "<64 lowercase hex digits>",
    "database_sha256": "<64 lowercase hex digits>"
  }
}
```

Paths are derived from the validated generation id, never arbitrary manifest
paths. `last_scan_at` is the successful publication timestamp; `created_at`
never changes. Source facts remain only in Scan (S05); these hashes bind
artifacts, not the source. The database stores the scan hash but not its own,
avoiding a circular hash. No scan format revision changes for this design.

Readers read the manifest once, validate its revision and ids, and pin that
generation for their whole operation/session. Before use, validate both file
hashes, database metadata binding, supported revisions, field mappings and
counts. Corruption or missing artifacts fails closed, never falls back to a
different file or silently starts a scan. Subsequent freshness checks use
that pinned scan. Full integrity verification cost must be measured in d1;
any later shortcut must retain an explicit integrity contract.

### 9.2 Publication protocol

1. Acquire an OS-backed exclusive **workspace writer lock** before project
   lookup/create, index modification or rescan, held through publication.
   Lock contention reports busy; a lock-file's existence or PID alone is not
   proof of ownership. OS release on process death avoids stale-lock deletion
   heuristics. This deliberately serializes local project writers initially;
   SaaS/multiple-host locking is D08. Readers of existing generations need no
   writer lock. Reserve a separate workspace maintenance lock: readers take
   it shared before reading a manifest and hold it until closing the pinned
   generation; writers take it shared before taking the writer lock. Cleanup
   must acquire it exclusively before the writer lock, proving no cooperating
   reader/writer is active. If that shared/exclusive primitive is not yet
   implemented on a platform, disable cleanup there; do not guess from PIDs.
2. Reserve project identity privately for a first scan (no manifest/index
   visibility yet). Create a fresh staging directory on the same filesystem
   as the final generation; never overwrite an existing generation id.
3. Build the database from the Scan hook, finalize metadata/listings, write
   the ordinary `scan_document(result)` bytes and its hash into `meta.format`.
   Validate scope, counts, mappings and prefix/subset invariants. A partial
   Scan with excluded records is publishable if storage is complete for its
   declared analyzed scope; storage failure is never “partial Scan”.
4. Commit the database transaction, checkpoint, close every write handle.
   Require a standalone database with no required WAL/sidecar, reopen it
   read-only for validation and close it. Flush/synchronize both files and
   directories using supported platform primitives. Hash the closed database.
5. Rename the staging directory to its unique final generation path. Flush
   the parent directory where supported. This still does not commit a project.
6. Prepare the complete revision-2 manifest and atomically replace
   `project.json` on the same filesystem, using O17's temporary-file discipline
   and required synchronization. **This replacement is the commit point.**
   Publish timestamps and both artifact hashes together.
7. Update the reconstructible index. Emit completion for the committed
   generation. Index failure is a committed success with an index-repair
   warning, not a rollback or a reported scan failure. If an error makes the
   commit outcome uncertain, re-read the manifest under the lock: classify
   by its generation id; if unreadable, report “outcome unknown, reopen for
   recovery”, never delete the potentially committed generation.

A rescan keeps the same project id and the previous generation available to
already-open readers. Normal scanning never deletes old generations. Deferred
maintenance may remove unreferenced generations only with no readers/writers;
a new generation does not promise user-facing version history (D02/D04).
All mutating internal entry points must use the writer discipline; replacing
only `scan_project()` while leaving `record_scan()` free to publish revision-2
metadata would break this protocol.

### 9.3 Incomplete states and recovery

| Observed state | Reader/recovery action |
| --- | --- |
| Staging directory, no committed manifest | Not a project to open/list/index. After exclusive ownership is established, remove only known staging files or quarantine them for inspection. |
| Complete generation renamed, manifest still old/missing | Uncommitted orphan; continue serving old generation if present. Never choose the newest directory automatically. |
| Manifest selects a valid generation, index missing/stale | Open it; rebuild the index from validated committed manifests. |
| Failure before commit during rescan | Old manifest and old artifacts remain authoritative; retain their timestamps. |
| Failure after commit during index/cleanup | New generation remains authoritative; report maintenance warning. |
| Manifest selected artifact missing, mismatched hash or corrupt DB | Incomplete/corrupt project; refuse data queries. Preserve evidence; explicit rescan or validated backup restoration required. |
| Revision-1 project (7.storage-a/b), with or without a scan | Legacy scan-only project, not database-ready. Do not fabricate an empty DB or infer freshness from last_scan_at. Rebuild explicitly from source to revision 2, preserving project id/created_at, and publish only on success. |
| Source absent | Existing valid generation can open with S09's missing-source warning. Rebuild cannot succeed; preserve artifacts. |

Locks protect concurrent writes, not external source modification. Immutable
generations avoid replacing an open DuckDB file on Windows. Do not publish a
database still dependent on its WAL: DuckDB's
[checkpoint](https://duckdb.org/docs/current/sql/statements/checkpoint)
synchronizes WAL data into the main file. DuckDB's
[concurrency contract](https://duckdb.org/docs/current/connect/concurrency)
does not supply a transaction across these three project artifacts.

The baseline guarantee is atomic visibility and recovery after process
failure on tested local filesystems. Power-loss durability depends on file
and directory synchronization support, particularly on Windows. D08 requires
platform evidence before stronger claims; network shares, object storage
and multi-host SaaS publication are not implicitly supported by this local
rename protocol. Old generations cost disk space until explicit maintenance;
retention/quotas remain D03, not an automatic `cache clear` side effect.

## 10. Acceptance and implementation test plan (S16)

The implementation gate reviews S07/S10-S16 and the explicit D06-D08
boundaries. No DuckDB dependency or loader is added by 7.storage-c.

| Area | Required acceptance evidence |
| --- | --- |
| Codec/schema | Reopen without the source or extensions; reject unknown logical versions, invalid tags, FK/mapping errors and physical incompatibility distinctly. Round-trip long strings, Unicode/control characters, very large integers, Decimal exponents/trailing zeros, boolean/null/container tags without precision loss. |
| CSV | Golden comparisons with the existing Scan reader for duplicate/blank/case-only headers, SQL keywords, BOM/cp1252, delimiter overrides, quoting/multiline records, blank lines, width errors, strict/tolerant mode, NUL/encoding failures and header-only files. Every emitted cell stays a string. |
| JSON | Root scalar/object/array, heterogeneous records, empty/missing collections, nested arrays, promoted collections, explicit paths crossing arrays, punctuation/empty keys, late fields, absent vs null vs empty, null parents, repeated parents, duplicate keys and both ijson backends. Preserve known backend limitations; do not call them fixed. |
| Limits/configuration | Default/file/argument precedence, lists replacing lists, fingerprints, all structural limits, long values, released frequency tables, zero listing limits, disabled duplicates, adaptive detector settings, mask/hide/show; persisted raw observations must never leak through default value APIs. |
| Parity | Dataset order/id/kind/count, paths and ids, per-field native counts/presence/array lengths, record locations, observation order and missing/empty membership equal Scan for tracked scope. Hook/non-hook and workers=1/multiple workers produce the same Scan except timings. No untracked field promoted into the profile. |
| Large results | More than 12,438 affected records and more than max_listed_records; late duplicate groups after max_tracked_records, first occurrence excluded from duplicates, cross-dataset separation, empty datasets, disabled cases. Compare complete prefixes and limited subsets, paginate without gaps/repeats, reject stale cursors. Force digest collisions to document the inherited equality rule. |
| Value queries | Frequencies/variants beyond Scan limits from DB alone, exact category/normalization parity including Unicode casefold/accent/whitespace, type-separated keys, long values, equal-mask merging before ranking, hidden lists, deterministic ties. Compare with exhaustive small reference fixtures. |
| Failures | Inject failures at every protocol boundary: parsing, sink insert, finalize, serialization, disk full/spill failure, commit/checkpoint/close, both renames, sync, manifest write, index update. Kill a subprocess before/after commit. Verify old-or-new visibility, no mixed pair, first-scan invisibility and explicit unknown outcomes. |
| Concurrency/recovery | Two writers for same source and different sources, lock owner killed, old reader during rescan, Windows open handles, orphan staging/final generations, corrupted manifest/hash/file, stale index, unsupported revision, missing source and legacy revision 1. No cleanup of an active or selected generation. |
| Resource/platform | Windows plus Linux/macOS local-filesystem CI, Python versions supported by the project, wheel availability. Benchmark CSV and JSON, wide/deep/long-value and million-record sources, insertion batching, spill disk, peak memory, final DB size, hash/open time and old+new+temporary peak disk. Set measured budgets before optimization; do not promise native-reader speed. |

The existing tests of lots a/b remain the baseline; extend them to cover
failure after scan writing, which they currently do not exercise. Update
their path/layout expectations deliberately when revision 2 is implemented.
Run pytest and Ruff, regenerate demos and verify unchanged one-shot CLI
behavior. Browser regression is needed only if report presentation changes.

Suggested sequential implementation lots (one conversation each):

1. **7.storage-d1 — storage codec and staged loader.** Select/test DuckDB
   dependency and physical format (D06), explicit schema, streaming sink,
   Scan metadata binding, raw round-trips, record memberships and semantic
   parity. Keep it private and unpublished until d2.
2. **7.storage-d2 — atomic project publication and recovery.** Revision-2
   manifest, location resolution, workspace locking, first scan/rescan,
   legacy rebuild, pinned readers, freshness/index integration, failure and
   concurrency tests. This is the gate before enabling database project use.
3. **7.storage-d3 — large-query interface and measurements.** Generation-bound
   pagination, full frequencies/variants, exposure, resource benchmarks and
   cache boundary. Do not imply per-detector/exclusion attribution; design
   D07 separately if the next Explore requirements need it.

No new public behavior ships in this design lot; no public format changelog,
release notes or tabalyst-studio changes are required. When implementation
exposes a CLI/API/report/demo change, update English documentation then and
record the corresponding tabalyst-studio follow-up.

## 11. Changes to this document

| Date | Change | Reason |
| --- | --- | --- |
| 2026-09-28 | Initial version. | Design of the project storage layer for a future Explore and Transform, requested by the maintainer ahead of any implementation lot. |
| 2026-09-28 | S02, S03, S04 and S08 implemented (`tabalyst.projects`); `platformdirs` accepted; `TABALYST_HOME` added; the example `project_id` corrected to a valid ULID. | Lot 7.storage-a. |
| 2026-09-28 | S05 and S09 implemented: the project scan service writes `scan.json`; project freshness reuses O12 through the location-independent `compare_source()`. | Lot 7.storage-b. |
| 2026-09-28 | D01 detailed: S07 amended; S10-S16 define schema, raw observation loading, scope, large listings and generation publication; D06-D08 name evidence still required. | Lot 7.storage-c, design only. Independent inference cannot establish Scan parity; per-file atomic replacement cannot commit an artifact set. |

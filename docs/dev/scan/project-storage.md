# Tabalyst Scan: project storage design

Default CSV Scan and Report stopped building this private DuckDB project
storage after the measured 0.4.3 regression. They now share a scan-only JSON
document; this design and its explicit private APIs remain available for future
query features. Existing generations are not removed by the default commands.

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
the private staged `project.duckdb` loader is implemented in d1 and atomic
generation publication in d2. CSV Scan and Report now use project storage by
default; Explore remains private.
Lot d3 added private paginated consumer queries and resource measurements.
The CSV command handoff changes the default `tabalyst scan` output, while
`tabalyst report --scan` keeps its standalone-document behavior (design.md
sections 16.3 and 16.6, decisions O12 and O17): a scan document explicitly
exported beside its source stays a supported mode for one-shot CLI use. Project
storage is the default central store for CSV commands, built from the same
`tabalyst.scanner.scan()` engine, for tools that need to reopen a dataset
without a full rescan.

## 1. Status of decisions

Labels follow design.md section 1: **Proposed** decisions become accepted or
are amended at a gate before the lot that implements them starts;
**Deferred** decisions are left open on purpose, to a named later point;
**Implemented** decisions are built and tested, in the lot named.

The maintainer accepted the lot c design at the d1 implementation gate.
Lot 7.storage-d1 implements the codec, private staged loader and baseline
record lists. Lot 7.storage-d2 implements section 9's publication protocol,
pinned readers and explicit orphan quarantine. Revision-1 projects remain
scan-only until explicitly rebuilt; a successful rebuild preserves their
identity and commits a revision-2 generation.
Lot 7.storage-d3 adds section 8.6's private consumer queries and section 8.7's
maintainer-amended capped value storage; the Scan contract is unchanged.

### Decision register

| ID | Topic | Decision | Status | Section |
| --- | --- | --- | --- | --- |
| S01 | Storage layout | One relative path under a storage root, `workspaces/<workspace_id>/projects/<project_id>/`, identical in local and SaaS mode; only the root differs. | Proposed | 3 |
| S02 | Project identity | `project_id` is a generated opaque identifier (ULID), used as the project's directory name; never derived from the source path (PROJ-01). | Implemented (lot 7.storage-a) | 4 |
| S03 | Workspace and dataset identity | `workspace_id` is the fixed constant `local` in CLI/local mode. No separate `dataset_id` is introduced while one project holds one source. | Implemented (lot 7.storage-a) | 4 |
| S04 | `project.json` schema | Its own `format`, `format_version` and `format_revision`; `project_id`, `workspace_id`, `source.path`, `source.name`, `created_at`, `last_scan_at` (PROJ-02). | Implemented (lot 7.storage-a) | 5 |
| S05 | Freshness storage | `project.json` does not duplicate the source's size, modification time or SHA-256: they stay in `scan.json`'s `source` block, already required by O12 (PROJ-03). | Implemented (lot 7.storage-b) | 5, 6 |
| S06 | Cache boundary | Everything under `cache/` is disposable at the file level; `project.duckdb` in full is project storage, never mixed with cache tables (CACHE-01). Explicit cleanup is limited to owned query directories. | Implemented privately (7.storage-d3/e); automatic quotas/cleanup deferred | 7, 8.6 |
| S07 | `project.duckdb` population | A layer above `tabalyst.scanner` consumes the same Tabalyst observations as Scan; no independent DuckDB source inference. Rebuilt in full per generation. Supersedes the original second-reader proposal. | Implemented privately (7.storage-d1) | 8.4 |
| S08 | Project lookup | `projects/index.json` maps a resolved source path to a `project_id`; reconstructible from `project.json` files, not authoritative (PROJ-06). | Implemented (lot 7.storage-a) | 4 |
| S09 | Relation to O12 | The freshness comparison of O12 (design.md section 16.6) is reused, not duplicated, resolving the source from `project.json`'s stored path instead of "beside the document" (PROJ-03, PROJ-04). | Implemented (lot 7.storage-b) | 6 |
| D01 | DuckDB schema | Explicit schema/codec/staging, atomic publication and private paginated queries. | Implemented privately (7.storage-d1/d2/d3) | 8, 9 |
| S10 | Internal format | `tabalyst.project-db`, alpha family `0.1.0a`; revision 1 reads exhaustive observations, revision 2 writes capped catalogs. Physical compatibility stays independent. | Implemented privately (d1/d3) | 8.1, 8.7 |
| S11 | Dataset representation | Revision 1 has ordered observations; revision 2 keeps complete record facts and bounded per-field catalogs, without row payload reconstruction. | Implemented privately (d1/d3) | 8.2, 8.7 |
| S12 | Raw values | Native tag plus canonical text, no SQL inference. New generations retain at most 10,000 distinct analyzable values per field, with occurrence/omission counts. | Amended by maintainer 2026-09-29; implemented (d3) | 8.3, 8.7 |
| S13 | Large results | Record memberships stay complete. Value queries are complete for retained values, explicitly limited for the full population after storage saturation. Scan measures never change. | Implemented privately (d1/d3) | 8.5-8.7 |
| S14 | Publication | Immutable generation directory and one atomic revision-2 `project.json` manifest replacement; readers pin a generation. | Implemented privately (7.storage-d2) | 9 |
| S15 | Scope and exposure | Raw local storage, exposure on every consumer; explicit structural scope, no claim of source-byte preservation. | Implemented privately (d1/d3) | 8.3-8.6 |
| S16 | Acceptance | Semantic parity, failure injection and platform tests precede enabling project database consumers. | d1/d2/d3 tested locally; remote OS CI remains unverified | 10 |
| D06 | DuckDB runtime and performance | DuckDB 1.5.5, physical v1.4.0, bounded batches; local loader/query/resource evidence, OS CI added. No native-reader speed or process-memory guarantee. | Selected/tested locally (7.storage-d1/d3) | 10.1, 10.2 |
| D07 | Rich row findings and JSON ancestry | Per-detector record attribution, exact source reconstruction and collection parent links need a richer engine/reader contract; design before Explore/Transform requires them. | Deferred | 8.5 |
| D08 | Deployment durability | Power-loss guarantees, network filesystems and SaaS writer coordination require platform evidence; first implementation supports tested local filesystems only. | Deferred | 9.3 |
| D02 | Transform history | Storage of future correction and transformation history inside a project. | Deferred | - |
| D03 | Cache policy | Private explicit owned-query cleanup is implemented; TTL, size quotas, automatic cleanup, generation retention and the exact `tabalyst cache` command surface remain open (CACHE-06, CACHE-07, specification section 7). | Partially implemented (e); remaining policy deferred | 7 |
| S17 | Private project reopening | Inspect/open a verified pinned generation with explicit current-source or snapshot intent; no automatic rescan. Explicit rescan must target the chosen project with a generation precondition. | Private f1/f2 implemented; product D04 default deferred | 6.1 |
| S18 | Product reopening policy | Open verified fresh projects against the current source; otherwise present the pinned assessment and require an explicit snapshot or rescan choice. | Accepted by maintainer; private adapter implemented (7.storage-g1) | 6.2 |
| D04 | Stale project default | Section 6.2 defines the first Explore-facing choice for stale/missing/failed checks; version comparison and history remain undecided (PROJ-04). | First private policy implemented; public exposure deferred | 6, 6.2 |
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
  the freshness comparison this design needs: a differing size is
  stale, otherwise the SHA-256 decides whatever the modification time (inspect
  design DP-D), so a merely touched file stays fresh; a missing
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

### 6.1 Private reopening contract (S17, lots 7.storage-f/f1/f2)

Framed after lot e on 2026-09-29; the maintainer's request to implement f1
accepts the read-only boundary. `_session.py` implements inspection/opening;
the explicit rescan boundary below is implemented in f2. It does not change
`open_generation()`, O12, public project exposure or the Scan engine. The
contract separates inspecting/reusing stored analysis from explicitly replacing
it. Product UX and the default Explore response to staleness remain deferred.

**Read-only session (implemented lot f1).** Select by
`StorageLocation` and `project_id`, never by source path/index. Open through
the existing verified generation context and use its one pinned manifest,
Scan and database for configuration comparison, source comparison and queries.
Do not call `project_freshness()` to read another manifest after pinning.
No open/inspection creates a project, scans a source or repairs an index.
Normal disposable reader/query scratch files remain allowed under `cache/`;
read-only means persistent project/source artifacts stay unchanged.

The session's immutable assessment identifies workspace/project/generation,
source path, check time, the existing `SourceCheck` fact, recorded and optional
requested configuration fingerprints, readiness, and structured warning/error
codes. It is transient metadata, not another persisted profile or public
format. Inspection returns readiness facts for a valid verified generation;
integrity failures raise before a query session can be yielded. Source I/O
failure is a separate failed assessment, never `missing` or `fresh`; do not
extend or reinterpret the shared three-state `SourceState` contract.
An assessment returned after closing its inspection context is advisory.
Subsequent opening rechecks the newly pinned generation; an optional
`expected_generation_id` binds a caller's earlier decision and rejects a
changed selection. Never treat an old assessment as current verification.

Two explicit opening intents are implemented:

| Intent | Fresh source | Stale source | Missing/non-file source | Source comparison I/O failure |
| --- | --- | --- | --- | --- |
| `require_current` (private default) | Queries allowed if settings match | Inspection explains blockage; opening refuses | Inspection explains blockage; opening refuses | Inspection records failure; opening refuses |
| `snapshot` (explicit) | Queries describe the stored generation | Queries allowed with stale-source warning | Queries allowed with source-not-checked warning | Queries allowed with check-failed warning; no current-source claim |

Both intents query the stored generation only. Freshness is O12's observation
at check time, not a live guarantee or atomic source snapshot. The
comparison hashes the source content (inspect design DP-D); the engine version
of the stored Scan is compared with the running one, and a difference adds
the warning `engine_version_changed`, which blocks `require_current` only. A long session may explicitly refresh its assessment against the
same pinned Scan; never switch generations or rescan implicitly. A concurrent
rescan does not invalidate an old pinned reader/cursor, nor make its previous
assessment proof about the new manifest. Assessment and all session page scope
must identify that same pinned generation. Existing limited catalogs and
complete record memberships keep their d3 meanings; a snapshot cannot recreate
discarded rows, full JSON or detector findings (D07).

**Configuration.** With no request, use the pinned Scan's effective config,
not today's defaults. The first private interface accepts only an optional
fully validated `ScanConfig` and compares its canonical fingerprint exactly.
A mismatch blocks opening in either intent: it is not merely stale source
content and cannot change stored normalization, exposure or detector results.
Inspection may still explain the mismatch. Do not implement partial config-file
merging in f1; leave that to a separately designed adapter. Page generation,
configuration, exposure and semantic versions continue to come from d3.

Legacy scan-only projects have no database session: explicitly report rebuild
required, with no fabricated DB or automatic upgrade. Corrupt/missing selected
artifacts and unsupported formats fail closed under d2; `snapshot` cannot bypass
verification or fall back to another generation. Source relocation/adoption,
multi-source projects, history comparison, arbitrary prior-generation opening
and a public CLI/API/HTTP/UI stay out of scope.

**Explicit rescan (implemented lot f2).** Reusing
`scan_project(source)` is insufficient: its publisher looks up the source path
and may choose another project when several projects share a path. The private
boundary takes project id, expected selected generation and source binding,
plus an optional complete replacement config. Under d2 writer ownership it
rereads that exact manifest and rejects a changed generation/source binding
before staging. It preserves project id and `created_at`, bypassing index
selection. The recorded config is the default. A source missing/unreadable
cannot be rescanned; cancellation/precommit failure preserves the old
generation. After successful publication, writer ownership ends before a
separately verified session pins the returned new manifest. An intervening
manifest change causes a conflict rather than opening another writer's
generation. Existing postcommit warnings/unknown outcomes are preserved.
Rescan is explicit even for a fresh source and never removes old generations.
New databases retain at most 10,000 raw typed analyzable keys per field.
Stored-value cap selection for rescans must also be explicit: f2 defaults to
10,000; preserving a smaller private cap is opt-in and cannot infer a single
cap from heterogeneous legacy metadata. f2 implements that as an explicit
`value_limit` argument from 1 to 10,000, defaulting to 10,000.

Acceptance for f1: fresh/touched/same-size-changed/different-size/missing/non-file
sources, inaccessible stat/hash, both intents, exact config/mismatch, corruption
and legacy cases; no scan/index mutator on read-only paths; hash all persistent
artifacts; return/close contexts without leaking locks or caches on refusal.
Exercise a rescan between pinning and comparison and during a live reader,
assessment refresh, stale inspection preconditions and generation-bound cursors.
Test mask/hide/show, saturated
catalogs and source-free snapshot pages. f2 additionally needs same-path
projects, stale preconditions, two writers, identity preservation, effective
configuration retention and d2 failure/unknown-outcome regressions.
Tests/artifacts stay outside the checkout; use the external root documented in
architecture.md. Local tests cannot establish D08 power-loss guarantees or
remote-platform support. S17's read-only boundary was accepted for f1;
f2's private boundary was accepted when the maintainer chose to continue after
f1; product D04 defaults and public exposure still need separate gates.

**Private f2 implementation.** `rescan_project()` requires
`expected_generation_id` and `expected_source` in addition to the selected
`project_id` and `StorageLocation`. It yields a `ProjectRescan` containing the
committed `PublishedGeneration` and a live `ProjectSession`. The publisher
checks both preconditions and verifies the selected old generation under d2
writer ownership, so a stale caller never stages or redirects through the
source index. The recorded ScanConfig is the default; a complete explicit
`ScanConfig` replaces it. Missing/non-file/unreadable source refuses before
staging, while a source that changes during staging follows d2 failure rules.
The publisher keeps project identity/creation time and old generations. It
releases writer ownership before the new generation is independently verified
and opened with `expected_generation_id`; an intervening publication yields
`CommittedRescanOpenError` with the committed result and underlying conflict.
Index/post-commit synchronization warnings remain attached to the result;
unknown commit outcomes remain errors and keep generation artifacts for
recovery. Progress `complete` is emitted only after the new session opens;
post-commit callback failures carry the committed result. The one-shot source
publisher and public API are unchanged.

**Private implementation.** `inspect_project()` returns an immutable
`SessionAssessment` after closing its verified reader. `open_project()` yields
a context-managed `ProjectSession` with `assessment`, `refresh_assessment()`,
`records_page()` and owned `materialize_values()` contexts. Both entry points
accept `requested_config`, `expected_generation_id` and a reader `QueryBudget`.
Assessment fields include `current_ready`, `snapshot_ready`, tuple warning/error
codes and a nullable `source_check`/`source_error`: failed source I/O has no
fabricated source state. Codes are `source_stale`, `source_not_checked`,
`source_check_failed` and `config_mismatch`. `SessionRefusedError` carries the
assessment; `GenerationConflictError` reports `generation_changed`. Integrity
and legacy failures retain the low-level `InputError` diagnostics (legacy
explicitly requires rebuilding), before any session is yielded.

Readiness gates entry. Refresh returns new facts about the same pinned Scan,
without changing the opening intent, blocking already-open stored queries or
mutating an earlier assessment. Outstanding value materializations close before
the generation connection on session exit; closed sessions reject new queries
and refresh. Session configuration fingerprints are captured at entry, so
mutating a caller's config object cannot change the decision on refresh.
No module is exported from `tabalyst` or `projects`; no persistent format changed.

### 6.2 First product reopening policy (S18, lots 7.storage-g/g1)

Accepted by the maintainer after lot g and implemented as a private adapter in
g1. It chooses only
the first behavior when an Explore-like caller opens one existing project. It
does not expose a CLI, public Python API, HTTP endpoint or UI yet. It does
not decide version comparison, history, source relocation or automatic cache
retention. The one-shot `tabalyst report --scan` staleness behavior stays O12.

**First-open decision.** Inspect by project id and keep its
immutable assessment and generation id with the caller's choice. If the source
is fresh and the requested complete ScanConfig matches (or no config is
requested), open with `require_current` and the inspected generation as an
expected precondition. If the source is stale, missing/non-file or its check
failed, pause before yielding stored queries: show the specific assessment,
including check time, and require an explicit `snapshot` or `rescan` choice.
Do not silently rescan, silently open a snapshot or claim that old results
describe the current source. Source state is a point-in-time O12 fact.

| Inspection result | Initial action | Explicit choices |
| --- | --- | --- |
| Fresh source, matching settings | Open `require_current`; recheck the same selected generation on entry. | Explicit rescan remains possible, including a new complete config. |
| Stale source | Show the old scan's check time and reason; wait for a choice. | `snapshot` with persistent stale-source warning, or targeted `rescan` with expected generation and source path. |
| Missing/non-file source | Show that current source content could not be checked; wait for a choice. | `snapshot` with source-not-checked warning. Rescan is unavailable until the source is restored at the recorded path. |
| Source stat/hash I/O failure | Show the check failure separately from missing; wait for a choice. | `snapshot` with check-failed warning. Rescan may be attempted only when the source is readable. |
| Complete config mismatch | Show recorded/requested fingerprints and block both opening intents. | Remove the request to use recorded settings and re-inspect, or explicitly rescan with a complete replacement config if the source is readable. |
| Corrupt/unsupported selected generation or legacy scan-only project | Fail closed with the existing integrity/rebuild diagnostic. | No snapshot fallback or automatic upgrade. |

The caller keeps `expected_generation_id` and `expected_source` from the
assessment, never replaces them with a source-index lookup. Opening or rescan
rejects an intervening manifest change and asks for a new inspection. A source
change between inspection and opening is rechecked by f1. A source change
after a successful rescan can make `require_current` refuse despite the new
generation having committed; the adapter must show that committed generation
from `CommittedRescanOpenError` and offer a new inspection, never retry a rescan
silently. An explicit snapshot always labels its generation and warning during
the session. A refresh updates the warning about the same pinned generation;
it does not switch generations or start a scan.

The product adapter may choose later wording and presentation, but must keep
the state distinctions and explicit choices above. Acceptance before exposing
it: fresh/stale/missing/non-file/I/O failure, config mismatch, corruption,
concurrent generation change, source change after rescan, and preservation of
older pinned sessions/cursors. D07 remains deferred; snapshot pages retain the
10,000-value catalog bound and cannot reconstruct discarded values or rows.

**Private g1 adapter.** `project_open_service.py` implements
`inspect_opening()` and the context-managed `enter_project()` decision.
`ProjectOpenDecision` binds storage root, workspace, project, generation,
source path, check time, requested/recorded configuration fingerprints and
available explicit choices. A fresh project is opened again with
`require_current` and its expected generation; a changed source between
inspection and opening returns a new decision instead of a current session.
`open_snapshot()` and `rescan_from_decision()` consume the earlier decision
with its original generation/source preconditions. A configuration mismatch
allows rescan only with the complete replacement configuration inspected by
the caller. Missing/non-file and failed-check decisions require reinspection
before a rescan can become an available choice. Source path changes with an
unchanged generation id are conflicts. A live old snapshot/cursor remains
usable during an explicit rescan. Integrity/legacy failures still raise before
a decision is yielded. No product presentation or public export is added.

F2 checks the selected manifest and both committed artifact hashes and reads
the recorded Scan/config before staging. It deliberately does not open a
second DuckDB connection to the old generation: an existing pinned reader may
use a different private spill directory, and DuckDB refuses another connection
to that same file with different connection settings. Opening either the old
snapshot or new generation remains fully verified by f1/d2. A mismatched or
missing artifact hash still blocks targeted rescan.

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

### 7.1 Explicit private query-cache maintenance (lot 7.storage-e)

The maintainer requested implementation of the framed e lot on 2026-09-29.
Only explicit maintenance of owned query directories is in scope. Automatic
TTL/quotas, generation retention, staging/quarantine disposal and public
commands remain deferred under D03. D07 and the 10,000-value cap are unchanged.

New query directories contain an owner-only `.tabalyst-query.json` marker,
written exclusively, flushed and synchronized before yielding the directory
to DuckDB. It has the exact keys `format` (`tabalyst.query-cache`), `revision`
(integer 1), `workspace_id`, `project_id`, `generation_id` and `query_id`
(fresh ULID). The directory is named `query-<query_id>`; all bindings must
match its storage path. This metadata is private and independent of Scan,
manifest and database revisions. It is ownership evidence inside the trusted
local storage boundary, not authentication against a hostile local writer.

Allowed contents are the marker, regular `values.duckdb` and
`values.duckdb.wal` files, and an optional `spill/` directory containing only
recognized DuckDB temporary files. Unknown contents, unmarked legacy caches,
invalid/unsupported markers, symlinks, Windows reparse points and multiply
linked files are preserved. Inventory reads bounded marker metadata and file
statistics only, never database or raw spill payloads. Byte counts describe
logical file lengths, not allocated disk space or a disk quota.

The private inventory is also an advisory dry-run plan. Execution requires
that plan and takes the exclusive workspace maintenance lock before the
writer lock. It re-inventories under ownership and acts only on unchanged
planned candidates (directory/file identities, marker bytes and file stats).
New or replaced targets are skipped; busy ownership raises ProjectBusyError
without cache mutation. Unsupported platforms cannot execute maintenance.
All cooperating readers/materializers/writers already hold shared maintenance
ownership. External non-cooperating changes are outside the local locking
guarantee; paths and entries are nevertheless checked again before removal.

Files are removed individually, without recursive deletion of a cache root;
the marker is last. Results distinguish removed, skipped and failed targets,
including actual removed logical bytes on partial failure. An ordinary
failure preserves the marker for retry (recreating it exclusively if final
directory removal fails). A process dying between final marker unlink and
empty-directory removal may leave an unmarked empty directory, which later
maintenance conservatively skips. No transaction across cache deletions or
power-loss guarantee is claimed. Normal query teardown uses the same content
validation, after closing all DuckDB handles, and preserves unknown contents.

Cleanup does not open the source, manifest or committed database. It touches
only planned owned query directories, including ones for old generation ids;
it neither deletes generations nor validates/promotes a generation. Rebuilding
materializations still uses verified pinned project storage, with unchanged
exposure, ordering, omission status and cursor semantics. Nothing calls this
maintenance automatically during scan/open/query. No public exports or adapter
are added; remote platform evidence remains to collect in storage CI.

Implementation uses `projects._cache.inventory_query_caches(location,
project_id)` to return an immutable `CacheInventory`; its entries have
`path`, `status`, `reason`, `logical_bytes` and `removed_bytes`. Private
comparison signatures bind directory identities, marker bytes and file
identity/size/timestamps. `clean_query_caches(location, project_id, plan=...)`
rejects a different root/workspace/project plan. Inventory statuses are
`candidate`, `skipped` or `error`; execution adds `removed`, retaining explicit
per-target failures and skipped/new/changed targets. Missing cache returns
no entries. The accepted spill names are `duckdb_temp_storage-<digits>.tmp`
and `duckdb_temp_block-<word-or-hyphen>.block`; other engine files are preserved
until this private protocol is deliberately extended. This format does not
introduce a supported public API or a cache authentication scheme.

## 8. Detailed database contract (D01, S07, S10-S13, S15)

Sections 8.1-8.5 describe the original exhaustive revision-1 database. The
maintainer amendment in 8.7 supersedes its raw retention and reopen proof for
new revision-2 generations. Section 8.6 supports both revisions explicitly.

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
meaning or required tables do. The d1 runtime is pinned to `duckdb==1.5.5`;
the loader selects physical `storage_compatibility_version='v1.4.0'` explicitly
when creating the database (header storage version 67). Writer version and
this target are recorded separately. The loader rejects another runtime
instead of silently changing storage behavior. See section 10.1 for evidence.
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

DuckDB 1.5.5 rejects cross-schema foreign keys. The d1 schema declares SQL
PK/unique/check/not-null constraints and same-schema FKs; the loader's
build/reopen validator enforces records-to-datasets, observations-to-fields
and membership-to-listings links explicitly, together with nullable parent
and collection links. The table layout and logical semantics are unchanged.

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

### 8.6 Private d3 query contract

`projects._queries` is internal: it is not exported by `tabalyst` or
`projects.__init__`, and has no CLI, HTTP adapter or public document format.
Use it inside an active `_generation.open_generation()` context:

```python
with open_generation(location, project_id, budget=QueryBudget()) as pinned:
    page = records_page(pinned, "rows", "records.with_missing", size=100)
    with materialize_values(pinned, "rows", "column_1") as values:
        frequencies = values.frequencies_page(size=100)
        groups = values.groups_page(size=100)
        if groups.items:
            variants = values.variants_page(groups.items[0].key, size=100)
```

Every page identifies workspace, project, generation, dataset, optional field,
listing, analyzed record count, the original Scan scope and dataset structural
limits, configuration fingerprint, exposure and semantic versions. Its origin
is `storage-derived`. Counts cover the whole retained population, independent
of page size and Scan's distinct/value/record/listing limits. Revision 2 also
reports storage omissions as specified in 8.7; Scan's envelopes
and artifact bytes stay unchanged. Record items are index/location references,
not row payloads or detector findings. Unknown datasets, listings and
unprofiled field ids are rejected. Empty populations give complete empty pages;
disabled duplicate detection gives `disabled`, a null count and no items.

Page sizes are strict integers from 1 through 1,000. Private immutable cursor
objects bind workspace/project/generation, dataset, field, listing, effective
configuration, exposure and query/normalization versions; variant cursors also
bind the exposed group key. Record keysets use `record_index > after`. Values
are sorted once during materialization, assigned stable dense ordinal keys and
paged by `position > after`, never OFFSET. Frequency tie order is count
descending, UTF-8 BLOB text ascending, then Scan's native-type order. Groups
and their variants use count descending then binary text. UTF-8 order equals
Python codepoint ordering for the valid Unicode retained by Scan, including
NUL and the BMP/non-BMP boundary, independently of locale SQL collations.

An old pinned reader can continue its cursor after a rescan; a newly opened
generation rejects that cursor with `StaleCursorError`. Identical cache
rebuilding retains cursor meaning. A cursor for another field, dataset,
listing or variant key is rejected rather than silently starting over.
These cursor objects are not an authenticated network protocol; a future
public transport must design its own serialization and trust boundary.

`materialize_values()` streams revision-1 observations or weighted revision-2
catalog values through the
shared `StringClassifier`, `Normalizer` and `ExposureGate`. Frequencies use
content strings and native numbers/booleans; absence, nulls, arrays, objects,
empty/blank/marker strings are excluded. Native tags and canonical numeric
text never pass through SQL numeric inference. Raw variant groups qualify
with at least two distinct raw content strings before exposure, exactly as
Scan does; qualifying equal masked keys and masked variants then merge before
ranking. A single-variant raw group cannot enter merely because its mask
matches another group. `hide` returns no value items or cursors, preserves
unexposed frequency/group counts, and rejects variant-key queries.

Each materialization uses a new owner-only disposable directory under
`cache/<generation_id>/query-*`. Raw intermediates can contain sensitive
values; the directory inherits the private project's access boundary. Only
the operation's own directory is removed on close/failure, after every handle
is closed. Concurrent sessions have separate directories. No derived table
is added to `project.duckdb`; a process killed during a query can leave a
disposable cache directory (automatic cleanup/quotas remain D03).

`QueryBudget` defaults to 256 MiB of DuckDB memory **per database instance**,
one thread and 1 GiB of DuckDB-accounted spill per instance. Connections to
the same generation may share that pool; a materializer owns a separate DB.
Generation validation/open and
value materialization have separate connections and spill directories.
One reader and one materializer can coexist; these limits do not bound total
process RSS, Python Scan state, database/cache file sizes or old-generation
retention. Query insert buffers cap rows at 2,048 and encoded payload at
4 MiB; one oversized value is processed alone without truncation. Page limits
bound item counts, not the bytes of a single long value. The loader retains
its private `memory_limit` setting and gains `spill_limit`; their d3 defaults
are 256 MiB and 1 GiB, aligned with readers and the measured policy. Both
also apply to read-only post-checkpoint validation.
Ingestion order preservation is disabled because indices and explicit query
orders define all semantics. Integrity verification over all retained data
is mandatory; a hash-only or sample-only shortcut is not introduced. Revision
2's discarded cells cannot be independently revalidated, as detailed in 8.7.

Memory, disk and spill exhaustion raises an explicit error; failed
materializations never yield a complete query object or truncate a list.
Validation memory failure is distinguished in the error message from schema
corruption. There is no automatic larger-budget retry. Larger settings are
an explicit private caller choice; section 10.2 records successes and failures.
Every connection also applies the quota with runtime `SET`: in pinned
DuckDB 1.5.5, the connect option alone could report a limit without enforcing
it in the temporary manager. Zero additionally disables the temporary
directory. Positive spill quotas govern DuckDB accounting, not an OS disk
quota: Windows temp-file lengths can retain freed blocks. Physical peaks
are measured separately; project/cache files are outside this spill quota.
D07 remains deferred, including attribution of detector results, excluded
locations, exact JSON ancestry and exact source reconstruction.

### 8.7 Maintainer amendment: 10,000 stored distinct values per field

On 2026-09-29, during d3 resource measurements, the maintainer explicitly
chose to cap **values conserved in `project.duckdb`**, rather than just pages.
This supersedes exhaustive raw-observation retention in sections 8.1-8.5 for
new generations. Revision-1 databases remain readable and retain their
original exhaustive validation/query behavior; they are never rewritten.
New publication writes database logical revision 2 and loader version 2,
with the same physical target, project manifest revision 2 and unchanged
Scan JSON. An explicit rescan builds the new form; no migration is required.

The sink still receives every analyzed record and computes the shared
version-1 digest and missing/empty flags before discarding any payload.
Complete record headers and the three memberships persist as before.
The new database replaces `data.observations` with `data.values`: dataset id,
profiled field id, first-seen value ordinal, native scalar tag, exact raw
canonical text and occurrence count. `meta.value_storage` stores per field
the distinct limit, retained distinct count, retained occurrences and omitted
occurrences. Dataset/field metadata and Scan remain authoritative for
structural/native statistics. There is no record-to-value mapping in revision 2.

The default and maximum limit is 10,000 **raw typed analyzable values** per
field (content strings, integers, numbers and booleans). Private callers may
choose a smaller positive limit. The first distinct keys in Scan reading
order are selected deterministically; long values are retained without
truncation. Equal later keys increment their counts even after saturation;
other payloads are dropped after a bounded batch. Catalog membership uses
exact native/text equality, never a hash or SQL cast. Empty, blank, marker,
null and container payloads are outside this catalog population. Unprofiled
paths never gain stored catalogs. Temporary batches cap rows and bytes;
DuckDB manages the temporary catalog under its memory/spill budget rather
than a Python set of every field's keys.
No full unbounded observation staging is built first. Bounded ingestion
batches commit privately to release update/delete undo; generation publication
still happens only after full finalization, validation and manifest replacement.

Value pages report `value_population`, `retained_occurrences`,
`omitted_occurrences`, `stored_distinct_limit` and database revision. If any
occurrences were omitted, their status is `limited`, reason
`stored_value_budget`. Page `total` counts entries derived from the retained
catalog, not full-source cardinality. Analytical/masked frequencies and
variant counts are lower bounds for the whole population: omitted raw values
could normalize/mask into a listed key. Hidden pages also carry the limitation
without exposing values. Record pages remain complete. Storage saturation
never becomes an apparently complete frequency list.

Reopen verifies catalog tags, exact keys, limits, counts, field mappings,
Scan bindings and complete memberships, including Scan prefix/subset
invariants. Artifact hashes bind full-hook record flags/digests to the
manifest. It cannot independently reconstruct digests or presence from
discarded cells; that former revision-1 proof is unavailable in revision 2.
D07 reconstruction/ancestry and per-detector attribution remain deferred.
Even retained catalog values do not recreate rows for a Transform export.
A consumer needing all raw rows requires a new design.

## 9. Atomic generations, failure and recovery (S14)

### 9.1 Why the layout must evolve

The original implementation of 7.storage-b wrote `scan.json` with
`write_text_atomic()`, then calls `record_scan()`. A scan failure before
writing preserves the old project, as its tests show. However, a failure
between those two writes can leave a new scan with old project metadata.
Adding a third rename does not make the three files atomic. The original
service also published metadata/index before scanning. Lot 7.storage-d2
replaces these separate writes with the protocol below. Legacy metadata
helpers remain available internally, under the writer lock, but cannot
republish or downgrade a revision-2 manifest.

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
An existing legacy root `scan.json` is preserved as evidence after rebuilding;
revision-2 readers derive both artifact paths exclusively from the manifest.

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

### 9.4 Implemented d2 boundaries and local evidence

`project_scan_service.scan_project()` now uses the private publisher. The
writer lock covers lookup, staging, synchronization, commit and index update.
Windows uses nonblocking `LockFileEx`; POSIX uses nonblocking `flock`.
Lock files remain outside the projects directory, and their existence is
never interpreted as ownership. Closing a handle or process death releases
ownership. Legacy mutators use the same writer discipline.

`_generation.open_generation()` holds a shared maintenance lock, reads the
manifest once and returns a read-only session pinned to the verified pair.
Normal scans retain old generations. `_recovery.quarantine_uncommitted()` is
an explicit private maintenance operation: it requires exclusive maintenance
and writer ownership, verifies the selected generation and moves only
unselected ULID directories to `.quarantine/`. It preserves their contents,
ignores unknown names/symlinks and fails closed for a corrupt selection.
No automatic cleanup or retention policy is implemented.

Files are closed and synchronized before publication. Manifest temporary
files use the destination directory, restrictive creation permissions,
flush/fsync/close, then `os.replace`. POSIX directory synchronization uses
`fsync`; the Windows implementation reports it unsupported rather than
claiming power-loss durability. Local Windows/Python 3.12 subprocess tests
demonstrate old-or-new visibility after process termination on both sides
of the commit point, writer release after termination and an old open
DuckDB reader surviving publication of a new generation. Linux/macOS and
other Python versions are included in the storage CI matrix but have not
been executed in this session. D08 remains deferred.

The 48 d2 tests cover first-scan invisibility, legacy upgrade/failure,
eleven injected pre-commit boundaries for first scans and rescans,
post-commit index warnings, reclassification after replacement errors,
unknown outcomes, corruption without fallback, missing-source freshness,
lock contention and quarantine blocked by readers/writers. These tests
extend the existing a/b layout expectations deliberately; the public CLI
continues to write its ordinary standalone scan/report artifacts.

## 10. Acceptance and implementation test plan (S16)

The implementation gate accepted S07/S10-S16 and the explicit D06-D08
boundaries. No DuckDB dependency or loader was added by 7.storage-c; d1
implements private staging only. The matrix below spans d1, d2 and d3;
publication/concurrency and public value queries are not claimed by d1.

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

No public behavior is enabled by c/d1; no public format changelog,
release notes or tabalyst-studio changes are required. When implementation
exposes a CLI/API/report/demo change, update English documentation then and
record the corresponding tabalyst-studio follow-up.

### 10.1 d1 runtime, platforms and measurements (D06)

**Runtime selection:** exact `duckdb==1.5.5`, physical target `v1.4.0`.
The [published wheel inventory](https://pypi.org/project/duckdb/1.5.5/)
was checked on 2026-09-28 through PyPI's version-specific JSON endpoint.
For standard CPython 3.11, 3.12, 3.13 and 3.14, each has wheels for Windows
AMD64/ARM64, Linux glibc x86-64/aarch64 (manylinux 2.26/2.28), macOS ARM64
11+ and macOS x86-64 (minimum 10.9/10.13/10.13/10.15 respectively).
This is wheel availability, not runtime validation of all architectures.
No musl, 32-bit, PyPy or free-threaded Python support is asserted for staging.

The storage CI matrix now runs Python 3.11-3.14 on `windows-latest`,
`ubuntu-latest` and `macos-latest`, requiring a binary wheel and running the
staging and existing a/b tests. Only Windows 11 AMD64, CPython 3.12.14 was
executed locally in this session; Linux/macOS and the other Python versions
remain CI evidence to collect before enabling database consumers in d2.
ARM64 wheel availability alone does not add a tested platform. Staging uses
local filesystems; network filesystems and power-loss durability remain D08.

The [DuckDB physical contract](https://duckdb.org/docs/current/internals/storage)
is independent of logical revision 1. Local tests verify header version 67
after checkpoint/close. An isolated DuckDB 1.4.2 wheel also reopened the
insurance database read-only and read all 105,000 observations. This is an
older-reader compatibility probe, not an additional supported writer.
No extension or source access is required. Reopen checks the exact scan
document hash, identity/version binding, canonical payloads, mappings,
counts, flags, shared record digests and complete-prefix/limited-subset
listing invariants. These checks are exhaustive and intentionally have a cost.

**Ingestion:** two parameterized column buffers, each capped at 2,048 rows
or 4 MiB of encoded payload (one oversized observation is flushed alone).
No registry of all unknown paths is retained. Dataset-local digest path
tokens keep the existing Scan bound of 65,536. The connection uses one
thread, a 256 MB DuckDB memory limit and a staging-owned spill directory;
this limit is not a total Python process memory guarantee. Raw project data
is protected by the private directory (0700) and artifact modes (0600) on
POSIX; Windows inherits local directory ACLs. d2 owns lock/sync/recovery.

Initial single-run measurements, imports excluded, Windows/Python above:

| Source | Records | Build including validation (s) | Read-only validation (s) | DB hash (s) | DB bytes | Peak process bytes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `examples/input/insurance-customers.csv` | 3,000 | 2.603 | 0.690 | 0.008 | 9,711,616 | 201,867,264 |
| `examples/input/orders.json` | 61 | 0.472 | 0.064 | 0.004 | 5,779,456 | 133,750,784 |
| Synthetic CSV, id/text/marker, `str(i)` repeated 100 times | 20,000 | 2.576 | 0.524 | 0.010 | 15,216,640 | 236,662,784 |

Reproduce with a fresh stage:

```console
python benchmarks/project_storage.py examples/input/insurance-customers.csv --stage artifacts/storage-measure-1
```

On the insurance input, 64-row buffers took 3.191 s versus 2.603 s at 2,048
and 2.521 s at 8,192, with similar process peaks (200-202 MB). These are
single runs, not speed guarantees; keep 2,048 to bound buffered rows while
amortizing inserts. `--batch-rows` allows later comparisons without changing
the loader defaults. The three default runs used no spill. A dedicated
32 MB runtime probe sorted 500,000 rows with about 39 MB of spill files,
with external access disabled, and returned every row. The 20,000-record
loader experiment at 64 MB failed explicitly during precommit validation;
indexes/non-spillable state can exhaust a low budget. It published nothing
and made no complete-result claim. Disk/spill errors similarly propagate.

`benchmarks/project_storage.py` records sampled staging/spill disk peaks,
process memory, final size, hash and reopen-validation times. Full repeated
CSV/JSON, wide/deep/long-value, million-record and old+new-generation peak
disk measurements remain d3. Baseline memberships are complete on disk,
including 13,000 affected records under zero listing and exhausted duplicate
budgets; pagination and exposure-aware value queries remain d3.

### 10.2 d3 queries, capped storage and resource evidence

`benchmarks/project_queries.py` measures synthetic CSV/JSON sources in a
fresh child process per repetition, with two publications of the same source.
Imports and source generation are excluded from timings. Each run records
loader subphases, hash and full verified-open time, all record pages, field
materialization and frequency/group/variant pages. JSON evidence remains in
the supplied fresh root; failures retain their stage and never retry with a
larger budget automatically. Only Windows 11 AMD64/Python 3.12.14 and the
pinned DuckDB 1.5.5 were executed locally. The storage CI matrix includes the
d3 tests, but remote OS/Python runs remain unverified.
The runs use one Scan worker, `max_distinct_per_field=2000`,
`max_tracked_values=20000`, `max_tracked_records=1000`, and zero record/value/
group listing limits, deliberately exhausting Scan tables. Loader and reader
budgets are 256 MiB/1 GiB; materializers use 64 MiB except long values at
256 MiB. File-system caches are not flushed; these are local warm-file
measurements, not cold-open latency or multi-worker process-memory guarantees.

Two fresh-process repetitions, each building first and replacement pairs.
Build ranges cover all four publications; open/hash ranges cover the two
verified new generations. RSS, spill and disk columns are the largest
observations across repetitions. Sizes are MiB, timings seconds:

| Synthetic source | Source MiB / records | Build s | Verified open / hash s | DB MiB | Process RSS MiB | Spill MiB | Project disk MiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| CSV, 3 columns | 17.27 / 1,000,000 | 59.43-67.84 | 3.08-4.45 / 0.043-0.055 | 68.51 | 433.98 | 9.59 | 138.51 |
| JSON, nested arrays/missing/container values | 9.02 / 100,000 | 9.45-12.59 | 0.45-0.55 / 0.008-0.009 | 14.01 | 189.56 | 0 | 29.70 |
| CSV, 100 columns | 2.39 / 10,000 | 10.63-11.30 | 0.37-0.38 / 0.005-0.007 | 5.76 | 189.63 | 0 | 17.31 |
| JSON, 30 nested child objects | 3.95 / 10,000 | 2.21-2.54 | 0.13-0.18 / 0.003-0.004 | 5.76 | 139.44 | 0 | 13.34 |
| CSV, long strings (up to about 8,000 characters) | 26.34 / 4,000 | 1.88-2.26 | 0.12-0.16 / 0.008-0.009 | 13.76 | 322.38 | 0 | 229.87 |

The million-record CSV's sampled rescan peak is 137.20 MiB: 68.59 MiB old
pair plus 68.60 MiB stage and small metadata files. Its overall 138.51 MiB
sample contains 68.59 MiB old, 68.59 MiB new and 1.32 MiB disposable query
cache, with no staging or spill at that instant. The 9.59 MiB spill peak
occurs earlier during loader finalization/validation and is not added again.
The wide case's Scan JSON alone is about 2.39 MiB and is part of each pair.
The deep case's largest sampled footprint includes old plus staging, whereas
the long-value case peaks with both pairs plus about 202.13 MiB of query
materialization files. A capped catalog can still produce a cache much larger
than its compressed committed database; each query removes its own files.

Materializing the million-record CSV id field takes 0.11-0.15 s; its ten
frequency pages take about 0.03 s in total. Full missing and duplicate record
walks take about 14-25 s each (1,000 items per page). Across the other cases,
field materialization ranges from 0.03 to 1.95 s; the upper end is long values.
No reader/value-query spill occurs under these particular budgets; zero is
a measured result, not a promise that all 10,000-key fields fit without spill.
The table's original configured quotas preceded the runtime-SET correction;
all measured spill peaks were below the intended 1 GiB. Targeted final probes
and another million-record run verify the corrected policy explicitly.
That final CSV run builds its first/replacement pairs in 61.33/58.05 s,
opens with full verification in 4.10 s, and hashes the DB in 0.042 s. Its
DB remains 68.51 MiB, high-water process RSS 432.40 MiB, sampled managed-spill
file peak 10.75 MiB and simultaneous project disk peak 138.51 MiB. These
are an additional single repetition after applying runtime quotas, with no
tests or other resource runs concurrent.

The long-value probe at 64 MiB/1 GiB succeeds with about 15 MiB of sampled
query spill. At 32 MiB it fails during materialization/autocheckpoint; at
64 MiB with spill disabled it also fails, with zero spill files. With a
1 MiB runtime quota it fails explicitly on offloading at 832 KiB used,
before yielding a query. Both previously committed pairs stay valid; only
the disposable query fails. A real 500,000-row sort also verifies disabled
spill and quota exhaustion. Query caches close/remove after these failures.
The runtime quota is reapplied on loader, staging-validation, generation
reader/maintenance verification and value-materializer connections. This
guards a pinned-engine initialization behavior; no larger-budget retry occurs.

Windows file lengths are not a hard spill-quota proof: DuckDB decrements its
accounted block extent on release, but disables file truncation on Windows.
This distinction follows the pinned runtime's
[temporary-file implementation](https://github.com/duckdb/duckdb/blob/v1.5.5/src/storage/temporary_file_manager.cpp#L310)
and is why peak-disk sampling remains necessary alongside configured quotas.

Reproduce with new roots (the script rejects an existing root):

```console
python benchmarks/project_queries.py --case csv --rows 1000000 --root artifacts/d3-csv --query-memory-mib 64 --repeat 2
python benchmarks/project_queries.py --case json --rows 100000 --root artifacts/d3-json --query-memory-mib 64 --repeat 2
python benchmarks/project_queries.py --case wide --rows 10000 --root artifacts/d3-wide --query-memory-mib 64 --repeat 2
python benchmarks/project_queries.py --case deep --rows 10000 --root artifacts/d3-deep --query-memory-mib 64 --repeat 2
python benchmarks/project_queries.py --case long --rows 4000 --root artifacts/d3-long --repeat 2
```

The million-record CSV has three columns, 500,000 distinct ids and adjacent
duplicate pairs. With the revision-2 catalog, the id field retains 10,000
keys/20,000 occurrences and reports 980,000 omitted occurrences. Its ten
1,000-item pages are limited; the low-cardinality variant field remains
complete. Missing memberships cover 333,334 records in 334 pages, duplicates
cover 500,000 records in 500 pages, with first occurrences excluded; Scan's
record listing limit is zero and digest budget only 1,000. Nothing is
truncated by the record page interface. High-cardinality value pages no
longer pretend to cover all 500,000 raw ids.

Before the retention amendment, the same million-record source under the
exhaustive revision-1 writer failed at 256 MiB and 1 GiB during finalization.
Explicit 2 GiB loading succeeded: two builds took 166.70/138.04 s, verified
open 24.21 s, DB 255.51 MiB, process high-water RSS 2,213.23 MiB. A 256 MiB
reader spilled up to 288.53 MiB during exhaustive reopen validation. This is
one exploratory run of the earlier implementation, with different retention
and integrity coverage; it is not a controlled speed comparison. Failed
low-budget builds published nothing and retained their evidence.

The first bounded prototype still held one ingestion transaction: repeated
catalog UPDATE/DELETE undo exhausted its 256 MiB budget on this source.
Short private catalog transactions release that undo and make the capped
ingestion succeed. This does not move d2's manifest commit point. Per-field
retention bounds payload cardinality, not record count, value length, the
number of fields, total process memory or final disk size.

Disk sampling runs every 10 ms and reports logical file lengths under the
project root, excluding the source, interpreter and retained evidence from
other runs. During rescan, an old committed pair coexists with staging; after
rename, old and new pairs coexist. Query/reader spill and materialization
files add to that footprint. `at_sampled_disk_peak` stores the simultaneous
old/new/staging/cache composition at each phase's largest sample. Independent
maxima must not be summed; spill is already included in staging or cache.
These disk samples are lower bounds on transient peaks and do not measure
filesystem allocation blocks. Process RSS/high-water measurements are also
reported; a DuckDB connection budget is not a process RSS guarantee.

The local measured policy sets loader/reader/query defaults to 256 MiB,
each with 1 GiB spill and one thread. These binary units supersede the d1
loader's decimal 256 MB and d3's initial decimal 1 GB spill setting.
The narrower 64 MiB materializer is an explicit experiment, not the default.
One oversized string can exceed a batch byte threshold and is handled alone.
Zero/insufficient spill or non-spillable hash/index state can still fail;
memory/spill errors remain explicit. There is no silent truncation or larger
budget retry. Automatic project retention/cache quotas are still D03; local
process-failure visibility does not resolve D08 power-loss/network durability.

Validation: exhaustive small-reference parity, both JSON backends, all 32
normalization flag combinations, Unicode/NUL/type ties, released Scan value
tables and zero listing limits; sensitive mask/hide/show, more than 13,000
affected records, revision-1 large value/group compatibility, cap saturation,
continued counts, batch independence, omitted analytical collisions, retained
fact corruption, real memory exhaustion, cache ownership and generation/query
cursor rejection. All retained catalog values can be read without the source
or a detector rerun. D07 richer findings and row/JSON reconstruction remain
deferred, including for capped catalogs.

## 11. Changes to this document

| Date | Change | Reason |
| --- | --- | --- |
| 2026-09-28 | Initial version. | Design of the project storage layer for a future Explore and Transform, requested by the maintainer ahead of any implementation lot. |
| 2026-09-28 | S02, S03, S04 and S08 implemented (`tabalyst.projects`); `platformdirs` accepted; `TABALYST_HOME` added; the example `project_id` corrected to a valid ULID. | Lot 7.storage-a. |
| 2026-09-28 | S05 and S09 implemented: the project scan service writes `scan.json`; project freshness reuses O12 through the location-independent `compare_source()`. | Lot 7.storage-b. |
| 2026-09-28 | D01 detailed: S07 amended; S10-S16 define schema, raw observation loading, scope, large listings and generation publication; D06-D08 name evidence still required. | Lot 7.storage-c, design only. Independent inference cannot establish Scan parity; per-file atomic replacement cannot commit an artifact set. |
| 2026-09-28 | Maintainer accepted c; private codec/schema/staged loader and record memberships implemented, D06 runtime/physical target selected with wheel and local measurement evidence. | Lot 7.storage-d1. No publication before d2; queries and large benchmarks remain d3. |
| 2026-09-28 | Revision-2 atomic generations, OS locks, pinned sessions, index/freshness integration, explicit legacy rebuild and orphan quarantine implemented with failure/process-termination tests. | Lot 7.storage-d2, continued at maintainer request. Interfaces remain private; directory durability on Windows, remote OS CI and d3 queries/resources are not claimed. |
| 2026-09-29 | Private generation-bound paginated records/values, shared normalization/exposure, memory/spill budgets and repeated large-source measurements. New DB revision 2 caps raw typed analyzable catalogs at 10,000 per field with explicit omissions; revision 1 remains readable. | Lot 7.storage-d3; maintainer explicitly chose to cap values conserved in project.duckdb. Complete record memberships persist; D07/D08 and all public project interfaces remain deferred. |
| 2026-09-29 | Private owned query-cache markers, metadata inventory/dry-run and explicit plan-bound cleanup under exclusive maintenance ownership; unknown contents and project storage are preserved. | Lot 7.storage-e, requested after framing. D03 automatic policies/public commands remain deferred; no change to the 10,000-value cap, D07 or public formats. |
| 2026-09-29 | Proposed S17 private reopening: pinned generation assessment, explicit current/snapshot intents, configuration comparison and separate project-targeted conditional rescan. | Lot 7.storage-f, design only. The existing source-index publisher cannot guarantee rescan of the explicitly selected project; f1/f2 stay unimplemented and product D04 defaults remain deferred. |
| 2026-09-29 | Accepted and implemented S17 read-only inspection/opening with immutable readiness facts, exact configuration matching, explicit snapshot warnings, refresh and generation preconditions. | Lot 7.storage-f1 requested by the maintainer. f2, product D04 defaults, public exposure, D07 and automatic D03 policies remain deferred; 10,000-value cap unchanged. |
| 2026-09-29 | Implemented S17 private conditional rescan targeted by project id with generation/source preconditions under writer ownership, recorded-config default, explicit replacement config and 10,000-key default cap. | Lot 7.storage-f2; the new generation is reopened separately with an exact precondition. Product D04 defaults, D07, public project interfaces and automatic D03 policies remain deferred. |
| 2026-09-29 | Proposed S18 first product reopening policy: fresh verified generation opens as current; stale/missing/failed checks require explicit snapshot or targeted rescan choice with persistent warnings. | Lot 7.storage-g, design only. Maintainer review required before any adapter; D07, version history and automatic D03 policy remain deferred. |
| 2026-09-29 | Accepted S18 and implemented its first private project-opening adapter, preserving inspection preconditions and explicit snapshot/rescan choices. F2 old-generation preflight now validates immutable artifact hashes and Scan/config without a second DuckDB connection, allowing a pinned reader to survive a rescan. | Lot 7.storage-g1. No CLI/API/HTTP/UI exposure or demo change; D07, version history and automatic D03 policy remain deferred. |

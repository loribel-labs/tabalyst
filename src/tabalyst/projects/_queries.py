# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Private generation-bound listings, exact for Scan's retained scope.

No detector reruns, source reads, JSON reconstruction or unprofiled payloads.
Query materializations are disposable and never change a committed artifact.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from dataclasses import dataclass, replace

import duckdb

from tabalyst.projects._query_budget import (
    QueryBudget,
    apply_spill_limit,
    query_directory,
)
from tabalyst.projects._validation import LISTINGS
from tabalyst.scanner.exposure import ExposureGate
from tabalyst.scanner.field import StringClassifier
from tabalyst.scanner.models import Scope, Structure, ValueCount, Variant
from tabalyst.scanner.normalization import VERSION, Normalizer
from tabalyst.scanner.values import _TYPE_ORDER

MAX_PAGE_SIZE = 1000
QUERY_SEMANTICS_VERSION = 2


class QueryError(ValueError):
    """Invalid query or cursor; no partial complete result is returned."""


class StaleCursorError(QueryError):
    """The cursor belongs to a different project, generation or query."""


@dataclass(frozen=True)
class Cursor:
    binding: tuple[str, ...]
    after: tuple


@dataclass(frozen=True)
class QueryScope:
    project_id: str
    workspace_id: str
    generation_id: str
    dataset_id: str
    field_id: str | None
    listing_id: str
    analyzed_records: int
    scan_scope: Scope
    structure: Structure
    config_sha256: str
    exposure: str | None
    origin: str = "storage-derived"
    query_semantics_version: int = QUERY_SEMANTICS_VERSION
    normalization_version: int = VERSION
    record_semantics_version: int = 1
    database_revision: int = 1
    stored_distinct_limit: int | None = None
    value_population: int | None = None
    retained_occurrences: int | None = None
    omitted_occurrences: int = 0


@dataclass(frozen=True)
class Page:
    scope: QueryScope
    status: str
    total: int | None
    items: tuple
    next_cursor: Cursor | None
    reason: str | None = None


@dataclass(frozen=True)
class RecordReference:
    record_index: int
    location: dict[str, int]


@dataclass(frozen=True)
class VariantGroupReference:
    key: str
    count: int
    distinct: int


def _dataset(pinned, dataset_id):
    for dataset in pinned.result.datasets:
        if dataset.id == dataset_id:
            return dataset
    raise QueryError("Unknown dataset")


def _scope(pinned, dataset, listing, field=None):
    return QueryScope(
        pinned.project.project_id,
        pinned.project.workspace_id,
        pinned.generation_id,
        dataset.id,
        None if field is None else field.id,
        listing,
        dataset.record_count,
        pinned.result.scope,
        dataset.structure,
        pinned.result.config_sha256,
        None if field is None else field.exposure,
    )


def _binding(scope, *extra):
    return (
        scope.project_id,
        scope.workspace_id,
        scope.generation_id,
        scope.dataset_id,
        scope.field_id or "",
        scope.listing_id,
        scope.config_sha256,
        scope.exposure or "show",
        str(QUERY_SEMANTICS_VERSION),
        str(VERSION),
        *extra,
    )


def _after(cursor, binding, size):
    if type(size) is not int or not 1 <= size <= MAX_PAGE_SIZE:
        raise QueryError(f"Page size must be between 1 and {MAX_PAGE_SIZE}")
    if cursor is None:
        return None
    if not isinstance(cursor, Cursor) or cursor.binding != binding:
        raise StaleCursorError("Cursor belongs to a different generation or query")
    after = cursor.after
    if not isinstance(after, tuple) or len(after) != 1:
        raise QueryError("Invalid cursor key")
    if type(after[0]) is not int or not 1 <= after[0] <= 2**63 - 1:
        raise QueryError("Invalid cursor index/count")
    return after


def records_page(pinned, dataset_id, listing_id, *, size=100, cursor=None):
    """Membership references only; payload ancestry and row findings are D07."""
    dataset = _dataset(pinned, dataset_id)
    if listing_id not in LISTINGS:
        raise QueryError("Unknown record listing")
    scope = _scope(pinned, dataset, listing_id)
    scope = replace(
        scope,
        database_revision=pinned.connection.execute(
            "SELECT format_revision FROM meta.format"
        ).fetchone()[0],
    )
    binding = _binding(scope)
    after = _after(cursor, binding, size)
    connection = pinned.connection
    status, total, reason = connection.execute(
        "SELECT status,record_count,reason FROM meta.listings "
        "WHERE dataset_id=? AND listing_id=?",
        [dataset_id, listing_id],
    ).fetchone()
    rows = connection.execute(
        "SELECT record_index,location_json FROM data.listing_records "
        "JOIN data.records USING(dataset_id,record_index) "
        "WHERE dataset_id=? AND listing_id=? AND record_index>? "
        "ORDER BY record_index LIMIT ?",
        [dataset_id, listing_id, 0 if after is None else after[0], size + 1],
    ).fetchall()
    items = tuple(RecordReference(r[0], json.loads(r[1])) for r in rows[:size])
    next_cursor = (
        Cursor(binding, (items[-1].record_index,)) if len(rows) > size else None
    )
    return Page(scope, status, total, items, next_cursor, reason)


class ValueQuery:
    """One fully built field materialization. Close through materialize_values()."""

    def __init__(self, pinned, dataset, field, connection, directory, gate, storage):
        self.pinned = pinned
        self.dataset = dataset
        self.field = field
        self.connection = connection
        self.directory = directory
        self.gate = gate
        self.closed = False
        self.value_count = field.values.count
        self.storage = storage
        self.frequency_count = connection.execute(
            "SELECT count(*) FROM frequencies"
        ).fetchone()[0]
        self.group_count = connection.execute("SELECT count(*) FROM groups").fetchone()[
            0
        ]

    def _page(self, listing, table, columns, factory, *, size, cursor, group_key=None):
        if self.closed:
            raise QueryError("Value query is closed")
        scope = _scope(self.pinned, self.dataset, listing, self.field)
        revision, limit, retained, omitted = self.storage
        scope = replace(
            scope,
            database_revision=revision,
            stored_distinct_limit=limit,
            value_population=self.value_count,
            retained_occurrences=retained,
            omitted_occurrences=omitted,
        )
        status = "limited" if omitted else "complete"
        reason = "stored_value_budget" if omitted else None
        binding = _binding(scope, *((group_key,) if group_key is not None else ()))
        after = _after(cursor, binding, size)
        where, parameters = "TRUE", []
        if group_key is not None:
            if not isinstance(group_key, str):
                raise QueryError("Invalid exposed group key")
            where = "group_key=?"
            parameters.append(group_key)
        total = self.connection.execute(
            f"SELECT count(*) FROM {table} WHERE {where}", parameters
        ).fetchone()[0]
        if self.gate.hides:
            return Page(
                scope, status, total, (), None, reason or "sensitive_values_hidden"
            )
        if after is not None:
            where += " AND position>?"
            parameters.append(after[0])
        rows = self.connection.execute(
            f"SELECT {columns},position FROM {table} WHERE {where} "
            "ORDER BY position LIMIT ?",
            [*parameters, size + 1],
        ).fetchall()
        selected = rows[:size]
        next_cursor = None
        if len(rows) > size:
            last = selected[-1]
            next_cursor = Cursor(binding, (last[-1],))
        return Page(
            scope,
            status,
            total,
            tuple(factory(r[:-1]) for r in selected),
            next_cursor,
            reason,
        )

    def frequencies_page(self, *, size=100, cursor=None):
        return self._page(
            "values.frequencies",
            "frequencies",
            "value,native_type,count,type_rank",
            lambda r: ValueCount(value=r[0], type=r[1], count=r[2]),
            size=size,
            cursor=cursor,
        )

    def groups_page(self, *, size=100, cursor=None):
        return self._page(
            "normalization.groups",
            "groups",
            "value,count,distinct_count",
            lambda r: VariantGroupReference(*r),
            size=size,
            cursor=cursor,
        )

    def variants_page(self, group_key, *, size=100, cursor=None):
        if self.closed:
            raise QueryError("Value query is closed")
        if self.gate.hides:
            raise QueryError("Hidden group keys cannot be queried")
        if (
            self.connection.execute(
                "SELECT 1 FROM groups WHERE value=?", [group_key]
            ).fetchone()
            is None
        ):
            raise QueryError("Unknown exposed group key")
        return self._page(
            "normalization.variants",
            "variants",
            "value,count",
            lambda r: Variant(value=r[0], count=r[1]),
            size=size,
            cursor=cursor,
            group_key=group_key,
        )


def _build_values(pinned, dataset, field, connection, budget, gate, storage):
    config = pinned.result.config
    strings = StringClassifier(
        config.values.null_markers, config.values.null_markers_case_sensitive
    )
    normalizer = Normalizer(config.normalization)
    connection.execute(
        "CREATE TABLE inputs(native_type VARCHAR,type_rank INTEGER,analytical VARCHAR,"
        "raw VARCHAR,key VARCHAR,exposed_key VARCHAR,exposed_raw VARCHAR,occurrences BIGINT)"
    )
    columns = [[] for _ in range(8)]
    byte_count = 0

    def flush():
        nonlocal columns, byte_count
        if columns[0]:
            connection.execute(
                "INSERT INTO inputs SELECT unnest(?::VARCHAR[]),unnest(?::INTEGER[]),"
                "unnest(?::VARCHAR[]),unnest(?::VARCHAR[]),unnest(?::VARCHAR[]),"
                "unnest(?::VARCHAR[]),unnest(?::VARCHAR[]),unnest(?::BIGINT[])",
                columns,
            )
            columns = [[] for _ in columns]
            byte_count = 0

    # A separate reader cursor prevents writes to the materializer from
    # invalidating the source stream. Python retains a bounded batch and at
    # most one oversized value; no full distinct table or path registry.
    reader = pinned.connection.cursor()
    try:
        if storage[0] == 2:
            reader.execute(
                "SELECT native_type,raw_text,count FROM data.values WHERE dataset_id=? AND field_id=?",
                [dataset.id, field.id],
            )
        else:
            reader.execute(
                "SELECT native_type,raw_text,1 FROM data.observations "
                "WHERE dataset_id=? AND field_id=? AND native_type IN "
                "('string','integer','number','boolean')",
                [dataset.id, field.id],
            )
        while row := reader.fetchone():
            native, raw, occurrences = row
            if native == "string":
                if strings.category(raw) != "content":
                    continue
                forms, _ = normalizer.run(raw)
                analytical, key = forms[2], forms[-1]
                values = (
                    native,
                    0,
                    gate.value(analytical) if not gate.hides else analytical,
                    raw,
                    key,
                    gate.value(key),
                    gate.value(raw),
                )
            else:
                values = (
                    native,
                    _TYPE_ORDER[native],
                    gate.value(raw) if not gate.hides else raw,
                    None,
                    None,
                    None,
                    None,
                )
            values = (*values, occurrences)
            size = sum(
                len(v.encode("utf-8")) if isinstance(v, str) else 8 for v in values
            )
            if byte_count + size > budget.batch_bytes:
                flush()
            for column, value in zip(columns, values, strict=True):
                column.append(value)
            byte_count += size
            if len(columns[0]) >= budget.batch_rows or byte_count >= budget.batch_bytes:
                flush()
        flush()
    finally:
        reader.close()
    if (
        connection.execute(
            "SELECT coalesce(sum(occurrences),0) FROM inputs"
        ).fetchone()[0]
        != storage[2]
    ):
        raise QueryError("Stored value population differs from Scan")
    connection.execute(
        "CREATE TABLE frequencies AS SELECT analytical AS value,native_type,type_rank,"
        "sum(occurrences)::BIGINT AS count,encode(analytical) AS sort_key "
        "FROM inputs GROUP BY ALL"
    )
    connection.execute(
        "CREATE TABLE raw_counts AS SELECT key,raw,exposed_key,exposed_raw,sum(occurrences)::BIGINT AS count "
        "FROM inputs WHERE native_type='string' GROUP BY ALL"
    )
    connection.execute(
        "CREATE TABLE qualifying AS SELECT key FROM raw_counts GROUP BY key HAVING count(*)>=2"
    )
    if gate.hides:
        connection.execute(
            "CREATE TABLE groups AS SELECT key AS value,0::BIGINT AS count,"
            "0::BIGINT AS distinct_count,encode(key) AS sort_key FROM qualifying"
        )
        connection.execute(
            "CREATE TABLE variants(group_key VARCHAR,value VARCHAR,count BIGINT,sort_key BLOB)"
        )
    else:
        connection.execute(
            "CREATE TABLE variants AS SELECT exposed_key AS group_key,exposed_raw AS value,"
            "sum(count)::BIGINT AS count,encode(exposed_raw) AS sort_key "
            "FROM raw_counts JOIN qualifying USING(key) GROUP BY ALL"
        )
        connection.execute(
            "CREATE TABLE groups AS SELECT group_key AS value,sum(count)::BIGINT AS count,"
            "count(*)::BIGINT AS distinct_count,encode(group_key) AS sort_key "
            "FROM variants GROUP BY ALL"
        )
    connection.execute(
        "DROP TABLE inputs; DROP TABLE raw_counts; DROP TABLE qualifying"
    )
    # Sort once under the spill budget. Stable dense ordinals make later
    # keyset pages cheap (row-group pruning), without repeated full sorts or
    # OFFSET scans. UTF-8 BLOB order equals Python codepoint order, independent
    # of locale/default SQL collation, including NUL and non-BMP characters.
    for table in ("frequencies", "groups", "variants"):
        partition = "PARTITION BY group_key " if table == "variants" else ""
        tie = ",type_rank" if table == "frequencies" else ""
        order = f"{partition}ORDER BY count DESC,sort_key{tie}"
        connection.execute(
            f"CREATE TABLE ranked_{table} AS SELECT *,row_number() OVER ({order}) AS position "
            f"FROM {table} ORDER BY " + ("group_key," if partition else "") + "position"
        )
        connection.execute(
            f"DROP TABLE {table}; ALTER TABLE ranked_{table} RENAME TO {table}"
        )


@contextmanager
def materialize_values(
    pinned, dataset_id, field_id, *, budget: QueryBudget | None = None
):
    """Rebuild from the stored population. Failures yield no listing.

    Cursors survive disposal/rebuilding under identical semantics. They remain
    valid for an old pinned reader; a new generation rejects them. Sessions
    are private, local and sequential. The raw connection is privileged access.
    """
    dataset = _dataset(pinned, dataset_id)
    if pinned.result.engine.normalization_version != VERSION:
        raise QueryError("Unsupported Scan normalization semantics")
    field = next((f for f in dataset.fields if f.id == field_id), None)
    if field is None:
        raise QueryError("Unknown or unprofiled field")
    budget = budget or QueryBudget()
    gate = ExposureGate(field.exposure or "show")
    revision = pinned.connection.execute(
        "SELECT format_revision FROM meta.format"
    ).fetchone()[0]
    if revision == 2:
        limit, retained, omitted = pinned.connection.execute(
            "SELECT distinct_limit,retained_occurrences,omitted_occurrences FROM meta.value_storage WHERE dataset_id=? AND field_id=?",
            [dataset.id, field.id],
        ).fetchone()
        storage = (revision, limit, retained, omitted)
    else:
        storage = (revision, None, field.values.count, 0)
    with query_directory(
        pinned.database_path.parent.parent.parent, pinned.generation_id
    ) as directory:
        connection = duckdb.connect(
            str(directory / "values.duckdb"), config=budget.config(directory / "spill")
        )
        query = None
        try:
            apply_spill_limit(connection, f"{budget.spill_bytes}B")
            _build_values(pinned, dataset, field, connection, budget, gate, storage)
            query = ValueQuery(
                pinned, dataset, field, connection, directory, gate, storage
            )
            yield query
        finally:
            if query is not None:
                query.closed = True
            connection.close()

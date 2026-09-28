"""Record-level facts of a dataset (design section 9.10).

Values are the scalar observations of a record: every cell of a CSV row,
every string, number, boolean or null of a JSON record. A field absent from a
record is not a value of that record. A record has missing values when one of
its values is missing under ``values.missing``, and is empty when it has
values and all are missing.

Duplicate records compare every observation (path, native type, value)
through a 128-bit BLAKE2b digest, one per distinct record, within a dataset.
``limits.max_tracked_records`` bounds the digests stored for the whole scan:
once it is reached, later records are still compared with the stored ones, so
the count becomes a proven lower bound (reason ``record_budget``).

A record of a dataset with declared fields (a CSV table) that observes the
root, then each declared path once, in order, as a string, is its values
alone: its digest hashes the value lengths and the joined values, with its
own personalization so it never equals the digest of another record.
"""

from __future__ import annotations

import hashlib
import operator
from array import array

from tabalyst.scanner.config import ScanConfig
from tabalyst.scanner.exposure import mask
from tabalyst.scanner.field import StringClassifier
from tabalyst.scanner.measures import canonical_text
from tabalyst.scanner.models import (
    Complete,
    Disabled,
    DuplicateRecords,
    Limited,
    PreviewRecord,
    RecordList,
    Records,
)
from tabalyst.scanner.observations import Record
from tabalyst.scanner.paths import ROOT, FieldPath

CONTAINER_TYPES = frozenset({"object", "array"})
# Paths numbered for the digests; later paths use their ``repr``.
MAX_PATH_TOKENS = 65_536
_TABLE_PERSON = b"tabalyst.table"
_path = operator.attrgetter("path")
_type = operator.attrgetter("type")
_value = operator.attrgetter("value")


class TableLayout:
    """The observations of a record of a declared table: the root, then each
    declared path once, in order, as a string."""

    __slots__ = ("paths", "size", "types")

    def __init__(self, declared: tuple[FieldPath, ...]) -> None:
        self.paths = (ROOT, *declared)
        self.types = ("object", *("string",) * len(declared))
        self.size = len(self.paths)

    def values(self, record: Record) -> list[str] | None:
        """The values of ``record`` when it has the layout, else ``None``.

        Readers reuse the declared path objects: identity is checked first.
        """
        observations = record.observations
        if (
            len(observations) != self.size
            or tuple(map(_type, observations)) != self.types
            or observations[0].value is not None
        ):
            return None
        paths = self.paths
        if (
            not all(map(operator.is_, map(_path, observations), paths))
            and tuple(map(_path, observations)) != paths
        ):
            return None
        return list(map(_value, observations[1:]))


def _table_digest(values: list[str]) -> bytes:
    """Digest of table values: the lengths make the joined text unambiguous."""
    digest = hashlib.blake2b(
        array("q", map(len, values)).tobytes(), digest_size=16, person=_TABLE_PERSON
    )
    digest.update("".join(values).encode("utf-8", "surrogatepass"))
    return digest.digest()


class PathTokens:
    """A short, stable digest token per path.

    Readers reuse the same path objects from record to record, so tokens are
    looked up by identity first: hashing a path hashes each of its segments.
    """

    __slots__ = ("_by_id", "_tokens")

    def __init__(self) -> None:
        self._tokens: dict[FieldPath, int | str] = {}
        self._by_id: dict[int, tuple[FieldPath, int | str]] = {}

    def token(self, path: FieldPath) -> int | str:
        entry = self._by_id.get(id(path))
        if entry is not None and entry[0] is path:
            return entry[1]
        tokens = self._tokens
        token = tokens.get(path)
        if token is None:
            if len(tokens) < MAX_PATH_TOKENS:
                token = tokens[path] = len(tokens)
            else:
                # A ``repr`` is quoted: it never equals the ``repr`` of a number.
                token = repr(path)
        by_id = self._by_id
        if len(by_id) >= MAX_PATH_TOKENS:
            by_id.clear()
        by_id[id(path)] = (path, token)
        return token


class DuplicateBudget:
    """Digests stored for duplicate detection across the datasets of a scan."""

    __slots__ = ("limit", "stored", "untracked")

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.stored = 0
        # Records whose digest could not be stored, for the whole scan.
        self.untracked = 0


class RecordContext:
    """Settings shared by the record facts of every dataset of a scan."""

    __slots__ = (
        "budget",
        "duplicates",
        "listed",
        "missing",
        "null_missing",
        "preview",
        "strings",
    )

    def __init__(self, config: ScanConfig, strings: StringClassifier) -> None:
        self.strings = strings
        # String categories counted as missing (design section 7).
        self.missing = frozenset(config.values.missing) - {"absent", "null"}
        self.null_missing = "null" in config.values.missing
        self.preview = config.records.preview
        self.duplicates = config.records.duplicates
        self.listed = config.limits.max_listed_records
        self.budget = DuplicateBudget(config.limits.max_tracked_records)

    def is_missing(self, value: str) -> bool:
        return self.strings.category(value) in self.missing

    def is_content(self, value: str) -> bool:
        return self.strings.category(value) == "content"


class RecordFacts:
    """Record-level facts of one dataset, collected while it is read."""

    __slots__ = (
        "_context",
        "_paths",
        "_seen",
        "_table",
        "duplicate_count",
        "duplicate_records",
        "empty_count",
        "empty_records",
        "missing_count",
        "missing_records",
        "preview",
        "untracked",
    )

    def __init__(
        self, context: RecordContext, declared: tuple[FieldPath, ...] = ()
    ) -> None:
        self._context = context
        self._seen: set[bytes] = set()
        self._paths = PathTokens()
        self._table = TableLayout(declared) if declared else None
        # Observed scalar values of the first records, per path.
        self.preview: list[tuple[int, dict[FieldPath, list[tuple[str, str | None]]]]] = []
        self.missing_count = 0
        self.missing_records: list[int] = []
        self.empty_count = 0
        self.empty_records: list[int] = []
        self.duplicate_count = 0
        self.duplicate_records: list[int] = []
        # Records whose digest was not stored once the budget was reached.
        self.untracked = 0

    def add(self, record: Record) -> None:
        context = self._context
        index = record.index
        keep_preview = len(self.preview) < context.preview
        values: dict[FieldPath, list[tuple[str, str | None]]] = {}
        missing = scalars = 0
        for observation in record.observations:
            native = observation.type
            if native in CONTAINER_TYPES:
                continue
            scalars += 1
            if native == "null":
                text = None
                missing += context.null_missing
            elif native == "string":
                text = observation.value
                missing += context.is_missing(text)
            elif keep_preview:
                text = canonical_text(native, observation.value)
            else:
                continue
            if keep_preview:
                values.setdefault(observation.path, []).append((native, text))
        if keep_preview:
            self.preview.append((index, values))
        listed = context.listed
        if missing:
            self.missing_count += 1
            if len(self.missing_records) < listed:
                self.missing_records.append(index)
            if missing == scalars:
                self.empty_count += 1
                if len(self.empty_records) < listed:
                    self.empty_records.append(index)
        if context.duplicates:
            self._compare(record)

    def _digest(self, record: Record) -> bytes:
        table = self._table
        if table is not None:
            values = table.values(record)
            if values is not None:
                return _table_digest(values)
        token = self._paths.token
        key = [
            (token(observation.path), observation.type, observation.value)
            for observation in record.observations
        ]
        return hashlib.blake2b(
            repr(key).encode("utf-8", "surrogatepass"), digest_size=16
        ).digest()

    def _compare(self, record: Record) -> None:
        digest = self._digest(record)
        if digest in self._seen:
            self.duplicate_count += 1
            if len(self.duplicate_records) < self._context.listed:
                self.duplicate_records.append(record.index)
            return
        budget = self._context.budget
        if budget.stored < budget.limit:
            self._seen.add(digest)
            budget.stored += 1
        else:
            self.untracked += 1
            budget.untracked += 1

    def finalize(
        self, ids: dict[FieldPath, str], exposures: dict[FieldPath, str | None]
    ) -> Records:
        context = self._context
        if not context.duplicates:
            count = Disabled()
        elif self.untracked:
            count = Limited(
                reason="record_budget",
                limit=context.budget.limit,
                lower_bound=self.duplicate_count,
            )
        else:
            count = Complete[int](value=self.duplicate_count)
        return Records(
            with_missing=RecordList(
                count=self.missing_count, records=self.missing_records
            ),
            empty=RecordList(count=self.empty_count, records=self.empty_records),
            duplicates=DuplicateRecords(count=count, records=self.duplicate_records),
            preview=[
                PreviewRecord(
                    record=index, values=self._exposed(observed, ids, exposures)
                )
                for index, observed in self.preview
            ],
        )

    def _exposed(
        self,
        observed: dict[FieldPath, list[tuple[str, str | None]]],
        ids: dict[FieldPath, str],
        exposures: dict[FieldPath, str | None],
    ) -> dict[str, list[str | None] | None]:
        """Preview values of the listed fields, through their exposure (design
        12.8). Nulls and strings that are not content are shown as read; a
        hidden value hides its whole cell."""
        cells: dict[str, list[str | None] | None] = {}
        for path, values in observed.items():
            field_id = ids.get(path)
            if field_id is None:
                continue
            exposure = exposures.get(path)
            if exposure in (None, "show"):
                cells[field_id] = [text for _, text in values]
                continue
            texts: list[str | None] | None = []
            for native, text in values:
                if text is None or (
                    native == "string" and not self._context.is_content(text)
                ):
                    texts.append(text)
                elif exposure == "mask":
                    texts.append(mask(text))
                else:
                    texts = None
                    break
            cells[field_id] = texts
        return cells

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Load and validate versioned Generate package manifests and CSV tables."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path, PureWindowsPath
from typing import Literal

import yaml

from tabalyst.errors import ConfigurationError
from tabalyst.generate_definition import StrictLoader

MAX_YAML_BYTES = 1_048_576
MAX_TABLES = 128
MAX_CSV_BYTES = 64 * 1_048_576
MAX_CELLS = 2_000_000
MAX_DATASETS = 64
MAX_COLUMNS = 256
MAX_PROFILES = 32
MAX_ROWS = 10_000_000
ROLES = frozenset({
    "dictionary", "entity", "relation", "weighted_relation",
    "constraint", "resource",
})
TYPES = frozenset({"string", "integer", "number", "boolean", "date"})
IDENTIFIER = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*\Z", re.ASCII)
ARTIFACT_ID = re.compile(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*\Z", re.ASCII)
OUTPUT_TYPES = TYPES | {"decimal", "datetime"}
VALUE_KINDS = frozenset({
    "constant", "sequence", "choice", "integer", "decimal", "boolean",
    "date", "datetime", "text", "reference", "relative_date", "conditional",
    "provider", "stable_id",
})

Cell = str | int | Decimal | bool | date | None


@dataclass(frozen=True)
class TableColumn:
    """Describe the physical and cell-level rules of one CSV column."""

    name: str
    type: Literal["string", "integer", "number", "boolean", "date"]
    required: bool
    unique: bool
    references: str | None
    minimum: Cell
    maximum: Cell


@dataclass(frozen=True)
class PackageTable:
    """Keep a validated catalog table in source order."""

    id: str
    role: str
    file: Path
    schema: Path
    columns: tuple[TableColumn, ...]
    rows: tuple[dict[str, Cell], ...]
    unique: tuple[str, ...]
    row_lines: tuple[int, ...]


@dataclass(frozen=True)
class DatasetPackage:
    """Represent validated, indexed catalog tables before generation."""

    root: Path
    id: str
    package_version: str
    manifest: dict[str, object]
    catalog: dict[str, object]
    tables: dict[str, PackageTable]
    input_paths: frozenset[Path]
    value_index: dict[str, dict[str, frozenset[Cell]]]
    relation_index: dict[str, dict[str, dict[Cell, tuple[dict[str, Cell], ...]]]]


def _fail(code: str, path: Path, message: str, row: int = 1, column: str = "-") -> None:
    raise ConfigurationError(f"{code}: {path}:{row}:{column}: {message}")


def _mapping(value: object, path: Path, allowed: set[str], required: set[str]) -> dict[str, object]:
    if not isinstance(value, dict):
        _fail("PACKAGE_SCHEMA", path, "expected a mapping")
    keys = set(value)
    if missing := required - keys:
        _fail("PACKAGE_SCHEMA", path, f"missing key {min(missing)!r}")
    if extra := keys - allowed:
        _fail("PACKAGE_SCHEMA", path, f"unknown key {min(extra)!r}")
    return value


def _identifier(value: object, path: Path, where: str, *, artifact: bool = False) -> str:
    pattern = ARTIFACT_ID if artifact else IDENTIFIER
    if not isinstance(value, str) or len(value) > 80 or not pattern.fullmatch(value):
        _fail("PACKAGE_SCHEMA", path, f"{where} must be a lowercase ASCII identifier")
    return value


def _relative(root: Path, value: object, source: Path, *, schema: bool = False) -> Path:
    if not isinstance(value, str) or not value or "\\" in value:
        _fail("PACKAGE_PATH", source, "resource path must be a relative slash-separated path")
    raw = Path(value)
    if raw.is_absolute() or PureWindowsPath(value).drive or ".." in raw.parts:
        _fail("PACKAGE_PATH", source, f"path escapes package: {value!r}")
    if schema and (not value.startswith("schemas/") or raw.suffix != ".yaml"):
        _fail("PACKAGE_PATH", source, "schema must be a YAML file under schemas/")
    resolved = (root / raw).resolve()
    if not resolved.is_relative_to(root):
        _fail("PACKAGE_PATH", source, f"path escapes package: {value!r}")
    if not resolved.is_file():
        _fail("PACKAGE_FILE_MISSING", resolved, "declared file does not exist")
    return resolved


def _yaml(path: Path) -> object:
    if path.stat().st_size > MAX_YAML_BYTES:
        _fail("PACKAGE_LIMIT", path, "YAML exceeds 1 MiB")
    try:
        with path.open("r", encoding="utf-8") as stream:
            return yaml.load(stream, Loader=StrictLoader)
    except (UnicodeError, yaml.YAMLError, ConfigurationError) as exc:
        _fail("PACKAGE_YAML", path, str(exc))


def _scalar(raw: str, kind: str, path: Path, row: int, column: str) -> Cell:
    if raw == "":
        return None
    try:
        if kind == "string":
            return raw
        if kind == "integer":
            if not re.fullmatch(r"-?(?:0|[1-9][0-9]*)", raw, re.ASCII):
                raise ValueError("invalid integer")
            return int(raw)
        if kind == "number":
            value = Decimal(raw)
            if not value.is_finite():
                raise ValueError("nonfinite number")
            return value
        if kind == "boolean":
            if raw not in {"true", "false"}:
                raise ValueError("boolean must be true or false")
            return raw == "true"
        parsed = date.fromisoformat(raw)
        if parsed.isoformat() != raw:
            raise ValueError("date must be YYYY-MM-DD")
        return parsed
    except (ValueError, InvalidOperation, OverflowError) as exc:
        _fail("PACKAGE_CSV_TYPE", path, f"{kind} value {raw!r}: {exc}", row, column)
    raise AssertionError(kind)


def _schema(path: Path, role: str) -> tuple[tuple[TableColumn, ...], tuple[str, ...]]:
    root = _mapping(_yaml(path), path, {"type", "columns", "unique"}, {"type", "columns"})
    if root["type"] != role:
        _fail("PACKAGE_SCHEMA", path, f"schema type must be {role!r}")
    raw_columns = root["columns"]
    if not isinstance(raw_columns, dict) or not 1 <= len(raw_columns) <= MAX_COLUMNS:
        _fail("PACKAGE_SCHEMA", path, "columns must be a nonempty mapping of at most 256 entries")
    columns: list[TableColumn] = []
    for name, raw in raw_columns.items():
        name = _identifier(name, path, "column")
        item = _mapping(raw, path, {"type", "required", "unique", "references", "min", "max"}, {"type", "required"})
        kind = item["type"]
        if not isinstance(kind, str) or kind not in TYPES:
            _fail("PACKAGE_SCHEMA", path, f"{name}: unsupported physical type")
        if type(item["required"]) is not bool or type(item.get("unique", False)) is not bool:
            _fail("PACKAGE_SCHEMA", path, f"{name}: required and unique must be boolean")
        reference = item.get("references")
        if reference is not None and (
            not isinstance(reference, str) or len(reference.split(".")) != 2
            or any(not IDENTIFIER.fullmatch(part) for part in reference.split("."))
        ):
            _fail("PACKAGE_SCHEMA", path, f"{name}: references must be table.column")
        minimum = _scalar(str(item["min"]), kind, path, 1, name) if "min" in item else None
        maximum = _scalar(str(item["max"]), kind, path, 1, name) if "max" in item else None
        if kind == "boolean" and (minimum is not None or maximum is not None):
            _fail("PACKAGE_SCHEMA", path, f"{name}: boolean bounds are unsupported")
        if minimum is not None and maximum is not None and minimum > maximum:
            _fail("PACKAGE_SCHEMA", path, f"{name}: min exceeds max")
        columns.append(TableColumn(name, kind, item["required"], item.get("unique", False),
                                   reference, minimum, maximum))
    raw_unique = root.get("unique", [])
    if not isinstance(raw_unique, list) or any(not isinstance(n, str) or n not in raw_columns for n in raw_unique):
        _fail("PACKAGE_SCHEMA", path, "unique must list declared columns")
    if len(raw_unique) != len(set(raw_unique)):
        _fail("PACKAGE_SCHEMA", path, "unique repeats a column")
    if role == "dictionary" and not {"id", "en"}.issubset(raw_columns):
        _fail("PACKAGE_SCHEMA", path, "dictionary requires id and en columns")
    if role == "weighted_relation" and "weight" not in raw_columns:
        _fail("PACKAGE_SCHEMA", path, "weighted relation requires weight")
    return tuple(columns), tuple(raw_unique)


def _csv(path: Path, columns: tuple[TableColumn, ...], unique: tuple[str, ...],
         role: str, cell_budget: int) -> tuple[tuple[dict[str, Cell], ...], tuple[int, ...]]:
    expected = [column.name for column in columns]
    seen: dict[str, set[Cell]] = {column.name: set() for column in columns if column.unique or column.name == "id"}
    seen_pairs: set[tuple[Cell, ...]] = set()
    rows: list[dict[str, Cell]] = []
    row_lines: list[int] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as stream:
            reader = csv.reader(stream, strict=True)
            header = next(reader, None)
            if header is None or len(header) != len(set(header)) or header != expected:
                _fail("PACKAGE_CSV_HEADER", path, f"header must be {expected!r}", 1)
            for record in reader:
                line = reader.line_num
                if len(record) != len(columns):
                    _fail("PACKAGE_CSV_ROW", path, "row width differs from header", line)
                if (len(rows) + 1) * len(columns) > cell_budget:
                    _fail("PACKAGE_LIMIT", path, "reference cells exceed 2,000,000", line)
                row: dict[str, Cell] = {}
                for column, raw in zip(columns, record, strict=True):
                    value = _scalar(raw, column.type, path, line, column.name)
                    if value is None and column.required:
                        _fail("PACKAGE_CSV_REQUIRED", path, "required cell is empty", line, column.name)
                    if value is not None and (column.name == "id" or column.name.endswith("_id")):
                        _identifier(value, path, f"{column.name} at CSV row {line}")
                    if value is not None and column.minimum is not None and value < column.minimum:
                        _fail("PACKAGE_CSV_BOUND", path, "value below min", line, column.name)
                    if value is not None and column.maximum is not None and value > column.maximum:
                        _fail("PACKAGE_CSV_BOUND", path, "value above max", line, column.name)
                    if column.name == "weight" and role == "weighted_relation" and (
                        value is None or type(value) not in (int, Decimal) or value <= 0
                    ):
                        _fail("PACKAGE_CSV_WEIGHT", path, "weight must be positive", line, column.name)
                    if column.name in seen and value is not None:
                        if value in seen[column.name]:
                            _fail("PACKAGE_CSV_DUPLICATE", path, "duplicate value", line, column.name)
                        seen[column.name].add(value)
                    row[column.name] = value
                if unique:
                    key = tuple(row[name] for name in unique)
                    if key in seen_pairs:
                        _fail("PACKAGE_CSV_DUPLICATE", path, "duplicate composite key", line, ",".join(unique))
                    seen_pairs.add(key)
                rows.append(row)
                row_lines.append(line)
    except (UnicodeError, csv.Error) as exc:
        _fail("PACKAGE_CSV_PARSE", path, str(exc))
    return tuple(rows), tuple(row_lines)


def _resolve_tables(
    tables: dict[str, PackageTable],
) -> tuple[dict[str, dict[str, frozenset[Cell]]],
           dict[str, dict[str, dict[Cell, tuple[dict[str, Cell], ...]]]]]:
    """Resolve declared foreign keys and group rows by their reference values."""
    values = {
        table_id: {
            column.name: frozenset(row[column.name] for row in table.rows
                                   if row[column.name] is not None)
            for column in table.columns
        }
        for table_id, table in tables.items()
    }
    grouped: dict[str, dict[str, dict[Cell, tuple[dict[str, Cell], ...]]]] = {}
    for table_id, table in tables.items():
        groups: dict[str, dict[Cell, list[dict[str, Cell]]]] = {}
        for column in table.columns:
            if column.references is None:
                continue
            target_id, target_column = column.references.split(".")
            target = tables.get(target_id)
            if target is None or target_column not in values[target_id]:
                _fail("PACKAGE_REFERENCE_SCHEMA", table.schema,
                      f"{column.name} references unknown {column.references}", 1, column.name)
            target_rule = next(rule for rule in target.columns if rule.name == target_column)
            if column.type != target_rule.type or not (target_rule.unique or target_column == "id"):
                _fail("PACKAGE_REFERENCE_SCHEMA", table.schema,
                      f"{column.name} must reference a unique column of the same type", 1, column.name)
            by_value: dict[Cell, list[dict[str, Cell]]] = {}
            for row, line in zip(table.rows, table.row_lines, strict=True):
                value = row[column.name]
                if value is None:
                    continue
                if value not in values[target_id][target_column]:
                    _fail("PACKAGE_REFERENCE_UNKNOWN", table.file,
                          f"unknown {target_id}.{target_column} ID {value!r}", line, column.name)
                by_value.setdefault(value, []).append(row)
            groups[column.name] = by_value
        grouped[table_id] = {
            name: {key: tuple(rows) for key, rows in entries.items()}
            for name, entries in groups.items()
        }
    return values, grouped


def _check_required_choices(tables: dict[str, PackageTable],
                            relations: dict[str, dict[str, dict[Cell, tuple[dict[str, Cell], ...]]]]) -> None:
    """Ensure each declared Computer generation has core component choices."""
    generations = tables.get("generation") or tables.get("model_generation")
    if generations is None:
        return
    if "id" not in {column.name for column in generations.columns}:
        _fail("PACKAGE_SCHEMA", generations.schema, "generation table requires id", 1, "id")
    for component in ("cpu", "memory", "storage", "display"):
        candidates = [table for table in tables.values()
                      if table.role in {"relation", "weighted_relation"}
                      and any(column.name == "generation_id"
                              and column.references == f"{generations.id}.id"
                              for column in table.columns)
                      and any(column.name == f"{component}_id"
                              for column in table.columns)]
        if not candidates:
            _fail("PACKAGE_REQUIRED_CHOICE", generations.schema,
                  f"no generation relation for required {component}", 1, f"{component}_id")
        for generation, line in zip(generations.rows, generations.row_lines, strict=True):
            ident = generation["id"]
            if not any(relations[table.id]["generation_id"].get(ident) for table in candidates):
                _fail("PACKAGE_REQUIRED_CHOICE", generations.file,
                      f"generation {ident!r} has no {component} choice", line, "id")


def _check_orphans(tables: dict[str, PackageTable],
                   relations: dict[str, dict[str, dict[Cell, tuple[dict[str, Cell], ...]]]]) -> None:
    """Reject required entity IDs that no relation can reach."""
    for entity in tables.values():
        if entity.role != "entity" or "id" not in {column.name for column in entity.columns}:
            continue
        links = [(table.id, column.name) for table in tables.values()
                 if table.role in {"relation", "weighted_relation"}
                 for column in table.columns
                 if column.required and column.references == f"{entity.id}.id"]
        if not links:
            continue
        linked: set[Cell] = {
            value for table_id, column in links for value in relations[table_id][column]
        }
        for row, line in zip(entity.rows, entity.row_lines, strict=True):
            if row["id"] not in linked:
                _fail("PACKAGE_REFERENCE_ORPHAN", entity.file,
                      f"required {entity.id} ID {row['id']!r} has no relation", line, "id")


def _manifest(path: Path) -> dict[str, object]:
    root = _mapping(_yaml(path), path, {
        "format", "format_version", "id", "package_version", "catalog", "defaults",
        "entities", "cohorts", "datasets", "generation_profiles",
        "output_profiles", "anomaly_profiles",
    }, {"format", "format_version", "id", "package_version", "catalog", "defaults", "datasets"})
    if root["format"] != "tabalyst.generate.package" or root["format_version"] != "0.1.0":
        _fail("PACKAGE_FORMAT", path, "unsupported package format or version")
    _identifier(root["id"], path, "package id")
    version = root["package_version"]
    if not isinstance(version, str) or not re.fullmatch(r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", version):
        _fail("PACKAGE_SCHEMA", path, "package_version must be SemVer")
    defaults = _mapping(root["defaults"], path, {"rows", "seed", "as_of_date"}, set())
    if "rows" in defaults and (type(defaults["rows"]) is not int or not 1 <= defaults["rows"] <= MAX_ROWS):
        _fail("PACKAGE_SCHEMA", path, "defaults.rows is out of range")
    if "seed" in defaults and type(defaults["seed"]) is not int:
        _fail("PACKAGE_SCHEMA", path, "defaults.seed must be an integer")
    if "as_of_date" in defaults:
        _scalar(str(defaults["as_of_date"]), "date", path, 1, "as_of_date")
    datasets = root["datasets"]
    if not isinstance(datasets, list) or not 1 <= len(datasets) <= MAX_DATASETS:
        _fail("PACKAGE_LIMIT", path, "datasets must contain 1 to 64 entries")
    ids: set[str] = set()
    for raw in datasets:
        item = _mapping(raw, path, {
            "id", "mode", "rows", "row_source", "schema", "source", "cohort",
            "steps", "inputs", "source_column",
        }, {"id", "mode"})
        ident = _identifier(item["id"], path, "dataset id", artifact=True)
        if ident in ids:
            _fail("PACKAGE_SCHEMA", path, f"duplicate dataset {ident!r}")
        ids.add(ident)
        if item["mode"] not in {"generated", "combine"}:
            _fail("PACKAGE_SCHEMA", path, "dataset mode must be generated or combine")
        if item["mode"] == "generated":
            if not {"row_source", "schema"}.issubset(item):
                _fail("PACKAGE_SCHEMA", path, "generated dataset needs row_source and schema")
            if item["row_source"] not in {"columns", "catalog_steps"}:
                _fail("PACKAGE_SCHEMA", path, "unknown row_source")
            if "rows" in item and (type(item["rows"]) is not int or not 1 <= item["rows"] <= MAX_ROWS):
                _fail("PACKAGE_SCHEMA", path, "dataset rows is out of range")
        elif not isinstance(item.get("inputs"), list) or not item["inputs"]:
            _fail("PACKAGE_SCHEMA", path, "combine dataset needs inputs")
    for name in ("generation_profiles", "output_profiles", "anomaly_profiles"):
        profiles = root.get(name, {})
        if not isinstance(profiles, dict) or len(profiles) > MAX_PROFILES:
            _fail("PACKAGE_LIMIT", path, f"{name} must have at most 32 profiles")
        for ident in profiles:
            _identifier(ident, path, f"{name} id")
    return root


def _output_schema(path: Path) -> None:
    schema = _mapping(_yaml(path), path, {"columns"}, {"columns"})
    columns = schema["columns"]
    if not isinstance(columns, list) or not 1 <= len(columns) <= MAX_COLUMNS:
        _fail("PACKAGE_SCHEMA", path, "output schema needs 1 to 256 columns")
    seen: set[str] = set()
    for raw in columns:
        column = _mapping(raw, path, {
            "name", "type", "from", "generate", "depends_on", "missing",
            "cohort", "label_table",
        }, {"name", "type"})
        name = column["name"]
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            _fail("PACKAGE_SCHEMA", path, "invalid output column name")
        if name in seen:
            _fail("PACKAGE_SCHEMA", path, f"duplicate output column {name!r}")
        seen.add(name)
        if not isinstance(column["type"], str) or column["type"] not in OUTPUT_TYPES:
            _fail("PACKAGE_SCHEMA", path, f"{name}: invalid output type")
        if ("from" in column) == ("generate" in column):
            _fail("PACKAGE_SCHEMA", path, f"{name}: use exactly one of from or generate")
        if "from" in column and not isinstance(column["from"], str):
            _fail("PACKAGE_SCHEMA", path, f"{name}: from must be text")
        if "generate" in column:
            operation = column["generate"]
            if not isinstance(operation, dict) or not isinstance(operation.get("kind"), str) or operation["kind"] not in VALUE_KINDS:
                _fail("PACKAGE_SCHEMA", path, f"{name}: unknown value operation")
        if "label_table" in column and "from" not in column:
            _fail("PACKAGE_SCHEMA", path, f"{name}: label_table requires from")
        if "depends_on" in column and (
            not isinstance(column["depends_on"], list)
            or any(not isinstance(dep, str) for dep in column["depends_on"])
        ):
            _fail("PACKAGE_SCHEMA", path, f"{name}: depends_on must list columns")


def _steps(items: object, path: Path, tables: dict[str, PackageTable],
           *, has_profiles: bool) -> None:
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_COLUMNS:
        _fail("PACKAGE_SCHEMA", path, "catalog_steps requires 1 to 256 steps")
    ids: set[str] = set()
    outputs: set[str] = {"generation_profile_id"} if has_profiles else set()
    for raw in items:
        step = _mapping(raw, path, {
            "id", "kind", "output", "source", "candidate_column", "where",
            "filters", "weight_column", "influences", "from_table",
            "selected", "column",
        }, {"id", "kind", "output"})
        ident = _identifier(step["id"], path, "step id")
        output = _identifier(step["output"], path, "step output")
        if ident in ids:
            _fail("PACKAGE_SCHEMA", path, f"duplicate step {ident!r}")
        if output in outputs:
            _fail("PACKAGE_SCHEMA", path, f"duplicate step output {output!r}")
        ids.add(ident)
        kind = step["kind"]
        if kind == "select":
            if not {"source", "candidate_column"}.issubset(step):
                _fail("PACKAGE_SCHEMA", path, "select step needs source and candidate_column")
            source = step["source"]
            if not isinstance(source, str) or source not in tables:
                _fail("PACKAGE_STEP_REFERENCE", path, f"unknown source table {source!r}")
            names = {column.name for column in tables[source].columns}
            candidate = step["candidate_column"]
            if not isinstance(candidate, str) or candidate not in names:
                _fail("PACKAGE_STEP_REFERENCE", path, f"unknown candidate column {candidate!r}")
            candidate_rule = next(column for column in tables[source].columns if column.name == candidate)
            if candidate_rule.type != "string":
                _fail("PACKAGE_STEP_REFERENCE", path, f"{ident}: candidate IDs must be strings")
            where = step.get("where", {})
            if not isinstance(where, dict) or any(
                not isinstance(column, str) or column not in names
                or not isinstance(field, str) or field not in outputs
                for column, field in where.items()
            ):
                _fail("PACKAGE_STEP_REFERENCE", path, f"{ident}: where requires source columns and prior fields")
            seen_candidates: set[tuple[Cell, ...]] = set()
            for row, line in zip(tables[source].rows, tables[source].row_lines, strict=True):
                if row[candidate] is None:
                    _fail("PACKAGE_STEP_CANDIDATE", tables[source].file,
                          f"{ident}: candidate is empty", line, candidate)
                if not isinstance(row[candidate], str) or not IDENTIFIER.fullmatch(row[candidate]):
                    _fail("PACKAGE_STEP_CANDIDATE", tables[source].file,
                          f"{ident}: candidate is not a canonical ID", line, candidate)
                key = tuple(row[column] for column in where) + (row[candidate],)
                if key in seen_candidates:
                    _fail("PACKAGE_STEP_DUPLICATE", tables[source].file,
                          f"duplicate candidate {row[candidate]!r} in {ident}", line, candidate)
                seen_candidates.add(key)
            weight = step.get("weight_column")
            if weight is not None and (
                not isinstance(weight, str) or weight not in names
                or next(column for column in tables[source].columns if column.name == weight).type
                not in {"integer", "number"}
            ):
                _fail("PACKAGE_STEP_REFERENCE", path, f"{ident}: invalid weight column")
            if weight is not None:
                for row, line in zip(tables[source].rows, tables[source].row_lines, strict=True):
                    value = row[weight]
                    if not isinstance(value, (int, Decimal)) or isinstance(value, bool) or value <= 0:
                        _fail("PACKAGE_CSV_WEIGHT", tables[source].file,
                              "weight must be positive", line, weight)
        elif kind == "derive":
            if not {"from_table", "selected", "column"}.issubset(step):
                _fail("PACKAGE_SCHEMA", path, "derive step needs from_table, selected and column")
            table = step["from_table"]
            if not isinstance(table, str) or table not in tables:
                _fail("PACKAGE_STEP_REFERENCE", path, f"unknown derive table {table!r}")
            if (not isinstance(step["selected"], str) or step["selected"] not in outputs
                or not isinstance(step["column"], str) or step["column"] not in {
                column.name for column in tables[table].columns
            }):
                _fail("PACKAGE_STEP_REFERENCE", path, f"{ident}: unknown selected field or column")
        else:
            _fail("PACKAGE_SCHEMA", path, f"unknown catalog step kind {kind!r}")
        outputs.add(output)


def load_generate_package(path: Path | str) -> DatasetPackage:
    """Load and index a package after validating its tables and references."""
    source = Path(path)
    if source.is_file() and source.name != "dataset.yaml":
        _fail("PACKAGE_FORMAT", source,
              "definition_version: 1 YAML is unsupported; supply a package directory or dataset.yaml")
    manifest_path = source / "dataset.yaml" if source.is_dir() else source
    if manifest_path.name != "dataset.yaml" or not manifest_path.is_file():
        _fail("PACKAGE_FILE_MISSING", manifest_path, "expected dataset.yaml")
    root = manifest_path.parent.resolve()
    manifest = _manifest(manifest_path)
    catalog_path = _relative(root, manifest["catalog"], manifest_path)
    catalog = _mapping(_yaml(catalog_path), catalog_path, {"tables"}, {"tables"})
    entries = catalog["tables"]
    if not isinstance(entries, dict) or len(entries) > MAX_TABLES:
        _fail("PACKAGE_LIMIT", catalog_path, "catalog must contain at most 128 tables")
    paths = {manifest_path.resolve(), catalog_path}
    tables: dict[str, PackageTable] = {}
    bytes_total = 0
    cells_total = 0
    for table_id, raw in entries.items():
        table_id = _identifier(table_id, catalog_path, "table id")
        item = _mapping(raw, catalog_path, {"role", "file", "schema"}, {"role", "file", "schema"})
        role = item["role"]
        if not isinstance(role, str) or role not in ROLES:
            _fail("PACKAGE_SCHEMA", catalog_path, f"{table_id}: unsupported role")
        file = _relative(root, item["file"], catalog_path)
        schema = _relative(root, item["schema"], catalog_path, schema=True)
        if file.suffix.lower() != ".csv":
            _fail("PACKAGE_SCHEMA", catalog_path, f"{table_id}: file must be CSV")
        if file in paths:
            _fail("PACKAGE_SCHEMA", catalog_path, f"{table_id}: file path is reused")
        paths.update((file, schema))
        bytes_total += file.stat().st_size
        if bytes_total > MAX_CSV_BYTES:
            _fail("PACKAGE_LIMIT", file, "reference CSV bytes exceed 64 MiB")
        columns, unique = _schema(schema, role)
        rows, row_lines = _csv(file, columns, unique, role, MAX_CELLS - cells_total)
        cells_total += len(rows) * len(columns)
        tables[table_id] = PackageTable(table_id, role, file, schema, columns, rows, unique, row_lines)
    values, relations = _resolve_tables(tables)
    for table in tables.values():
        if table.role not in {"relation", "weighted_relation"}:
            continue
        foreign = tuple(column.name for column in table.columns if column.references)
        if len(foreign) < 2:
            continue
        seen_pairs: set[tuple[Cell, ...]] = set()
        for row, line in zip(table.rows, table.row_lines, strict=True):
            pair = tuple(row[name] for name in foreign)
            if pair in seen_pairs:
                _fail("PACKAGE_RELATION_DUPLICATE", table.file,
                      "duplicate relation pair", line, ",".join(foreign))
            seen_pairs.add(pair)
    _check_required_choices(tables, relations)
    _check_orphans(tables, relations)
    datasets = manifest["datasets"]
    assert isinstance(datasets, list)
    for raw in datasets:
        if raw["mode"] == "generated":
            schema_path = _relative(root, raw["schema"], manifest_path, schema=True)
            paths.add(schema_path)
            _output_schema(schema_path)
            if raw["row_source"] == "catalog_steps":
                _steps(raw.get("steps"), manifest_path, tables,
                       has_profiles=bool(manifest.get("generation_profiles")))
    raw_entities = manifest.get("entities", [])
    if not isinstance(raw_entities, list) or len(raw_entities) > MAX_DATASETS:
        _fail("PACKAGE_LIMIT", manifest_path, "entities must contain at most 64 entries")
    for raw in raw_entities:
        if not isinstance(raw, dict) or "schema" not in raw:
            _fail("PACKAGE_SCHEMA", manifest_path, "entity requires a schema")
        schema_path = _relative(root, raw["schema"], manifest_path, schema=True)
        paths.add(schema_path)
        _output_schema(schema_path)
    package = DatasetPackage(root, manifest["id"], manifest["package_version"],
                             manifest, catalog, tables, frozenset(paths), values, relations)
    from tabalyst.generate_selection import validate_selection_package

    validate_selection_package(package)
    return package

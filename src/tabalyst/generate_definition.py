# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Strict, located YAML definition loading, adapted from the prototype loader."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from tabalyst.errors import ConfigurationError, InputError

MAX_BYTES = 1_048_576
MAX_DATASETS = 64
MAX_COLUMNS = 256
MAX_ROWS = 10_000_000
MAX_PROFILES = 32
SAFE_ID = re.compile(r"[a-z][a-z0-9]*(?:[-_][a-z0-9]+)*\Z")
COLUMN_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")
KINDS = {
    "constant", "sequence", "choice", "integer", "decimal", "boolean",
    "date", "datetime", "text", "reference", "relative_date", "conditional", "common",
    "insurance",
}
TYPES = {"string", "integer", "decimal", "boolean", "date", "datetime"}
MAX_NUMBER = 1_000_000_000_000
GENERATOR_KEYS = {
    "constant": {"value"},
    "sequence": {"prefix", "width", "start"},
    "choice": {"weights"},
    "integer": {"min", "max"},
    "decimal": {"min", "max", "scale"},
    "boolean": set(),
    "date": {"min", "max", "format"},
    "datetime": {"min", "max", "format"},
    "text": {"length"},
    "reference": {"entity", "field"},
    "relative_date": {"from", "offset", "format"},
    "conditional": {"from", "cases", "default"},
    "common": {"provider", "field", "group", "profile", "province", "first", "last",
               "unit_probability", "direction_probability", "language"},
    "insurance": {"field", "group"},
}


class LocatedDict(dict):
    line: int
    column: int


class LocatedList(list):
    line: int
    column: int


class StrictLoader(yaml.SafeLoader):
    """SafeLoader with duplicate-key and alias rejection and source positions."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        if self.check_event(yaml.AliasEvent):
            event = self.peek_event()
            raise ConfigurationError(
                f"YAML aliases are unsupported at line {event.start_mark.line + 1}"
            )
        return super().compose_node(parent, index)

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> LocatedDict:
        result = LocatedDict()
        result.line = node.start_mark.line + 1
        result.column = node.start_mark.column + 1
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str):
                raise ConfigurationError(
                    f"Mapping key must be text at line {key_node.start_mark.line + 1}"
                )
            if key in result:
                raise ConfigurationError(
                    f"Duplicate key {key!r} at line {key_node.start_mark.line + 1}"
                )
            result[key] = self.construct_object(value_node, deep=deep)
        return result

    def construct_sequence(self, node: yaml.SequenceNode, deep: bool = False) -> LocatedList:
        result = LocatedList()
        result.line = node.start_mark.line + 1
        result.column = node.start_mark.column + 1
        result.extend(self.construct_object(child, deep=deep) for child in node.value)
        return result


# YAML timestamps become strings; the definition validates ISO dates itself.
StrictLoader.yaml_implicit_resolvers = {
    key: [(tag, pattern) for tag, pattern in values if tag != "tag:yaml.org,2002:timestamp"]
    for key, values in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
StrictLoader.add_constructor("tag:yaml.org,2002:map", StrictLoader.construct_mapping)
StrictLoader.add_constructor("tag:yaml.org,2002:seq", StrictLoader.construct_sequence)


@dataclass(frozen=True)
class GenerateDefinition:
    source: Path
    id: str
    defaults: dict[str, Any]
    csv: dict[str, Any]
    schemas: dict[str, Any]
    entities: tuple[dict[str, Any], ...]
    cohorts: tuple[dict[str, Any], ...]
    datasets: tuple[dict[str, Any], ...]
    anomaly_profiles: tuple[dict[str, Any], ...]


def _fail(source: Path, value: Any, message: str) -> None:
    line = getattr(value, "line", 1)
    column = getattr(value, "column", 1)
    raise ConfigurationError(f"{source}:{line}:{column}: {message}")


def _mapping(source: Path, value: Any, where: str, allowed: set[str]) -> dict:
    if not isinstance(value, dict):
        _fail(source, value, f"{where} must be a mapping")
    unknown = set(value) - allowed
    if unknown:
        _fail(source, value, f"{where} has unknown key {min(unknown)!r}")
    return value


def _list(source: Path, value: Any, where: str, maximum: int, nonempty: bool = False) -> list:
    if not isinstance(value, list) or len(value) > maximum or (nonempty and not value):
        _fail(source, value, f"{where} must contain {1 if nonempty else 0} to {maximum} items")
    return value


def _id(source: Path, value: Any, where: str) -> str:
    if not isinstance(value, str) or len(value) > 80 or not SAFE_ID.fullmatch(value):
        _fail(source, value, f"{where} must be a safe lower-case identifier")
    return value


def _positive(source: Path, value: Any, where: str, maximum: int = MAX_ROWS) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        _fail(source, value, f"{where} must be an integer from 1 to {maximum}")
    return value


def _bounded_number(value: Any) -> bool:
    return type(value) in (int, float) and abs(value) <= MAX_NUMBER and math.isfinite(value)


def _date(source: Path, value: Any, where: str) -> str:
    if not isinstance(value, str):
        _fail(source, value, f"{where} must be an ISO date")
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        _fail(source, value, f"{where} must be an ISO date")
    if parsed.isoformat() != value:
        _fail(source, value, f"{where} must be YYYY-MM-DD")
    return value


def _columns(source: Path, value: Any, where: str) -> None:
    columns = _list(source, value, where, MAX_COLUMNS, nonempty=True)
    names: set[str] = set()
    for column in columns:
        item = _mapping(source, column, f"{where} column", {
            "name", "type", "generate", "depends_on", "missing", "cohort",
        })
        name = item.get("name")
        if not isinstance(name, str) or not COLUMN_NAME.fullmatch(name):
            _fail(source, item, f"{where} column name is invalid")
        if name in names:
            _fail(source, item, f"{where} repeats column {name!r}")
        names.add(name)
        if not isinstance(item.get("type"), str) or item["type"] not in TYPES:
            _fail(source, item, f"{where}.{name} has invalid physical type")
        generator = _mapping(source, item.get("generate"), f"{where}.{name}.generate", {
            "kind", "value", "prefix", "width", "start", "weights", "min", "max",
            "scale", "entity", "field", "from", "offset", "format", "length",
            "cases", "default", "provider", "group", "profile", "province",
            "first", "last", "language", "unit_probability", "direction_probability",
        })
        kind = generator.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            _fail(source, generator, f"{where}.{name} has unknown generator kind")
        extra = set(generator) - GENERATOR_KEYS[kind] - {"kind"}
        if extra:
            _fail(source, generator, f"{where}.{name}.{kind} has invalid parameter {min(extra)!r}")
        if kind == "common":
            from tabalyst.generate_references import FIELDS

            provider = generator.get("provider")
            if provider not in FIELDS or generator.get("field") not in FIELDS[provider]:
                _fail(source, generator, "common needs a supported provider and field")
            _id(source, generator.get("group"), "common.group")
            if item["type"] != "string":
                _fail(source, generator, "common fields require string type")
            permitted = {"person": {"profile"}, "address": {"profile", "province", "unit_probability", "direction_probability", "language"},
                         "contact": {"first", "last", "province", "language"}}[provider]
            if set(generator) - {"kind", "provider", "field", "group"} - permitted:
                _fail(source, generator, "common provider has invalid parameters")
            if "profile" in generator and generator["profile"] not in {"fr", "en", "mixed"}:
                _fail(source, generator, "common.profile must be fr, en or mixed")
            if "province" in generator and provider == "address" and (
                not isinstance(generator["province"], str) or
                generator["province"] not in {"QC", "ON", "BC", "AB", "NB", "NS", "MB", "SK", "NL", "PE", "YT", "NT", "NU"}
            ):
                _fail(source, generator, "common address province is unknown")
            for probability in ("unit_probability", "direction_probability"):
                if probability in generator and (type(generator[probability]) not in (int, float)
                    or not math.isfinite(generator[probability]) or not 0 <= generator[probability] <= 1):
                    _fail(source, generator, f"common.{probability} must be from 0 to 1")
            if provider == "contact" and (any(not isinstance(generator.get(key), str) for key in ("first", "last", "province"))):
                _fail(source, generator, "common contact needs first, last and province columns")
        if kind == "insurance":
            from tabalyst.generate_insurance import FIELDS as INSURANCE_FIELDS

            if generator.get("field") not in INSURANCE_FIELDS or generator.get("field") != name:
                _fail(source, generator, "insurance.field must match a supported column name")
            _id(source, generator.get("group"), "insurance.group")
            if item["type"] != "string":
                _fail(source, generator, "insurance fields require string type")
        if kind == "constant" and "value" not in generator:
            _fail(source, generator, "constant.value is required")
        if kind == "constant" and (type(generator["value"]) not in (str, int, float, bool)
                                   or (type(generator["value"]) is float and not math.isfinite(generator["value"]))):
            _fail(source, generator, "constant.value must be a scalar")
        if kind == "choice":
            weights = generator.get("weights")
            if not isinstance(weights, dict) or not weights or len(weights) > 256:
                _fail(source, generator, "choice.weights must be a nonempty mapping")
            if any(not isinstance(k, str) or not k or not _bounded_number(v) or v <= 0
                   for k, v in weights.items()):
                _fail(source, weights, "choice weights must be positive numbers")
        if kind == "sequence":
            if "prefix" in generator and not isinstance(generator["prefix"], str):
                _fail(source, generator, "sequence.prefix must be text")
            if "width" in generator:
                _positive(source, generator["width"], "sequence.width", 100)
            if "start" in generator:
                _positive(source, generator["start"], "sequence.start")
        if kind in {"integer", "decimal"}:
            lower, upper = generator.get("min"), generator.get("max")
            if not _bounded_number(lower) or not _bounded_number(upper) or lower > upper:
                _fail(source, generator, f"{kind} requires min <= max")
            if kind == "integer" and (type(lower) is not int or type(upper) is not int):
                _fail(source, generator, "integer bounds must be integers")
            if kind == "decimal":
                scale = generator.get("scale", 2)
                if type(scale) is not int or not 0 <= scale <= 9:
                    _fail(source, generator, "decimal.scale must be from 0 to 9")
                factor = 10 ** scale
                left = (Decimal(str(lower)) * factor).to_integral_value(rounding="ROUND_CEILING")
                right = (Decimal(str(upper)) * factor).to_integral_value(rounding="ROUND_FLOOR")
                if left > right:
                    _fail(source, generator, "decimal bounds contain no value at the selected scale")
        if kind in {"date", "datetime"}:
            parser = date.fromisoformat if kind == "date" else datetime.fromisoformat
            for bound in ("min", "max"):
                if bound in generator:
                    try:
                        parsed = parser(generator[bound])
                    except (TypeError, ValueError):
                        _fail(source, generator, f"{kind}.{bound} must be ISO")
                    if parsed.isoformat() != generator[bound] or (kind == "datetime" and parsed.tzinfo is not None):
                        _fail(source, generator, f"{kind}.{bound} must be canonical local ISO")
            if "min" in generator and "max" in generator and generator["min"] > generator["max"]:
                _fail(source, generator, f"{kind} requires min <= max")
            if "format" in generator:
                fmt = generator["format"]
                if (not isinstance(fmt, str) or not 1 <= len(fmt) <= 80
                        or re.search(r"%(?![%YymdHMS])", fmt)):
                    _fail(source, generator, f"{kind}.format has an unsupported directive")
        if kind == "sequence" and item["type"] != "string":
            _fail(source, generator, "sequence requires string type")
        if kind == "text" and item["type"] != "string":
            _fail(source, generator, "text requires string type")
        if kind == "integer" and item["type"] != "integer":
            _fail(source, generator, "integer generator requires integer type")
        if kind == "decimal" and item["type"] != "decimal":
            _fail(source, generator, "decimal generator requires decimal type")
        if kind == "boolean" and item["type"] != "boolean":
            _fail(source, generator, "boolean generator requires boolean type")
        if kind in {"date", "datetime"} and item["type"] != kind:
            _fail(source, generator, f"{kind} generator requires {kind} type")
        if kind == "reference" and (not isinstance(generator.get("entity"), str) or not isinstance(generator.get("field"), str)):
            _fail(source, generator, "reference requires entity and field")
        if kind == "text" and "length" in generator:
            _positive(source, generator["length"], "text.length", 10000)
        if kind == "relative_date" and (
            not isinstance(generator.get("from"), str)
            or type(generator.get("offset")) is not int
            or not -3_650_000 <= generator["offset"] <= 3_650_000
        ):
            _fail(source, generator, "relative_date requires from and integer offset")
        if kind == "relative_date" and item["type"] not in {"date", "datetime"}:
            _fail(source, generator, "relative_date requires date or datetime type")
        if kind == "relative_date" and "format" in generator:
            fmt = generator["format"]
            if (not isinstance(fmt, str) or not 1 <= len(fmt) <= 80
                    or re.search(r"%(?![%YymdHMS])", fmt)):
                _fail(source, generator, "relative_date.format has an unsupported directive")
        if kind == "conditional":
            cases = generator.get("cases")
            if (not isinstance(generator.get("from"), str) or not isinstance(cases, dict)
                    or not cases or len(cases) > 256 or "default" not in generator
                    or any(not isinstance(key, str) or type(val) not in (str, int, float, bool)
                           or (type(val) is float and not math.isfinite(val))
                           for key, val in cases.items())
                    or type(generator["default"]) not in (str, int, float, bool)
                    or (type(generator["default"]) is float
                        and not math.isfinite(generator["default"]))):
                _fail(source, generator, "conditional requires from, scalar cases and default")
        dependencies = _list(source, item.get("depends_on", []), "depends_on", MAX_COLUMNS)
        if any(not isinstance(dep, str) for dep in dependencies) or len(set(dependencies)) != len(dependencies):
            _fail(source, item, "depends_on contains invalid or repeated names")
        if kind == "common" and generator["provider"] == "contact" and (
            not {generator[key] for key in ("first", "last", "province", "language") if key in generator}.issubset(dependencies)
        ):
            _fail(source, generator, "common contact inputs must be declared in depends_on")
        if kind in {"relative_date", "conditional"} and generator["from"] not in dependencies:
            _fail(source, generator, f"{kind}.from must be declared in depends_on")
        missing = item.get("missing")
        if missing is not None and (type(missing) not in (float, int)
                                    or not math.isfinite(missing) or not 0 <= missing <= 1):
            _fail(source, item, "missing must be a probability from 0 to 1")
        if "cohort" in item:
            _id(source, item["cohort"], "column cohort")
    graph = {item["name"]: item.get("depends_on", []) for item in columns}
    done: set[str] = set()
    active: set[str] = set()

    def visit(name: str) -> None:
        if name in active:
            _fail(source, value, f"{where} has a column dependency cycle")
        if name in done:
            return
        active.add(name)
        for dep in graph[name]:
            if dep not in graph:
                _fail(source, value, f"{where} references unknown column {dep!r}")
            visit(dep)
        active.remove(name)
        done.add(name)

    for name in graph:
        visit(name)
    by_name = {item["name"]: item for item in columns}
    groups: dict[str, tuple] = {}
    for item in columns:
        generator = item["generate"]
        if generator["kind"] != "common":
            continue
        signature = tuple(sorted((key, value) for key, value in generator.items() if key != "field"))
        group = generator["group"]
        if group in groups and groups[group] != signature:
            _fail(source, generator, "common group has inconsistent provider parameters")
        groups[group] = signature
        if generator["provider"] == "contact":
            for key in ("first", "last", "province", "language"):
                if key not in generator:
                    continue
                if generator[key] not in by_name or by_name[generator[key]]["type"] != "string":
                    _fail(source, generator, "common contact needs declared string input columns")

    for item in columns:
        generator = item["generate"]
        if generator["kind"] == "relative_date":
            parent = by_name[generator["from"]]
            if parent["type"] != item["type"]:
                _fail(source, generator, "relative_date source must match date or datetime type")
            if "format" in parent["generate"]:
                _fail(source, generator, "relative_date source must use ISO format")


def load_generate_definition(path: str | Path) -> GenerateDefinition:
    """Load one bounded YAML document and validate its v1 structure."""
    source = Path(path).resolve()
    try:
        exists = source.is_file()
        size = source.stat().st_size if exists else 0
    except OSError as exc:
        raise InputError(f"Cannot inspect definition file {source}: {exc}") from exc
    if not exists:
        raise InputError(f"Definition file does not exist: {source}")
    if size > MAX_BYTES:
        raise ConfigurationError(f"{source}: definition exceeds {MAX_BYTES} bytes")
    try:
        with source.open("r", encoding="utf-8") as stream:
            root = yaml.load(stream, Loader=StrictLoader)
    except (yaml.YAMLError, UnicodeError) as exc:
        mark = getattr(exc, "problem_mark", None)
        position = f":{mark.line + 1}:{mark.column + 1}" if mark else ""
        raise ConfigurationError(f"{source}{position}: invalid YAML: {exc}") from exc
    except ConfigurationError as exc:
        raise ConfigurationError(f"{source}: {exc}") from exc
    except OSError as exc:
        raise InputError(f"Cannot read definition file {source}: {exc}") from exc
    root = _mapping(source, root, "definition", {
        "definition_version", "id", "defaults", "csv", "schemas", "entities",
        "cohorts", "datasets", "anomaly_profiles",
    })
    if type(root.get("definition_version")) is not int or root["definition_version"] != 1:
        _fail(source, root, "definition_version must be 1")
    identifier = _id(source, root.get("id"), "definition id")
    defaults = _mapping(source, root.get("defaults", {}), "defaults", {"seed", "as_of_date"})
    if "seed" in defaults and type(defaults["seed"]) is not int:
        _fail(source, defaults, "defaults.seed must be an integer")
    if "as_of_date" in defaults:
        _date(source, defaults["as_of_date"], "defaults.as_of_date")
    csv_settings = _mapping(source, root.get("csv", {}), "csv", {"delimiter"})
    if "delimiter" in csv_settings and (not isinstance(csv_settings["delimiter"], str) or len(csv_settings["delimiter"]) != 1 or csv_settings["delimiter"] in "\r\n\x00"):
        _fail(source, csv_settings, "csv.delimiter must be one safe character")
    raw_schemas = root.get("schemas", {})
    schemas = _mapping(source, raw_schemas, "schemas", set(raw_schemas) if isinstance(raw_schemas, dict) else set())
    if len(schemas) > MAX_DATASETS:
        _fail(source, schemas, "too many schemas")
    for name, schema in schemas.items():
        _id(source, name, "schema id")
        _mapping(source, schema, f"schema {name}", {"columns"})
        _columns(source, schema.get("columns"), f"schemas.{name}.columns")
    entities = _list(source, root.get("entities", []), "entities", MAX_DATASETS)
    cohorts = _list(source, root.get("cohorts", []), "cohorts", MAX_DATASETS)
    for collection, label, allowed in (
        (entities, "entity", {"id", "count", "generator", "columns"}),
        (cohorts, "cohort", {"id", "weight", "values", "formats"}),
    ):
        seen: set[str] = set()
        for item in collection:
            _mapping(source, item, label, allowed)
            name = _id(source, item.get("id"), f"{label} id")
            if name in seen:
                _fail(source, item, f"duplicate {label} id {name!r}")
            seen.add(name)
            if label == "entity":
                _positive(source, item.get("count"), "entity.count", 100_000)
                if not isinstance(item.get("generator"), str) or item["generator"] not in {"company", "person"}:
                    _fail(source, item, "entity.generator must be company or person")
                if "columns" not in item:
                    _fail(source, item, "entity.columns is required")
                _columns(source, item["columns"], f"entities.{name}.columns")
                if item["count"] * len(item["columns"]) > 1_000_000:
                    _fail(source, item, "entity pool exceeds 1000000 cells")
                if any(c["generate"]["kind"] == "reference" for c in item["columns"]):
                    _fail(source, item, "entity columns cannot reference another entity")
                if any(c["generate"]["kind"] == "insurance" for c in item["columns"]):
                    _fail(source, item, "insurance columns require a branch dataset")
            elif not _bounded_number(item.get("weight")) or item["weight"] <= 0:
                _fail(source, item, "cohort.weight must be positive")
            else:
                for key in ("values", "formats"):
                    if key in item and not isinstance(item[key], dict):
                        _fail(source, item, f"cohort.{key} must be a mapping")
                for column, value in item.get("values", {}).items():
                    if not isinstance(column, str) or not COLUMN_NAME.fullmatch(column) or not isinstance(value, str):
                        _fail(source, item, "cohort.values must map column names to text")
                for column, mapping in item.get("formats", {}).items():
                    if (not isinstance(column, str) or not COLUMN_NAME.fullmatch(column)
                            or not isinstance(mapping, dict) or not mapping or len(mapping) > 256
                            or any(not isinstance(a, str) or not isinstance(b, str)
                                   for a, b in mapping.items())):
                        _fail(source, item, "cohort.formats must map columns to text replacements")
    datasets = _list(source, root.get("datasets"), "datasets", MAX_DATASETS, nonempty=True)
    known: dict[str, dict] = {}
    for item in datasets:
        _mapping(source, item, "dataset", {"id", "rows", "columns", "schema", "combine", "source", "cohort"})
        name = _id(source, item.get("id"), "dataset id")
        if name in known:
            _fail(source, item, f"duplicate dataset id {name!r}")
        if "source" in item:
            _id(source, item["source"], "dataset source")
        if "cohort" in item:
            _id(source, item["cohort"], "dataset cohort")
        modes = sum(key in item for key in ("columns", "schema", "combine"))
        if modes != 1:
            _fail(source, item, f"dataset {name} needs exactly one of columns, schema, combine")
        if "combine" in item:
            if "rows" in item:
                _fail(source, item, "combined dataset cannot declare rows")
            combine = _mapping(source, item["combine"], "combine", {"inputs", "source_column"})
            inputs = _list(source, combine.get("inputs"), "combine.inputs", MAX_DATASETS, nonempty=True)
            if any(not isinstance(x, str) for x in inputs) or len(inputs) != len(set(inputs)) or any(x not in known or "combine" in known[x] for x in inputs):
                _fail(source, combine, "combine.inputs must be distinct preceding generated datasets")
            if "source_column" in combine and (not isinstance(combine["source_column"], str) or not COLUMN_NAME.fullmatch(combine["source_column"])):
                _fail(source, combine, "combine.source_column is invalid")
            headers = [tuple((c["name"], c["type"]) for c in (known[x].get("columns") or schemas[known[x]["schema"]]["columns"])) for x in inputs]
            if len(set(headers)) != 1 or combine.get("source_column") in {field for field, _ in headers[0]}:
                _fail(source, combine, "combine inputs have incompatible headers")
        else:
            _positive(source, item.get("rows"), f"dataset {name}.rows")
            if "columns" in item:
                _columns(source, item["columns"], f"datasets.{name}.columns")
            elif not isinstance(item["schema"], str) or item["schema"] not in schemas:
                _fail(source, item, f"dataset {name} references unknown schema")
            columns = item.get("columns") or schemas[item["schema"]]["columns"]
            if any(c["generate"]["kind"] == "insurance" for c in columns) and item.get("source") not in {"principal", "ontario", "quebec"}:
                _fail(source, item, "insurance columns require a supported dataset source")
        known[name] = item
    pools = {entity["id"]: {column["name"]: column for column in entity["columns"]}
             for entity in entities}
    cohort_ids = {cohort["id"] for cohort in cohorts}
    all_columns = [entity["columns"] for entity in entities]
    all_columns.extend(item.get("columns") or schemas[item["schema"]]["columns"]
                       for item in datasets if "combine" not in item)
    string_columns = {column["name"] for columns in all_columns for column in columns
                      if column["type"] == "string"}
    reference_columns = {column["name"] for columns in all_columns for column in columns
                         if column["generate"]["kind"] == "reference"}
    for cohort in cohorts:
        unknown = (set(cohort.get("values", {})) | set(cohort.get("formats", {}))) - string_columns
        if unknown:
            _fail(source, cohort, f"cohort references unknown string column {min(unknown)!r}")
        if (set(cohort.get("values", {})) | set(cohort.get("formats", {}))) & reference_columns:
            _fail(source, cohort, "cohort cannot replace entity reference values")
    for item in (*entities, *datasets):
        if "cohort" in item and item["cohort"] not in cohort_ids:
            _fail(source, item, "dataset cohort is not declared")
    for columns in all_columns:
        for column in columns:
            if "cohort" in column and column["cohort"] not in cohort_ids:
                _fail(source, column, "column cohort is not declared")
    for schema_columns in ([item.get("columns") or schemas[item["schema"]]["columns"]
                            for item in datasets if "combine" not in item]):
        for column in schema_columns:
            generator = column["generate"]
            if generator["kind"] != "reference":
                continue
            pool = pools.get(generator["entity"])
            field = pool.get(generator["field"]) if pool else None
            if field is None or field["type"] != column["type"]:
                _fail(source, generator, "reference needs a declared entity field of matching type")
    profiles = _list(source, root.get("anomaly_profiles", []), "anomaly_profiles", MAX_PROFILES)
    seen_profiles: set[str] = set()
    for item in profiles:
        _mapping(source, item, "anomaly profile", {"id", "targets", "operations"})
        name = _id(source, item.get("id"), "profile id")
        if name in seen_profiles:
            _fail(source, item, f"duplicate profile id {name!r}")
        seen_profiles.add(name)
        targets = _list(source, item.get("targets"), "profile.targets", MAX_DATASETS, nonempty=True)
        if any(not isinstance(target, str) for target in targets) or len(set(targets)) != len(targets) or any(target not in known for target in targets):
            _fail(source, item, "profile.targets must be distinct declared datasets")
        operations = _list(source, item.get("operations", []), "profile.operations", 256)
        for operation in operations:
            _mapping(source, operation, "profile operation", {"kind", "column", "rate", "value", "when"})
            if not isinstance(operation.get("kind"), str) or operation["kind"] not in {"set_missing", "replace", "duplicate", "format", "swap"}:
                _fail(source, operation, "unknown anomaly operation kind")
            column = operation.get("column")
            if not isinstance(column, str) or not COLUMN_NAME.fullmatch(column):
                _fail(source, operation, "operation.column must name a column")
            rate = operation.get("rate")
            if type(rate) not in (int, float) or not math.isfinite(rate) or not 0 <= rate <= 1:
                _fail(source, operation, "operation.rate must be from 0 to 1")
            value = operation.get("value")
            if operation["kind"] in {"replace", "format", "swap"} and not isinstance(value, str):
                _fail(source, operation, "operation.value must be text")
            if operation["kind"] in {"set_missing", "duplicate"} and "value" in operation:
                _fail(source, operation, "operation.value is unused for this kind")
            if operation["kind"] == "format" and value not in {"upper", "lower", "strip", "date_slash", "phone_spaces"}:
                _fail(source, operation, "unknown format mutation")
            if "when" in operation and (not isinstance(operation["when"], dict)
                or len(operation["when"]) != 1 or any(not isinstance(k, str) or not isinstance(v, str)
                                                 for k, v in operation["when"].items())):
                _fail(source, operation, "operation.when must map one column to text")
            for target in targets:
                dataset = known[target]
                if "combine" in dataset:
                    first = known[dataset["combine"]["inputs"][0]]
                    columns = first.get("columns") or schemas[first["schema"]]["columns"]
                    names = {c["name"] for c in columns}
                    if dataset["combine"].get("source_column"):
                        names.add(dataset["combine"]["source_column"])
                else:
                    columns = dataset.get("columns") or schemas[dataset["schema"]]["columns"]
                    names = {c["name"] for c in columns}
                required = {column}
                if operation["kind"] == "swap":
                    required.add(value)
                    if value == column:
                        _fail(source, operation, "swap requires two different columns")
                required.update(operation.get("when", {}))
                if not required <= names:
                    _fail(source, operation, f"operation references unknown column in {target}")
    return GenerateDefinition(
        source, identifier, defaults, csv_settings, schemas, tuple(entities),
        tuple(cohorts), tuple(datasets), tuple(profiles),
    )

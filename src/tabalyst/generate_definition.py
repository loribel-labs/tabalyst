# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Strict, located YAML definition loading, adapted from the prototype loader."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
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
    "date", "datetime", "text", "reference", "relative_date",
}
TYPES = {"string", "integer", "decimal", "boolean", "date", "datetime"}
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
        })
        kind = generator.get("kind")
        if not isinstance(kind, str) or kind not in KINDS:
            _fail(source, generator, f"{where}.{name} has unknown generator kind")
        extra = set(generator) - GENERATOR_KEYS[kind] - {"kind"}
        if extra:
            _fail(source, generator, f"{where}.{name}.{kind} has invalid parameter {min(extra)!r}")
        if kind == "constant" and "value" not in generator:
            _fail(source, generator, "constant.value is required")
        if kind == "constant" and type(generator["value"]) not in (str, int, float, bool):
            _fail(source, generator, "constant.value must be a scalar")
        if kind == "choice":
            weights = generator.get("weights")
            if not isinstance(weights, dict) or not weights or len(weights) > 256:
                _fail(source, generator, "choice.weights must be a nonempty mapping")
            if any(not isinstance(k, str) or type(v) not in (int, float) or v <= 0 for k, v in weights.items()):
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
            if type(lower) not in (int, float) or type(upper) not in (int, float) or lower > upper:
                _fail(source, generator, f"{kind} requires min <= max")
        if kind == "reference" and (not isinstance(generator.get("entity"), str) or not isinstance(generator.get("field"), str)):
            _fail(source, generator, "reference requires entity and field")
        if kind == "text" and "length" in generator:
            _positive(source, generator["length"], "text.length", 10000)
        if kind == "relative_date" and (
            not isinstance(generator.get("from"), str)
            or type(generator.get("offset")) is not int
        ):
            _fail(source, generator, "relative_date requires from and integer offset")
        dependencies = _list(source, item.get("depends_on", []), "depends_on", MAX_COLUMNS)
        if any(not isinstance(dep, str) for dep in dependencies) or len(set(dependencies)) != len(dependencies):
            _fail(source, item, "depends_on contains invalid or repeated names")
        missing = item.get("missing")
        if missing is not None and (type(missing) not in (float, int) or not 0 <= missing <= 1):
            _fail(source, item, "missing must be a probability from 0 to 1")
        if "cohort" in item and not isinstance(item["cohort"], str):
            _fail(source, item, "column cohort must be text")
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
                _positive(source, item.get("count"), "entity.count")
                if not isinstance(item.get("generator"), str) or item["generator"] not in {"company", "person"}:
                    _fail(source, item, "entity.generator must be company or person")
                if "columns" in item:
                    _columns(source, item["columns"], f"entities.{name}.columns")
            elif type(item.get("weight")) not in (int, float) or item["weight"] <= 0:
                _fail(source, item, "cohort.weight must be positive")
            else:
                for key in ("values", "formats"):
                    if key in item and not isinstance(item[key], dict):
                        _fail(source, item, f"cohort.{key} must be a mapping")
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
            if len(set(headers)) != 1 or combine.get("source_column") in headers[0]:
                _fail(source, combine, "combine inputs have incompatible headers")
        else:
            _positive(source, item.get("rows"), f"dataset {name}.rows")
            if "columns" in item:
                _columns(source, item["columns"], f"datasets.{name}.columns")
            elif not isinstance(item["schema"], str) or item["schema"] not in schemas:
                _fail(source, item, f"dataset {name} references unknown schema")
        known[name] = item
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
            if "column" in operation and not isinstance(operation["column"], str):
                _fail(source, operation, "operation.column must be text")
            rate = operation.get("rate")
            if type(rate) not in (int, float) or not 0 <= rate <= 1:
                _fail(source, operation, "operation.rate must be from 0 to 1")
    return GenerateDefinition(
        source, identifier, defaults, csv_settings, schemas, tuple(entities),
        tuple(cohorts), tuple(datasets), tuple(profiles),
    )

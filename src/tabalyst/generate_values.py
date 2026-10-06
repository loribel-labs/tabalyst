# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Streaming elementary values for Tabalyst Generate."""

from __future__ import annotations

import hashlib
import random
import string
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from tabalyst.errors import ConfigurationError
from tabalyst.generate_insurance import InsuranceProvider
from tabalyst.generate_references import CommonProvider, CommonReferences


def _stream(seed: int, dataset: str, column: str, operation: str) -> random.Random:
    identity = f"{seed}\0{dataset}\0{column}\0{operation}".encode()
    return random.Random(int.from_bytes(hashlib.sha256(identity).digest(), "big"))


def _date_bound(value: Any, fallback: str, *, timestamp: bool) -> date | datetime:
    text = fallback if value is None else value
    try:
        parsed = datetime.fromisoformat(text) if timestamp else date.fromisoformat(text)
    except (TypeError, ValueError) as exc:
        label = "datetime" if timestamp else "date"
        raise ConfigurationError(f"{label} bounds must be ISO values") from exc
    if parsed.isoformat() != text or (timestamp and parsed.tzinfo is not None):
        raise ConfigurationError("Date bounds must be canonical local ISO values")
    return parsed


def _value(kind: str, config: dict, index: int, rng: random.Random,
           as_of_date: str) -> str:
    if kind == "constant":
        value = config["value"]
        return str(value).lower() if type(value) is bool else str(value)
    if kind == "sequence":
        number = config.get("start", 1) + index
        return f"{config.get('prefix', '')}{number:0{config.get('width', 1)}d}"
    if kind == "choice":
        weights = config["weights"]
        return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]
    if kind == "integer":
        return str(rng.randint(config["min"], config["max"]))
    if kind == "decimal":
        scale = config.get("scale", 2)
        factor = 10 ** scale
        lower = int((Decimal(str(config["min"])) * factor).to_integral_value(rounding="ROUND_CEILING"))
        upper = int((Decimal(str(config["max"])) * factor).to_integral_value(rounding="ROUND_FLOOR"))
        return f"{Decimal(rng.randint(lower, upper)) / factor:.{scale}f}"
    if kind == "boolean":
        return "true" if rng.getrandbits(1) else "false"
    if kind in {"date", "datetime"}:
        timestamp = kind == "datetime"
        default_min = "1970-01-01T00:00:00" if timestamp else "1970-01-01"
        default_max = f"{as_of_date}T23:59:59" if timestamp else as_of_date
        lower = _date_bound(config.get("min"), default_min, timestamp=timestamp)
        upper = _date_bound(config.get("max"), default_max, timestamp=timestamp)
        if upper < lower:
            raise ConfigurationError(f"{kind} requires min <= max")
        if timestamp:
            value = lower + timedelta(seconds=rng.randint(0, int((upper - lower).total_seconds())))
        else:
            value = lower + timedelta(days=rng.randint(0, (upper - lower).days))
        return value.strftime(config["format"]) if "format" in config else value.isoformat()
    if kind == "text":
        alphabet = string.ascii_letters + string.digits
        return "".join(rng.choices(alphabet, k=config.get("length", 12)))
    raise ConfigurationError(f"Generator kind {kind!r} requires a later Generate lot")


def _ordered_columns(columns: list[dict]) -> list[dict]:
    """Evaluate dependencies first without changing the declared CSV order."""
    by_name = {column["name"]: column for column in columns}
    ordered: list[dict] = []
    visited: set[str] = set()

    def visit(name: str) -> None:
        if name in visited:
            return
        for dependency in by_name[name].get("depends_on", []):
            visit(dependency)
        visited.add(name)
        ordered.append(by_name[name])

    for column in columns:
        visit(column["name"])
    return ordered


def generate_rows(dataset: str, columns: list[dict], count: int, seed: int,
                  as_of_date: str, pools: dict[str, list[dict[str, str]]] | None = None,
                  references: CommonReferences | None = None,
                  cohorts: tuple[dict, ...] = (), fixed_cohort: str | None = None,
                  source: str | None = None,
                  insurance_provider: InsuranceProvider | None = None):
    """Yield rows with independent value and missingness streams per column."""
    pools = pools or {}
    ordered = _ordered_columns(columns)
    streams = {
        column["name"]: (
            _stream(seed, dataset, column["name"], "value"),
            _stream(seed, dataset, column["name"], "missing"),
        ) for column in columns
    }
    common = CommonProvider(references or CommonReferences()) if any(
        c["generate"]["kind"] == "common" for c in columns
    ) else None
    insurance = insurance_provider or (InsuranceProvider(references or CommonReferences()) if any(
        c["generate"]["kind"] == "insurance" for c in columns
    ) else None)
    group_streams = {
        c["generate"]["group"]: _stream(seed, dataset, c["generate"]["group"], "common")
        for c in columns if c["generate"]["kind"] == "common"
    }
    insurance_streams = {
        c["generate"]["group"]: _stream(seed, dataset, c["generate"]["group"], "insurance")
        for c in columns if c["generate"]["kind"] == "insurance"
    }
    selections: dict[str, tuple[list[int], random.Random]] = {}
    cohort_rng = _stream(seed, dataset, "cohort", "selection")
    cohort_names = [cohort["id"] for cohort in cohorts]
    cohort_weights = [cohort["weight"] for cohort in cohorts]
    cohort_by_id = {cohort["id"]: cohort for cohort in cohorts}
    for column in columns:
        generator = column["generate"]
        if generator["kind"] == "reference" and generator["entity"] not in selections:
            entity = generator["entity"]
            if entity not in pools or not pools[entity]:
                raise ConfigurationError(f"Entity {entity!r} has no generated rows")
            rng = _stream(seed, dataset, entity, "entity_selection")
            order = list(range(len(pools[entity])))
            rng.shuffle(order)
            selections[entity] = (order, rng)
    for index in range(count):
        row: dict[str, str] = {}
        cohort_id = fixed_cohort or (cohort_rng.choices(
            cohort_names, weights=cohort_weights, k=1,
        )[0] if cohorts else None)
        cohort = cohort_by_id.get(cohort_id, {})
        group_values: dict[str, dict[str, str]] = {}
        for entity, (order, rng) in selections.items():
            if index and index % len(order) == 0:
                rng.shuffle(order)
        for column in ordered:
            name = column["name"]
            value_rng, missing_rng = streams[name]
            generator = column["generate"]
            kind = generator["kind"]
            if kind == "common":
                group = generator["group"]
                if group not in group_values:
                    provider = generator["provider"]
                    method = getattr(common, provider)
                    args = (generator, row, group_streams[group]) if provider == "contact" else (
                        generator, group_streams[group]
                    )
                    group_values[group] = method(*args)
                value = group_values[group][generator["field"]]
            elif kind == "insurance":
                group = generator["group"]
                if group not in group_values:
                    group_values[group] = insurance.row(
                        source, index + 1, insurance_streams[group], as_of_date,
                    )
                value = group_values[group][generator["field"]]
            elif kind == "reference":
                order, _ = selections[generator["entity"]]
                value = pools[generator["entity"]][order[index % len(order)]][generator["field"]]
            elif kind == "conditional":
                source = row[generator["from"]]
                choice = generator["cases"].get(source, generator["default"])
                value = str(choice).lower() if type(choice) is bool else str(choice)
            elif kind == "relative_date":
                source = row[generator["from"]]
                if source:
                    try:
                        parsed = datetime.fromisoformat(source) if column["type"] == "datetime" else date.fromisoformat(source)
                        shifted = parsed + timedelta(days=generator["offset"])
                    except (TypeError, ValueError, OverflowError) as exc:
                        raise ConfigurationError(f"Invalid relative_date source for {name!r}") from exc
                    value = shifted.strftime(generator["format"]) if "format" in generator else shifted.isoformat()
                else:
                    value = ""
            else:
                value = _value(kind, generator, index, value_rng, as_of_date)
            if value and name in cohort.get("values", {}):
                value = cohort["values"][name]
            if value and name in cohort.get("formats", {}):
                value = cohort["formats"][name].get(value, value)
            row[name] = "" if (column.get("cohort", cohort_id) != cohort_id
                               or missing_rng.random() < column.get("missing", 0)) else value
        yield row

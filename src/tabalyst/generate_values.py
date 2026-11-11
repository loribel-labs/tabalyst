# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Streaming elementary values for Tabalyst Generate."""

from __future__ import annotations

import hashlib
import math
import random
import string
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from tabalyst.errors import ConfigurationError
from tabalyst.generate_definition import MONTHS
from tabalyst.generate_draws import truncated_lognormal
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
    if parsed.isoformat() != text or (isinstance(parsed, datetime) and parsed.tzinfo is not None):
        raise ConfigurationError("Date bounds must be canonical local ISO values")
    return parsed


def _lognormal(config: dict, rng: random.Random, factor: int, lower: int, upper: int) -> int:
    """Draw a log-normal value truncated to [min, max], in units of the scale."""
    drawn = truncated_lognormal(rng, config["median"], config["sigma"], lower / factor, upper / factor)
    return min(max(round(drawn * factor), lower), upper)


def _offset(rng: random.Random, span: int, growth: float | None, units_per_day: int) -> int:
    """Pick a step from 0 to `span`, uniformly or growing by `growth` a year.

    With growth the density is exponential, so a year holds (1 + growth) times the
    rows of the year before; its inverse CDF keeps one random number per value.
    """
    if growth is None:
        return rng.randint(0, span)
    if span == 0:
        return 0
    rate = math.log1p(growth) / (365.25 * units_per_day)
    step = math.log1p(rng.random() * math.expm1(rate * span)) / rate
    return min(int(step), span)


def _weekday(picked: date, lower: date, upper: date) -> date:
    """Move a Saturday to Friday and a Sunday to Monday, or the other way at a bound."""
    weekday = picked.weekday()
    if weekday < 5:
        return picked
    for shift in ((-1, 2) if weekday == 5 else (1, -2)):
        moved = picked + timedelta(days=shift)
        if lower <= moved <= upper:
            return moved
    return picked


def _after(generator: dict, source: str, as_of_date: str, timestamp: bool) -> dict:
    """Raise the lower bound of a date to the source date; past `max`, the source wins.

    ISO dates and canonical local datetimes compare as text, as the definition checks.
    """
    lower = generator.get("min", "1970-01-01T00:00:00" if timestamp else "1970-01-01")
    upper = generator.get("max", f"{as_of_date}T23:59:59" if timestamp else as_of_date)
    lower = max(lower, source)
    return {**generator, "min": lower, "max": max(upper, lower)}


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
        if config.get("distribution", "uniform") == "lognormal":
            picked = _lognormal(config, rng, factor, lower, upper)
        else:
            picked = rng.randint(lower, upper)
        return f"{Decimal(picked) / factor:.{scale}f}"
    if kind == "boolean":
        if "true_share" in config:
            return "true" if rng.random() < config["true_share"] else "false"
        return "true" if rng.getrandbits(1) else "false"
    if kind in {"date", "datetime"}:
        timestamp = kind == "datetime"
        default_min = "1970-01-01T00:00:00" if timestamp else "1970-01-01"
        default_max = f"{as_of_date}T23:59:59" if timestamp else as_of_date
        date_lower = _date_bound(config.get("min"), default_min, timestamp=timestamp)
        date_upper = _date_bound(config.get("max"), default_max, timestamp=timestamp)
        if date_upper < date_lower:
            raise ConfigurationError(f"{kind} requires min <= max")
        picked_date: date
        if timestamp:
            assert isinstance(date_lower, datetime) and isinstance(date_upper, datetime)
            span = int((date_upper - date_lower).total_seconds())
            picked_date = date_lower + timedelta(seconds=_offset(rng, span, config.get("growth"), 86400))
        else:
            span = (date_upper - date_lower).days
            picked_date = date_lower + timedelta(days=_offset(rng, span, config.get("growth"), 1))
        if config.get("weekdays"):
            picked_date = _weekday(picked_date, date_lower, date_upper)
        return picked_date.strftime(config["format"]) if "format" in config else picked_date.isoformat()
    if kind == "text":
        alphabet = string.ascii_letters + string.digits
        return "".join(rng.choices(alphabet, k=config.get("length", 12)))
    raise ConfigurationError(f"Generator kind {kind!r} requires a later Generate lot")


def _scaled(value: str, factor: float, scale: int) -> str:
    """Multiply a decimal text by a factor, rounded half to even at the scale."""
    product = (Decimal(value) * Decimal(str(factor))).quantize(Decimal(1).scaleb(-scale))
    return f"{product:.{scale}f}"


def _by_value(value: str, generator: dict, source: str) -> str:
    """Scale a drawn decimal by the factor of another column's value, if it has one."""
    factor = generator["by_value"]["factors"].get(source)
    return value if factor is None or not value else _scaled(value, factor, generator.get("scale", 2))


def _by_month(value: str, generator: dict, source: str) -> str:
    """Scale a drawn decimal by the factor of its source date's month.

    An empty source date, or a month without a factor, keeps the drawn value. The
    product is rounded half to even at the generator's scale, so it may pass `max`.
    """
    if not source:
        return value
    try:
        month = date.fromisoformat(source[:10]).month
    except ValueError as exc:
        raise ConfigurationError(f"Invalid by_month source date {source!r}") from exc
    factor = generator["by_month"]["factors"].get(MONTHS[month - 1])
    if factor is None:
        return value
    return _scaled(value, factor, generator.get("scale", 2))


def _round_to(value: str, generator: dict, rng: random.Random) -> str:
    """Round a decimal half to even to `round_to.step` on a `round_to.share` of the rows.

    One random number is drawn for every value, rounded or not, so the choice of a
    row never depends on the others. A value under half a step becomes zero.
    """
    round_to = generator["round_to"]
    if rng.random() >= round_to["share"]:
        return value
    step = Decimal(str(round_to["step"]))
    rounded = (Decimal(value) / step).to_integral_value() * step
    return f"{rounded:.{generator.get('scale', 2)}f}"


def _missing_rate(column: dict, row: dict[str, str]) -> float:
    """The missing rate of a column for this row: by the value of `missing_by.from`, else `missing`."""
    base = column.get("missing", 0)
    rule = column.get("missing_by")
    if rule is None:
        return base
    source = row[rule["from"]]
    if not source:
        return rule.get("empty", base)
    return rule.get("cases", {}).get(source, base)


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
    # A stream of its own, so that adding a rounding never shifts the values drawn.
    rounding = {
        column["name"]: _stream(seed, dataset, column["name"], "round")
        for column in columns if "round_to" in column["generate"]
    }
    # Each case merged once with its generator; a value without a case keeps the declared one.
    case_generators = {
        column["name"]: {
            case: column["generate"] | override
            for case, override in column["generate"]["by_case"]["cases"].items()
        }
        for column in columns if "by_case" in column["generate"]
    }
    common = CommonProvider(references or CommonReferences()) if any(
        c["generate"]["kind"] == "common" for c in columns
    ) else None
    insurance = insurance_provider
    if insurance is None and any(c["generate"]["kind"] == "insurance" for c in columns):
        raise ConfigurationError("Insurance generation requires a validated package provider")
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
            if name in case_generators:
                generator = case_generators[name].get(row[generator["by_case"]["from"]], generator)
            if "after" in generator and row[generator["after"]]:
                generator = _after(generator, row[generator["after"]], as_of_date, kind == "datetime")
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
                assert insurance is not None
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
                if kind == "decimal" and "by_month" in generator:
                    value = _by_month(value, generator, row[generator["by_month"]["from"]])
                if kind == "decimal" and "by_value" in generator:
                    value = _by_value(value, generator, row[generator["by_value"]["from"]])
                if kind == "decimal" and "round_to" in generator:
                    value = _round_to(value, generator, rounding[name])
            if value and name in cohort.get("values", {}):
                value = cohort["values"][name]
            if value and name in cohort.get("formats", {}):
                value = cohort["formats"][name].get(value, value)
            row[name] = "" if (column.get("cohort", cohort_id) != cohort_id
                               or missing_rng.random() < _missing_rate(column, row)) else value
        yield row

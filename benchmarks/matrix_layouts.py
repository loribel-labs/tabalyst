# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Deterministic CSV layouts of the final benchmark matrix (design 17.2, lot 11).

The layouts that ``generate_data.py`` already writes (``standard``, ``worst-width``,
``long-text``, ``many-lengths``) cover the realistic, wide and text cases. These
cover the rest of the matrix of the specification: low and high cardinality, the
transition around K, short identifiers, repeated rows, many columns and
normalization with and without effect. Every value is fictional, and the same
seed gives the same bytes.

    python benchmarks/matrix_layouts.py low-cardinality 1000000 OUT.csv
    python benchmarks/matrix_layouts.py transition 200000 OUT.csv --distinct 9999
"""

import argparse
import csv
import random
import unicodedata
from datetime import date, timedelta
from pathlib import Path

from generate_data import FIELDS, _record

LAYOUTS = (
    "low-cardinality",
    "high-cardinality",
    "transition",
    "short-ids",
    "repeated",
    "wide",
    "normalization-clean",
    "normalization-effect",
)

LOW_DOMAINS = (10, 12, 20, 25, 30, 40, 50, 60, 80, 100)
_HEX = "0123456789abcdef"
_ALNUM = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _text(rng: random.Random, length: int, alphabet: str = _HEX) -> str:
    return "".join(rng.choices(alphabet, k=length))


def _low_cardinality(rng: random.Random, index: int) -> dict[str, object]:
    """Ten columns of 10 to 100 values, drawn so that a few dominate."""
    record: dict[str, object] = {}
    for number, size in enumerate(LOW_DOMAINS, start=1):
        pick = min(int(rng.expovariate(3.0 / size)), size - 1)
        record[f"c{number:02d}"] = f"v{number:02d}-{pick:03d}"
    record["n"] = rng.randint(1, 50)
    return record


def _high_cardinality(rng: random.Random, index: int) -> dict[str, object]:
    """Almost one different value per row in every column."""
    day = date(1920, 1, 1) + timedelta(days=rng.randrange(365 * 100))
    return {
        "id": index,
        "token": _text(rng, 24),
        "email": f"{_text(rng, 10)}@example.com",
        "amount": round(rng.uniform(0, 1_000_000), 4),
        "when": f"{day.isoformat()}T{rng.randrange(24):02d}:{rng.randrange(60):02d}:{rng.randrange(60):02d}",
        "text": _text(rng, rng.randint(12, 40), _HEX + " "),
        "ratio": rng.random(),
        "status": rng.choice(["a", "b", "c"]),
    }


def _short_ids(rng: random.Random, index: int) -> dict[str, object]:
    """Short identifiers of 8 to 12 characters, nearly all distinct."""
    return {
        "id": _text(rng, 12, _ALNUM),
        "ref": f"R{index:07d}",
        "code": _text(rng, 10, _ALNUM) if rng.random() < 0.95 else _text(rng, 8, _ALNUM),
        "serial": _text(rng, 9, _HEX),
        "status": rng.choice(["new", "open", "closed"]),
        "region": rng.choice(["east", "west", "north", "south"]),
        "amount": f"{rng.uniform(1, 900):.2f}",
    }


def _wide(rng: random.Random, index: int, columns: int) -> dict[str, object]:
    """``columns`` columns cycling through eight kinds of content."""
    record: dict[str, object] = {}
    for number in range(columns):
        kind = number % 8
        name = f"k{number:03d}"
        if kind == 0:
            record[name] = f"E{rng.randrange(12):02d}"
        elif kind == 1:
            record[name] = rng.randint(0, 100_000)
        elif kind == 2:
            record[name] = f"{rng.uniform(0, 5000):.2f}"
        elif kind == 3:
            record[name] = (date(2000, 1, 1) + timedelta(days=rng.randrange(9000))).isoformat()
        elif kind == 4:
            record[name] = _text(rng, 8, _ALNUM)
        elif kind == 5:
            record[name] = rng.choice(["yes", "no"])
        elif kind == 6:
            record[name] = " ".join(rng.choices(["alpha", "beta", "gamma", "delta", "omega"], k=rng.randint(1, 6)))
        else:
            record[name] = f"{index}-{rng.randrange(10)}"
    return record


def _normalization(rng: random.Random, index: int, rows: int, effect: bool) -> dict[str, object]:
    """Three text columns of a few hundred values. With ``effect`` the last tenth
    of the rows come in other forms (case, padding, decomposed accents), so a
    normalization that looked useless proves otherwise late in the file."""
    names = ["Québec", "Montréal", "Zoë", "Étienne", "Chloé", "Hélène", "Noël", "Françoise"]
    base = rng.choice(names) + f" {rng.randrange(60)}"
    city = rng.choice(["Laval", "Gatineau", "Lévis", "Sherbrooke"]) + f"-{rng.randrange(40)}"
    tag = f"tag{rng.randrange(150)}"
    if effect and index > rows * 0.9:
        form = rng.randrange(3)
        if form == 0:
            base = unicodedata.normalize("NFD", base)
        elif form == 1:
            city = f"  {city.upper()} "
        else:
            tag = tag.upper()
    return {"id": index, "name": base, "city": city, "tag": tag}


def _fields(layout: str, columns: int) -> list[str]:
    sample = {
        "low-cardinality": _low_cardinality,
        "high-cardinality": _high_cardinality,
        "short-ids": _short_ids,
    }
    rng = random.Random(0)
    if layout in sample:
        return list(sample[layout](rng, 1))
    if layout == "wide":
        return list(_wide(rng, 1, columns))
    if layout == "repeated":
        return list(FIELDS)
    if layout == "transition":
        return ["id", "value", "group"]
    return list(_normalization(rng, 1, 10, False))


def write_layout(
    layout: str,
    rows: int,
    path: Path,
    *,
    seed: int = 42,
    columns: int = 100,
    distinct: int = 10_000,
) -> None:
    """Write ``rows`` records of ``layout`` as a CSV file at ``path``."""
    rng = random.Random(seed)
    fields = _fields(layout, columns)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(fields)
        recent: list[list[str]] = []
        for index in range(1, rows + 1):
            if layout == "low-cardinality":
                record = _low_cardinality(rng, index)
            elif layout == "high-cardinality":
                record = _high_cardinality(rng, index)
            elif layout == "short-ids":
                record = _short_ids(rng, index)
            elif layout == "wide":
                record = _wide(rng, index, columns)
            elif layout == "transition":
                # Exactly ``distinct`` values of ``value``, each used in turn
                # so that every one appears as soon as ``rows`` allows.
                record = {"id": index, "value": f"val-{index % distinct:06d}", "group": index % 7}
            elif layout in ("normalization-clean", "normalization-effect"):
                record = _normalization(rng, index, rows, layout.endswith("effect"))
            elif layout == "repeated":
                if recent and rng.random() < 0.5:
                    writer.writerow(recent[rng.randrange(len(recent))])
                    continue
                record = _record(rng, index)
                row = [("N/A" if v is None else (f"{v:.2f}" if k == "amount" else str(v))) for k, v in record.items()]
                recent.append(row)
                if len(recent) > 20_000:
                    recent.pop(rng.randrange(len(recent)))
                writer.writerow(row)
                continue
            else:
                raise ValueError(f"Unknown layout: {layout}")
            writer.writerow(record[field] for field in fields)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("layout", choices=LAYOUTS)
    parser.add_argument("rows", type=int)
    parser.add_argument("output", type=Path)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--columns", type=int, default=100)
    parser.add_argument("--distinct", type=int, default=10_000)
    args = parser.parse_args()
    write_layout(
        args.layout, args.rows, args.output, seed=args.seed, columns=args.columns, distinct=args.distinct
    )


if __name__ == "__main__":
    main()

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Sources and runs shared by the tests of the smart sample."""

from datetime import UTC, datetime

from planner_helpers import scan_csv
from second_pass_helpers import deep_csv

from tabalyst.scanner.smart import plan_sampling
from tabalyst.scanner.smart.execute import select_rows
from tabalyst.scanner.smart.result import build_document

NORMAL = [f"Region-{chr(65 + i)}" for i in range(13)]
SINGLETONS = [f"Regoin-typo-{i}" for i in range(10)]


def region_rows(per_normal: int = 100) -> list[str]:
    """Rows of a region and a running number, so that only the region is a
    column with few values."""
    names = [name for name in NORMAL for _ in range(per_normal)] + SINGLETONS
    return [f"{name},{number}" for number, name in enumerate(names)]


def run(tmp_path, header, rows, size, **settings):
    result = scan_csv(tmp_path, header, rows, **settings)
    plan = plan_sampling(result, size=size)
    return result, plan, select_rows(result, tmp_path / "data.csv", plan)


def rich_rows(count: int = 900) -> list[str]:
    """Every family of target in one file: a category with rare values, a code
    with a minority pattern, decimals with zero and both signs, integers, ISO dates,
    a number column with text in it, and a branch that decides the shape of an id."""
    rows = []
    for i in range(count):
        region = NORMAL[i % 5] if i % 97 else SINGLETONS[(i // 97) % 10]
        code = f"AB-{1000 + i}" if i % 53 else f"zz{i}"
        amount = ["0", f"-{i}.5", f"{i}.25"][i % 3]
        quantity = str(i % 400)
        when = f"20{10 + i % 9:02d}-0{1 + i % 9}-1{i % 9}"
        measure = str(i) if i % 41 else "n/a"
        branch = ("north", "south", "east")[i % 3]
        client = f"{branch[0].upper()}{i:05d}" if i % 61 else f"X{i:05d}"
        rows.append(f"{region},{code},{amount},{quantity},{when},{measure},{branch},{client}")
    return rows


RICH_HEADER = "region,code,amount,quantity,when,measure,branch,client"


def report(tmp_path, header, rows, size, **settings):
    """Scan, run the second pass, plan and select; the report of the sample."""
    result, _, outcome = deep_csv(tmp_path, header, rows, **settings)
    deep = outcome.document
    plan = plan_sampling(result, deep=deep, size=size)
    selection = select_rows(result, tmp_path / "data.csv", plan, deep=deep)
    document = build_document(
        result,
        plan,
        selection,
        percent=None,
        output_name="data.sample.csv",
        encoding="utf-8",
        delimiter=",",
        started_at=datetime.now(UTC),
        duration_seconds=1.0,
        scan_ran=False,
    )
    return result, plan, selection, document


def dated_rows(count: int = 700) -> list[str]:
    """Dates of three kinds, ambiguous dates, and a column that is half numbers and
    half text; every column has far more than 100 distinct values."""
    rows = []
    for i in range(count):
        day = f"{2018 + i % 4}-{1 + i % 12:02d}-{1 + i % 28:02d}"
        aware = f"{day}T{i % 24:02d}:{i % 60:02d}:00+0{i % 3}:00"
        naive = f"{day} {i % 24:02d}:{i % 60:02d}:30"
        slash = f"{1 + i % 12:02d}/{1 + (i * 5) % 12:02d}/{2000 + i % 20}"
        mixed = str(i * 3) if i % 2 else f"word{i}"
        rows.append(",".join([day, aware, naive, slash, mixed, str(i)]))
    return rows

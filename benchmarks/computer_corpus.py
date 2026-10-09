# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Measure Computer generation and audit paired CSVs outside the checkout."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import subprocess
import sys
import time
from collections import Counter
from decimal import Decimal
from pathlib import Path

import psutil

from tabalyst.generate_computer_output import LABEL_FIELDS, PROFILE_COLUMNS
from tabalyst.generate_package import load_generate_package


def audit(package_path: Path, output_dir: Path, rows: int, profile: str) -> dict[str, object]:
    """Validate the package and stream-check both localized outputs and their measures."""
    package = load_generate_package(package_path)
    declared_files = {path.relative_to(package.root).as_posix() for path in package.input_paths}
    corpus_files = {path.relative_to(package.root).as_posix()
                    for path in package.root.rglob("*") if path.suffix in {".csv", ".yaml"}}
    assert declared_files == corpus_files
    columns = PROFILE_COLUMNS[profile]
    output_profiles = package.manifest["output_profiles"]
    assert isinstance(output_profiles, dict)
    assert output_profiles[profile] == list(columns)
    assert tuple(field for field in PROFILE_COLUMNS["extended"] if field in PROFILE_COLUMNS["compact"]) == PROFILE_COLUMNS["compact"]
    assert tuple(field for field in PROFILE_COLUMNS["extended"] if field in PROFILE_COLUMNS["standard"]) == PROFILE_COLUMNS["standard"]
    metadata = json.loads((output_dir / "computers.meta.json").read_text(encoding="utf-8"))
    assert metadata["request"]["rows"] == rows
    assert metadata["request"]["output_profile"] == profile
    assert metadata["request"]["seed"] == 42
    assert len(metadata["resource_sha256"]) == len(package.input_paths)
    for source in package.input_paths:
        key = source.relative_to(package.root).as_posix()
        assert metadata["resource_sha256"][key] == hashlib.sha256(source.read_bytes()).hexdigest()

    counts: dict[str, Counter[str]] = {name: Counter() for name in (
        "computer_type", "gpu_type", "memory_gb", "storage_gb", "stock_status",
        "promotion_status", "shipping_availability",
    ) if name in columns}
    pairs: Counter[str] = Counter()
    relation_fields = (("memory_gb", "list_price"),
                       ("review_count", "units_sold_30d"),
                       ("units_sold_30d", "sales_rank"))
    moments = {fields: [0.0] * 5 for fields in relation_fields if set(fields) <= set(columns)}
    def product_id(index: int) -> str:
        digest = hashlib.sha256()
        for part in ("computers", "42", str(index)):
            encoded = part.encode("utf-8")
            digest.update(len(encoded).to_bytes(8, "big"))
            digest.update(encoded)
        return "prd_" + digest.hexdigest()[:40]

    with (output_dir / "computers-en.csv").open(encoding="utf-8", newline="") as en_stream, (
        output_dir / "computers-fr.csv"
    ).open(encoding="utf-8", newline="") as fr_stream:
        english, french = csv.DictReader(en_stream), csv.DictReader(fr_stream)
        assert tuple(english.fieldnames or ()) == tuple(french.fieldnames or ()) == columns
        observed = 0
        for left, right in zip(english, french, strict=True):
            observed += 1
            assert all(left[field] == right[field] for field in columns if field not in LABEL_FIELDS)
            assert left["product_id"] == product_id(observed - 1)
            for field, counter in counts.items():
                counter[left[field]] += 1
            pairs[f'{left["gpu_type"]}:{left["memory_gb"]}'] += 1
            for (x_field, y_field), values in moments.items():
                x, y = float(left[x_field]), float(left[y_field])
                values[0] += x
                values[1] += y
                values[2] += x * x
                values[3] += y * y
                values[4] += x * y
            assert Decimal(left["current_price"]) <= Decimal(left["list_price"])
            assert (int(left["stock_quantity"]) == 0) == (left["stock_status"] == "out_of_stock")
            if profile == "extended":
                assert int(left["memory_slots_used"]) <= int(left["memory_slots_total"])
                assert int(left["m2_slots_used"]) <= int(left["m2_slots_total"])
                assert Decimal(left["lowest_price_30d"]) <= Decimal(left["current_price"]) <= Decimal(left["highest_price_30d"])
                assert int(left["units_sold_30d"]) <= 5 or int(left["stock_quantity"]) > 0
                assert (left["promotion_status"] == "Active") == (Decimal(left["discount_percent"]) > 0)
        assert observed == rows
    if rows >= 10_000:
        laptop_share = counts["computer_type"]["Laptop"] / rows
        assert 0.72 < laptop_share < 0.78
        assert pairs["discrete:16"] == 0
        assert pairs["discrete:32"] > 0
        assert pairs["integrated:16"] > pairs["integrated:32"]
        assert counts["storage_gb"]["1024"] > 0
    correlations: dict[str, float] = {}
    for (x_field, y_field), (sum_x, sum_y, sum_x2, sum_y2, sum_xy) in moments.items():
        numerator = rows * sum_xy - sum_x * sum_y
        denominator = math.sqrt((rows * sum_x2 - sum_x**2) * (rows * sum_y2 - sum_y**2))
        correlations[f"{x_field}:{y_field}"] = round(numerator / denominator, 4)
    if rows >= 10_000 and profile == "extended":
        assert correlations["memory_gb:list_price"] > 0.7
        assert correlations["review_count:units_sold_30d"] > 0.8
        assert correlations["units_sold_30d:sales_rank"] < -0.99
    return {
        "rows": rows, "columns": len(columns),
        "distributions": {field: dict(counter) for field, counter in counts.items()},
        "gpu_memory": dict(pairs),
        "correlations": correlations,
        "sha256": {locale: hashlib.sha256((output_dir / f"computers-{locale}.csv").read_bytes()).hexdigest()
                   for locale in ("en", "fr") if rows <= 10_000},
    }


def benchmark(package_path: Path, output_dir: Path, rows: int, profile: str) -> dict[str, object]:
    """Run the CLI once and sample its peak resident memory until completion."""
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [sys.executable, "-m", "tabalyst", "generate", str(package_path),
               "-d", str(output_dir), "--rows", str(rows), "--seed", "42",
               "--output-profile", profile]
    start = time.perf_counter()
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True) as child:
        process = psutil.Process(child.pid)
        peak_rss = 0
        while child.poll() is None:
            try:
                processes = (process, *process.children(recursive=True))
                current_rss = sum(item.memory_info().rss for item in processes if item.is_running())
                peak_rss = max(peak_rss, current_rss)
            except psutil.NoSuchProcess:
                pass
            time.sleep(0.05)
        stdout, stderr = child.communicate()
        if child.returncode:
            raise RuntimeError(f"Computer generation failed: {stdout}\n{stderr}")
    seconds = time.perf_counter() - start
    measures = audit(package_path, output_dir, rows, profile)
    measures.update({"generation_seconds": round(seconds, 3),
                     "peak_rss_mib": round(peak_rss / 1024**2, 2),
                     "csv_mib": round(sum((output_dir / f"computers-{locale}.csv").stat().st_size
                                          for locale in ("en", "fr")) / 1024**2, 2)})
    return measures


def main() -> None:
    """Run one requested volume and save a machine-readable result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--rows", type=int, required=True)
    parser.add_argument("--profile", choices=tuple(PROFILE_COLUMNS), default="extended")
    parser.add_argument("--audit-only", action="store_true")
    args = parser.parse_args()
    package_path = args.package.resolve()
    output_dir = args.output_dir.resolve()
    checkout = Path(__file__).resolve().parents[1]
    if output_dir == checkout or checkout in output_dir.parents:
        parser.error("output directory must be outside the checkout")
    result = (audit(package_path, output_dir, args.rows, args.profile) if args.audit_only
              else benchmark(package_path, output_dir, args.rows, args.profile))
    (output_dir / "audit.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

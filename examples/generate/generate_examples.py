# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Generate every editable example definition into a separate output folder."""

from __future__ import annotations

import argparse
from pathlib import Path

from tabalyst.errors import TabalystError
from tabalyst.generate_definition import load_generate_definition
from tabalyst.generate_service import build_generate_plan, generate_datasets

HERE = Path(__file__).resolve().parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir", type=Path, default=HERE / "output",
        help="Destination root (default: examples/generate/output).",
    )
    parser.add_argument(
        "--rows", type=int,
        help="Override each definition's row count for a smaller review run.",
    )
    parser.add_argument(
        "--clean-only", action="store_true",
        help="Generate clean CSV files without anomaly profiles.",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Replace existing generated files.",
    )
    args = parser.parse_args()
    definitions = sorted((HERE / "input").glob("*.yaml"))
    if not definitions:
        parser.error("No YAML definitions found in examples/generate/input")

    # Preflight every plan before the first output is written.
    plans = []
    destinations: set[Path] = set()
    try:
        for path in definitions:
            definition = load_generate_definition(path)
            profiles = (None,) if args.clean_only or not definition.anomaly_profiles else (
                profile["id"] for profile in definition.anomaly_profiles
            )
            for profile in profiles:
                folder = args.output_dir / path.stem
                if profile is not None and len(definition.anomaly_profiles) > 1:
                    folder /= profile
                plan = build_generate_plan(
                    path, output_dir=folder, rows=args.rows,
                    anomaly_profile=profile, force=args.force,
                )
                for artifact in plan.artifacts:
                    destination = artifact.path.resolve()
                    if destination in destinations:
                        raise ValueError(f"Two plans target {destination}")
                    destinations.add(destination)
                plans.append(plan)
        for plan in plans:
            result = generate_datasets(plan)
            label = plan.definition.id
            if plan.anomaly_profile:
                label += f"/{plan.anomaly_profile}"
            print(f"{label}: {len(result.paths)} files")
            for path in result.paths:
                print(f"  {path}")
    except (TabalystError, OSError, ValueError) as exc:
        parser.exit(1, f"Generate examples failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

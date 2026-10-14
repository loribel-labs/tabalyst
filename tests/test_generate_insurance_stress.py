# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Check the Insurance dirty_stress profile: every class has its absolute number of rows."""

from __future__ import annotations

import csv
import json
import re
from collections import Counter, defaultdict
from collections.abc import Iterator
from importlib.resources import files
from pathlib import Path

import pytest

from tabalyst.generate_service import build_generate_plan, generate_datasets

PACKAGE = Path(str(files("tabalyst").joinpath("generate_examples", "insurance")))

# Rows (events) per class: the specification of docs/dev/generate/insurance-stress-cases.md,
# section 1, measured in examples/datasets/insurance-customers.csv, plus the cases of
# sections 3 and 5. A class that the clean version already produces by itself is not listed:
# 3 start-after-end and 15 modification-before-creation dates, 80 "Quebec" without accent.
CLASSES = {
    "id_client_missing_digit": 20,
    "id_client_double_hyphen": 17,
    "date_other_branch_format": 67,
    "province_nom_lower": 12,
    "province_code_city_mismatch": 3,
    "city_mojibake": 2,
    "mode_paiement_accent_removed": 17,
    "type_contrat_variant": 7,
    "claim_amount_zero": 5,
    "claim_amount_negative": 1,
    "id_contrat_missing_digit": 22,
    "id_contrat_double_hyphen": 14,
    "id_contrat_empty": 9,
    "agence_code_double_hyphen": 16,
    "prenom_empty": 7,
    "nom_empty": 4,
    "date_naissance_empty": 6,
    "province_code_empty": 3,
    "type_contrat_empty": 2,
    "name_space_inside": 8,
    "name_double_space": 11,
    "nom_leading_apostrophe": 1,
    "province_code_lower": 23,
    "pays_code_lower": 22,
    "code_postal_double_space": 54,
    "code_postal_char_missing": 21,
    "telephone_double_space": 42,
    "courriel_space_inside": 12,
    "category_suffix_x": 22,
    "date_slash": 41,
    "date_start_after_end": 27,
    "prime_annuelle_negative": 25,
    "prime_annuelle_text": 5,
    "prime_annuelle_currency_suffix": 4,
    "prime_annuelle_currency_prefix": 3,
    "prime_annuelle_currency_fr": 3,
    "prime_annuelle_currency_code": 2,
    "date_fin_sentinel": 2,
    "nom_voie_very_long": 2,
    "prenom_typo": 47,
    "nom_typo": 79,
    "ville_typo": 62,
    "nom_voie_typo": 79,
    "ville_space_inside": 6,
    "duplicate_rows": 8,
}

# What the changed cell must look like, for the classes with a simple shape.
AFTER = {
    "id_client_double_hyphen": r".*--.*",
    "id_contrat_empty": r"",
    "agence_code_double_hyphen": r"AG--[A-Z]{2}-\d{3}",
    "prenom_empty": r"",
    "pays_code_lower": r"ca",
    "province_code_lower": r"[a-z]{2}",
    "code_postal_double_space": r"[A-Z]\d[A-Z]  \d[A-Z]\d",
    "telephone_double_space": r"\+1  \d{3}-\d{3}-\d{4}",
    "courriel_space_inside": r".* .*",
    "claim_amount_zero": r"0\.00",
    "claim_amount_negative": r"-\d+\.\d{2}",
    "prime_annuelle_negative": r"-\d+\.\d{2}",
    "prime_annuelle_currency_suffix": r"\d+\.\d{2} \$",
    "prime_annuelle_currency_prefix": r"\$\d+\.\d{2}",
    "prime_annuelle_currency_fr": r"\d{1,3}(?: \d{3})*,\d{2} \$",
    "prime_annuelle_currency_code": r"\d+\.\d{2} CAD",
    "date_fin_sentinel": r"9999-12-31",
    "nom_voie_very_long": r".{300}",
    "nom_leading_apostrophe": r"'.+",
    "city_mojibake": r"MontrÃ©al",
}


@pytest.fixture(scope="module", params=[3000, 100000], ids=["3000-rows", "100000-rows"])
def stress(request: pytest.FixtureRequest, tmp_path_factory: pytest.TempPathFactory,
           ) -> Iterator[tuple[int, Path]]:
    rows = request.param
    out = tmp_path_factory.mktemp(f"stress-{rows}")
    generate_datasets(build_generate_plan(
        PACKAGE, rows=rows, seed=42, anomaly_profile="dirty_stress", output_dir=out))
    yield rows, out


def _changes(out: Path) -> list[dict[str, str]]:
    path = out / "insurance-combined.dirty_stress.changes.csv"
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream))


def test_every_class_has_its_absolute_number_of_rows_at_any_size(
        stress: tuple[int, Path]) -> None:
    _, out = stress
    events: dict[str, set[str]] = defaultdict(set)
    for change in _changes(out):
        events[change["class"]].add(change["event_id"])
    assert {name: len(ids) for name, ids in events.items()} == CLASSES


def test_summary_applies_every_requested_row_and_skips_none(stress: tuple[int, Path]) -> None:
    rows, out = stress
    summary = json.loads(
        (out / "insurance-combined.dirty_stress.summary.json").read_text(encoding="utf-8"))
    assert summary["total_rows"] == rows
    assert all(entry["skipped_rows"] == 0 and entry["applied_rows"] == entry["requested_rows"]
               == entry["count"] for entry in summary["operations"])
    assert all("rate" not in entry for entry in summary["operations"])
    per_class = Counter[str]()
    for entry in summary["operations"]:
        per_class[entry["class"]] += entry["applied_rows"]
    assert dict(per_class) == CLASSES
    assert summary["affected_rows"] == summary["events"] == sum(CLASSES.values())


def test_a_row_carries_one_class_and_the_journal_matches_the_files(
        stress: tuple[int, Path]) -> None:
    _, out = stress
    with (out / "insurance-combined.csv").open(encoding="utf-8", newline="") as stream:
        clean = list(csv.DictReader(stream))
    with (out / "insurance-combined.dirty_stress.csv").open(encoding="utf-8", newline="") as stream:
        altered = list(csv.DictReader(stream))
    classes: dict[str, set[str]] = defaultdict(set)
    for change in _changes(out):
        position = int(change["row_number"]) - 2
        classes[change["row_number"]].add(change["class"])
        assert change["before"] == clean[position][change["column"]]
        assert change["after"] == altered[position][change["column"]]
    assert all(len(names) == 1 for names in classes.values())
    changed = {int(number) - 2 for number in classes}
    assert all(altered[i] == clean[i] for i in range(len(clean)) if i not in changed)


def test_changed_cells_have_the_shape_of_their_class(stress: tuple[int, Path]) -> None:
    _, out = stress
    for change in _changes(out):
        pattern = AFTER.get(change["class"])
        if pattern is not None:
            assert re.fullmatch(pattern, change["after"]), (change["class"], change["after"])


def test_clean_file_is_the_same_with_and_without_the_profile(
        stress: tuple[int, Path], tmp_path: Path) -> None:
    rows, out = stress
    if rows != 3000:
        pytest.skip("the clean file is compared once, at the smallest size")
    generate_datasets(build_generate_plan(PACKAGE, rows=rows, seed=42, output_dir=tmp_path))
    assert (tmp_path / "insurance-combined.csv").read_bytes() == (
        out / "insurance-combined.csv").read_bytes()


def test_dirty_stress_rejects_a_file_too_small_for_its_classes(tmp_path: Path) -> None:
    from tabalyst.errors import ReportError

    with pytest.raises(ReportError, match="rows can take it|but the dataset has"):
        generate_datasets(build_generate_plan(
            PACKAGE, rows=300, seed=42, anomaly_profile="dirty_stress",
            output_dir=tmp_path / "small"))
    assert not list((tmp_path / "small").glob("*dirty_stress*"))

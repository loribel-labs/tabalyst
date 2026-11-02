# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Stratified sampling with a minimum of one row per stratum and the quota per
stratum of ``stratified-balanced`` (tests T01 to T16 of the specification)."""

import csv
from collections import Counter

import pytest
from typer.testing import CliRunner

import tabalyst
from tabalyst.cli import app
from tabalyst.errors import InputError
from tabalyst.scanner.stratify import allocate_strata_with_minimum

runner = CliRunner()


def _write(path, header, rows):
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)


def _read(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.reader(stream))[1:]


def _populations(tmp_path, counts, name="data.csv"):
    source = tmp_path / name
    _write(source, ["kind", "n"], [(kind, i) for kind, count in counts.items() for i in range(count)])
    return source


def _balanced(source, tmp_path, **options):
    options.setdefault("output", tmp_path / "s.csv")
    return tabalyst.sample_csv(source, method="stratified-balanced", **options)


# The allocation with a minimum -------------------------------------------------


def test_the_allocation_with_a_minimum_keeps_the_total_and_one_row_of_each():
    counts = {"big": 990, "rare": 10, "tiny": 1}

    allocated = allocate_strata_with_minimum(counts, 20)

    assert sum(allocated.values()) == 20
    assert allocated["tiny"] == 1 and allocated["rare"] >= 1
    assert all(allocated[key] <= counts[key] for key in counts)


def test_the_allocation_with_a_minimum_never_exceeds_a_population():
    assert allocate_strata_with_minimum({"a": 1, "b": 1, "c": 98}, 100) == {"a": 1, "b": 1, "c": 98}
    assert allocate_strata_with_minimum({"a": 2, "b": 3}, 5) == {"a": 2, "b": 3}


def test_the_allocation_with_a_minimum_is_proportional_when_nothing_is_rare():
    assert allocate_strata_with_minimum({"a": 700, "b": 300}, 10) == {"a": 7, "b": 3}


def test_the_allocation_with_a_minimum_breaks_ties_by_the_text_of_the_key():
    assert allocate_strata_with_minimum({"b": 2, "a": 2, "c": 2}, 4) == {"a": 2, "b": 1, "c": 1}


def test_the_allocation_with_a_minimum_refuses_a_size_under_the_strata():
    with pytest.raises(ValueError):
        allocate_strata_with_minimum({"a": 5, "b": 5, "c": 5}, 2)


# stratified: minimum of one row (T10, T11, T12) --------------------------------


def test_T10_T11_a_stratified_sample_has_the_exact_size_and_a_row_of_each_stratum(tmp_path):
    source = _populations(tmp_path, {"std": 7000, "prem": 2000, "vip": 1000, "ra": 12, "rb": 3})

    result = tabalyst.sample_csv(
        source, method="stratified", field="kind", rows=50, seed=3, output=tmp_path / "s.csv"
    )

    counts = Counter(row[0] for row in _read(tmp_path / "s.csv"))
    assert sum(counts.values()) == result.sample_rows == 50
    assert set(counts) == {"std", "prem", "vip", "ra", "rb"}
    assert result.strata_uncovered == 0


def test_T12_a_stratified_sample_smaller_than_its_strata_stops_and_names_the_minimum(tmp_path):
    source = _populations(tmp_path, {"a": 5, "b": 5, "c": 5})
    output = tmp_path / "s.csv"

    with pytest.raises(InputError, match=r"cannot keep one row of each of the 3 strata.*--rows 3"):
        tabalyst.sample_csv(source, method="stratified", field="kind", rows=2, output=output)

    assert not output.exists()


# stratified-balanced (T01 to T09) ----------------------------------------------


def test_T01_the_quota_applies_to_each_stratum_and_nothing_moves_to_another(tmp_path):
    source = _populations(tmp_path, {"std": 700, "prem": 200, "vip": 100, "ra": 12, "rb": 3})

    result = _balanced(source, tmp_path, field="kind", per_value=100, seed=1)

    counts = Counter(row[0] for row in _read(tmp_path / "s.csv"))
    assert counts == {"std": 100, "prem": 100, "vip": 100, "ra": 12, "rb": 3}
    assert result.sample_rows == 315 and result.source_rows == 1015
    assert result.per_value == 100
    assert (result.strata_known, result.strata_selected, result.strata_uncovered) == (5, 5, 0)
    assert result.strata_capped == 2  # std and prem; vip has exactly 100


def test_T02_T03_a_stratum_of_one_row_or_exactly_the_quota_is_kept_whole(tmp_path):
    source = _populations(tmp_path, {"one": 1, "exact": 4, "big": 40})

    _balanced(source, tmp_path, field="kind", per_value=4, seed=2)

    counts = Counter(row[0] for row in _read(tmp_path / "s.csv"))
    assert counts == {"one": 1, "exact": 4, "big": 4}


def test_T04_several_fields_give_a_quota_to_each_combination(tmp_path):
    source = tmp_path / "multi.csv"
    rows = [("n", "a")] * 10 + [("n", "b")] * 3 + [("s", "a")] * 7
    _write(source, ["region", "segment"], rows)

    result = _balanced(source, tmp_path, field=["region", "segment"], per_value=5, seed=1)

    counts = Counter(tuple(row) for row in _read(tmp_path / "s.csv"))
    assert counts == {("n", "a"): 5, ("n", "b"): 3, ("s", "a"): 5}
    assert result.strata_known == 3 and result.fields == ("region", "segment")


def test_T05_missing_values_are_a_stratum_of_their_own(tmp_path):
    source = _populations(tmp_path, {"": 6, "a": 6})

    _balanced(source, tmp_path, field="kind", per_value=2, seed=1)

    assert Counter(row[0] for row in _read(tmp_path / "s.csv")) == {"": 2, "a": 2}


@pytest.mark.parametrize("value", [0, -3, 2.5, True, "x"])
def test_T06_a_quota_that_is_not_a_positive_whole_number_is_refused(tmp_path, value):
    source = _populations(tmp_path, {"a": 3})

    with pytest.raises(InputError, match="--per-value must be a whole number greater than 0"):
        _balanced(source, tmp_path, field="kind", per_value=value)


def test_T07_a_size_goal_does_not_go_with_a_quota(tmp_path):
    source = _populations(tmp_path, {"a": 3})

    with pytest.raises(InputError, match="--rows and --percent do not go with stratified-balanced"):
        _balanced(source, tmp_path, field="kind", per_value=1, rows=2)
    with pytest.raises(InputError, match="--rows and --percent do not go with stratified-balanced"):
        _balanced(source, tmp_path, field="kind", per_value=1, percent=10)
    with pytest.raises(InputError, match="--per-value is required"):
        _balanced(source, tmp_path, field="kind")
    with pytest.raises(InputError, match="--field is required"):
        _balanced(source, tmp_path, per_value=1)


def test_a_quota_goes_with_the_balanced_method_only(tmp_path):
    source = _populations(tmp_path, {"a": 3})

    with pytest.raises(InputError, match="--per-value can only be used with the stratified-balanced"):
        tabalyst.sample_csv(
            source, method="stratified", field="kind", rows=1, per_value=1, output=tmp_path / "s.csv"
        )


def test_T08_the_same_seed_gives_the_same_file_and_another_seed_another_draw(tmp_path):
    source = _populations(tmp_path, {"a": 200, "b": 300, "c": 5})

    _balanced(source, tmp_path, field="kind", per_value=20, seed=7, output=tmp_path / "one.csv")
    _balanced(source, tmp_path, field="kind", per_value=20, seed=7, output=tmp_path / "two.csv")
    _balanced(source, tmp_path, field="kind", per_value=20, seed=8, output=tmp_path / "three.csv")

    assert (tmp_path / "one.csv").read_bytes() == (tmp_path / "two.csv").read_bytes()
    assert (tmp_path / "one.csv").read_bytes() != (tmp_path / "three.csv").read_bytes()


def test_T09_identical_rows_are_distinct_records_and_no_position_is_drawn_twice(tmp_path):
    source = tmp_path / "same.csv"
    _write(source, ["k", "n"], [("a", "x")] * 6 + [("b", "y")] * 2)

    _balanced(source, tmp_path, field="k", per_value=4, seed=1)

    assert Counter(tuple(row) for row in _read(tmp_path / "s.csv")) == {("a", "x"): 4, ("b", "y"): 2}

    unique = tmp_path / "unique.csv"
    _write(unique, ["k", "n"], [("a", i) for i in range(50)])
    _balanced(unique, tmp_path, field="k", per_value=30, seed=1, output=tmp_path / "u.csv")
    drawn = [row[1] for row in _read(tmp_path / "u.csv")]
    assert len(drawn) == len(set(drawn)) == 30
    assert drawn == sorted(drawn, key=int)  # the file order is kept


def test_T13_more_strata_than_the_ceiling_stop_the_run_without_an_output(tmp_path):
    source = tmp_path / "many.csv"
    _write(source, ["id"], [(i,) for i in range(50)])
    output = tmp_path / "s.csv"

    with pytest.raises(InputError, match=r"more than 10 strata.*--max-strata"):
        _balanced(source, tmp_path, field="id", per_value=1, max_strata=10, output=output)

    assert not output.exists()


def test_T14_quotes_newlines_delimiter_and_encoding_are_kept(tmp_path):
    source = tmp_path / "latin.csv"
    rows = [("é", "a;b\nc"), ("é", 'say "hi"'), ("z", "d")]
    with source.open("w", newline="", encoding="latin-1") as stream:
        csv.writer(stream, delimiter=";").writerows([["k", "text"], *rows])

    _balanced(
        source, tmp_path, field="k", per_value=5, seed=1, delimiter=";", encoding="latin-1"
    )

    with (tmp_path / "s.csv").open(newline="", encoding="latin-1") as stream:
        assert list(csv.reader(stream, delimiter=";")) == [["k", "text"], *map(list, rows)]


def test_T15_the_batch_api_and_the_cli_give_the_same_file(tmp_path):
    source = _populations(tmp_path, {"a": 100, "b": 100, "c": 3})

    batch = tabalyst.generate_samples(
        [source],
        method="stratified-balanced",
        field="kind",
        per_value=10,
        seed=5,
        output=tmp_path / "api.csv",
    )
    result = runner.invoke(
        app,
        ["sample", str(source), "--sample-method", "stratified-balanced", "--field", "kind",
         "--per-value", "10", "--seed", "5", "-o", str(tmp_path / "cli.csv")],
    )

    assert batch.succeeded and result.exit_code == 0, result.output
    assert (tmp_path / "api.csv").read_bytes() == (tmp_path / "cli.csv").read_bytes()
    assert "Per value:     up to 10 rows" in result.output
    assert "Sample rows:   23" in result.output
    assert "Strata:        3 known, 3 sampled, 0 without rows" in result.output
    assert "Drawn from:    2 strata with more rows than the quota; the other 1 are kept whole" in result.output
    assert "Seed:          5" in result.output


def test_the_cli_refuses_incompatible_options_with_a_clear_message(tmp_path):
    source = _populations(tmp_path, {"a": 5})
    base = ["sample", str(source), "--field", "kind"]

    balanced_rows = runner.invoke(
        app, [*base, "--sample-method", "stratified-balanced", "--per-value", "2", "--rows", "3"]
    )
    quota_alone = runner.invoke(app, [*base, "--sample-method", "stratified", "--per-value", "2"])
    random_field = runner.invoke(app, ["sample", str(source), "--sample-method", "random",
                                       "--rows", "2", "--field", "kind"])

    assert balanced_rows.exit_code == 2 and "--rows and --percent do not go" in balanced_rows.output
    assert quota_alone.exit_code == 2 and "--per-value only goes with" in quota_alone.output
    assert random_field.exit_code == 2 and "stratified-balanced" in random_field.output


def test_the_cli_warns_when_the_balanced_sample_holds_half_of_the_file(tmp_path):
    source = tmp_path / "ids.csv"
    _write(source, ["id"], [(i,) for i in range(10)])

    result = runner.invoke(
        app,
        ["sample", str(source), "--sample-method", "stratified-balanced", "--field", "id",
         "--per-value", "1", "-o", str(tmp_path / "s.csv")],
    )

    assert result.exit_code == 0 and "holds half of the file or more" in result.output


def test_T16_the_other_methods_are_unchanged(tmp_path):
    source = _populations(tmp_path, {"a": 30})

    for method in ("first", "last", "random"):
        result = tabalyst.sample_csv(
            source, method=method, rows=5, seed=1, output=tmp_path / f"{method}.csv"
        )
        assert result.sample_rows == 5
        assert (result.per_value, result.strata_capped) == (None, None)

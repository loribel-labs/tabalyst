# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON Inspect contract: the command and its integration with Scan and Report (lot JI-7).

Design sections 11 to 13: ``tabalyst inspect``, automatic and controlled
parcours, suspension on ambiguity, incompatible configuration, outputs.
"""

import json
import math

import pytest
from inspect_helpers import (
    edit_json_file,
    parameters,
    rows,
    write_json,
    write_jsonl,
    write_text,
)
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.projects.location import StorageLocation

pytestmark = pytest.mark.inspect_lot("JI-7")

runner = CliRunner()

SHOP = {
    "export": {"version": 2},
    "customers": [
        {"id": index, "name": f"N{index}", "address": {"city": "Lyon"}, "tags": ["a"]}
        for index in range(1, 4)
    ],
}
TWO = {"a": rows(3), "b": rows(3)}


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))
    return StorageLocation.local()


def _visible(source):
    return source.with_name(source.name + "-inspect.json")


def _inspect(*args):
    return runner.invoke(app, ["inspect", *map(str, args)])


def _scan_document(storage, source) -> dict:
    return json.loads(storage.shared_scan_path(source).read_text(encoding="utf-8"))


def _report(tmp_path, source, *args):
    out = tmp_path / "out"
    result = runner.invoke(app, ["report", str(source), "-d", str(out), *map(str, args)])
    return result, out


def _profile(out, source) -> dict:
    return json.loads((out / f"{source.stem}.report.json").read_text(encoding="utf-8"))


# The command (CA-01, CA-02) -----------------------------------------------------


def test_inspect_writes_the_visible_file_beside_the_source(tmp_path, storage):
    source = write_json(tmp_path, "clients.json", SHOP)

    result = _inspect(source)

    assert result.exit_code == 0, result.output
    document = json.loads(_visible(source).read_text(encoding="utf-8"))
    assert document["config"]["structure"]["dataset_path"] == "$.customers[]"
    assert "$.customers[]" in result.output
    assert not storage.shared_inspect_path(source).exists()
    assert not storage.shared_scan_path(source).exists()


def test_inspect_accepts_several_sources_and_patterns(tmp_path):
    write_json(tmp_path, "a.json", rows(2))
    write_jsonl(tmp_path, "b.jsonl", rows(2))
    write_jsonl(tmp_path, "c.ndjson", rows(2))

    result = _inspect(tmp_path / "a.json", tmp_path / "b.jsonl", tmp_path / "c.ndjson")

    assert result.exit_code == 0, result.output
    assert sorted(path.name for path in tmp_path.glob("*-inspect.json")) == [
        "a.json-inspect.json",
        "b.jsonl-inspect.json",
        "c.ndjson-inspect.json",
    ]


def test_same_stem_sources_have_distinct_inspect_files(tmp_path):
    write_json(tmp_path, "data.json", rows(2))
    write_jsonl(tmp_path, "data.jsonl", rows(2))

    result = _inspect(tmp_path / "data.json", tmp_path / "data.jsonl")

    assert result.exit_code == 0, result.output
    assert (tmp_path / "data.json-inspect.json").is_file()
    assert (tmp_path / "data.jsonl-inspect.json").is_file()


def test_inspect_refuses_other_kinds_of_source(tmp_path):
    source = write_text(tmp_path, "data.csv", "id,city\n1,Paris\n")

    result = _inspect(source)

    assert result.exit_code == 2
    assert ".json" in result.output
    assert not _visible(source).exists()


def test_invalid_json_fails_and_writes_nothing(tmp_path, storage):
    source = write_text(tmp_path, "broken.json", '[{"id": 1}, {"id": }]')

    result = _inspect(source)

    assert result.exit_code == 4
    assert not _visible(source).exists()
    assert not storage.shared_inspect_path(source).exists()


def test_invalid_json_leaves_the_existing_file_alone(tmp_path):
    source = write_json(tmp_path, "shop.json", SHOP)
    assert _inspect(source).exit_code == 0
    before = _visible(source).read_bytes()
    write_text(tmp_path, "shop.json", '{"customers": [')

    result = _inspect(source)

    assert result.exit_code == 4
    assert _visible(source).read_bytes() == before


def test_an_unresolved_selection_is_a_successful_inspection(tmp_path):
    source = write_json(tmp_path, "shop.json", TWO)

    result = _inspect(source)

    assert result.exit_code == 0, result.output
    assert "$.a[]" in result.output and "$.b[]" in result.output
    config = json.loads(_visible(source).read_text(encoding="utf-8"))["config"]
    assert config["structure"]["dataset_path"] is None


def test_reinspection_options(tmp_path):
    source = write_json(tmp_path, "shop.json", SHOP)
    assert _inspect(source).exit_code == 0
    path = _visible(source)
    edit_json_file(path, lambda d: d["config"]["flatten"].update(separator="/"))

    assert _inspect(source).exit_code == 0
    assert json.loads(path.read_text(encoding="utf-8"))["config"]["flatten"]["separator"] == "/"

    assert _inspect(source, "--reset-config").exit_code == 0
    assert json.loads(path.read_text(encoding="utf-8"))["config"]["flatten"]["separator"] == "."

    edit_json_file(path, lambda d: d["config"]["flatten"].update(separator="ab"))
    before = path.read_bytes()
    refused = _inspect(source)
    assert refused.exit_code == 2
    assert path.read_bytes() == before
    assert _inspect(source, "--force").exit_code == 0
    assert json.loads(path.read_text(encoding="utf-8"))["config"]["flatten"]["separator"] == "."


def test_inspect_files_are_not_sources(tmp_path):
    source = write_json(tmp_path, "shop.json", SHOP)
    assert _inspect(source).exit_code == 0

    refused = _inspect(_visible(source))

    assert refused.exit_code == 2
    assert "Inspect file" in refused.output
    for command in ("scan", "report"):
        listed = runner.invoke(app, [command, str(tmp_path / "*.json"), "-d", str(tmp_path / "o")])
        assert listed.exit_code == 0, listed.output
    assert not (tmp_path / "o" / "shop.json-inspect.report.html").exists()


# Automatic parcours (CA-06, EF-10, EF-11) ----------------------------------------


def test_report_with_no_file_inspects_automatically_and_continues(tmp_path, storage):
    source = write_json(tmp_path, "page.json", {"count": 3, "results": rows(3)})

    result, out = _report(tmp_path, source)

    assert result.exit_code == 0, result.output
    assert [item["id"] for item in _profile(out, source)["datasets"]] == ["$.results[]"]
    assert storage.shared_inspect_path(source).is_file()
    assert not _visible(source).exists()


def test_scan_and_report_apply_the_same_interpretation(tmp_path, storage):
    source = write_json(tmp_path, "shop.json", SHOP)
    assert runner.invoke(app, ["scan", str(source)]).exit_code == 0
    scanned = storage.shared_scan_path(source).read_bytes()

    result, out = _report(tmp_path, source)

    assert result.exit_code == 0, result.output
    assert storage.shared_scan_path(source).read_bytes() == scanned
    assert [item["id"] for item in _scan_document(storage, source)["datasets"]] == [
        "$.customers[]"
    ]
    assert [item["id"] for item in _profile(out, source)["datasets"]] == ["$.customers[]"]


def test_a_dominant_collection_needs_no_choice(tmp_path):
    big = math.ceil(parameters().DOMINANCE_RATIO * 2)
    source = write_json(tmp_path, "page.json", {"results": rows(big), "included": rows(2)})

    result, out = _report(tmp_path, source)

    assert result.exit_code == 0, result.output
    assert [item["id"] for item in _profile(out, source)["datasets"]] == ["$.results[]"]


# Ambiguity (CA-09, CA-10, EF-16, EF-17) --------------------------------------------


@pytest.mark.parametrize("command", ["scan", "report"])
def test_an_ambiguous_source_suspends_scan_and_report(tmp_path, storage, command):
    source = write_json(tmp_path, "shop.json", TWO)
    out = tmp_path / "out"

    result = runner.invoke(app, [command, str(source), "-d", str(out)])

    assert result.exit_code == 2
    assert "$.a[]" in result.output and "$.b[]" in result.output
    assert not out.exists() or not any(out.iterdir())
    assert not storage.shared_scan_path(source).exists()
    assert not _visible(source).exists()


def test_the_user_resolves_the_ambiguity_in_the_file(tmp_path, storage):
    source = write_json(tmp_path, "shop.json", TWO)
    assert _inspect(source).exit_code == 0
    edit_json_file(
        _visible(source),
        lambda d: d["config"].update(structure={"dataset_path": "$.b[]"}),
    )

    result, out = _report(tmp_path, source)

    assert result.exit_code == 0, result.output
    assert [item["id"] for item in _profile(out, source)["datasets"]] == ["$.b[]"]


def test_the_command_line_resolves_the_ambiguity(tmp_path, storage):
    source = write_json(tmp_path, "shop.json", TWO)

    result = runner.invoke(app, ["scan", str(source), "--collection", "$.a[]"])

    assert result.exit_code == 0, result.output
    assert [item["id"] for item in _scan_document(storage, source)["datasets"]] == ["$.a[]"]


# Visible configuration (CA-05, EF-09, EF-11) ------------------------------------------


def test_the_edited_file_changes_the_interpretation_and_the_identity(tmp_path, storage):
    source = write_json(tmp_path, "shop.json", SHOP)
    assert runner.invoke(app, ["scan", str(source)]).exit_code == 0
    first = _scan_document(storage, source)
    assert _inspect(source).exit_code == 0
    edit_json_file(_visible(source), lambda d: d["config"]["flatten"].update(separator="/"))

    result = runner.invoke(app, ["scan", str(source)])

    assert result.exit_code == 0, result.output
    second = _scan_document(storage, source)
    assert second["config"]["json"]["flatten"]["separator"] == "/"
    assert second["config_sha256"] != first["config_sha256"]
    displays = [item["display"] for item in second["datasets"][0]["fields"]]
    assert "address/city" in displays and "address.city" not in displays


def test_a_depth_limit_set_in_the_file_reaches_the_report(tmp_path):
    source = write_json(tmp_path, "shop.json", SHOP)
    assert _inspect(source).exit_code == 0
    edit_json_file(_visible(source), lambda d: d["config"]["flatten"].update(max_depth=1))

    result, out = _report(tmp_path, source)

    assert result.exit_code == 0, result.output
    names = [item["name"] for item in _profile(out, source)["datasets"][0]["columns"]]
    assert "address" in names
    assert "address.city" not in names


def test_a_root_array_runs_the_whole_cycle_with_the_visible_choices(tmp_path):
    # CA-07: inspect, edit, report on a root array of objects.
    source = write_json(
        tmp_path,
        "rows.json",
        [{"id": i, "address": {"city": "Lyon"}, "tags": ["a", "b"]} for i in range(1, 4)],
    )
    inspected = _inspect(source)
    assert inspected.exit_code == 0, inspected.output
    document = json.loads(_visible(source).read_text(encoding="utf-8"))
    assert document["config"]["structure"]["dataset_path"] == "$[]"
    edit_json_file(_visible(source), lambda d: d["config"]["flatten"].update(max_depth=1))

    result, out = _report(tmp_path, source)

    assert result.exit_code == 0, result.output
    profile = _profile(out, source)
    assert len(profile["datasets"]) == 1
    names = [item["name"] for item in profile["datasets"][0]["columns"]]
    assert "address" in names
    assert "address.city" not in names


def test_an_invalid_visible_file_stops_scan_and_report(tmp_path, storage):
    source = write_json(tmp_path, "shop.json", SHOP)
    assert _inspect(source).exit_code == 0
    edit_json_file(_visible(source), lambda d: d["config"]["arrays"].update(mode="explode"))
    before = _visible(source).read_bytes()

    for command in ("scan", "report"):
        result = runner.invoke(app, [command, str(source), "-d", str(tmp_path / "o")])
        assert result.exit_code == 2
        assert "arrays.mode" in result.output
    assert _visible(source).read_bytes() == before
    assert not storage.shared_inspect_path(source).exists()


# A changed source (CA-20, D06, I-T01) ----------------------------------------------------


def test_a_configured_path_that_disappeared_is_an_incompatibility(tmp_path, storage):
    source = write_json(tmp_path, "page.json", {"results": rows(3)})
    assert _inspect(source).exit_code == 0
    before = _visible(source).read_bytes()
    write_json(tmp_path, "page.json", {"records": rows(3)})
    out = tmp_path / "out"

    for command in ("scan", "report"):
        result = runner.invoke(app, [command, str(source), "-d", str(out)])
        assert result.exit_code == 2
        assert "$.results[]" in result.output
        assert "Inspect file" in result.output
    assert not storage.shared_scan_path(source).exists()
    assert not out.exists() or not any(out.iterdir())
    assert _visible(source).read_bytes() == before


def test_a_changed_source_keeps_the_choices_and_is_scanned_again(tmp_path, storage):
    source = write_json(tmp_path, "page.json", {"results": rows(3, city="Paris")})
    assert _inspect(source).exit_code == 0
    assert runner.invoke(app, ["scan", str(source)]).exit_code == 0
    first = storage.shared_scan_path(source).read_bytes()
    write_json(tmp_path, "page.json", {"results": rows(3, city="Lyons")})

    result = runner.invoke(app, ["scan", str(source)])

    assert result.exit_code == 0, result.output
    assert "different version of the source" in result.output
    assert storage.shared_scan_path(source).read_bytes() != first
    assert (
        _scan_document(storage, source)["source"]["sha256"]
        != json.loads(_visible(source).read_text(encoding="utf-8"))["source"]["sha256"]
    )


def test_the_recorded_hash_never_authorizes_a_reuse(tmp_path, storage):
    import os

    source = write_json(tmp_path, "page.json", {"results": rows(3, city="Paris")})
    assert _inspect(source).exit_code == 0
    assert runner.invoke(app, ["scan", str(source)]).exit_code == 0
    first = storage.shared_scan_path(source).read_bytes()
    stat = source.stat()
    write_json(tmp_path, "page.json", {"results": rows(3, city="Lyons")})
    assert source.stat().st_size == stat.st_size
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))

    assert runner.invoke(app, ["scan", str(source)]).exit_code == 0

    assert storage.shared_scan_path(source).read_bytes() != first


# JSONL (CA-18, CA-19) --------------------------------------------------------------------


def test_jsonl_scan_is_partial_but_successful_by_default(tmp_path, storage):
    source = write_text(tmp_path, "events.jsonl", '{"id": 1}\nnot json\n{"id": 3}\n')

    result = runner.invoke(app, ["scan", str(source)])

    assert result.exit_code == 0, result.output
    document = _scan_document(storage, source)
    assert document["status"] == "partial"
    assert document["source"]["format"] == "jsonl"
    assert document["scope"]["exclusions"] == {"invalid_line": 1}


def test_jsonl_strict_policy_set_in_the_file(tmp_path):
    source = write_text(tmp_path, "events.jsonl", '{"id": 1}\nnot json\n{"id": 3}\n')
    assert _inspect(source).exit_code == 0
    edit_json_file(_visible(source), lambda d: d["config"].update(errors={"policy": "strict"}))

    result = runner.invoke(app, ["scan", str(source)])

    assert result.exit_code == 4
    assert "line 2" in result.output


def test_jsonl_report_does_not_replace_a_sibling_json_source(tmp_path):
    write_json(tmp_path, "data.json", rows(2))
    source = write_jsonl(tmp_path, "data.jsonl", rows(2))
    out = tmp_path / "out"

    result = runner.invoke(app, ["report", str(source), "-d", str(out)])

    assert result.exit_code == 0, result.output
    assert (out / "data.report.html").is_file()
    assert (out / "data.report.json").is_file()


def test_same_stem_scan_outputs_collide_and_the_batch_is_rejected(tmp_path):
    write_json(tmp_path, "data.json", rows(2))
    write_jsonl(tmp_path, "data.jsonl", rows(2))
    out = tmp_path / "out"

    result = runner.invoke(
        app,
        ["scan", str(tmp_path / "data.json"), str(tmp_path / "data.jsonl"), "-d", str(out)],
    )

    assert result.exit_code != 0
    assert not out.exists() or not any(out.iterdir())


def test_the_entry_point_leaves_wildcard_expansion_to_tabalyst(monkeypatch):
    # Windows: an expanded "*.json" would hand over the Inspect files as paths.
    import importlib

    cli_app = importlib.import_module("tabalyst.cli.app")

    seen = {}
    monkeypatch.setattr(cli_app, "app", lambda **kwargs: seen.update(kwargs))
    cli_app.main()
    assert seen == {"windows_expand_args": False}

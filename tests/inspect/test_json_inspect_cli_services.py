# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON Inspect: the service, the Python API and the wiring of Scan and Report (lot JI-7).

Complements ``test_json_inspect_cli.py`` with what the design leaves to the
implementation: batch planning, the API, the review decisions of lot JI-6 and
the interplay with ``report --scan``.
"""

import json

import pytest
from inspect_helpers import edit_json_file, rows, write_json, write_jsonl, write_text
from typer.testing import CliRunner

import tabalyst
from tabalyst.cli import app
from tabalyst.errors import ConfigurationError, InputError
from tabalyst.projects.location import StorageLocation

pytestmark = pytest.mark.inspect_lot("JI-7")

runner = CliRunner()

SHOP = {"customers": [{"id": index, "address": {"city": "Lyon"}} for index in range(1, 4)]}
TWO = {"a": rows(3), "b": rows(2)}


@pytest.fixture(autouse=True)
def storage(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path / "storage"))
    return StorageLocation.local()


def _visible(source):
    return source.with_name(source.name + "-inspect.json")


def _config_file(tmp_path, document, name="settings.json"):
    return write_json(tmp_path, name, document)


def _invoke(*args):
    return runner.invoke(app, [str(item) for item in args])


# Planning (design 13) -------------------------------------------------------------


def test_a_batch_with_an_unknown_kind_is_rejected_before_any_reading(tmp_path):
    shop = write_json(tmp_path, "shop.json", SHOP)
    table = write_text(tmp_path, "table.csv", "id\n1\n")

    result = _invoke("inspect", shop, table)

    assert result.exit_code == 2
    assert "table.csv" in result.output
    assert not _visible(shop).exists()


def test_a_configuration_file_cannot_be_replaced_by_an_inspection(tmp_path):
    shop = write_json(tmp_path, "shop.json", SHOP)
    settings = _config_file(tmp_path, {}, "shop.json-inspect.json")

    result = _invoke("inspect", shop, "--config", settings)

    assert result.exit_code == 4
    assert "overwrite an input file" in result.output
    assert json.loads(settings.read_text(encoding="utf-8")) == {}


def test_inspect_rejects_quiet_with_verbose(tmp_path):
    shop = write_json(tmp_path, "shop.json", SHOP)

    assert _invoke("inspect", shop, "-q", "-v").exit_code == 2


def test_a_failed_source_does_not_stop_the_batch(tmp_path):
    broken = write_text(tmp_path, "broken.json", "[{")
    shop = write_json(tmp_path, "shop.json", SHOP)

    result = _invoke("inspect", broken, shop)

    assert result.exit_code == 4
    assert "1 succeeded, 1 failed" in result.output
    assert _visible(shop).is_file()
    assert not _visible(broken).exists()


def test_a_config_file_seeds_a_new_inspect_file(tmp_path):
    shop = write_json(tmp_path, "shop.json", SHOP)
    settings = _config_file(
        tmp_path, {"scan": {"json": {"flatten": {"separator": "/"}}}}
    )

    assert _invoke("inspect", shop, "-c", settings).exit_code == 0

    config = json.loads(_visible(shop).read_text(encoding="utf-8"))["config"]
    assert config["flatten"]["separator"] == "/"


def test_messages_name_what_is_kept_and_the_candidates(tmp_path):
    shop = write_json(tmp_path, "shop.json", TWO)
    assert _invoke("inspect", shop).exit_code == 0
    edit_json_file(
        _visible(shop), lambda d: d["config"].update(structure={"dataset_path": "$.b[]"})
    )

    result = _invoke("inspect", shop, "-v")

    assert result.exit_code == 0, result.output
    assert "Selection: none" in result.output
    assert "Configured collection: $.b[] (kept from the existing file)" in result.output
    assert "$.a[] (3 elements)" in result.output


def test_quiet_keeps_the_warnings(tmp_path):
    shop = write_json(tmp_path, "shop.json", TWO)

    result = _invoke("inspect", shop, "-q")

    assert result.exit_code == 0
    assert "Inspect:" not in result.output
    assert "equally plausible" in result.output


def test_ambiguous_selection_lists_a_report_command_per_collection(tmp_path):
    shop = write_json(tmp_path, "shop.json", TWO)

    result = _invoke("inspect", shop)

    assert "Choose the collection to analyze:" in result.output
    assert "tabalyst report" in result.output
    assert "--collection a" in result.output
    assert "--collection b" in result.output
    assert "--all-collections" in result.output


def test_report_takes_a_collection_by_path_or_by_name(tmp_path):
    shop = write_json(tmp_path, "shop.json", TWO)

    by_path = _invoke("report", shop, "--collection", "$.a[]", "-o", tmp_path / "a.html")
    by_name = _invoke("report", shop, "--collection", "b", "-o", tmp_path / "b.html")

    assert by_path.exit_code == 0, by_path.output
    assert by_name.exit_code == 0, by_name.output
    assert "$.a[]" in (tmp_path / "a.json").read_text(encoding="utf-8")
    assert "$.b[]" in (tmp_path / "b.json").read_text(encoding="utf-8")


def test_collection_short_form_is_a_path_without_dollar_and_brackets():
    from tabalyst.cli.terminal import collection_paths

    assert collection_paths(["products", "data.items", "data.items[]", "$.a[]"]) == [
        "$.products[]",
        "$.data.items[]",
        "$.data.items[]",
        "$.a[]",
    ]
    assert collection_paths([".", "[]"]) == ["$[]", "$[]"]
    assert collection_paths(['["a.b"]']) == ['$["a.b"][]']
    assert collection_paths(["groups.121", "121.items"]) == [
        '$.groups["121"][]',
        '$["121"].items[]',
    ]
    assert collection_paths(None) is None


def test_report_refuses_a_collection_with_a_scan_document(tmp_path):
    shop = write_json(tmp_path, "shop.json", TWO)

    result = _invoke("report", shop, "--scan", "--collection", "a")

    assert result.exit_code == 2
    assert "--collection cannot be used with --scan" in result.output


# The Python API ---------------------------------------------------------------------


def test_inspect_writes_the_visible_file_and_returns_it(tmp_path, storage):
    shop = write_json(tmp_path, "shop.json", SHOP)

    outcome = tabalyst.inspect(shop)

    assert outcome.path == _visible(shop)
    assert outcome.source == shop
    assert outcome.document.detection.selection.path == "$.customers[]"
    written = json.loads(outcome.path.read_text(encoding="utf-8"))
    assert written == outcome.document.model_dump(mode="json")
    assert not storage.shared_inspect_path(shop).exists()


def test_inspect_returns_the_document_as_written_on_reinspection(tmp_path):
    shop = write_json(tmp_path, "shop.json", TWO)
    tabalyst.inspect(shop)
    edit_json_file(
        _visible(shop), lambda d: d["config"].update(structure={"dataset_path": "$.zz[]"})
    )

    outcome = tabalyst.inspect(shop)

    assert outcome.document.config.structure.dataset_path == "$.zz[]"
    assert "configured_path_not_found" in [item.code for item in outcome.document.warnings]
    written = json.loads(outcome.path.read_text(encoding="utf-8"))
    assert written["warnings"] == outcome.document.model_dump(mode="json")["warnings"]


def test_inspect_raises_where_the_batch_reports(tmp_path):
    broken = write_text(tmp_path, "broken.json", "[{")
    shop = write_json(tmp_path, "shop.json", SHOP)

    with pytest.raises(InputError):
        tabalyst.inspect(broken)
    with pytest.raises(ConfigurationError):
        tabalyst.inspect(write_text(tmp_path, "table.csv", "id\n1\n"))

    batch = tabalyst.generate_inspections([broken, shop])
    assert not batch.succeeded
    assert [item.source for item in batch.successes] == [shop]
    assert [type(item.error) for item in batch.failures] == [InputError]


def test_inspect_refuses_an_invalid_file_before_reading_the_source(tmp_path, monkeypatch):
    shop = write_json(tmp_path, "shop.json", SHOP)
    tabalyst.inspect(shop)
    edit_json_file(_visible(shop), lambda d: d["config"]["flatten"].update(separator="ab"))
    monkeypatch.setattr(
        "tabalyst.inspect_service.inspect_source",
        lambda *args, **kwargs: pytest.fail("the source was read"),
    )

    with pytest.raises(ConfigurationError):
        tabalyst.inspect(shop)


def test_generate_scans_resolves_json_like_the_command(tmp_path):
    shop = write_json(tmp_path, "shop.json", SHOP)
    ambiguous = write_json(tmp_path, "two.json", TWO)

    batch = tabalyst.generate_scans([shop, ambiguous], output_dir=tmp_path / "scans")

    assert [item.job.source for item in batch.successes] == [shop]
    assert [item.result.datasets[0].id for item in batch.successes] == ["$.customers[]"]
    assert len(batch.failures) == 1
    assert isinstance(batch.failures[0].error, ConfigurationError)
    assert not (tmp_path / "scans" / "two.scan.json").exists()


# Review decisions of lot JI-6 -------------------------------------------------------------


@pytest.mark.parametrize("how", ["command_line", "config_file"])
def test_a_collection_that_is_already_decided_skips_the_automatic_inspection(
    tmp_path, storage, how
):
    source = write_json(tmp_path, "two.json", TWO)
    args = ["scan", source]
    if how == "command_line":
        args += ["--collection", "$.b[]"]
    else:
        args += ["-c", _config_file(tmp_path, {"scan": {"json": {"collections": ["$.b[]"]}}})]

    result = _invoke(*args)

    assert result.exit_code == 0, result.output
    document = json.loads(storage.shared_scan_path(source).read_text(encoding="utf-8"))
    assert [item["id"] for item in document["datasets"]] == ["$.b[]"]
    assert not storage.shared_inspect_path(source).exists()


def test_the_source_is_hashed_once_to_validate_the_cache_and_the_scan(
    tmp_path, monkeypatch
):
    source = write_json(tmp_path, "shop.json", SHOP)
    assert _invoke("report", source, "-d", tmp_path / "out").exit_code == 0
    calls = []
    from tabalyst import scan_reuse
    from tabalyst.inspector import resolution

    for module in (resolution, scan_reuse):
        original = module.file_sha256

        def counted(path, original=original):
            calls.append(path)
            return original(path)

        monkeypatch.setattr(module, "file_sha256", counted)

    result = _invoke("report", source, "-d", tmp_path / "out", "--force")

    assert result.exit_code == 0, result.output
    assert len(calls) == 1


def test_a_suspension_still_says_that_the_cache_could_not_be_written(tmp_path, monkeypatch):
    source = write_json(tmp_path, "two.json", TWO)
    monkeypatch.setattr(
        "tabalyst.inspector.resolution.write_inspect_cache",
        lambda *args: "Could not write the Inspect cache here.",
    )

    result = _invoke("scan", source)

    assert result.exit_code == 2
    assert "Could not write the Inspect cache here." in result.output


# Scan and Report share one stored scan --------------------------------------------------


@pytest.mark.parametrize("make", [write_json, write_jsonl])
def test_report_reuses_the_stored_scan_while_nothing_changes(tmp_path, storage, make):
    name = "data.json" if make is write_json else "data.jsonl"
    source = make(tmp_path, name, rows(3))
    assert _invoke("report", source, "-d", tmp_path / "out").exit_code == 0
    stored = storage.shared_scan_path(source).read_bytes()

    again = _invoke("report", source, "-d", tmp_path / "out", "--force")

    assert again.exit_code == 0, again.output
    assert storage.shared_scan_path(source).read_bytes() == stored


def test_an_edited_inspect_file_makes_report_scan_again(tmp_path, storage):
    source = write_json(tmp_path, "shop.json", SHOP)
    assert _invoke("report", source, "-d", tmp_path / "out").exit_code == 0
    stored = storage.shared_scan_path(source).read_bytes()
    assert _invoke("inspect", source).exit_code == 0
    edit_json_file(_visible(source), lambda d: d["config"]["flatten"].update(separator="/"))

    result = _invoke("report", source, "-d", tmp_path / "out", "--force")

    assert result.exit_code == 0, result.output
    assert storage.shared_scan_path(source).read_bytes() != stored


def test_a_command_line_collection_that_overrides_the_file_is_announced(tmp_path):
    source = write_json(tmp_path, "two.json", TWO)
    assert _invoke("inspect", source).exit_code == 0
    edit_json_file(
        _visible(source), lambda d: d["config"].update(structure={"dataset_path": "$.a[]"})
    )

    result = _invoke("scan", source, "--collection", "$.b[]")

    assert result.exit_code == 0, result.output
    assert "--collection overrides config.structure.dataset_path ($.a[])" in result.output


def test_explicit_inspect_files_are_refused_by_every_command(tmp_path):
    source = write_json(tmp_path, "shop.json", SHOP)
    assert _invoke("inspect", source).exit_code == 0

    for command in ("scan", "report"):
        refused = _invoke(command, _visible(source))
        assert refused.exit_code == 2
        assert "Inspect file" in refused.output


# A mixed batch (finding of the review of lot JI-4) ----------------------------------------------


def test_json_collections_of_a_config_file_apply_to_json_sources_only(tmp_path, storage):
    two = write_json(tmp_path, "two.json", TWO)
    events = write_jsonl(tmp_path, "events.jsonl", rows(2))
    settings = _config_file(tmp_path, {"scan": {"json": {"collections": ["$.b[]"]}}})

    result = _invoke("scan", two, events, "-c", settings)

    assert result.exit_code == 0, result.output
    for source, wanted in ((two, "$.b[]"), (events, "$[]")):
        document = json.loads(storage.shared_scan_path(source).read_text(encoding="utf-8"))
        assert [item["id"] for item in document["datasets"]] == [wanted]


def test_a_command_line_collection_that_a_jsonl_source_cannot_have_fails_alone(
    tmp_path, storage
):
    two = write_json(tmp_path, "two.json", TWO)
    events = write_jsonl(tmp_path, "events.jsonl", rows(2))

    result = _invoke("scan", two, events, "--collection", "$.b[]")

    assert result.exit_code == 2
    assert "events.jsonl" in result.output and "1 succeeded, 1 failed" in result.output
    assert storage.shared_scan_path(two).is_file()
    assert not storage.shared_scan_path(events).exists()


# report --scan (design 10.2) --------------------------------------------------------------------


def _scan_beside(tmp_path, source):
    output = tmp_path / "shop.scan.json"
    assert _invoke("scan", source, "-o", output).exit_code == 0
    return output


def test_report_scan_stays_quiet_when_the_inspect_file_matches_the_document(tmp_path):
    source = write_json(tmp_path, "shop.json", SHOP)
    document = _scan_beside(tmp_path, source)
    assert _invoke("inspect", source).exit_code == 0

    result = _invoke("report", "--scan", document, "-d", tmp_path / "out")

    assert result.exit_code == 0, result.output
    assert "Inspect file" not in result.output


def test_report_scan_warns_when_the_inspect_file_asks_for_other_settings(tmp_path):
    source = write_json(tmp_path, "shop.json", SHOP)
    document = _scan_beside(tmp_path, source)
    assert _invoke("inspect", source).exit_code == 0
    edit_json_file(_visible(source), lambda d: d["config"]["flatten"].update(separator="/"))

    result = _invoke("report", "--scan", document, "-d", tmp_path / "out")

    assert result.exit_code == 0, result.output
    assert "shop.json-inspect.json sets a configuration that differs" in result.output


def test_report_scan_does_not_stop_on_an_invalid_inspect_file(tmp_path):
    source = write_json(tmp_path, "shop.json", SHOP)
    document = _scan_beside(tmp_path, source)
    assert _invoke("inspect", source).exit_code == 0
    edit_json_file(_visible(source), lambda d: d["config"]["arrays"].update(mode="explode"))

    result = _invoke("report", "--scan", document, "-d", tmp_path / "out")

    assert result.exit_code == 0, result.output
    assert "not compared with the scan document" in result.output


def test_report_scan_ignores_a_jsonl_dataset_written_in_the_inspect_file(tmp_path):
    source = write_jsonl(tmp_path, "events.jsonl", rows(2))
    document = tmp_path / "events.scan.json"
    assert _invoke("scan", source, "-o", document).exit_code == 0
    assert _invoke("inspect", source).exit_code == 0
    config = json.loads(_visible(source).read_text(encoding="utf-8"))["config"]
    assert config["structure"]["dataset_path"] == "$[]"

    result = _invoke("report", "--scan", document, "-d", tmp_path / "out")

    assert result.exit_code == 0, result.output
    assert "Inspect file" not in result.output

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Persistence and resolution beyond the contract (lot JI-6).

Cases the contract tests do not pin: the cache and the search depth, a cache
that cannot be written, a non-judgeable path on re-inspection, CSV and JSONL in
the resolver, hash sharing and stable text.
"""

import json

import pytest
from inspect_helpers import (
    edit_json_file,
    inspect_object,
    rows,
    write_json,
    write_jsonl,
    write_text,
)

from tabalyst import scan_reuse
from tabalyst.errors import ConfigurationError, InputError, ReportError
from tabalyst.inspector.persistence import (
    inspect_path,
    read_inspect_cache,
    read_visible_inspect,
    write_inspection,
)
from tabalyst.inspector.resolution import resolve_interpretation
from tabalyst.projects.location import StorageLocation
from tabalyst.scanner.config import config_sha256

pytestmark = pytest.mark.inspect_lot("JI-6")

DEEP = {"a": {"b": {"c": {"d": rows(3)}}}}  # four keys: below the default depth


@pytest.fixture
def location(tmp_path):
    return StorageLocation(tmp_path / "storage")


def _text(path):
    return json.loads(path.read_text(encoding="utf-8"))


# The cache and the search depth -----------------------------------------------


def test_a_cache_made_at_another_discovery_depth_is_not_reused(tmp_path, location):
    source = write_json(tmp_path, "deep.json", DEEP)
    with pytest.raises(ConfigurationError, match="json.discovery_max_depth"):
        resolve_interpretation(source, location=location)

    deeper = {"json": {"discovery_max_depth": 4}}
    result = resolve_interpretation(source, scan_layer=deeper, location=location)

    assert result.origin == "automatic"
    assert result.config.json_.collections == ["$.a.b.c.d[]"]
    cached = read_inspect_cache(location.shared_inspect_path(source))
    assert cached.detection.scope.discovery_max_depth == 4
    assert resolve_interpretation(source, scan_layer=deeper, location=location).origin == "cache"


def test_a_cache_that_cannot_be_written_is_a_notice(tmp_path):
    blocked = tmp_path / "storage"
    blocked.write_text("a file where the storage root should be", encoding="utf-8")
    source = write_json(tmp_path, "page.json", {"results": rows(3)})

    result = resolve_interpretation(source, location=StorageLocation(blocked))

    assert result.origin == "automatic"
    assert result.config.json_.collections == ["$.results[]"]
    assert any("Inspect cache" in notice for notice in result.notices)


def test_a_known_hash_is_not_computed_again(tmp_path, location, monkeypatch):
    source = write_json(tmp_path, "page.json", {"results": rows(3)})
    first = resolve_interpretation(source, location=location)
    sha = _text(location.shared_inspect_path(source))["source"]["sha256"]

    def fail(path):
        raise AssertionError("the source was hashed again")

    monkeypatch.setattr(scan_reuse, "file_sha256", fail)
    monkeypatch.setattr("tabalyst.inspector.resolution.file_sha256", fail)
    second = resolve_interpretation(source, location=location, source_sha256=sha)

    assert second.origin == "cache"
    assert second.config == first.config


def test_a_size_that_differs_is_enough_to_rebuild_the_cache(tmp_path, location, monkeypatch):
    source = write_json(tmp_path, "page.json", {"results": rows(3)})
    resolve_interpretation(source, location=location)
    write_json(tmp_path, "page.json", {"results": rows(4)})

    def fail(path):
        raise AssertionError("a different size needs no hash")

    monkeypatch.setattr("tabalyst.inspector.resolution.file_sha256", fail)

    assert resolve_interpretation(source, location=location).origin == "automatic"


def test_an_invalid_source_leaves_no_cache(tmp_path, location):
    source = write_text(tmp_path, "broken.json", '{"results": [{"id": 1},')

    with pytest.raises(InputError):
        resolve_interpretation(source, location=location)

    assert not location.shared_inspect_path(source).exists()


def test_an_invalid_visible_file_stops_the_resolution(tmp_path, location):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    inspect_path(source).write_text('{"format": "tabalyst.inspect"}', encoding="utf-8")

    with pytest.raises(ConfigurationError, match="shop.json-inspect.json"):
        resolve_interpretation(source, location=location)

    assert not location.shared_inspect_path(source).exists()


# The visible file ---------------------------------------------------------


def test_a_byte_order_mark_in_the_visible_file_is_accepted(tmp_path):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    path = write_inspection(source, inspect_object(source))
    path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())

    assert read_visible_inspect(path).config.structure.dataset_path == "$.customers[]"


def test_two_inspections_of_the_same_source_differ_only_by_the_date(tmp_path):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    path = write_inspection(source, inspect_object(source))
    first = _text(path)

    write_inspection(source, inspect_object(source))

    second = _text(path)
    assert first["inspect"].pop("generated_at") <= second["inspect"].pop("generated_at")
    assert first == second


def test_the_inspection_replaces_a_text_it_formatted_itself(tmp_path):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    path = write_inspection(source, inspect_object(source))
    edit_json_file(path, lambda document: document["config"]["flatten"].update(separator="/"))

    write_inspection(source, inspect_object(source))

    text = path.read_text(encoding="utf-8")
    assert text.startswith('{\n  "format"') and text.endswith("}\n")
    assert _text(path)["config"]["flatten"]["separator"] == "/"


@pytest.mark.parametrize(
    "chosen",
    ["$.a[].b[]", "$.a.b.c.d[]"],  # crosses an array; deeper than the discovery depth
)
def test_a_path_the_candidates_cannot_judge_is_not_warned_about(tmp_path, chosen):
    source = write_json(tmp_path, "shop.json", {"a": rows(2), "z": rows(2)})
    path = write_inspection(source, inspect_object(source))
    edit_json_file(path, lambda d: d["config"].update(structure={"dataset_path": chosen}))

    write_inspection(source, inspect_object(source))

    assert not [w for w in _text(path)["warnings"] if w["code"] == "configured_path_not_found"]


def test_a_missing_jsonl_path_is_judged(tmp_path):
    source = write_jsonl(tmp_path, "events.jsonl", rows(2))
    path = write_inspection(source, inspect_object(source))
    edit_json_file(path, lambda d: d["config"].update(structure={"dataset_path": "$.a[]"}))

    write_inspection(source, inspect_object(source))

    codes = [w["code"] for w in _text(path)["warnings"]]
    assert "configured_path_not_found" in codes


def test_reset_config_does_not_warn_about_the_path_it_replaces(tmp_path):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    path = write_inspection(source, inspect_object(source))
    edit_json_file(path, lambda d: d["config"].update(structure={"dataset_path": "$.gone[]"}))

    write_inspection(source, inspect_object(source), reset_config=True)

    document = _text(path)
    assert document["config"]["structure"] == {"dataset_path": "$.customers[]"}
    assert not [w for w in document["warnings"] if w["code"] == "configured_path_not_found"]


def test_a_directory_in_place_of_the_file_is_an_invalid_file(tmp_path):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    inspect_path(source).mkdir()

    with pytest.raises(ConfigurationError):
        write_inspection(source, inspect_object(source))


def test_a_dangling_link_is_not_replaced_silently(tmp_path):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    try:
        inspect_path(source).symlink_to(tmp_path / "missing.json")
    except OSError:
        pytest.skip("symbolic links are not available")

    with pytest.raises(ConfigurationError):
        write_inspection(source, inspect_object(source))

    assert inspect_path(source).is_symlink()


def test_a_failed_write_is_an_error_of_the_action(tmp_path, monkeypatch):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})

    def fail(path, content):
        raise PermissionError("denied")

    monkeypatch.setattr("tabalyst.inspector.persistence.write_text_atomic", fail)

    with pytest.raises(ReportError, match="Cannot write Inspect file"):
        write_inspection(source, inspect_object(source))

    assert not inspect_path(source).exists()


# The resolver for other formats ---------------------------------------------


def test_a_csv_source_has_no_inspect(tmp_path, location):
    source = write_text(tmp_path, "data.csv", "a;b\n1;2\n")

    result = resolve_interpretation(source, delimiter=";", location=location)

    assert result.origin == "none" and result.collection_origin == "none"
    assert result.config.csv.delimiter == ";"
    assert not location.root.exists()
    assert not inspect_path(source).exists()


def test_a_written_jsonl_file_does_not_change_the_rules_applied(tmp_path, location):
    source = write_jsonl(tmp_path, "events.jsonl", rows(2))
    before = resolve_interpretation(source, location=location).config

    write_inspection(source, inspect_object(source))  # writes dataset_path "$[]"
    after = resolve_interpretation(source, location=location)

    assert after.origin == "visible"
    assert config_sha256(after.config) == config_sha256(before)


def test_a_command_line_path_equal_to_the_visible_one_is_not_a_notice(tmp_path, location):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    write_inspection(source, inspect_object(source))

    result = resolve_interpretation(source, collections=['$["customers"][]'], location=location)

    assert result.collection_origin == "command_line"
    assert result.notices == ()


def test_the_origin_of_the_collection_follows_the_layer_that_decided(tmp_path, location):
    source = write_json(tmp_path, "shop.json", {"a": rows(3), "b": rows(3)})
    write_inspection(source, inspect_object(source))  # ambiguous: no path

    from_layer = resolve_interpretation(
        source, scan_layer={"json": {"collections": ["$.b[]"]}}, location=location
    )

    assert from_layer.origin == "visible"
    assert from_layer.collection_origin == "config_file"

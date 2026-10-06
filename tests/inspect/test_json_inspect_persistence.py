# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON Inspect contract: visible file, cache and resolution (lot JI-6).

Design sections 4.6, 11 and 12: naming, atomic writing, re-inspection that
keeps the user's choices, layers of configuration, automatic cache.
"""

import json
import math
from pathlib import Path

import pytest
from inspect_helpers import (
    edit_json_file,
    inspect_document,
    inspect_object,
    parameters,
    rows,
    write_json,
    write_jsonl,
)

from tabalyst.errors import ConfigurationError
from tabalyst.projects.location import StorageLocation
from tabalyst.scanner import scan

pytestmark = pytest.mark.inspect_lot("JI-6")

TWO = {"a": rows(3), "b": rows(3)}  # equally plausible: nothing is selected


def _persistence():
    from tabalyst.inspector import persistence

    return persistence


def _resolution():
    from tabalyst.inspector import resolution

    return resolution


def _write(source: Path, **settings) -> Path:
    return _persistence().write_inspection(source, inspect_object(source, **settings))


def _resolve(source: Path, location, **options):
    return _resolution().resolve_interpretation(source, location=location, **options)


@pytest.fixture
def location(tmp_path):
    return StorageLocation(tmp_path / "storage")


def _dominated(tmp_path, name="dom.json"):
    """A source where ``a`` is selected automatically over ``b``."""
    ratio = parameters().DOMINANCE_RATIO
    return write_json(
        tmp_path, name, {"a": rows(math.ceil(ratio * 2)), "b": rows(2)}
    )


# Names (CA-01, CA-02, D02) -------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("clients.json", "clients.json-inspect.json"),
        ("events.jsonl", "events.jsonl-inspect.json"),
        ("events.ndjson", "events.ndjson-inspect.json"),
        ("My Data.v2.json", "My Data.v2.json-inspect.json"),
        ("DATA.JSON", "DATA.JSON-inspect.json"),
    ],
)
def test_the_name_is_the_full_source_name_plus_a_suffix(tmp_path, source, expected):
    path = _persistence().inspect_path(tmp_path / source)

    assert path == tmp_path / expected


def test_sources_with_the_same_stem_have_distinct_inspect_files(tmp_path):
    inspect_path = _persistence().inspect_path
    names = {
        inspect_path(tmp_path / name).name
        for name in ("data.json", "data.jsonl", "data.ndjson")
    }

    assert len(names) == 3


def test_the_visible_file_is_written_beside_the_source(tmp_path):
    source = write_json(tmp_path, "clients.json", {"customers": rows(2)})

    path = _write(source)

    assert path == tmp_path / "clients.json-inspect.json"
    text = path.read_text(encoding="utf-8")
    document = json.loads(text)
    assert list(document)[-1] == "config"
    assert text.endswith("\n")
    assert text.startswith('{\n  "format"')
    assert str(tmp_path) not in text


def test_writing_leaves_no_temporary_file(tmp_path):
    source = write_json(tmp_path, "clients.json", rows(2))

    _write(source)

    assert sorted(item.name for item in tmp_path.iterdir()) == [
        "clients.json",
        "clients.json-inspect.json",
    ]


# Re-inspection (CA-04, D05, EF-07) -----------------------------------------


def test_reinspection_refreshes_the_detection_and_keeps_the_choices(tmp_path):
    source = write_json(tmp_path, "shop.json", TWO)
    path = _write(source)
    edited = edit_json_file(
        path,
        lambda document: document["config"].update(
            structure={"dataset_path": "$.b[]"},
            flatten={"enabled": True, "separator": "/", "max_depth": 3},
        ),
    )
    write_json(tmp_path, "shop.json", {**TWO, "c": rows(3)})

    _write(source)

    after = json.loads(path.read_text(encoding="utf-8"))
    assert [item["path"] for item in after["detection"]["candidates"]] == [
        "$.a[]",
        "$.b[]",
        "$.c[]",
    ]
    assert after["config"] == edited["config"]
    assert list(after["config"]) == list(edited["config"])
    assert after["source"]["size_bytes"] == source.stat().st_size


def test_a_partial_config_stays_partial(tmp_path):
    source = write_json(tmp_path, "shop.json", TWO)
    path = _write(source)
    edit_json_file(path, lambda document: document.update(config={"flatten": {"separator": "/"}}))

    _write(source)

    assert json.loads(path.read_text(encoding="utf-8"))["config"] == {
        "flatten": {"separator": "/"}
    }


def test_reset_config_regenerates_the_choices(tmp_path):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    path = _write(source)
    edit_json_file(path, lambda document: document["config"]["flatten"].update(separator="/"))

    _persistence().write_inspection(source, inspect_object(source), reset_config=True)

    assert json.loads(path.read_text(encoding="utf-8"))["config"]["flatten"]["separator"] == "."


def test_a_preserved_path_missing_from_the_new_source_is_a_warning(tmp_path):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2), "orders": rows(2)})
    path = _write(source)
    edit_json_file(
        path, lambda document: document["config"].update(structure={"dataset_path": "$.orders[]"})
    )
    write_json(tmp_path, "shop.json", {"customers": rows(2)})

    _write(source)

    after = json.loads(path.read_text(encoding="utf-8"))
    codes = {item["code"]: item for item in after["warnings"]}
    assert codes["configured_path_not_found"]["path"] == "$.orders[]"
    assert after["config"]["structure"] == {"dataset_path": "$.orders[]"}


def test_a_file_renamed_with_its_source_keeps_working(tmp_path):
    source = write_json(tmp_path, "old.json", {"customers": rows(2)})
    old = _write(source)
    copy = write_json(tmp_path, "new.json", {"customers": rows(2)})
    target = _persistence().inspect_path(copy)
    target.write_bytes(old.read_bytes())

    _write(copy)

    warnings = json.loads(target.read_text(encoding="utf-8"))["warnings"]
    mismatch = [item for item in warnings if item["code"] == "source_name_mismatch"]
    assert mismatch and mismatch[0]["level"] == "info"
    assert mismatch[0]["path"] == "old.json"


# Files that are not overwritten (I-E01) ---------------------------------------

BROKEN = {
    "invalid separator": lambda d: d["config"]["flatten"].update(separator="ab"),
    "unknown key": lambda d: d["config"].update(surprise=1),
    "unsupported mode": lambda d: d["config"]["arrays"].update(mode="explode"),
    "unsupported revision": lambda d: d.update(format_revision=999),
    "unsupported version": lambda d: d.update(format_version="0.1.0a"),
    "other format": lambda d: d.update(format="tabalyst.scan"),
    "unknown kind": lambda d: d["inspect"].update(kind="csv"),
}


@pytest.mark.parametrize("name", list(BROKEN))
def test_an_invalid_visible_file_is_never_replaced(tmp_path, name):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    path = _write(source)
    edit_json_file(path, BROKEN[name])
    before = path.read_bytes()

    with pytest.raises(ConfigurationError):
        _write(source)

    assert path.read_bytes() == before


def test_a_file_that_is_not_json_is_never_replaced(tmp_path):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    path = _persistence().inspect_path(source)
    path.write_text("not json at all", encoding="utf-8")

    with pytest.raises(ConfigurationError):
        _write(source)

    assert path.read_text(encoding="utf-8") == "not json at all"


@pytest.mark.parametrize("name", list(BROKEN))
def test_force_replaces_an_invalid_file(tmp_path, name):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    path = _write(source)
    edit_json_file(path, BROKEN[name])

    _persistence().write_inspection(source, inspect_object(source), force=True)

    document = json.loads(path.read_text(encoding="utf-8"))
    assert document["format_revision"] == 1
    assert document["config"]["flatten"]["separator"] == "."


# Reading the visible file (CA-28, ET-02) --------------------------------------


def _read(path):
    return _persistence().read_visible_inspect(path)


def test_a_valid_file_is_read(tmp_path):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    visible = _read(_write(source))

    assert visible.kind == "json"
    assert visible.config.structure.dataset_path == "$.customers[]"
    assert visible.recorded_name == "shop.json"
    assert visible.recorded_sha256 == inspect_document(source)["source"]["sha256"]


@pytest.mark.parametrize(
    ("edit", "fragment"),
    [
        (lambda d: d.update(format_revision=999), "format_revision"),
        (lambda d: d.update(format_version="9.9.9"), "format_version"),
        (lambda d: d["inspect"].update(kind="csv"), "kind"),
        (lambda d: d["config"]["flatten"].update(sepator="/"), "config.flatten.sepator"),
        (lambda d: d["config"]["flatten"].update(enabled="true"), "config.flatten.enabled"),
        (lambda d: d["config"]["arrays"].update(mode="explode"), "not supported"),
        (lambda d: d.pop("config"), "config"),
    ],
)
def test_unsupported_or_invalid_files_are_refused_clearly(tmp_path, edit, fragment):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    path = _write(source)
    edit_json_file(path, edit)

    with pytest.raises(ConfigurationError) as error:
        _read(path)

    assert fragment in str(error.value)
    assert path.name in str(error.value)


def test_informative_zones_do_not_have_to_be_valid(tmp_path):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    path = _write(source)
    edit_json_file(
        path,
        lambda d: d.update(detection="damaged", warnings=3, source={"sha256": 7}),
    )

    visible = _read(path)

    assert visible.config.structure.dataset_path == "$.customers[]"
    assert visible.recorded_sha256 is None


# Resolution: layers (D04, EF-09, EF-10) ------------------------------------------


def test_no_file_means_automatic_inspection_then_the_cache(tmp_path, location):
    source = write_json(tmp_path, "page.json", {"results": rows(3)})

    first = _resolve(source, location)
    cache = location.shared_inspect_path(source)
    cached = cache.read_bytes()
    second = _resolve(source, location)

    assert first.origin == "automatic"
    assert second.origin == "cache"
    assert first.config.json_.collections == ["$.results[]"]
    assert second.config == first.config
    assert cache.read_bytes() == cached
    assert not _persistence().inspect_path(source).exists()
    assert first.inspect_path is None


def test_the_cache_is_written_beside_the_scan_cache(tmp_path, location):
    source = write_json(tmp_path, "page.json", {"results": rows(3)})
    _resolve(source, location)

    assert location.shared_inspect_path(source).parent == location.shared_scan_path(source).parent
    assert location.shared_inspect_path(source).name == "inspect.json"


def test_the_visible_file_beats_the_cache(tmp_path, location):
    source = _dominated(tmp_path)
    assert _resolve(source, location).config.json_.collections == ["$.a[]"]
    path = _write(source)
    edit_json_file(path, lambda d: d["config"].update(structure={"dataset_path": "$.b[]"}))
    cache_before = location.shared_inspect_path(source).read_bytes()

    result = _resolve(source, location)

    assert result.origin == "visible"
    assert result.inspect_path == path
    assert result.config.json_.collections == ["$.b[]"]
    assert location.shared_inspect_path(source).read_bytes() == cache_before


def test_resolution_never_touches_the_visible_file(tmp_path, location):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    path = _write(source)
    before, stamp = path.read_bytes(), path.stat().st_mtime_ns

    _resolve(source, location)

    assert path.read_bytes() == before
    assert path.stat().st_mtime_ns == stamp


def test_config_files_beat_the_automatic_detection(tmp_path, location):
    source = _dominated(tmp_path)

    result = _resolve(source, location, scan_layer={"json": {"collections": ["$.b[]"]}})

    assert result.config.json_.collections == ["$.b[]"]


def test_the_visible_file_beats_config_files(tmp_path, location):
    source = _dominated(tmp_path)
    path = _write(source)
    edit_json_file(path, lambda d: d["config"].update(structure={"dataset_path": "$.a[]"}))

    result = _resolve(source, location, scan_layer={"json": {"collections": ["$.b[]"]}})

    assert result.config.json_.collections == ["$.a[]"]


def test_command_line_beats_the_visible_file_and_says_so(tmp_path, location):
    source = _dominated(tmp_path)
    _write(source)

    result = _resolve(source, location, collections=["$.b[]"])

    assert result.config.json_.collections == ["$.b[]"]
    assert any("--collection" in notice for notice in result.notices)


def test_omitted_keys_inherit_and_present_keys_win(tmp_path, location):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    path = _write(source)
    layer = {"errors": {"policy": "tolerant"}, "json": {"flatten": {"separator": "/"}}}
    edit_json_file(path, lambda d: d["config"].update(flatten={"enabled": True}))
    edit_json_file(path, lambda d: d["config"].pop("errors"))

    result = _resolve(source, location, scan_layer=layer)

    assert result.config.errors.policy == "tolerant"  # omitted in the file
    assert result.config.json_.flatten.separator == "/"  # omitted in the file
    edit_json_file(
        path, lambda d: d["config"].update(flatten={"separator": "|"}, errors={"policy": "strict"})
    )
    result = _resolve(source, location, scan_layer=layer)
    assert result.config.errors.policy == "strict"
    assert result.config.json_.flatten.separator == "|"


def test_a_null_policy_in_the_file_means_the_default_of_the_format(tmp_path, location):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})
    path = _write(source)
    edit_json_file(path, lambda d: d["config"].update(errors={"policy": None}))

    result = _resolve(source, location, scan_layer={"errors": {"policy": "tolerant"}})

    assert result.config.errors.policy == "strict"


def test_an_undecided_path_lets_a_lower_layer_choose(tmp_path, location):
    source = write_json(tmp_path, "shop.json", TWO)
    _write(source)

    result = _resolve(source, location, scan_layer={"json": {"collections": ["$.b[]"]}})

    assert result.config.json_.collections == ["$.b[]"]


def test_the_visible_file_seeds_from_the_config_files(tmp_path):
    source = write_json(tmp_path, "shop.json", {"customers": rows(2)})

    path = _write(source, json={"flatten": {"separator": "/"}})

    assert json.loads(path.read_text(encoding="utf-8"))["config"]["flatten"]["separator"] == "/"


# Nothing selected (DP-13, EF-16) ----------------------------------------------


@pytest.mark.parametrize("with_file", [False, True])
def test_an_ambiguous_source_suspends_with_its_candidates(tmp_path, location, with_file):
    source = write_json(tmp_path, "shop.json", TWO)
    if with_file:
        _write(source)

    with pytest.raises(ConfigurationError) as error:
        _resolve(source, location)

    message = str(error.value)
    assert "$.a[]" in message and "$.b[]" in message
    if with_file:
        assert "dataset_path" in message and "shop.json-inspect.json" in message
    else:
        assert "--collection" in message and "tabalyst inspect" in message


def test_a_source_without_a_collection_suspends(tmp_path, location):
    source = write_json(tmp_path, "one.json", {"id": 1})

    with pytest.raises(ConfigurationError, match="collection"):
        _resolve(source, location)


def test_jsonl_has_nothing_to_detect(tmp_path, location):
    source = write_jsonl(tmp_path, "events.jsonl", rows(2))

    result = _resolve(source, location)

    assert result.origin == "none"
    assert result.config.json_.collections in (None, ["$[]"])
    assert result.config.errors.policy == "tolerant"
    assert not location.shared_inspect_path(source).exists()


def test_a_visible_file_may_set_the_policy_of_a_jsonl_source(tmp_path, location):
    source = write_jsonl(tmp_path, "events.jsonl", rows(2))
    path = _write(source)
    edit_json_file(path, lambda d: d["config"].update(errors={"policy": "strict"}))

    result = _resolve(source, location)

    assert result.origin == "visible"
    assert result.config.errors.policy == "strict"


def test_a_jsonl_visible_file_with_another_path_is_refused(tmp_path, location):
    source = write_jsonl(tmp_path, "events.jsonl", rows(2))
    path = _write(source)
    edit_json_file(path, lambda d: d["config"].update(structure={"dataset_path": "$.a[]"}))

    with pytest.raises(ConfigurationError):
        _resolve(source, location)


# The cache (DP-15, PO-12) --------------------------------------------------------


def _same_size_other_content(source: Path) -> None:
    import os

    stat = source.stat()
    text = source.read_text(encoding="utf-8").replace('"id": 1', '"id": 9', 1)
    source.write_text(text, encoding="utf-8", newline="")
    assert source.stat().st_size == stat.st_size
    os.utime(source, ns=(stat.st_atime_ns, stat.st_mtime_ns))


def test_a_changed_source_rebuilds_the_cache(tmp_path, location):
    source = write_json(tmp_path, "page.json", {"results": rows(3)})
    _resolve(source, location)
    before = json.loads(location.shared_inspect_path(source).read_text(encoding="utf-8"))
    _same_size_other_content(source)

    result = _resolve(source, location)

    after = json.loads(location.shared_inspect_path(source).read_text(encoding="utf-8"))
    assert result.origin == "automatic"
    assert after["source"]["sha256"] != before["source"]["sha256"]


@pytest.mark.parametrize(
    "edit",
    [
        lambda d: d["inspect"].update(tabalyst_version="0.0.1"),
        lambda d: d.update(format_revision=999),
        lambda d: d["source"].update(sha256="0" * 64),
    ],
)
def test_a_stale_cache_is_rebuilt(tmp_path, location, edit):
    source = write_json(tmp_path, "page.json", {"results": rows(3)})
    _resolve(source, location)
    edit_json_file(location.shared_inspect_path(source), edit)

    assert _resolve(source, location).origin == "automatic"


@pytest.mark.parametrize("content", ["", "{", "[]", '{"format": "other"}'])
def test_a_corrupt_cache_is_absent_not_an_error(tmp_path, location, content):
    source = write_json(tmp_path, "page.json", {"results": rows(3)})
    _resolve(source, location)
    location.shared_inspect_path(source).write_text(content, encoding="utf-8")

    result = _resolve(source, location)

    assert result.origin == "automatic"
    assert result.config.json_.collections == ["$.results[]"]
    assert json.loads(location.shared_inspect_path(source).read_text(encoding="utf-8"))


def test_the_cache_keeps_an_unresolved_outcome(tmp_path, location):
    source = write_json(tmp_path, "shop.json", TWO)
    for _ in range(2):
        with pytest.raises(ConfigurationError):
            _resolve(source, location)

    cached = json.loads(location.shared_inspect_path(source).read_text(encoding="utf-8"))
    assert cached["config"]["structure"]["dataset_path"] is None


# A configured path that is gone (DP-16, CA-20) ----------------------------------


def test_a_configured_path_that_is_gone_is_an_incompatibility(tmp_path, location):
    resolution = _resolution()
    source = write_json(tmp_path, "page.json", {"results": rows(3)})
    path = _write(source)
    write_json(tmp_path, "page.json", {"records": rows(3)})
    interpretation = _resolve(source, location)
    result = scan(source, config=interpretation.config)

    with pytest.raises(ConfigurationError) as error:
        resolution.check_result(interpretation, result)

    assert "$.results[]" in str(error.value)
    assert path.name in str(error.value)
    assert "$.records[]" not in str(error.value)


@pytest.mark.parametrize("origin", ["command_line", "config_file"])
def test_other_layers_keep_the_warning_and_the_empty_dataset(tmp_path, location, origin):
    resolution = _resolution()
    source = write_json(tmp_path, "page.json", {"results": rows(3)})
    options = (
        {"collections": ["$.gone[]"]}
        if origin == "command_line"
        else {"scan_layer": {"json": {"collections": ["$.gone[]"]}}}
    )
    interpretation = _resolve(source, location, **options)
    result = scan(source, config=interpretation.config)

    resolution.check_result(interpretation, result)

    assert [d.code for d in result.diagnostics] == ["json_collection_not_found"]


def test_a_compatible_result_has_no_notice_when_the_hash_agrees(tmp_path, location):
    resolution = _resolution()
    source = write_json(tmp_path, "page.json", {"results": rows(3)})
    _write(source)
    interpretation = _resolve(source, location)

    notices = resolution.check_result(interpretation, scan(source, config=interpretation.config))

    assert notices == ()


def test_a_changed_source_gives_the_notice_and_keeps_the_configuration(tmp_path, location):
    resolution = _resolution()
    source = write_json(tmp_path, "page.json", {"results": rows(3)})
    _write(source)
    write_json(tmp_path, "page.json", {"results": rows(4)})
    interpretation = _resolve(source, location)
    result = scan(source, config=interpretation.config)

    notices = resolution.check_result(interpretation, result)

    assert any("different version of the source" in notice for notice in notices)
    assert result.datasets[0].record_count == 4

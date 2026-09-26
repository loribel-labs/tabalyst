import codecs
import hashlib

import pytest

from tabalyst import InputError
from tabalyst.progress import ProgressPhase
from tabalyst.scanner import ScanConfig, ScanResult, scan
from tabalyst.scanner.models import Limited


def _write(tmp_path, content: bytes, name: str = "data.csv"):
    path = tmp_path / name
    path.write_bytes(content)
    return path


def _scan(path, **settings) -> dict:
    return scan(path, config=ScanConfig.model_validate(settings)).model_dump(
        mode="json"
    )


def _field(result: dict, display: str) -> dict:
    [rows] = result["datasets"]
    [match] = [item for item in rows["fields"] if item["display"] == display]
    return match


def test_digest_and_size_cover_a_source_larger_than_the_read_buffer(tmp_path):
    content = b"id,text\n" + b"".join(
        f"{index},value {index}\n".encode() for index in range(200_000)
    )
    path = _write(tmp_path, content)

    result = _scan(path)

    assert len(content) > 1 << 20
    assert result["source"]["size_bytes"] == len(content)
    assert result["source"]["sha256"] == hashlib.sha256(content).hexdigest()
    assert result["datasets"][0]["record_count"] == 200_000


def test_byte_order_mark_is_hashed_but_not_part_of_the_header(tmp_path):
    content = codecs.BOM_UTF8 + "nom,ville\nAnaïs,Montréal\n".encode()
    path = _write(tmp_path, content)

    result = _scan(path)

    assert result["source"]["csv"] == {"delimiter": ",", "header": ["nom", "ville"]}
    assert result["source"]["sha256"] == hashlib.sha256(content).hexdigest()
    assert _field(result, "ville")["strings"]["content"] == 1


def test_locations_use_the_first_physical_line_of_multiline_records(tmp_path):
    path = _write(tmp_path, b'a,b\r\n1,"two\r\nlines"\r\n3\r\n\r\n4,5\r\n')

    result = _scan(path, errors={"policy": "tolerant"})

    [diagnostic] = result["diagnostics"]
    assert diagnostic["locations"] == [
        {"record": 2, "line": 4},
        {"record": 3, "line": 5},
    ]
    assert result["scope"]["records_read"] == 4
    assert result["datasets"][0]["record_count"] == 2


def test_strict_error_names_record_and_first_physical_line(tmp_path):
    path = _write(tmp_path, b'a,b\n1,"x\ny"\n\n')

    with pytest.raises(InputError, match=r"record 2 \(starting at physical line 4\)"):
        scan(path)


def test_locations_are_capped_but_counts_stay_complete(tmp_path):
    path = _write(tmp_path, b"a,b\n" + b"1\n" * 5 + b"1,2\n")

    result = _scan(path, errors={"policy": "tolerant", "max_locations": 2})

    [diagnostic] = result["diagnostics"]
    assert diagnostic["count"] == 5
    assert len(diagnostic["locations"]) == 2
    assert result["scope"]["exclusions"] == {"width_mismatch": 5}


@pytest.mark.parametrize(
    ("content", "message"),
    [
        (b"a,b\n1,\x002\n", "NUL characters near physical line 2"),
        (b"a,b\n1,\xe9\n", "Cannot decode"),
        (b'a,b\n1,"x"y\n', "Invalid CSV near physical line 2"),
        (b"\n1,2\n", "no header"),
    ],
    ids=["nul", "undecodable", "quoting", "blank-header"],
)
@pytest.mark.parametrize("policy", ["strict", "tolerant"])
def test_unreadable_content_is_fatal_under_both_policies(
    tmp_path, content, message, policy
):
    path = _write(tmp_path, content)

    with pytest.raises(InputError, match=message):
        _scan(path, errors={"policy": policy})


def test_configured_delimiter_and_encoding_are_used(tmp_path):
    path = _write(tmp_path, "nom;ville\nAnaïs;Montréal\n".encode("cp1252"))

    result = _scan(path, csv={"delimiter": ";", "encoding": "cp1252"})

    assert result["source"]["csv"]["header"] == ["nom", "ville"]
    assert result["source"]["encoding"] == "cp1252"


def test_markers_can_ignore_case_and_missing_definition_is_configurable(tmp_path):
    path = _write(tmp_path, b'v\nnull\n N/A \nNULL\n""\nx\n')

    value = _field(
        _scan(
            path,
            values={
                "null_markers": ["NULL", "n/a"],
                "null_markers_case_sensitive": False,
                "missing": ["marker"],
            },
        ),
        "v",
    )

    assert value["strings"]["marker"] == 3
    assert value["strings"]["empty"] == 1
    assert value["missing"]["count"] == 3
    assert value["missing"]["components"]["marker"] == 3


def test_missing_and_non_file_sources_are_input_errors(tmp_path):
    with pytest.raises(InputError):
        scan(tmp_path / "missing.csv")
    with pytest.raises(InputError):
        scan(tmp_path)


def test_json_sources_wait_for_their_reader(tmp_path):
    with pytest.raises(InputError, match="not supported yet"):
        scan(_write(tmp_path, b"[]", "data.json"))


def test_progress_reports_reading_and_completion(tmp_path):
    events = []

    scan(_write(tmp_path, b"a\n1\n"), on_progress=events.append)

    assert [event.phase for event in events] == [
        ProgressPhase.READING,
        ProgressPhase.COMPLETE,
    ]


def test_limited_envelope_omits_an_unproven_bound():
    limited = Limited(reason="precision", limit=28)

    assert limited.model_dump() == {
        "status": "limited",
        "reason": "precision",
        "limit": 28,
    }


def test_results_are_immutable(tmp_path):
    result = scan(_write(tmp_path, b"a\n1\n"))

    assert isinstance(result, ScanResult)
    with pytest.raises(ValueError):
        result.status = "partial"

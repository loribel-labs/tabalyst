# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON text of the documents Tabalyst writes: compact, or indented for reading."""

import json
import re
from typing import Any

# Sample entries of a field, which are by far the largest part of a scan.
_LIST_LINE = re.compile(r'^( *)"listed": "\\u0000tabalyst-list-(\d+)"(,?)$', re.MULTILINE)
# The rows of the row sample of a dataset, one per line.
_ROWS_LINE = re.compile(r'^( *)"rows": "\\u0000tabalyst-rows-(\d+)"(,?)$', re.MULTILINE)
# The ids of a stratum by length, on one line.
_IDS_LINE = re.compile(r'^( *)"ids": "\\u0000tabalyst-ids-(\d+)"(,?)$', re.MULTILINE)


def dump_json(document: dict[str, Any], *, indent: bool = False) -> str:
    """The JSON text of a scan or report document, ending with a newline.

    Compact by default. With ``indent`` the document is indented by two spaces
    and every entry of a sample is written on one line, which keeps the file
    readable at about half the size of a fully indented one. Neither form
    changes the document.
    """
    if not indent:
        return json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n"
    lists = _detach_sample_lists(document)
    ids = _detach_ids(document)
    rows = _detach_rows(document)
    text = json.dumps(document, indent=2, ensure_ascii=False)
    try:
        text = _LIST_LINE.sub(lambda match: _entries(match, lists, "listed"), text)
        text = _ROWS_LINE.sub(lambda match: _entries(match, rows, "rows"), text)
        return _IDS_LINE.sub(lambda match: _inline_ids(match, ids), text) + "\n"
    finally:
        _restore_rows(document, rows)
        _restore_ids(document, ids)
        _restore_sample_lists(document, lists)


def _sample_owners(document: dict[str, Any]) -> list[dict[str, Any]]:
    """The blocks that hold a ``listed`` of sample entries: ``values.samples``,
    its ``long_texts`` and its ``by_length`` of every field."""
    owners = []
    for dataset in document.get("datasets") or ():
        for field in dataset.get("fields") or ():
            samples = (field.get("values") or {}).get("samples")
            if samples is None:
                continue
            owners.append(samples)
            for name in ("long_texts", "by_length"):
                if samples.get(name) is not None:
                    owners.append(samples[name])
    return owners


def _strata(document: dict[str, Any]) -> list[dict[str, Any]]:
    """The strata by length of every field."""
    return [
        stratum
        for owner in _sample_owners(document)
        for stratum in owner.get("strata") or ()
    ]


def _detach_ids(document: dict[str, Any]) -> list[list[int]]:
    ids = []
    for stratum in _strata(document):
        ids.append(stratum["ids"])
        stratum["ids"] = f"\0tabalyst-ids-{len(ids) - 1}"
    return ids


def _restore_ids(document: dict[str, Any], ids: list[list[int]]) -> None:
    for stratum, value in zip(_strata(document), ids, strict=True):
        stratum["ids"] = value


def _inline_ids(match: re.Match[str], ids: list[list[int]]) -> str:
    margin, number, comma = match.group(1), int(match.group(2)), match.group(3)
    return f'{margin}"ids": {json.dumps(ids[number])}{comma}'


def _detach_sample_lists(document: dict[str, Any]) -> list[list[Any]]:
    """Replace each sample listing by a placeholder and return the listings."""
    lists = []
    for owner in _sample_owners(document):
        lists.append(owner["listed"])
        owner["listed"] = f"\0tabalyst-list-{len(lists) - 1}"
    return lists


def _restore_sample_lists(document: dict[str, Any], lists: list[list[Any]]) -> None:
    for owner, listed in zip(_sample_owners(document), lists, strict=True):
        owner["listed"] = listed


def _row_samples(document: dict[str, Any]) -> list[dict[str, Any]]:
    """The row sample of every dataset."""
    return [
        sample
        for dataset in document.get("datasets") or ()
        if (sample := (dataset.get("records") or {}).get("sample")) is not None
    ]


def _detach_rows(document: dict[str, Any]) -> list[list[Any]]:
    rows = []
    for sample in _row_samples(document):
        rows.append(sample["rows"])
        sample["rows"] = f"\0tabalyst-rows-{len(rows) - 1}"
    return rows


def _restore_rows(document: dict[str, Any], rows: list[list[Any]]) -> None:
    for sample, value in zip(_row_samples(document), rows, strict=True):
        sample["rows"] = value


def _entries(match: re.Match[str], lists: list[list[Any]], name: str) -> str:
    """The listing at the placeholder's line, one entry per line."""
    margin, number, comma = match.group(1), int(match.group(2)), match.group(3)
    listed = lists[number]
    if not listed:
        return f'{margin}"{name}": []{comma}'
    inner = margin + "  "
    body = ",\n".join(
        inner + json.dumps(entry, ensure_ascii=False) for entry in listed
    )
    return f'{margin}"{name}": [\n{body}\n{margin}]{comma}'

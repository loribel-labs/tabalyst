# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON text of the documents Tabalyst writes: compact, or indented for reading."""

import json
import re
from typing import Any

# Sample entries of a field, which are by far the largest part of a scan.
_LIST_LINE = re.compile(r'^( *)"listed": "\\u0000tabalyst-list-(\d+)"(,?)$', re.MULTILINE)


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
    text = json.dumps(document, indent=2, ensure_ascii=False)
    try:
        return _LIST_LINE.sub(lambda match: _entries(match, lists), text) + "\n"
    finally:
        _restore_sample_lists(document, lists)


def _sample_owners(document: dict[str, Any]) -> list[dict[str, Any]]:
    """The blocks that hold a ``listed`` of sample entries: ``values.samples``
    and ``values.samples.long_texts`` of every field."""
    owners = []
    for dataset in document.get("datasets") or ():
        for field in dataset.get("fields") or ():
            samples = (field.get("values") or {}).get("samples")
            if samples is None:
                continue
            owners.append(samples)
            if samples.get("long_texts") is not None:
                owners.append(samples["long_texts"])
    return owners


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


def _entries(match: re.Match[str], lists: list[list[Any]]) -> str:
    """The listing at the placeholder's line, one entry per line."""
    margin, number, comma = match.group(1), int(match.group(2)), match.group(3)
    listed = lists[number]
    if not listed:
        return f'{margin}"listed": []{comma}'
    inner = margin + "  "
    body = ",\n".join(
        inner + json.dumps(entry, ensure_ascii=False) for entry in listed
    )
    return f'{margin}"listed": [\n{body}\n{margin}]{comma}'

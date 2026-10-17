# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Read the Summary table of a rendered report as the browser would see it."""

from html.parser import HTMLParser


class Pop:
    """A dialog of a cell (``div.pop``): its attributes and its text."""

    def __init__(self, attrs: dict[str, str | None]) -> None:
        self.attrs = attrs
        self.parts: list[str] = []

    @property
    def text(self) -> str:
        return " ".join("".join(self.parts).split())


class Cell:
    """One th or td: its attributes and its text.

    ``text`` is what the cell prints; the dialogs it holds (``pops``) and the buttons
    that open them (``buttons``, as attributes and text) are apart.
    """

    def __init__(self, tag: str, attrs: dict[str, str | None]) -> None:
        self.tag = tag
        self.attrs = attrs
        self.parts: list[str] = []
        self.pops: list[Pop] = []
        self.buttons: list[tuple[dict[str, str | None], list[str]]] = []

    @property
    def text(self) -> str:
        return " ".join("".join(self.parts).split())

    def button_texts(self) -> list[str]:
        return [" ".join("".join(parts).split()) for _, parts in self.buttons]

    def __getitem__(self, name: str) -> str:
        return str(self.attrs[name])

    def get(self, name: str) -> str | None:
        return self.attrs.get(name)


class Row:
    def __init__(self, attrs: dict[str, str | None]) -> None:
        self.attrs = attrs
        self.cells: list[Cell] = []


class _TableParser(HTMLParser):
    def __init__(self, table_id: str) -> None:
        super().__init__()
        self.table_id = table_id
        self.inside = 0
        self.headers: list[str] = []
        self.rows: list[Row] = []
        self.html = ""
        self._cell: Cell | None = None
        self._in_head = False
        self._in_ht = False
        self._head_text: list[str] = []
        self._in_body = False
        self._pop: Pop | None = None
        self._pop_depth = 0
        self._button: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag == "table":
            if self.inside or values.get("id") == self.table_id:
                self.inside += 1
            return
        if not self.inside:
            return
        if self._pop is not None and tag == "div":
            self._pop_depth += 1
        elif tag == "div" and self._cell is not None and "pop" in (values.get("class") or "").split():
            self._pop = Pop(values)
            self._pop_depth = 1
            self._cell.pops.append(self._pop)
        elif tag == "button" and self._cell is not None and self._pop is None:
            self._button = []
            self._cell.buttons.append((values, self._button))
        if tag == "thead":
            self._in_head = True
        elif tag == "tbody":
            self._in_body = True
        elif tag == "tr" and self._in_body:
            self.rows.append(Row(values))
        elif tag in {"td", "th"} and self._in_body:
            self._cell = Cell(tag, values)
            self.rows[-1].cells.append(self._cell)
        elif tag == "span" and self._in_head and "ht" in (values.get("class") or "").split():
            self._in_ht = True
            self._head_text = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "table" and self.inside:
            self.inside -= 1
        elif tag == "thead":
            self._in_head = False
        elif tag == "tbody":
            self._in_body = False
        elif tag == "div" and self._pop is not None:
            self._pop_depth -= 1
            if not self._pop_depth:
                self._pop = None
        elif tag == "button":
            self._button = None
        elif tag in {"td", "th"}:
            self._cell = None
        elif tag == "span" and self._in_ht:
            self._in_ht = False
            self.headers.append("".join(self._head_text).strip())

    def handle_data(self, data: str) -> None:
        if self._in_ht:
            self._head_text.append(data)
        if self._pop is not None:
            self._pop.parts.append(data)
        elif self._cell is not None:
            self._cell.parts.append(data)
            if self._button is not None:
                self._button.append(data)


def columns_table(html: str, table_id: str = "summary-table") -> _TableParser:
    """Headers (``.headers``) and body rows (``.rows``) of the table ``table_id``."""
    parser = _TableParser(table_id)
    parser.feed(html)
    marker = html.index(f'id="{table_id}"')
    parser.html = html[marker : html.index("</table>", marker)]
    return parser


def row_for(table: _TableParser, name: str) -> Row:
    """The only row whose first cell holds ``name``."""
    found = [row for row in table.rows if row.cells[0]["data-v"] == name]
    assert len(found) == 1, name
    return found[0]

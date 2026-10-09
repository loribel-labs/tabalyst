# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Registry of the analyzers the planner knows (design 20.5).

Internal only: no external loading (O21). The order of registration is the
order of the candidates in a plan.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator

from tabalyst.scanner.planner.analyzer import Analyzer


class AnalyzerRegistry:
    """Analyzer classes by ``id``, in registration order."""

    def __init__(self, analyzers: Iterable[type[Analyzer]] = ()) -> None:
        self._classes: dict[str, type[Analyzer]] = {}
        for analyzer in analyzers:
            self.register(analyzer)

    def register(self, analyzer: type[Analyzer]) -> type[Analyzer]:
        """Add an analyzer class. Raises ``TypeError`` for a class that is not an
        ``Analyzer`` or has no outputs, and ``ValueError`` for a known ``id``."""
        if not (isinstance(analyzer, type) and issubclass(analyzer, Analyzer)):
            raise TypeError(f"Analyzers must subclass Analyzer: {analyzer!r}")
        identifier = getattr(analyzer, "id", None)
        if not isinstance(identifier, str) or not identifier:
            raise TypeError(f"Analyzer {analyzer.__name__} has no id")
        if not getattr(analyzer, "outputs", ()):
            raise TypeError(f"Analyzer {identifier!r} declares no outputs")
        if identifier in self._classes:
            raise ValueError(f"Analyzer {identifier!r} is already registered")
        self._classes[identifier] = analyzer
        return analyzer

    def __iter__(self) -> Iterator[type[Analyzer]]:
        return iter(self._classes.values())

    def __contains__(self, identifier: object) -> bool:
        return identifier in self._classes

    def __len__(self) -> int:
        return len(self._classes)


def default_registry() -> AnalyzerRegistry:
    """A fresh registry holding the built-in analyzers."""
    from tabalyst.scanner.planner.analyzers import BUILT_INS

    return AnalyzerRegistry(BUILT_INS)

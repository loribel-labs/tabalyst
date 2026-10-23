# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract tests for Tabalyst Dedup, enabled lot by lot.

Each test declares the implementation lot that provides its behavior with
``@pytest.mark.dedup_lot("4")`` and the requirement it covers with
``@pytest.mark.dedup_t("T03")``. Tests of lots missing from ``ENABLED_LOTS`` are
skipped, so the suite stays green while the feature is built. A lot enables itself
by uncommenting its own line below (one lot per line, separated by a blank line, so
that lots built in parallel do not conflict when merged). Tests marked
``dedup_heavy`` also need ``-m dedup_heavy`` on the command line.

The expectations follow ``docs/dev/dedup/design.md``. Changing one requires updating
that document in the same lot. The plan is in ``tabalyst-gb``
(``KANBAN/05-PROGRESS/2026-10-22-tabalyst-dedup-plan.md``).
"""

import pytest

ENABLED_LOTS: set[str] = {
    "1",  # options, discovery, planned outputs

    "2",  # canonical key, in-memory store, counters

    "3",  # disk store, budget, spill

    "4",  # first pass, limit, metrics

    "5",  # second pass, CSV outputs

    # "6",  # JSON report

    # "7",  # cache, ownership, recovery

    # "8",  # batch runner, batch report, Python API

    # "9",  # command line

    # "10",  # hardening, scale

    # "11",  # finalization
}


def pytest_collection_modifyitems(config, items):
    wants_heavy = "dedup_heavy" in (config.getoption("markexpr", default="") or "")
    for item in items:
        marker = item.get_closest_marker("dedup_lot")
        if marker is not None and marker.args[0] not in ENABLED_LOTS:
            item.add_marker(
                pytest.mark.skip(
                    reason=f"Dedup lot {marker.args[0]} is not implemented yet"
                )
            )
        if item.get_closest_marker("dedup_heavy") is not None and not wants_heavy:
            item.add_marker(
                pytest.mark.skip(reason="heavy Dedup test: run with -m dedup_heavy")
            )

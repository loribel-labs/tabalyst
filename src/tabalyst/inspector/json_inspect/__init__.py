# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""JSON Inspect: the engine that describes a JSON or JSONL source (design inspect).

``inspect_source`` reads a source once and returns an ``InspectDocument``;
``parameters`` holds the measured bounds of the detection (design section 15).
"""

from tabalyst.inspector.json_inspect import parameters
from tabalyst.inspector.json_inspect.build import inspect_source

__all__ = ["inspect_source", "parameters"]

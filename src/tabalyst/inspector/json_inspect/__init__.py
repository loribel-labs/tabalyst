"""JSON Inspect: the engine that describes a JSON or JSONL source (design inspect).

``inspect_source`` reads a source once and returns an ``InspectDocument``;
``parameters`` holds the measured bounds of the detection (design section 15).
"""

from tabalyst.inspector.json_inspect import parameters
from tabalyst.inspector.json_inspect.build import inspect_source

__all__ = ["inspect_source", "parameters"]

"""Detector registry and the detectors of one scan (design 12.1 to 12.4).

``DetectorSet`` instantiates the enabled detectors of a registry with their
configuration, classifies values and turns per-field tallies into results.
A detector that raises on a field fails for that field only (CA19).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from decimal import Decimal
from fractions import Fraction

from tabalyst.errors import ConfigurationError
from tabalyst.scanner.config import ScanConfig, exact_share
from tabalyst.scanner.detectors.base import (
    NOT_TESTED,
    Classification,
    Detector,
    DetectorFailure,
)
from tabalyst.scanner.detectors.boolean import BooleanDetector
from tabalyst.scanner.detectors.email import EmailDetector
from tabalyst.scanner.detectors.enumeration import EnumerationDetector
from tabalyst.scanner.detectors.number import NumberDetector, is_integer_format
from tabalyst.scanner.detectors.pattern import pattern_detector
from tabalyst.scanner.detectors.phone import PhoneDetector
from tabalyst.scanner.detectors.postal import PostalCodeDetector
from tabalyst.scanner.detectors.shape import shape
from tabalyst.scanner.detectors.temporal import DateDetector
from tabalyst.scanner.detectors.url import UrlDetector
from tabalyst.scanner.exposure import SHOW, ExposureGate
from tabalyst.scanner.measures import UNCONVERTIBLE
from tabalyst.scanner.models import (
    Coverage,
    DetectorComplete,
    DetectorDisabled,
    DetectorFailed,
    DetectorNotApplicable,
    Disabled,
    Evidence,
    Failed,
    FormatCount,
    InterpretationCandidate,
    Interpretations,
    NotApplicable,
)
from tabalyst.scanner.technical import string_family

BUILT_INS: tuple[type[Detector], ...] = (
    NumberDetector,
    DateDetector,
    BooleanDetector,
    EnumerationDetector,
    EmailDetector,
    UrlDetector,
    PhoneDetector,
    PostalCodeDetector,
)
_NATIVE_SCALARS = ("string", "integer", "number", "boolean")
_NO_VALUES = NotApplicable(reason="no_values")
_STATES = ("matched", "ambiguous", "invalid", "not_matched")

# ``report_failure(detector_id, error)`` records a ``detector_failed``
# diagnostic and returns its index.
FailureReporter = Callable[[str, str], int]


class _NotEligible:
    """The value's native type is not accepted by the detector."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "NOT_ELIGIBLE"


NOT_ELIGIBLE = _NotEligible()


class DetectorRegistry:
    """Detector classes by ``id``, in registration order."""

    def __init__(self, detectors: Iterable[type[Detector]] = ()) -> None:
        self._classes: dict[str, type[Detector]] = {}
        for detector in detectors:
            self.register(detector)

    def register(self, detector: type[Detector]) -> type[Detector]:
        if not (isinstance(detector, type) and issubclass(detector, Detector)):
            raise TypeError(f"Detectors must subclass Detector: {detector!r}")
        identifier = getattr(detector, "id", None)
        if not isinstance(identifier, str) or not identifier:
            raise TypeError(f"Detector {detector.__name__} has no id")
        if not isinstance(getattr(detector, "family", None), str):
            raise TypeError(f"Detector {identifier!r} has no family")
        if identifier in self._classes:
            raise ValueError(f"Detector {identifier!r} is already registered")
        self._classes[identifier] = detector
        return detector

    def __iter__(self) -> Iterator[type[Detector]]:
        return iter(self._classes.values())

    def __contains__(self, identifier: object) -> bool:
        return identifier in self._classes


def default_registry() -> DetectorRegistry:
    """A fresh registry holding the built-in detectors."""
    return DetectorRegistry(BUILT_INS)


class DetectorTally:
    """Coverage, formats and evidence of one detector on one field."""

    __slots__ = (
        "accumulator",
        "ambiguous",
        "detector",
        "eligible",
        "error",
        "examples",
        "formats",
        "invalid",
        "matched",
        "max_examples",
        "max_length",
        "not_matched",
        "not_tested",
    )

    def __init__(self, detector: Detector, max_examples: int, max_length: int) -> None:
        self.detector = detector
        self.max_examples = max_examples
        self.max_length = max_length
        self.eligible = 0
        self.matched = 0
        self.ambiguous = 0
        self.invalid = 0
        self.not_matched = 0
        self.not_tested = 0
        self.formats: dict[str, int] = {}
        self.examples: dict[str, list[str]] = {state: [] for state in _STATES}
        self.error: str | None = None
        try:
            self.accumulator = detector.accumulator()
        except Exception as exc:  # noqa: BLE001 - detector code is isolated (CA19)
            self.error = type(exc).__name__

    def add(self, value: str, classification: object, count: int) -> None:
        if classification is NOT_ELIGIBLE or self.error is not None:
            return
        self.eligible += count
        if classification is None:  # the most frequent case
            state = "not_matched"
            self.not_matched += count
        elif classification is NOT_TESTED:
            self.not_tested += count
            return
        elif type(classification) is DetectorFailure:
            self.error = classification.error
            return
        else:
            state = classification.state
            if state == "matched":
                self.matched += count
                name = classification.format
                if name is not None:
                    self.formats[name] = self.formats.get(name, 0) + count
            elif state == "ambiguous":
                self.ambiguous += count
            elif state == "invalid":
                self.invalid += count
            else:
                self.error = "InvalidState"
                return
        examples = self.examples[state]
        if (
            len(examples) < self.max_examples
            and len(value) <= self.max_length
            and value not in examples
        ):
            examples.append(value)
        try:
            self.accumulator.add(value, classification, count)
        except Exception as exc:  # noqa: BLE001 - detector code is isolated (CA19)
            self.error = type(exc).__name__

    def exposes_sensitive_values(self) -> bool:
        """A sensitive detector matched a value of the field, or failed on it,
        which cannot prove that nothing matched (design 12.8)."""
        return self.detector.sensitive and (self.matched > 0 or self.error is not None)

    def result(self, report_failure: FailureReporter, gate: ExposureGate = SHOW):
        detector = self.detector
        identity = {"id": detector.id, "version": detector.version}
        if self.error is None and self.eligible:
            try:
                details = self.accumulator.details(gate)
                matches = detector.scope != "field" or self.accumulator.field_matches()
            except Exception as exc:  # noqa: BLE001 - detector code is isolated (CA19)
                self.error = type(exc).__name__
        if self.error is not None:
            return DetectorFailed(
                **identity,
                reason="detector_error",
                diagnostic=report_failure(detector.id, self.error),
            )
        if not self.eligible:
            return DetectorNotApplicable(**identity, reason="no_values")
        matched, not_matched = self.matched, self.not_matched
        formats, examples = self.formats, self.examples
        if not matches:
            # A field-level detector rejects the field: no value matches.
            not_matched += matched
            matched = 0
            formats = {}
            moved = (examples["matched"] + examples["not_matched"])[: self.max_examples]
            examples = {**examples, "matched": [], "not_matched": moved}
        tested = self.eligible - self.not_tested
        return DetectorComplete(
            **identity,
            coverage=Coverage(
                eligible=self.eligible,
                tested=tested,
                matched=matched,
                ambiguous=self.ambiguous,
                invalid=self.invalid,
                not_matched=not_matched,
                not_tested=self.not_tested,
                share_tested=round(matched / tested, 4) if tested else None,
                share_eligible=round(matched / self.eligible, 4),
            ),
            formats=[
                FormatCount(format=name, count=count)
                for name, count in sorted(
                    formats.items(), key=lambda item: (-item[1], item[0])
                )
            ],
            evidence=Evidence(
                **{state: gate.examples(values) for state, values in examples.items()}
            ),
            details=details,
        )


def _is_number(value: object) -> bool:
    return type(value) is int or isinstance(value, Decimal) or value is UNCONVERTIBLE


class DetectorSet:
    """The detectors of one scan, in registry order."""

    __slots__ = (
        "_date",
        "_exposure",
        "_idle",
        "_number",
        "_plans",
        "active",
        "entries",
        "max_examples",
        "max_length",
        "minimum_share",
    )

    def __init__(self, registry: DetectorRegistry, config: ScanConfig) -> None:
        self.entries: list[tuple[type[Detector], Detector | None]] = []
        active: list[Detector] = []
        # Declarative patterns follow the registry, in configuration order.
        patterns = [pattern_detector(settings) for settings in config.patterns]
        for pattern in patterns:
            if pattern.id in registry:
                raise ConfigurationError(
                    f"Pattern {pattern.id!r} collides with a registered detector"
                )
        for detector_class in (*registry, *patterns):
            section = getattr(config.detectors, detector_class.id, None)
            settings = {} if section is None else section.model_dump()
            detector = None
            if settings.get("enabled", True):
                detector = detector_class(settings)
                active.append(detector)
            self.entries.append((detector_class, detector))
        self.active = tuple(active)
        index = {detector.id: i for i, detector in enumerate(active)}
        self._number = index.get("number")
        self._date = index.get("date")
        self.max_examples = config.limits.max_evidence_examples
        self.max_length = config.limits.max_stored_value_length
        self.minimum_share = exact_share(config.detection.minimum_share)
        self._exposure = ExposureGate(config.exposure.sensitive_values)
        # Native types that no active detector accepts need no work.
        self._idle = {
            native_type: (NOT_ELIGIBLE,) * len(active)
            for native_type in _NATIVE_SCALARS
            if not any(native_type in detector.accepts for detector in active)
        }
        # Per native type and detector: ``classify``, input cap and shapes,
        # or ``None`` when the type is not accepted.
        self._plans = {
            native_type: tuple(
                (detector.classify, detector.max_input_length, detector.shapes)
                if native_type in detector.accepts
                else None
                for detector in active
            )
            for native_type in _NATIVE_SCALARS
        }

    def versions(self) -> dict[str, int]:
        return {detector.id: detector.version for detector in self.active}

    def classify(self, native_type: str, text: str) -> tuple[object, ...]:
        """One entry per active detector: a classification, ``None`` (not
        matched), ``NOT_TESTED``, ``NOT_ELIGIBLE`` or a ``DetectorFailure``."""
        idle = self._idle.get(native_type)
        if idle is not None:
            return idle
        results: list[object] = []
        value_shape = None
        for plan in self._plans[native_type]:
            if plan is None:
                results.append(NOT_ELIGIBLE)
                continue
            classify, cap, pattern = plan
            if cap is not None and len(text) > cap:
                results.append(NOT_TESTED)
                continue
            if pattern is not None:
                if value_shape is None:
                    value_shape = shape(text)
                if pattern.fullmatch(value_shape) is None:
                    results.append(None)
                    continue
            try:
                found = classify(text)
            except Exception as exc:  # noqa: BLE001 - detector code is isolated (CA19)
                found = DetectorFailure(type(exc).__name__)
            else:
                if found is not None and not isinstance(found, Classification):
                    found = DetectorFailure("TypeError")
            results.append(found)
        return tuple(results)

    def analyze(self, text: str) -> tuple[tuple[object, ...], object, bool, str]:
        """Classifications of an analytical string, the number the number
        detector reads without ambiguity, whether it has a decimal form, and
        the technical type family."""
        classifications = self.classify("string", text)
        number, decimal_form = None, False
        if self._number is not None:
            found = classifications[self._number]
            if (
                isinstance(found, Classification)
                and found.state == "matched"
                and _is_number(found.value)
            ):
                number = found.value
                decimal_form = not is_integer_format(found.format)
        family = string_family(text, classifications, self._date, self._number)
        return classifications, number, decimal_form, family

    def gate(self, tallies: list[DetectorTally]) -> ExposureGate | None:
        """The exposure gate of a sensitive field, ``None`` otherwise."""
        if any(tally.exposes_sensitive_values() for tally in tallies):
            return self._exposure
        return None

    def tallies(self) -> list[DetectorTally]:
        return [
            DetectorTally(detector, self.max_examples, self.max_length)
            for detector in self.active
        ]

    def results(
        self,
        tallies: list[DetectorTally] | None,
        report_failure: FailureReporter,
        gate: ExposureGate = SHOW,
    ) -> list:
        """Every registered detector in order; ``tallies`` is ``None`` for a
        field without analyzable values."""
        results = []
        position = 0
        for detector_class, detector in self.entries:
            if detector is None:
                results.append(
                    DetectorDisabled(
                        id=detector_class.id, version=detector_class.version
                    )
                )
                continue
            if tallies is None:
                results.append(
                    DetectorNotApplicable(
                        id=detector.id, version=detector.version, reason="no_values"
                    )
                )
            else:
                results.append(tallies[position].result(report_failure, gate))
            position += 1
        return results

    def temporal(self, tallies: list[DetectorTally] | None, results: list):
        """The ``temporal`` block, produced by the date detector."""
        if self._date is None:
            return Disabled()
        result = next(item for item in results if item.id == "date")
        if result.status == "failed":
            return Failed(reason=result.reason, diagnostic=result.diagnostic)
        if result.status != "complete":
            return _NO_VALUES
        produce = getattr(tallies[self._date].accumulator, "temporal", None)
        return Disabled() if produce is None else produce()

    def interpretations(self, results: list) -> Interpretations:
        candidates = [
            InterpretationCandidate(
                detector=result.id,
                matched=result.coverage.matched,
                share_eligible=result.coverage.share_eligible,
            )
            for result in results
            if result.status == "complete"
            and result.coverage.matched
            and Fraction(result.coverage.matched, result.coverage.eligible)
            >= self.minimum_share
        ]
        candidates.sort(key=lambda item: (-item.matched, item.detector))
        return Interpretations(
            primary=candidates[0].detector if len(candidates) == 1 else None,
            candidates=candidates,
        )

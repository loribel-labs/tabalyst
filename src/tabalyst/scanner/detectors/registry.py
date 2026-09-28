"""Detector registry and the detectors of one scan (design 12.1 to 12.4).

``DetectorSet`` instantiates the enabled detectors of a registry with their
configuration, classifies values and turns per-field tallies into results.
A detector that raises on a field fails for that field only (CA19).
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Sequence
from datetime import date
from decimal import Decimal
from fractions import Fraction

from tabalyst.errors import ConfigurationError
from tabalyst.scanner.config import ScanConfig, exact_share
from tabalyst.scanner.detectors.base import (
    Classification,
    Detector,
    DetectorFailure,
)
from tabalyst.scanner.detectors.boolean import BooleanDetector
from tabalyst.scanner.detectors.currency import CurrencyDetector
from tabalyst.scanner.detectors.email import EmailDetector
from tabalyst.scanner.detectors.enumeration import EnumerationDetector
from tabalyst.scanner.detectors.ip import IpAddressDetector
from tabalyst.scanner.detectors.number import NumberDetector, is_integer_format
from tabalyst.scanner.detectors.pattern import pattern_detector
from tabalyst.scanner.detectors.percentage import PercentageDetector
from tabalyst.scanner.detectors.phone import PhoneDetector
from tabalyst.scanner.detectors.postal import PostalCodeDetector
from tabalyst.scanner.detectors.quantity import QuantityDetector
from tabalyst.scanner.detectors.shape import shape
from tabalyst.scanner.detectors.temporal import DateDetector
from tabalyst.scanner.detectors.url import UrlDetector
from tabalyst.scanner.detectors.uuid import UuidDetector
from tabalyst.scanner.exposure import SHOW, ExposureGate
from tabalyst.scanner.measures import UNCONVERTIBLE
from tabalyst.scanner.models import (
    Adaptive,
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
from tabalyst.scanner.technical import BOOLEAN_WORDS

BUILT_INS: tuple[type[Detector], ...] = (
    NumberDetector,
    DateDetector,
    BooleanDetector,
    EnumerationDetector,
    EmailDetector,
    UrlDetector,
    PhoneDetector,
    PostalCodeDetector,
    CurrencyDetector,
    PercentageDetector,
    QuantityDetector,
    UuidDetector,
    IpAddressDetector,
)
_NATIVE_SCALARS = ("string", "integer", "number", "boolean")
_NO_VALUES = NotApplicable(reason="no_values")
_STATES = ("matched", "ambiguous", "invalid", "not_matched")
# Distinct shapes memoized by a detector set (``DetectorSet._fits``).
SHAPE_CACHE_SIZE = 4_096

# ``report_failure(detector_id, error)`` records a ``detector_failed``
# diagnostic and returns its index.
FailureReporter = Callable[[str, str], int]
# ``report_probe(detector_id, count, warmup_reactions)`` records a
# ``detector_skipped_reacted`` warning for ``count`` probed occurrences of a
# detector skipped after ``warmup_reactions`` reactions, and returns its index.
ProbeReporter = Callable[[str, int, int], int]
# Probed occurrences that must react before a rare detector is reported as
# reacting more than its warm-up promised.
PROBE_REACTIONS = 10


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


def _ignores_unmatched(accumulator: object) -> bool:
    """Whether the class that defines ``accumulator.add`` declares, in its own
    body, that ``add`` does nothing for unmatched values."""
    for cls in type(accumulator).__mro__:
        if "add" in cls.__dict__:
            return cls.__dict__.get("ignores_unmatched", False) is True
    return False


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
        "probe_reactions",
        "probe_tested",
        "recent_reactions",
        "rejected",
        "skipped",
        "skipped_after",
        "unmatched_examples",
        "unmatched_to_accumulator",
        "warmup_reactions",
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
        # Adaptive detection: values not tested, and the warm-up size once
        # the detector is skipped for the field.
        self.skipped = 0
        self.skipped_after: int | None = None
        # Distinct values of the warm-up that the detector reacted to, in all
        # and in its second half; probed occurrences once it is skipped, and
        # those that reacted.
        self.warmup_reactions = 0
        self.recent_reactions = 0
        self.probe_tested = 0
        self.probe_reactions = 0
        self.formats: dict[str, int] = {}
        self.examples: dict[str, list[str]] = {state: [] for state in _STATES}
        self.error: str | None = None
        # A field-level detector whose accumulator rejects the field: later
        # values are counted as not matched without being classified.
        self.rejected = False
        self.unmatched_examples = self.examples["not_matched"]
        self.unmatched_to_accumulator = True
        try:
            self.accumulator = detector.accumulator()
        except Exception as exc:  # noqa: BLE001 - detector code is isolated (CA19)
            self.error = type(exc).__name__
        else:
            self.unmatched_to_accumulator = not _ignores_unmatched(self.accumulator)

    def add(self, value: str, classification: object, count: int) -> None:
        """Account for ``count`` occurrences of a tested value; ``None`` means
        not matched, a ``DetectorFailure`` fails the detector."""
        if self.error is not None:
            return
        self.eligible += count
        if classification is None:  # the most frequent case
            self.not_matched += count
            examples = self.unmatched_examples
            if (
                len(examples) < self.max_examples
                and len(value) <= self.max_length
                and value not in examples
            ):
                examples.append(value)
            if self.unmatched_to_accumulator:
                try:
                    self.accumulator.add(value, None, count)
                except Exception as exc:  # noqa: BLE001 - detector code is isolated (CA19)
                    self.error = type(exc).__name__
            return
        self._hit(value, classification, count)

    def _hit(self, value: str, classification: object, count: int) -> bool:
        """A matched, ambiguous or invalid value, or a failure; ``False`` once
        the detector failed."""
        if not isinstance(classification, Classification):
            self.error = (
                classification.error
                if type(classification) is DetectorFailure
                else "TypeError"
            )
            return False
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
            return False
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
            return False
        return True

    def add_many(
        self, values: Sequence[str], counts: Sequence[int], results: Sequence[object]
    ) -> None:
        """``add`` for each tested value, in order: unmatched values are
        counted together when the accumulator ignores them."""
        if self.error is not None:
            return
        hits = [i for i, found in enumerate(results) if found is not None]
        if self.unmatched_to_accumulator and len(hits) < len(results):
            # The accumulator sees unmatched values too, in order.
            for value, found, count in zip(values, results, counts, strict=True):
                self.add(value, found, count)
            return
        total = sum(counts)
        reacted = 0
        for i in hits:
            count = counts[i]
            if not self._hit(values[i], results[i], count):
                return
            reacted += count
        self.eligible += total
        self.not_matched += total - reacted
        examples = self.unmatched_examples
        if len(examples) < self.max_examples and len(hits) < len(results):
            limit = self.max_length
            for value, found in zip(values, results, strict=True):
                if found is None and len(value) <= limit and value not in examples:
                    examples.append(value)
                    if len(examples) >= self.max_examples:
                        break

    def untested(self, count: int) -> None:
        """``count`` occurrences above the input cap of the detector."""
        if self.error is None:
            self.eligible += count
            self.not_tested += count

    def skip(self, count: int) -> None:
        """``count`` occurrences that adaptive detection did not test."""
        if self.error is None:
            self.eligible += count
            self.not_tested += count
            self.skipped += count

    def reject(self, values: Sequence[str], counts: Sequence[int]) -> None:
        """Values of a field that a field-level detector already rejects: not
        matched, as they would be once the field is rejected (``result``)."""
        if self.error is not None:
            return
        total = sum(counts)
        self.eligible += total
        self.not_matched += total
        # Rejected fields list the first matched and unmatched examples
        # together (``result``): keep filling the same listing.
        matched = self.examples["matched"]
        examples = self.unmatched_examples
        room = self.max_examples - len(matched) - len(examples)
        limit = self.max_length
        for value in values:
            if room <= 0:
                break
            if len(value) <= limit and value not in matched and value not in examples:
                examples.append(value)
                room -= 1

    def exposes_sensitive_values(self) -> bool:
        """A sensitive detector matched a value of the field, or failed on it,
        which cannot prove that nothing matched (design 12.8)."""
        return self.detector.sensitive and (self.matched > 0 or self.error is not None)

    def result(
        self,
        report_failure: FailureReporter,
        gate: ExposureGate = SHOW,
        report_probe: ProbeReporter | None = None,
        rare_share: Fraction = Fraction(0),
    ):
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
        adaptive = None
        if self.skipped_after is not None:
            if self.warmup_reactions:
                # A rare detector is expected to react now and then: only
                # probes that react more often than its warm-up are reported.
                reactions = self.probe_reactions
                warn = reactions >= PROBE_REACTIONS and reactions > (
                    rare_share * self.probe_tested
                )
            else:
                # Without any reaction in the warm-up, every reaction comes
                # from a probe.
                reactions = matched + self.ambiguous + self.invalid
                warn = reactions > 0
            adaptive = Adaptive(
                skipped_after=self.skipped_after,
                warmup_reactions=self.warmup_reactions,
                not_tested=self.skipped,
                diagnostic=(
                    report_probe(detector.id, reactions, self.warmup_reactions)
                    if warn and report_probe is not None
                    else None
                ),
            )
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
            adaptive=adaptive,
        )


def _is_number(value: object) -> bool:
    return type(value) is int or isinstance(value, Decimal) or value is UNCONVERTIBLE


def _one_by_one(classify: Callable[[str], object], values: Sequence[str]) -> list:
    """``classify`` of each value; an exception becomes a ``DetectorFailure``
    at its position (CA19)."""
    results: list[object] = []
    for value in values:
        try:
            results.append(classify(value))
        except Exception as exc:  # noqa: BLE001 - detector code is isolated (CA19)
            results.append(DetectorFailure(type(exc).__name__))
    return results


def _count_warmup(
    tally: DetectorTally, results: list, positions: list[int] | None, warmup: tuple
) -> None:
    """Reactions of a tally to the values first met in the warm-up, once per
    distinct value, in all and in its second half."""
    fresh, recent = warmup
    for j, found in enumerate(results):
        if found is not None:
            position = j if positions is None else positions[j]
            if position in fresh:
                tally.warmup_reactions += 1
                if position in recent:
                    tally.recent_reactions += 1


def _count_probes(
    tally: DetectorTally,
    results: list,
    counts: Sequence[int],
    positions: list[int],
    rewarm: set[int] | None,
) -> None:
    """Probed occurrences of a skipped detector and those that reacted;
    warm-up values of a streamed field are not probes."""
    for j, found in enumerate(results):
        if rewarm is not None and positions[j] in rewarm:
            continue
        count = counts[j]
        tally.probe_tested += count
        if found is not None:
            tally.probe_reactions += count


class DetectorSet:
    """The detectors of one scan, in registry order."""

    __slots__ = (
        "_adaptive",
        "_date",
        "_exposure",
        "_field_scope",
        "_number",
        "_plans",
        "_shape_cache",
        "active",
        "entries",
        "max_examples",
        "max_length",
        "minimum_share",
        "probe_interval",
        "rare_reactions",
        "rare_share",
        "warmup_values",
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
        self.warmup_values = config.detection.warmup_values
        self.probe_interval = config.detection.probe_interval
        # The most warm-up values a rare detector reacts to.
        self.rare_share = exact_share(config.detection.rare_share)
        self.rare_reactions = int(self.rare_share * self.warmup_values)
        # The number and date detectors give every value its technical type
        # family (design 9.7): adaptive detection never skips them.
        self._adaptive = tuple(
            i not in (self._number, self._date) for i in range(len(active))
        )
        self._field_scope = tuple(detector.scope == "field" for detector in active)
        self._exposure = ExposureGate(config.exposure.sensitive_values)
        # Per native type, the detectors that accept it, with their position,
        # input cap and shapes.
        self._plans = {
            native_type: tuple(
                (i, detector, detector.max_input_length, detector.shapes)
                for i, detector in enumerate(active)
                if native_type in detector.accepts
            )
            for native_type in _NATIVE_SCALARS
        }
        self._shape_cache: dict[str, tuple[bool, ...]] = {}

    def versions(self) -> dict[str, int]:
        return {detector.id: detector.version for detector in self.active}

    def accepts(self, native_type: str) -> bool:
        """Whether an active detector accepts values of ``native_type``."""
        return bool(self._plans[native_type])

    def spans(self, native_types: set[str]) -> bool:
        """Whether an active detector accepts several of ``native_types``."""
        return any(len(detector.accepts & native_types) > 1 for detector in self.active)

    def run(
        self,
        tallies: list[DetectorTally],
        native_type: str,
        values: Sequence[str],
        counts: Sequence[int],
        lengths: Sequence[int] | None = None,
        skipped: tuple[bool, ...] | None = None,
        tested: Sequence[int] = (),
        warmup: tuple | None = None,
        rewarm: set[int] | None = None,
    ) -> tuple[list | None, list | None]:
        """Classify a batch of distinct values of one native type, in
        first-seen order, and add them to the tallies (design 12 and 13).

        ``values`` are analytical texts for strings, canonical texts for other
        types, with their ``lengths`` when known. The detectors flagged in
        ``skipped`` test only the values at the positions ``tested`` (warm-up
        values of a streamed field, at ``rewarm``, and probes) and count the
        others as not tested. During the warm-up, ``warmup`` holds the
        positions of the values met for the first time and, among them, those
        of its second half, whose reactions each tally counts once. Returns
        the results of the number and date detectors for strings, aligned
        with ``values`` (``None`` where a value was not tested), or ``None``.
        """
        numbers = dates = None
        total = None
        for i, detector, cap, pattern in self._plans[native_type]:
            tally = tallies[i]
            keeps = native_type == "string" and (i == self._number or i == self._date)
            if tally.error is not None and not keeps:
                continue
            batch, batch_counts, batch_lengths = values, counts, lengths
            positions = None
            if skipped is not None and skipped[i]:
                if total is None:
                    total = sum(counts)
                tally.skip(total - sum(counts[j] for j in tested))
                if not tested:
                    continue
                positions = tested
                batch = [values[j] for j in tested]
                batch_counts = [counts[j] for j in tested]
                batch_lengths = None if lengths is None else [lengths[j] for j in tested]
            if tally.rejected:
                tally.reject(batch, batch_counts)
                continue
            if cap is not None:
                longest = (
                    max(batch_lengths, default=0)
                    if batch_lengths is not None
                    else max(map(len, batch), default=0)
                )
                if longest > cap:
                    # Values above the input cap are not tested (design 12.2).
                    kept = [j for j, value in enumerate(batch) if len(value) <= cap]
                    tally.untested(
                        sum(batch_counts) - sum(batch_counts[j] for j in kept)
                    )
                    positions = (
                        kept if positions is None else [positions[j] for j in kept]
                    )
                    batch = [batch[j] for j in kept]
                    batch_counts = [batch_counts[j] for j in kept]
            results = self._classify(i, detector, pattern, batch)
            tally.add_many(batch, batch_counts, results)
            if tally.error is None:
                if warmup is not None:
                    _count_warmup(tally, results, positions, warmup)
                elif skipped is not None and skipped[i]:
                    _count_probes(tally, results, batch_counts, positions, rewarm)
            if self._field_scope[i] and not tally.rejected and tally.error is None:
                try:
                    tally.rejected = bool(tally.accumulator.rejects_field())
                except Exception as exc:  # noqa: BLE001 - detector code is isolated (CA19)
                    tally.error = type(exc).__name__
            if keeps:
                if positions is not None:
                    aligned: list[object] = [None] * len(values)
                    for position, found in zip(positions, results, strict=True):
                        aligned[position] = found
                    results = aligned
                if i == self._number:
                    numbers = results
                else:
                    dates = results
        return numbers, dates

    def _classify(
        self, index: int, detector: Detector, pattern, values: Sequence[str]
    ) -> list:
        """Results of one detector on ``values``, in order. Values whose shape
        the detector rules out are not matched without being classified."""
        if pattern is not None:
            fits = self._fits
            candidates = [
                j for j, value in enumerate(values) if fits(shape(value))[index]
            ]
            results: list[object] = [None] * len(values)
            found = self._classify(
                index, detector, None, [values[j] for j in candidates]
            )
            for j, result in zip(candidates, found, strict=True):
                results[j] = result
            return results
        try:
            results = detector.classify_many(values)
            if len(results) != len(values):
                raise ValueError("classify_many returned a wrong number of results")
        except Exception:  # noqa: BLE001 - detector code is isolated (CA19)
            # Locate the failure: each value alone, in order.
            results = _one_by_one(detector.classify, values)
        return results

    def _fits(self, value_shape: str) -> tuple[bool, ...]:
        """Whether ``value_shape`` fits the shapes of each active detector.

        Shapes repeat across values far more than values do: the matches are
        memoized per shape, in a bounded cache.
        """
        cache = self._shape_cache
        fits = cache.get(value_shape)
        if fits is None:
            if len(cache) >= SHAPE_CACHE_SIZE:
                cache.clear()
            fits = cache[value_shape] = tuple(
                detector.shapes is None
                or detector.shapes.fullmatch(value_shape) is not None
                for detector in self.active
            )
        return fits

    def skipping(self, tallies: list[DetectorTally]) -> tuple[bool, ...] | None:
        """The adaptive detectors skipped for the rest of a field once its
        warm-up is over, ``None`` when there are none (design 13): those that
        reacted to none of the warm-up values, and the rare ones, which
        reacted to at most ``detection.rare_share`` of them and to none in
        its second half. A detector that failed or rejected the field is
        never skipped, nor is a rare sensitive detector that has not matched:
        the field might have values to mask. Skipped tallies record the
        warm-up."""
        skip = tuple(
            adaptive and self._skippable(tally)
            for adaptive, tally in zip(self._adaptive, tallies, strict=True)
        )
        if not any(skip):
            return None
        for tally, skipped in zip(tallies, skip, strict=True):
            if skipped:
                tally.skipped_after = self.warmup_values
        return skip

    def _skippable(self, tally: DetectorTally) -> bool:
        if tally.error is not None or tally.rejected:
            return False
        reactions = tally.warmup_reactions
        if not reactions:
            return True
        # A rare detector still reacting in the second half of the warm-up
        # may be becoming frequent, as in a sorted file: it stays.
        if reactions > self.rare_reactions or tally.recent_reactions:
            return False
        return not tally.detector.sensitive or tally.matched > 0

    def add_string_measures(
        self,
        measures,
        values: Sequence[str],
        counts: Sequence[int],
        lengths: Sequence[int],
        numbers: list | None,
        dates: list | None,
    ) -> None:
        """Technical type families and numbers of analytical strings, from the
        results of the number and date detectors (design 9.4 and 9.7): the
        rules of ``technical.string_family``."""
        families = measures.families
        numeric = measures.numeric
        other = 0
        # Longer values that neither detector recognized are text.
        candidates = [
            j
            for j, length in enumerate(lengths)
            if length <= 5
            or (numbers is not None and numbers[j] is not None)
            or (dates is not None and dates[j] is not None)
        ]
        for j in candidates:
            count = counts[j]
            found = None if dates is None else dates[j]
            if isinstance(found, Classification) and (
                found.state == "ambiguous"
                or (found.state == "matched" and type(found.value) is date)
            ):
                family = "date"
            elif lengths[j] <= 5 and values[j].casefold() in BOOLEAN_WORDS:
                family = "boolean"
            else:
                family = "text"
            found = None if numbers is None else numbers[j]
            if isinstance(found, Classification):
                state = found.state
                if state == "matched":
                    integer = is_integer_format(found.format)
                    if family == "text":
                        family = "integer" if integer else "number"
                    if _is_number(found.value):
                        numeric.add(found.value, not integer, False, count)
                elif state == "ambiguous" and family == "text":
                    family = "number"
            if family != "text":
                families[family] = families.get(family, 0) + count
                other += count
        text = sum(counts) - other
        if text:
            families["text"] = families.get("text", 0) + text

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
        report_probe: ProbeReporter | None = None,
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
                results.append(
                    tallies[position].result(
                        report_failure, gate, report_probe, self.rare_share
                    )
                )
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

# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Insight lot 18: the arrays and the sets of keys of JSON, the long texts and the
sensitive columns counted without a value (design 20.33 to 20.35, decision O61).

The oracles below are built from the data the tests generate, never from the
accumulators: the lengths of the arrays and the sets of keys come from the Python
objects written to the file, the words and digits of a text from the text itself,
and the masks of a sensitive column from a mask written here.
"""

from __future__ import annotations

import json
import random
import tracemalloc
from collections import Counter

import jsonschema
import pytest
from planner_helpers import by_analyzer, scan_csv
from scan_helpers import write_text
from second_pass_helpers import entry, forced_plan
from typer.testing import CliRunner

from tabalyst.cli import app
from tabalyst.config import DeepSettings
from tabalyst.report_deep import result_summary
from tabalyst.reporting import dataset_views, load_profile
from tabalyst.scanner import ScanConfig, scan
from tabalyst.scanner.planner import default_registry, plan_analyses
from tabalyst.scanner.planner.facts import ROOT_FIELD
from tabalyst.scanner.secondpass import deep_document, run_second_pass
from tabalyst.scanner.secondpass.document import analysis_key
from tabalyst.scanner.secondpass.exactset import ExactPool
from tabalyst.scanner.secondpass.forms import FormsAccumulator, floored
from tabalyst.scanner.secondpass.models import DistinctLimited
from tabalyst.scanner.secondpass.parallel import part_name
from tabalyst.scanner.secondpass.schema import deep_schema
from tabalyst.scanner.secondpass.texts import (
    FingerprintAccumulator,
    TextAccumulator,
    bucket,
    fingerprint,
)
from tabalyst.source_guard import StaleSource

runner = CliRunner()
# Few samples: the Scan does not hold every distinct value, so nothing is answered
# from them and the source is read.
READ = {"limits": {"max_samples": 50}}
WIDE = DeepSettings.model_validate({"structure": {"max_listed": 100}})
# The counts of a sensitive column are off by default (decision O61).
ON = DeepSettings.model_validate({"sensitive": {"enabled": True}})


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TABALYST_HOME", str(tmp_path.parent / f"{tmp_path.name}-home"))


# JSON: arrays and sets of keys ---------------------------------------------------


def _events(count: int = 1_203, seed: int = 18) -> list[dict[str, object]]:
    """Records with arrays of several lengths (one inside the items of another), an
    object that has some of its keys and objects in the items of an array."""
    rng = random.Random(seed)
    records: list[dict[str, object]] = []
    for position in range(count):
        record: dict[str, object] = {"id": position}
        if rng.random() < 0.85:
            record["tags"] = [f"t{k}" for k in range(rng.choice((0, 1, 1, 2, 3, 5, 8)))]
        orders = []
        for number in range(rng.randint(0, 3)):
            order: dict[str, object] = dict.fromkeys(
                rng.sample(("sku", "qty", "note", "price"), rng.randint(1, 4)), number
            )
            if rng.random() < 0.4:
                order["lines"] = [1] * rng.randint(0, 3)
            orders.append(order)
        record["orders"] = orders
        draw = rng.random()
        if draw < 0.5:
            record["addr"] = rng.choice(
                ({"city": "Q"}, {"city": "R", "zip": "1"}, {"city": "S", "zip": "2", "country": "CA"})
            )
        elif draw < 0.6:
            record["addr"] = None
        records.append(record)
    return records


def _json_deep(tmp_path, records, name="data.jsonl", deep=WIDE, **settings):
    tmp_path.mkdir(parents=True, exist_ok=True)
    text = (
        json.dumps(records)
        if name.endswith(".json")
        else "\n".join(json.dumps(item) for item in records) + "\n"
    )
    path = write_text(tmp_path, name, text)
    result = scan(path, config=ScanConfig.model_validate({**READ, **settings}))
    plan = plan_analyses(
        result, forced=True, registry=default_registry().runnable(), deep=deep
    )
    outcome = run_second_pass(result, path, plan, settings=deep, workers=1)
    return result, plan, outcome, path


def _complete(outcome, analyzer, display):
    found = entry(outcome, analyzer, display)
    assert found.status == "complete", (found.reason, found.detail)
    return found.result


def _key_sets(result):
    names = set(result.key_names)
    return {frozenset(names - set(item.absent)): item.count for item in result.listed}


def test_array_lengths_are_counted_exactly_at_every_depth(tmp_path):
    records = _events()
    _, _, outcome, _ = _json_deep(tmp_path, records)

    wanted = {
        "tags": [len(r["tags"]) for r in records if "tags" in r],
        "orders": [len(r["orders"]) for r in records],
        "orders[].lines": [
            len(o["lines"]) for r in records for o in r["orders"] if "lines" in o
        ],
    }
    for display, lengths in wanted.items():
        found = _complete(outcome, "array_profile", display)
        counted = Counter(lengths)
        assert {item.length: item.count for item in found.length_histogram} == dict(counted)
        assert found.arrays == len(lengths)
        assert found.empty == counted[0]
        assert found.items == sum(lengths)
        assert (found.min_length, found.max_length) == (min(lengths), max(lengths))
        assert found.mean_length == pytest.approx(sum(lengths) / len(lengths))
        ordered = sorted(lengths)
        middle = len(ordered) // 2
        median = (
            ordered[middle]
            if len(ordered) % 2
            else (ordered[middle - 1] + ordered[middle]) / 2
        )
        assert found.quantiles[2].value == median
        assert found.quantiles[2].accuracy == "exact"
        assert result_summary(found)[1] == "exact"


def test_arrays_of_the_same_length_are_answered_by_the_scan(tmp_path):
    records = [{"id": n, "pair": [n, n + 1]} for n in range(300)]
    _, plan, _, _ = _json_deep(tmp_path, records)

    found = by_analyzer(plan, "array_profile")["pair"]

    assert found.selection.state == "already_satisfied"
    assert found.selection.reason == "lengths_constant"


def test_arrays_spread_over_too_wide_a_range_are_left_out(tmp_path):
    records = [{"id": n, "items": list(range(n % 40))} for n in range(200)]
    deep = DeepSettings.model_validate({"arrays": {"max_lengths": 10}})
    _, plan, _, _ = _json_deep(tmp_path, records, deep=deep)

    found = by_analyzer(plan, "array_profile")["items"]

    assert found.applicability.reasons == ["array_lengths_too_wide"]


@pytest.mark.parametrize("name", ["data.jsonl", "data.json"])
def test_the_sets_of_keys_of_records_and_objects_are_counted_exactly(tmp_path, name):
    records = _events()
    _, plan, outcome, _ = _json_deep(tmp_path, records, name=name)

    root = _complete(outcome, "structure_variants", ROOT_FIELD)
    assert _key_sets(root) == dict(Counter(frozenset(r) for r in records))
    assert root.objects == len(records) and root.complete and root.untracked == 0
    assert root.keys == len(root.key_names) == 4
    assert root.always == sum(
        1 for key in root.key_names if all(key in r for r in records)
    )
    address = _complete(outcome, "structure_variants", "addr")
    objects = [r["addr"] for r in records if isinstance(r.get("addr"), dict)]
    assert _key_sets(address) == dict(Counter(frozenset(o) for o in objects))
    assert address.objects == len(objects)
    items = _complete(outcome, "structure_variants", "orders[]")
    orders = [o for r in records for o in r["orders"]]
    assert _key_sets(items) == dict(Counter(frozenset(o) for o in orders))
    assert items.objects == len(orders)
    assert by_analyzer(plan, "structure_variants")["$"].method == "key_sets"
    for found in (root, address, items):
        assert sum(item.count for item in found.listed) + found.other_objects == found.objects
        assert [item.count for item in found.listed] == sorted(
            (item.count for item in found.listed), reverse=True
        )


def test_the_sets_of_keys_do_not_depend_on_how_many_records_there_are(tmp_path):
    records = _events(5_200, seed=4)
    _, _, outcome, _ = _json_deep(tmp_path, records)

    root = _complete(outcome, "structure_variants", ROOT_FIELD)

    assert _key_sets(root) == dict(Counter(frozenset(r) for r in records))
    assert root.objects == 5_200


def test_sets_beyond_the_limit_are_summed_up_and_the_count_says_so(tmp_path):
    records = _events()
    deep = DeepSettings.model_validate({"structure": {"max_variants": 3, "max_listed": 2}})
    _, _, outcome, _ = _json_deep(tmp_path, records, deep=deep)

    items = _complete(outcome, "structure_variants", "orders[]")

    orders = [frozenset(o) for r in records for o in r["orders"]]
    first = list(dict.fromkeys(orders))[:3]
    counted = Counter(orders)
    assert not items.complete and items.distinct == 3
    assert len(items.listed) == 2
    assert items.untracked == sum(1 for o in orders if o not in first)
    tracked = sorted((counted[s] for s in first), reverse=True)
    assert [item.count for item in items.listed] == tracked[:2]
    assert items.other_objects == tracked[2]
    assert sum(item.count for item in items.listed) + items.other_objects + items.untracked == len(orders)
    assert result_summary(items)[1] == "at_least"


def test_a_list_of_keys_is_cut_at_the_limit_and_the_total_is_kept(tmp_path):
    records = _events()
    deep = DeepSettings.model_validate({"structure": {"max_keys": 2, "max_listed": 100}})
    _, _, outcome, _ = _json_deep(tmp_path, records, deep=deep)

    items = _complete(outcome, "structure_variants", "orders[]")

    assert items.keys == 5 and len(items.key_names) == 2 and items.key_names_truncated
    for item in items.listed:
        assert len(item.absent) <= 2
        assert item.absent_total == items.keys - item.keys


def test_nothing_is_counted_where_there_is_one_set_one_object_or_a_table(tmp_path):
    records = [{"id": n, "name": "x", "box": {"w": 1}} for n in range(300)]
    _, plan, _, _ = _json_deep(tmp_path, records)

    structure = by_analyzer(plan, "structure_variants")
    assert structure["$"].applicability.reasons == ["uniform_keys"]
    assert structure["box"].applicability.reasons == ["uniform_keys"]
    single = [{"a": 1, "b": {"x": 1, "y": 2}}, {"a": 2}]
    _, plan, _, _ = _json_deep(tmp_path / "single", single)
    assert by_analyzer(plan, "structure_variants")["b"].applicability.reasons == ["single_object"]
    (tmp_path / "csv").mkdir()
    table = scan_csv(tmp_path / "csv", "a,b", [f"{n},x" for n in range(200)], **READ)
    assert by_analyzer(forced_plan(table), "structure_variants") == {}


def test_a_source_that_changed_fails_the_json_checks(tmp_path):
    records = _events(400)
    result, plan, _, path = _json_deep(tmp_path, records)
    changed = [dict(r, extra=1) if n == 7 else r for n, r in enumerate(records)]
    write_text(tmp_path, "data.jsonl", "\n".join(json.dumps(r) for r in changed) + "\n")

    with pytest.raises(StaleSource):
        run_second_pass(result, path, plan, workers=1)


# Long texts ----------------------------------------------------------------------

WORDS = ("alpha", "beta", "gamma", "delta", "12", "345", "6789", "omega", "x²", "٣٤")


def _text(rng: random.Random) -> str:
    text = " ".join(rng.choice(WORDS) for _ in range(rng.randint(15, 70)))
    return text + ("\nsecond line 42" if rng.random() < 0.3 else "")


def _texts_csv(tmp_path, rows: int = 9_500, seed: int = 18):
    """A column of texts drawn from a pool (so some repeat), one of unique texts and
    a short one."""
    rng = random.Random(seed)
    pool = [_text(rng) for _ in range(400)]
    table = {
        "id": [str(n) for n in range(rows)],
        "note": [rng.choice(pool) for _ in range(rows)],
        "free": [f"{_text(rng)} #{n}" for n in range(rows)],
        "code": [f"C{n % 30}" for n in range(rows)],
    }
    tmp_path.mkdir(parents=True, exist_ok=True)
    import csv as csv_module
    import io

    buffer = io.StringIO()
    writer = csv_module.writer(buffer, lineterminator="\n")
    writer.writerow(list(table))
    writer.writerows(zip(*table.values(), strict=True))
    write_text(tmp_path, "data.csv", buffer.getvalue())
    result = scan(tmp_path / "data.csv", config=ScanConfig.model_validate(READ))
    return table, result


def _profile(texts):
    return {
        "words": [len(t.split()) for t in texts],
        "lines": [len(t.splitlines()) or 1 for t in texts],
        "digits": [sum(1 for c in t if c.isdecimal()) for t in texts],
        "chars": [len(t) for t in texts],
    }


def test_the_words_lines_and_digits_of_texts_are_counted_exactly_across_batches(tmp_path):
    table, result = _texts_csv(tmp_path)
    outcome = run_second_pass(result, tmp_path / "data.csv", forced_plan(result), workers=1)

    for display in ("note", "free"):
        found = _complete(outcome, "text_profile", display)
        measured = _profile(table[display])
        assert found.texts == len(table[display])
        assert found.characters == sum(measured["chars"])
        assert found.words == sum(measured["words"])
        assert (found.min_words, found.max_words) == (min(measured["words"]), max(measured["words"]))
        assert found.lines == sum(measured["lines"])
        assert found.max_lines == max(measured["lines"])
        assert found.multi_line == sum(1 for n in measured["lines"] if n > 1)
        assert found.digits == sum(measured["digits"])
        assert found.digit_share == pytest.approx(sum(measured["digits"]) / sum(measured["chars"]))
        words = Counter(bucket(n) for n in measured["words"])
        assert sum(item.count for item in found.word_buckets) == found.texts
        for item in found.word_buckets:
            low = 0 if item.low == 0 else item.low.bit_length()
            assert item.count == words[low]
        shares = Counter(
            0 if d == 0 else -(-d * 10 // c) for d, c in zip(measured["digits"], measured["chars"], strict=True)
        )
        assert found.digit_buckets == [shares[i] for i in range(11)]
        assert result_summary(found)[1] == "exact"


def test_short_values_have_no_text_profile_and_no_fingerprint(tmp_path):
    _, result = _texts_csv(tmp_path)
    plan = forced_plan(result)

    assert "code" not in by_analyzer(plan, "text_profile")
    assert "code" not in by_analyzer(plan, "fingerprint_distinct")
    assert {"note", "free"} <= set(by_analyzer(plan, "text_profile"))


def test_texts_are_told_apart_by_fingerprint_and_the_repeated_ones_are_counted(tmp_path):
    table, result = _texts_csv(tmp_path)
    outcome = run_second_pass(result, tmp_path / "data.csv", forced_plan(result), workers=1)

    found = _complete(outcome, "fingerprint_distinct", "note")

    counts = Counter(table["note"])
    assert found.accuracy == "fingerprint_based" and found.bits == 128
    assert found.values == len(table["note"]) and found.distinct == len(counts)
    assert found.redundant == found.values - found.distinct and not found.unique
    again = [(text, n) for text, n in counts.items() if n > 1]
    assert found.repeated == len(again)
    assert found.repeated_occurrences == sum(n for _, n in again)
    top = sorted(again, key=lambda item: (-item[1], fingerprint("string", item[0])))[:10]
    assert [(item.digest, item.count) for item in found.listed] == [
        (fingerprint("string", text).hex(), n) for text, n in top
    ]
    assert result_summary(found)[1] == "fingerprint"
    # Unique texts are answered by the Scan, which counted them.
    assert by_analyzer(forced_plan(result), "fingerprint_distinct")["free"].selection.state == (
        "already_satisfied"
    )


def test_a_listed_digest_is_the_one_the_scan_gives_its_long_texts(tmp_path):
    from tabalyst.scanner.longtext import digest_of

    assert fingerprint("string", "a long text\né").hex() == digest_of(
        "string", "a long text\né"
    )[0]


def test_the_texts_of_a_json_source_are_profiled_too(tmp_path):
    rng = random.Random(2)
    records = [{"id": n, "body": _text(rng) if n % 9 else 12} for n in range(900)]
    _, _, outcome, _ = _json_deep(tmp_path, records, deep=DeepSettings())

    found = _complete(outcome, "text_profile", "body")
    texts = [r["body"] for r in records if isinstance(r["body"], str)]
    assert found.texts == len(texts)
    assert found.words == sum(len(t.split()) for t in texts)
    prints = _complete(outcome, "fingerprint_distinct", "body")
    assert prints.values == len(records)
    assert prints.distinct == len({str(r["body"]) for r in records})


def test_text_profile_memory_does_not_grow_with_the_texts():
    accumulator = TextAccumulator()
    rng = random.Random(1)
    base = " ".join(rng.choice(WORDS) for _ in range(9_000))
    tracemalloc.start()
    for round_ in range(300):
        batch = [f"{base} {round_}-{k}" for k in range(4)]
        accumulator.add_strings(batch, [1] * 4)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert accumulator.texts == 1_200
    assert peak < 4_000_000, peak


def test_fingerprints_stay_within_the_pool_and_say_what_is_proven(tmp_path):
    pool = ExactPool(40_000)
    accumulator = FingerprintAccumulator(pool, 5)
    for round_ in range(200):
        accumulator.add_strings([f"{round_}-{k} " + "x" * 5_000 for k in range(50)], [1] * 50)
    found = accumulator.result(10_000, None, None)

    assert isinstance(found, DistinctLimited)
    assert found.lower_bound < 10_000
    assert pool.used <= pool.total + 50 * 400
    assert accumulator.counts == {}


def test_texts_give_the_same_results_in_workers_and_in_the_process(tmp_path):
    _, result = _texts_csv(tmp_path, rows=4_300)
    plan = forced_plan(result)
    alone = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    shared = run_second_pass(result, tmp_path / "data.csv", plan, workers=2)
    for analyzer in ("text_profile", "fingerprint_distinct"):
        mine = {e.display: e.result.model_dump(mode="json") for e in alone.document.analyses if e.analyzer == analyzer}
        theirs = {e.display: e.result.model_dump(mode="json") for e in shared.document.analyses if e.analyzer == analyzer}
        assert mine == theirs and mine
    assert part_name(TextAccumulator()) == "texts"


# Sensitive columns without a value ------------------------------------------------


def _config(directory):
    """A configuration file that turns the counts of sensitive columns on."""
    path = directory / "config.json"
    path.write_text(json.dumps({"deep": {"sensitive": {"enabled": True}}}), encoding="utf-8")
    return path


def _mask(text: str) -> str:
    return "".join(
        "9" if c.isdigit() else ("A" if c.isupper() else "a") if c.isalpha() else c for c in text
    )


PRIVATE = ("10.0.{a}.{b}", "192.168.{a}.{b}")
PUBLIC = ("8.8.{a}.{b}", "93.184.{a}.{b}")


def _sensitive_csv(tmp_path, rows: int = 4_300, seed: int = 18):
    """An email, an address and a phone number per row, with a few rare forms, and
    a column that is not sensitive."""
    rng = random.Random(seed)
    emails, ips, phones, kinds = [], [], [], []
    for n in range(rows):
        emails.append(f"zq{n}@leak.test" if n % 11 else f"Z{n}.Q@leak.test")
        if n % 700 == 0:
            ips.append("127.0.0.1")
            kinds.append("ipv4_loopback")
        elif n % 3 == 0:
            ips.append(rng.choice(PRIVATE).format(a=rng.randint(0, 9), b=rng.randint(1, 99)))
            kinds.append("ipv4_private")
        else:
            ips.append(rng.choice(PUBLIC).format(a=rng.randint(0, 9), b=rng.randint(1, 99)))
            kinds.append("ipv4_public")
        phones.append(
            f"06 {rng.randint(10, 99)} {rng.randint(10, 99)} {rng.randint(10, 99)} {rng.randint(10, 99)}"
            if n % 2
            else f"514-555-{rng.randint(1000, 9999)}"
        )
    table = {"id": [str(n) for n in range(rows)], "email": emails, "ip": ips, "phone": phones, "tag": [f"T{n % 7}" for n in range(rows)]}
    tmp_path.mkdir(parents=True, exist_ok=True)
    write_text(
        tmp_path,
        "data.csv",
        ",".join(table) + "\n" + "\n".join(",".join(row) for row in zip(*table.values(), strict=True)) + "\n",
    )
    config = {"limits": {"max_samples": 50, "max_distinct_per_field": 100, "max_tracked_values": 100}}
    result = scan(tmp_path / "data.csv", config=ScanConfig.model_validate(config))
    return table, kinds, result


def _floor(counts, floor):
    """The counts that are shown, and those that are summed up: a count below the
    floor is, and while what is summed up holds fewer values than the floor the
    smallest one shown joins it."""
    shown = {key: n for key, n in counts.items() if n >= floor}
    others = {key: n for key, n in counts.items() if n < floor}
    while shown and 0 < sum(others.values()) < floor:
        smallest = max(shown, key=lambda key: (-shown[key], key))
        others[smallest] = shown.pop(smallest)
    return shown, others


def test_the_masks_of_a_masked_column_are_counted_exactly_across_batches(tmp_path):
    table, _, result = _sensitive_csv(tmp_path)
    outcome = run_second_pass(result, tmp_path / "data.csv", forced_plan(result, ON), workers=1)

    for display in ("email", "ip", "phone"):
        found = _complete(outcome, "sensitive_forms", display)
        masks = Counter(_mask(v) for v in table[display])
        assert found.values == len(table[display]) and found.complete
        assert found.forms == len(masks)
        listed = {item.form: item.count for item in found.listed}
        shown, others = _floor(masks, found.min_count)
        assert listed == shown
        assert found.other_forms == len(others)
        assert found.other_values == sum(others.values())


def test_the_class_of_addresses_and_phone_numbers_is_counted_with_a_floor(tmp_path):
    table, kinds, result = _sensitive_csv(tmp_path)
    outcome = run_second_pass(result, tmp_path / "data.csv", forced_plan(result, ON), workers=1)

    ips = _complete(outcome, "sensitive_forms", "ip").classes
    counted = Counter(kinds)
    assert ips.detector == "ip_address" and ips.unclassified == 0
    assert {i.form: i.count for i in ips.listed} == dict(counted)
    phones = _complete(outcome, "sensitive_forms", "phone").classes
    expected = Counter("fr_06" if v.startswith("06") else "nanp_geographic" for v in table["phone"])
    assert {i.form: i.count for i in phones.listed} == dict(expected)
    assert _complete(outcome, "sensitive_forms", "email").classes is None


def test_a_form_or_class_below_the_floor_is_summed_up_with_more(tmp_path):
    shown, others, count = floored([("a", 200), ("b", 30), ("c", 3), ("d", 2)], 5, 20)
    assert (shown, others, count) == ([("a", 200), ("b", 30)], 2, 5)
    shown, others, count = floored([("a", 200), ("b", 30), ("c", 3)], 5, 20)
    assert (shown, others, count) == ([("a", 200)], 2, 33)
    shown, others, count = floored([("a", 9), ("b", 8)], 5, 1)
    assert (shown, others, count) == ([("a", 9)], 1, 8)
    shown, others, count = floored([("a", 3), ("b", 1)], 5, 20)
    assert (shown, others, count) == ([], 2, 4)

    _, _, result = _sensitive_csv(tmp_path, rows=1_500)
    deep = DeepSettings.model_validate({"sensitive": {"enabled": True, "min_count": 5}})
    outcome = run_second_pass(result, tmp_path / "data.csv", forced_plan(result, deep), settings=deep, workers=1)
    found = _complete(outcome, "sensitive_forms", "ip")
    for item in [*found.listed, *found.classes.listed]:
        assert item.count >= found.min_count
    assert found.other_values == 0 or found.other_values >= found.min_count
    assert found.classes.other == 0 or found.classes.other >= found.min_count


def test_a_rare_mask_is_never_listed(tmp_path):
    rows = [f"a{n}@x.test" for n in range(300)] + ["Q.R@x.test", "Q.S@x.test", "Q.T@x.test"]
    tmp_path.mkdir(parents=True, exist_ok=True)
    write_text(tmp_path, "data.csv", "email\n" + "\n".join(rows) + "\n")
    config = {"limits": {"max_samples": 50, "max_distinct_per_field": 100, "max_tracked_values": 100}}
    result = scan(tmp_path / "data.csv", config=ScanConfig.model_validate(config))
    outcome = run_second_pass(result, tmp_path / "data.csv", forced_plan(result, ON), workers=1)

    found = _complete(outcome, "sensitive_forms", "email")

    assert all(item.count >= 5 for item in found.listed)
    assert "A.A@a.aaaa" not in {item.form for item in found.listed}
    assert found.other_forms >= 1 and found.other_values >= 5


def test_no_value_of_a_sensitive_column_is_in_the_document(tmp_path):
    table, _, result = _sensitive_csv(tmp_path)
    outcome = run_second_pass(result, tmp_path / "data.csv", forced_plan(result, ON), workers=2)
    text = deep_document(outcome.document)

    for needle in ("leak.test", "zq12@", "10.0.", "192.168.", "8.8.", "93.184.", "514-555", "127.0.0.1"):
        assert needle not in text, needle
    for display in ("email", "ip", "phone"):
        for value in table[display][:200]:
            assert value not in text
    # The distinct count of a masked column is two numbers.
    distinct = _complete(outcome, "exact_distinct", "email")
    assert distinct.distinct == len(set(table["email"]))
    assert by_analyzer(forced_plan(result, ON), "exact_distinct")["email"].parameters["exposure"] == "mask"


def test_the_counts_of_a_sensitive_column_are_off_by_default(tmp_path):
    table, _, result = _sensitive_csv(tmp_path)
    plan = forced_plan(result)

    assert DeepSettings().sensitive.enabled is False
    assert by_analyzer(plan, "sensitive_forms") == {}
    for display in ("email", "ip", "phone"):
        assert by_analyzer(plan, "exact_distinct")[display].applicability.reasons == [
            "sensitive_exposure"
        ]
    outcome = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    text = deep_document(outcome.document)
    assert "sensitive_forms" not in text and "leak.test" not in text
    assert len(set(table["email"])) > 0


def test_a_column_that_hides_its_values_gets_a_count_and_nothing_else(tmp_path):
    table, _, _ = _sensitive_csv(tmp_path)
    hidden = scan(
        tmp_path / "data.csv",
        config=ScanConfig.model_validate(
            {
                "limits": {"max_samples": 50, "max_distinct_per_field": 100, "max_tracked_values": 100},
                "exposure": {"sensitive_values": "hide"},
            }
        ),
    )
    plan = forced_plan(hidden, ON)

    assert by_analyzer(plan, "sensitive_forms")["email"].applicability.reasons == ["hidden_exposure"]
    assert by_analyzer(plan, "position_drift")["email"].applicability.reasons == ["sensitive_exposure"]
    # Short values are no texts, so these two have no candidate for the column.
    assert "email" not in by_analyzer(plan, "text_profile")
    outcome = run_second_pass(hidden, tmp_path / "data.csv", plan, workers=1)
    assert _complete(outcome, "exact_distinct", "email").distinct == len(set(table["email"]))
    text = deep_document(outcome.document)
    assert "leak.test" not in text and "A.A" not in text


def test_a_sensitive_column_is_never_counted_by_an_automatic_plan(tmp_path):
    _, _, result = _sensitive_csv(tmp_path)

    plan = plan_analyses(result, deep=ON)

    for candidate in plan.candidates:
        if candidate.analyzer in (
            "sensitive_forms",
            "array_profile",
            "structure_variants",
            "text_profile",
            "fingerprint_distinct",
        ) or (candidate.analyzer == "exact_distinct" and candidate.display in ("email", "ip", "phone")):
            assert candidate.selection.state != "selected", candidate.id


def test_masks_and_counts_are_the_same_in_workers_and_in_the_process(tmp_path):
    _, _, result = _sensitive_csv(tmp_path)
    plan = forced_plan(result, ON)
    alone = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    shared = run_second_pass(result, tmp_path / "data.csv", plan, workers=2)
    for analyzer in ("sensitive_forms", "exact_distinct"):
        mine = {e.display: e.result.model_dump(mode="json") for e in alone.document.analyses if e.analyzer == analyzer}
        theirs = {e.display: e.result.model_dump(mode="json") for e in shared.document.analyses if e.analyzer == analyzer}
        assert mine == theirs and mine
    assert part_name(FormsAccumulator(min_count=5, max_listed=5, max_tracked=10, detector=None)) == "forms"


def test_masks_past_the_limit_are_summed_up_and_the_count_says_so(tmp_path):
    emails = [f"{'a' * (n % 30 + 1)}@x.test" for n in range(900)]
    tmp_path.mkdir(parents=True, exist_ok=True)
    write_text(tmp_path, "data.csv", "\n".join(["email", *emails]) + "\n")
    config = {"limits": {"max_samples": 50, "max_distinct_per_field": 100, "max_tracked_values": 100}}
    result = scan(tmp_path / "data.csv", config=ScanConfig.model_validate(config))
    deep = DeepSettings.model_validate({"sensitive": {"enabled": True, "max_tracked": 10}})
    outcome = run_second_pass(result, tmp_path / "data.csv", forced_plan(result, deep), settings=deep, workers=1)

    found = _complete(outcome, "sensitive_forms", "email")

    masks = Counter(_mask(v) for v in emails)
    first = list(dict.fromkeys(_mask(v) for v in emails))[:10]
    assert len(masks) == 30 and not found.complete and found.forms == 10
    assert found.untracked == sum(n for m, n in masks.items() if m not in first)
    assert found.other_values >= found.untracked
    assert result_summary(found)[1] == "at_least"


def test_the_class_of_an_address_follows_its_range():
    from tabalyst.scanner.detectors.ip import IP_CLASSES, ip_class

    cases = {
        "8.8.8.8": "ipv4_public",
        "10.1.2.3": "ipv4_private",
        "172.16.0.1": "ipv4_private",
        "172.32.0.1": "ipv4_public",
        "127.0.0.1": "ipv4_loopback",
        "169.254.1.1": "ipv4_link_local",
        "100.64.0.1": "ipv4_shared",
        "224.0.0.1": "ipv4_multicast",
        "0.0.0.0": "ipv4_unspecified",
        "192.0.2.5": "ipv4_reserved",
        "::1": "ipv6_loopback",
        "fe80::1": "ipv6_link_local",
        "fd00::1": "ipv6_private",
        "2606:4700::1111": "ipv6_public",
        "2001:db8::1": "ipv6_reserved",
    }
    for address, kind in cases.items():
        assert ip_class(address) == kind and kind in IP_CLASSES


def test_the_fast_path_of_dotted_addresses_gives_the_class_of_the_ranges():
    from ipaddress import IPv4Address

    from tabalyst.scanner.detectors.ip import _CLASS_NETWORKS, _ipv4_class

    rng = random.Random(3)
    probes = ["0.0.0.0", "255.255.255.255", "172.15.0.1", "172.16.0.1", "172.31.255.255", "172.32.0.1"]
    probes += [f"{rng.choice((0, 10, 100, 127, 169, 172, 192, 198, 203, 224, 239, 240))}."
               f"{rng.randint(0, 255)}.{rng.randint(0, 3)}.{rng.randint(0, 255)}" for _ in range(3_000)]
    for text in probes:
        address = IPv4Address(text)
        expected = next(
            (f"ipv4_{name}" for name, networks in _CLASS_NETWORKS for net in networks
             if net.version == 4 and address in net),
            "ipv4_public",
        )
        assert _ipv4_class(text) == expected, text


def test_the_class_of_a_phone_number_never_holds_an_area_code():
    from tabalyst.scanner.detectors.phone import PHONE_CLASSES, phone_class

    cases = {
        ("06 12 34 56 78", "fr"): "fr_06",
        ("+33 1 23 45 67 89", "fr"): "fr_01",
        ("0033 (0) 4 12 34 56 78", "fr"): "fr_04",
        ("514-555-1234", "nanp"): "nanp_geographic",
        ("(800) 555-1234", "nanp"): "nanp_toll_free",
        ("1-900-555-1234", "nanp"): "nanp_premium",
    }
    for (number, region), kind in cases.items():
        assert phone_class(number, region) == kind and kind in PHONE_CLASSES
    assert all("514" not in kind for kind in PHONE_CLASSES)


# Document, reuse and report ------------------------------------------------------


def test_the_documents_validate_against_their_schema_and_every_summary_reads(tmp_path):
    _, _, result = _sensitive_csv(tmp_path / "s")
    sensitive = run_second_pass(result, tmp_path / "s" / "data.csv", forced_plan(result, ON), workers=1)
    _, texts = _texts_csv(tmp_path / "t")
    prose = run_second_pass(texts, tmp_path / "t" / "data.csv", forced_plan(texts), workers=1)
    _, _, structure, _ = _json_deep(tmp_path / "j", _events(400))
    kinds = set()
    for outcome in (sensitive, prose, structure):
        jsonschema.validate(json.loads(deep_document(outcome.document)), deep_schema())
        for found in outcome.document.analyses:
            if found.result is not None:
                kinds.add(found.result.kind)
                assert result_summary(found.result)[0]
    assert {
        "array_profile",
        "structure_variants",
        "text_profile",
        "fingerprint_distinct",
        "sensitive_forms",
    } <= kinds


def test_a_result_is_reused_while_the_scan_and_the_settings_do_not_change(tmp_path):
    _, _, result = _sensitive_csv(tmp_path)
    plan = forced_plan(result, ON)
    first = run_second_pass(result, tmp_path / "data.csv", plan, workers=1)
    again = run_second_pass(result, tmp_path / "data.csv", plan, previous=first.document, workers=1)
    assert not again.read_source
    mine = {e.id for e in first.document.analyses if e.analyzer == "sensitive_forms"}
    assert mine and mine <= set(again.reused)

    deep = DeepSettings.model_validate({"sensitive": {"enabled": True, "min_count": 9}})
    other = forced_plan(result, deep)
    moved = {c.id for c in other.candidates if c.analyzer == "sensitive_forms" and c.selection.state == "selected"}
    assert moved
    keys = {
        analysis_key(plan.base, c) for c in plan.candidates if c.id in moved
    } & {analysis_key(other.base, c) for c in other.candidates if c.id in moved}
    assert not keys


def test_the_analyses_are_declared_at_most_moderate_and_run_on_a_forced_pass_only(tmp_path):
    _, _, result = _sensitive_csv(tmp_path)
    plan = forced_plan(result, ON)
    chosen = [
        c
        for c in plan.candidates
        if c.analyzer in ("sensitive_forms", "text_profile", "fingerprint_distinct") and c.costs
    ]
    assert chosen
    assert {c.costs.cpu for c in chosen} <= {"very_low", "low", "moderate"}
    assert {c.utility.score for c in chosen} == {40}


def test_the_report_prints_the_cards_of_the_json_and_no_value_of_a_sensitive_column(tmp_path):
    rng = random.Random(6)
    records = [
        {
            "id": n,
            "mail": f"zq{n}@leak.test",
            "tags": ["t"] * rng.choice((0, 1, 2, 4)),
            **({"note": f"call {n} about the invoice\nthanks"} if n % 3 else {}),
            "box": {"w": 1} if n % 2 else {"w": 1, "h": 2},
        }
        for n in range(700)
    ]
    path = write_text(tmp_path, "events.jsonl", "\n".join(json.dumps(r) for r in records) + "\n")
    result = runner.invoke(app, ["report", str(path), "--deep", "--yes"])
    assert result.exit_code == 0, result.output
    profile = load_profile(path.with_suffix(".report.json"))

    cards = dataset_views(profile)[0].insights
    families = {card.family for card in cards}
    assert {"structure"} <= families
    titles = {card.title for card in cards}
    assert "Sets of keys of the records" in titles and "Lengths of the arrays" in titles
    root = next(card for card in cards if card.title == "Sets of keys of the records")
    assert root.scope == "dataset" and root.fields == []
    html = path.with_suffix(".report.html").read_text(encoding="utf-8")
    assert "leak.test" not in html
    # The domain is a declared key of the detector (DEC-027), published with its count;
    # no address is.
    text = path.with_suffix(".report.json").read_text(encoding="utf-8")
    assert "@leak.test" not in text and "zq1" not in text


def test_the_report_prints_the_masks_of_a_masked_column_and_never_a_value(tmp_path):
    table, _, _scanned = _sensitive_csv(tmp_path)
    source = tmp_path / "data.csv"
    result = runner.invoke(app, ["report", str(source), "--deep", "--yes", "--config", str(_config(tmp_path))])
    assert result.exit_code == 0, result.output
    profile = load_profile(source.with_suffix(".json"))

    cards = dataset_views(profile)[0].insights
    forms = [card for card in cards if card.family == "forms"]
    assert {card.column for card in forms} >= {"email", "ip", "phone"}
    for card in forms:
        masks = card.tables[0].rows
        assert masks and all(row[0] == _mask(row[0]) for row in masks)
    html = source.with_suffix(".html").read_text(encoding="utf-8")
    assert "leak.test" not in html
    for value in table["ip"][:100]:
        assert value not in html


def test_a_document_edited_to_hold_a_value_is_not_printed(tmp_path):
    _sensitive_csv(tmp_path)
    source = tmp_path / "data.csv"
    assert runner.invoke(app, ["report", str(source), "--deep", "--yes", "--config", str(_config(tmp_path))]).exit_code == 0
    path = source.with_suffix(".json")
    document = json.loads(path.read_text(encoding="utf-8"))
    for item in document["analyses"]["deep"]["analyses"]:
        if item["analyzer"] == "sensitive_forms" and item["display"] == "email":
            item["result"]["listed"][0]["form"] = "zq12@leak.test"
        if item["analyzer"] == "sensitive_forms" and item["display"] == "ip":
            item["result"]["classes"]["listed"][0]["form"] = "10.0.1.1"
    edited = tmp_path / "edited.json"
    edited.write_text(json.dumps(document), encoding="utf-8")

    cards = dataset_views(load_profile(edited))[0].insights

    shown = {card.column for card in cards if card.family == "forms"}
    assert "email" not in shown and "ip" not in shown and "phone" in shown

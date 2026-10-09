# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Contract tests for deterministic catalog selection and exclusions."""

from collections import Counter
from pathlib import Path

import pytest

from tabalyst.errors import ConfigurationError
from tabalyst.generate_package import load_generate_package
from tabalyst.generate_selection import select_catalog_row


def _fixture(root: Path) -> Path:
    (root / "schemas").mkdir()
    (root / "data").mkdir()
    (root / "dataset.yaml").write_text(
        'format: tabalyst.generate.package\nformat_version: "0.1.0"\n'
        'id: mini_computer\npackage_version: "0.1.0"\n'
        'catalog: catalog.yaml\ndefaults: {rows: 10, seed: 42}\n'
        'generation_profiles: {balanced: {}}\n'
        'datasets:\n  - id: computers\n    mode: generated\n'
        '    row_source: catalog_steps\n    schema: schemas/computers.yaml\n'
        '    steps:\n'
        '      - {id: series, kind: select, output: generation_id, source: series, candidate_column: id}\n'
        '      - id: cpu\n        kind: select\n        output: cpu_id\n'
        '        source: series_cpu\n        candidate_column: cpu_id\n'
        '        where: {series_id: generation_id}\n        weight_column: weight\n'
        '      - id: memory\n        kind: select\n        output: memory_id\n'
        '        source: series_memory\n        candidate_column: memory_id\n'
        '        where: {series_id: generation_id}\n        weight_column: weight\n'
        '        influences:\n          - source: cpu_memory\n'
        '            candidate_column: memory_id\n            where: {cpu_id: cpu_id}\n',
        encoding="utf-8",
    )
    (root / "schemas/computers.yaml").write_text(
        'columns:\n  - {name: cpu, type: string, from: cpu_id}\n', encoding="utf-8",
    )
    (root / "catalog.yaml").write_text(
        'tables:\n'
        '  series: {role: dictionary, file: data/series.csv, schema: schemas/series.yaml}\n'
        '  cpu: {role: dictionary, file: data/cpu.csv, schema: schemas/cpu.yaml}\n'
        '  memory: {role: dictionary, file: data/memory.csv, schema: schemas/memory.yaml}\n'
        '  series_cpu: {role: weighted_relation, file: data/series_cpu.csv, schema: schemas/series_cpu.yaml}\n'
        '  series_memory: {role: weighted_relation, file: data/series_memory.csv, schema: schemas/series_memory.yaml}\n'
        '  cpu_memory: {role: weighted_relation, file: data/cpu_memory.csv, schema: schemas/cpu_memory.yaml}\n'
        '  excludes: {role: constraint, file: data/excludes.csv, schema: schemas/excludes.yaml}\n',
        encoding="utf-8",
    )
    for name in ("series", "cpu", "memory"):
        (root / f"schemas/{name}.yaml").write_text(
            'type: dictionary\ncolumns:\n'
            '  id: {type: string, required: true, unique: true}\n'
            '  en: {type: string, required: true}\n', encoding="utf-8",
        )
    (root / "data/series.csv").write_text("id,en\ngen_one,One\n", encoding="utf-8")
    (root / "data/cpu.csv").write_text("id,en\nalpha,Alpha\nbeta,Beta\n", encoding="utf-8")
    (root / "data/memory.csv").write_text("id,en\nmem_16,16 GB\nmem_32,32 GB\n", encoding="utf-8")
    for name, first, first_table, second, second_table in (
        ("series_cpu", "series_id", "series", "cpu_id", "cpu"),
        ("series_memory", "series_id", "series", "memory_id", "memory"),
        ("cpu_memory", "cpu_id", "cpu", "memory_id", "memory"),
    ):
        (root / f"schemas/{name}.yaml").write_text(
            'type: weighted_relation\ncolumns:\n'
            f'  {first}: {{type: string, required: true, references: {first_table}.id}}\n'
            f'  {second}: {{type: string, required: true, references: {second_table}.id}}\n'
            '  weight: {type: number, required: true}\n', encoding="utf-8",
        )
    (root / "data/series_cpu.csv").write_text(
        "series_id,cpu_id,weight\ngen_one,alpha,1\ngen_one,beta,3\n", encoding="utf-8",
    )
    (root / "data/series_memory.csv").write_text(
        "series_id,memory_id,weight\ngen_one,mem_16,1\ngen_one,mem_32,3\n", encoding="utf-8",
    )
    (root / "data/cpu_memory.csv").write_text(
        "cpu_id,memory_id,weight\nalpha,mem_16,4\nbeta,mem_32,4\n", encoding="utf-8",
    )
    (root / "schemas/excludes.yaml").write_text(
        'type: constraint\ncolumns:\n'
        '  scope_id: {type: string, required: true}\n'
        '  condition_field: {type: string, required: true}\n'
        '  condition_id: {type: string, required: true}\n'
        '  target_field: {type: string, required: true}\n'
        '  target_id: {type: string, required: true}\n'
        '  action: {type: string, required: true}\n', encoding="utf-8",
    )
    (root / "data/excludes.csv").write_text(
        'scope_id,condition_field,condition_id,target_field,target_id,action\n',
        encoding="utf-8",
    )
    return root


def _draws(root: Path, count: int = 10, seed: int = 42) -> list[tuple[str, str]]:
    package = load_generate_package(root)
    return [(row["cpu_id"], row["memory_id"]) for index in range(count)
            for row in [select_catalog_row(package, "computers", seed, index, "balanced")]]


def test_repeats_ten_row_snapshot_and_changes_with_seed(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    first = _draws(root)
    assert first == _draws(root)
    assert first != _draws(root, seed=43)
    assert first == [
        ("beta", "mem_32"), ("alpha", "mem_16"), ("beta", "mem_32"),
        ("beta", "mem_32"), ("beta", "mem_32"), ("beta", "mem_32"),
        ("beta", "mem_32"), ("beta", "mem_32"), ("beta", "mem_32"),
        ("beta", "mem_16"),
    ]


def test_weights_are_relative_and_influences_shift_distribution(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    first = _draws(root, 3000)
    cpu = Counter(item[0] for item in first)
    assert 2100 < cpu["beta"] < 2400
    memory_given_beta = Counter(memory for chosen, memory in first if chosen == "beta")
    assert memory_given_beta["mem_32"] > memory_given_beta["mem_16"] * 8
    path = root / "data/series_cpu.csv"
    path.write_text(path.read_text(encoding="utf-8").replace(",1\n", ",10\n").replace(",3\n", ",30\n"), encoding="utf-8")
    assert first == _draws(root, 3000)


def test_candidate_order_uses_ids_instead_of_csv_order(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    first = _draws(root, 100)
    path = root / "data/series_cpu.csv"
    path.write_text(
        "series_id,cpu_id,weight\ngen_one,beta,3\ngen_one,alpha,1\n",
        encoding="utf-8",
    )
    assert first == _draws(root, 100)


def test_future_exclusions_remove_impossible_branch(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "data/excludes.csv"
    path.write_text(path.read_text(encoding="utf-8")
                    + 'global,memory_id,mem_16,cpu_id,alpha,exclude\n'
                    + 'balanced,memory_id,mem_32,cpu_id,alpha,exclude\n', encoding="utf-8")
    draws = _draws(root, 200)
    assert {cpu for cpu, _ in draws} == {"beta"}


def test_exclusions_are_idempotent_and_profile_scoped(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "data/excludes.csv"
    line = 'balanced,cpu_id,alpha,memory_id,mem_16,exclude\n'
    path.write_text(path.read_text(encoding="utf-8") + line, encoding="utf-8")
    once = _draws(root, 200)
    path.write_text(path.read_text(encoding="utf-8") + line, encoding="utf-8")
    assert once == _draws(root, 200)
    package = load_generate_package(root)
    unscoped = [select_catalog_row(package, "computers", 42, index)
                for index in range(200)]
    assert any(row["cpu_id"] == "alpha" and row["memory_id"] == "mem_16"
               for row in unscoped)


def test_derived_field_constraint_uses_source_id(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    manifest = root / "dataset.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(
        '      - id: memory\n',
        '      - {id: cpu_name, kind: derive, output: cpu_name, from_table: cpu, selected: cpu_id, column: en}\n'
        '      - id: memory\n',
    ), encoding="utf-8")
    path = root / "data/excludes.csv"
    path.write_text(path.read_text(encoding="utf-8")
                    + 'global,cpu_name,alpha,memory_id,mem_16,exclude\n', encoding="utf-8")
    package = load_generate_package(root)
    rows = [select_catalog_row(package, "computers", 42, index, "balanced")
            for index in range(200)]
    assert all(not (row["cpu_id"] == "alpha" and row["memory_id"] == "mem_16")
               for row in rows)
    assert any(row["cpu_name"] == "Alpha" for row in rows)


def test_filter_intersection_can_exhaust_candidates(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    manifest = root / "dataset.yaml"
    manifest.write_text(manifest.read_text(encoding="utf-8").replace(
        '        influences:\n          - source: cpu_memory\n',
        '        filters:\n          - source: cpu_memory\n'
        '            candidate_column: memory_id\n'
        '            where: {cpu_id: cpu_id}\n'
        '        influences:\n          - source: cpu_memory\n',
    ), encoding="utf-8")
    (root / "data/cpu_memory.csv").write_text(
        "cpu_id,memory_id,weight\n", encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="GENERATION_IMPOSSIBLE_CONFIGURATION"):
        _draws(root)


def test_unrelated_later_step_does_not_change_prior_choices(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    first = _draws(root, 100)
    manifest = root / "dataset.yaml"
    text = manifest.read_text(encoding="utf-8")
    text = text.replace('            where: {cpu_id: cpu_id}\n',
                        '            where: {cpu_id: cpu_id}\n'
                        '      - {id: extra, kind: select, output: extra_id, source: cpu, candidate_column: id}\n')
    manifest.write_text(text, encoding="utf-8")
    assert first == _draws(root, 100)


def test_empty_completion_reports_context(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    path = root / "data/excludes.csv"
    path.write_text(path.read_text(encoding="utf-8")
                    + 'global,generation_id,gen_one,cpu_id,alpha,exclude\n'
                    + 'global,generation_id,gen_one,cpu_id,beta,exclude\n', encoding="utf-8")
    with pytest.raises(ConfigurationError, match=r"GENERATION_IMPOSSIBLE_CONFIGURATION: dataset=computers generation=gen_one.*field=cpu_id"):
        _draws(root)


@pytest.mark.parametrize("line", [
    'global,cpu_id,missing,memory_id,mem_16,exclude\n',
    'unknown,cpu_id,alpha,memory_id,mem_16,exclude\n',
    'global,cpu_id,alpha,memory_id,mem_16,allow\n',
])
def test_rejects_invalid_constraint_at_load(tmp_path: Path, line: str) -> None:
    root = _fixture(tmp_path)
    path = root / "data/excludes.csv"
    path.write_text(path.read_text(encoding="utf-8") + line, encoding="utf-8")
    with pytest.raises(ConfigurationError, match="PACKAGE_CONSTRAINT"):
        load_generate_package(root)


def test_rejects_duplicate_influence_for_one_context(tmp_path: Path) -> None:
    root = _fixture(tmp_path)
    schema = root / "schemas/cpu_memory.yaml"
    schema.write_text(schema.read_text(encoding="utf-8").replace(
        '  weight: {type: number, required: true}\n',
        '  variant_id: {type: string, required: true, references: series.id}\n'
        '  weight: {type: number, required: true}\n',
    ), encoding="utf-8")
    (root / "data/series.csv").write_text(
        "id,en\ngen_one,One\ngen_two,Two\n", encoding="utf-8",
    )
    path = root / "data/cpu_memory.csv"
    path.write_text(
        "cpu_id,memory_id,variant_id,weight\n"
        "alpha,mem_16,gen_one,4\nalpha,mem_16,gen_two,2\n"
        "beta,mem_32,gen_one,4\n", encoding="utf-8",
    )
    with pytest.raises(ConfigurationError, match="PACKAGE_STEP_DUPLICATE"):
        load_generate_package(root)


def test_search_limit_is_explicit_instead_of_reporting_impossibility(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _fixture(tmp_path)
    package = load_generate_package(root)
    monkeypatch.setattr("tabalyst.generate_selection.MAX_SEARCH_NODES", 1)
    with pytest.raises(ConfigurationError, match="GENERATION_SEARCH_LIMIT"):
        select_catalog_row(package, "computers", 42, 0)

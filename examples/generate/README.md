# Generate examples

`input/` holds four editable YAML definitions. Run all of them from the
repository root with an editable Tabalyst installation:

```console
python examples/generate/generate_examples.py
```

The script writes `output/<yaml-stem>/`. It uses the row counts declared in
each YAML and selects every anomaly profile; a selected profile also writes
its untouched clean CSV. The default Insurance run has 275,000 combined rows.
The current four definitions produce 16 files, about 230 MiB in total.
`output/` is local and ignored by Git.

Use `--rows 30 --output-dir PATH` for a small review outside the checkout,
`--clean-only` to omit anomalies, and `--force` to replace planned files.
Without `--force`, an existing generated file stops the run before any new
definition is executed. If a YAML later declares several profiles, each gets
its own subfolder to avoid filename collisions.

The copies of `input/crm.yaml` and `input/insurance.yaml` under
`src/tabalyst/generate_examples/` are packaged for the `--example` CLI option.
Keep each pair byte-identical when editing either definition.

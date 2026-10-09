# Generate examples

`input/` holds three transitional YAML definitions; `crm/` holds the CRM package.
Run all of them from the
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

The CRM package under `src/tabalyst/generate_examples/crm/` is packaged for
`--example crm`. Keep it identical to the visible `crm/` package. The
Insurance YAML under `src/tabalyst/generate_examples/` remains transitional;
keep it identical to `input/insurance.yaml`.

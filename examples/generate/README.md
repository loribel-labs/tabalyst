# Generate examples

`crm/`, `insurance/`, `common-references/`, and `cohorts-anomalies/` are
versioned packages. Run all four from the repository root with an editable
Tabalyst installation:

```console
python examples/generate/generate_examples.py
```

The script writes `output/<package-name>/`. It uses the row counts declared in
each package and selects every anomaly profile; a selected profile also writes
its untouched clean CSV. The default Insurance run has 275,000 combined rows.
The current four definitions produce 16 files, about 230 MiB in total.
`output/` is local and ignored by Git.

Use `--rows 30 --output-dir PATH` for a small review outside the checkout,
`--clean-only` to omit anomalies, and `--force` to replace planned files.
Without `--force`, an existing generated file stops the run before any new
package is executed. If a package later declares several profiles, each gets
its own subfolder to avoid filename collisions.

The CRM and Insurance packages under `src/tabalyst/generate_examples/` are
bundled for `--example crm` and `--example insurance`. Keep each identical to
its visible package. Insurance's seven synthetic resource tables and their
provenance are in `insurance/data/` and `insurance/SOURCES.md`.

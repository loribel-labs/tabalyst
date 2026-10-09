# Generate examples

`common-references/` and `cohorts-anomalies/` are small editable fixtures.
The CRM and Insurance packages have their single source under
`src/tabalyst/generate_examples/`. Run all four column packages from the
repository root with an editable Tabalyst installation:

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

The CRM, Insurance, and Computer packages under `src/tabalyst/generate_examples/`
are the only copies and are available as `--example crm`, `--example insurance`,
and `--example computer`. Insurance's seven synthetic resource tables and
provenance are in `src/tabalyst/generate_examples/insurance/data/` and
`src/tabalyst/generate_examples/insurance/SOURCES.md`.

# Tabalyst examples

The examples are organized by input name so additional public datasets can be
added without mixing source data and generated artifacts.

```text
examples/
|-- config.json
|-- generate/
|   |-- generate_examples.py
|   |-- input/ (four YAML definitions)
|   `-- output/ (generated locally; ignored by Git)
|-- input/
|   |-- basic.csv
|   |-- insurance-customers.csv
|   |-- orders.json
|   |-- sales.xlsx
|   `-- web-events.jsonl
`-- output/
    |-- basic/
    |   |-- report.html
    |   |-- report.json
    |   `-- executions.json
    |-- insurance-customers/
    |   |-- report.html
    |   |-- report.json
    |   |-- report/ (34 standalone column pages with --details)
    |   `-- executions.json
    |-- orders/
    |   |-- report.html
    |   |-- report.json
    |   `-- executions.json
    |-- sales/
    |   |-- report.html
    |   |-- report.json
    |   `-- executions.json
    `-- web-events/
        |-- report.html
        |-- report.json
        `-- executions.json
```

`basic.csv` is a five-row smoke example. `insurance-customers.csv` contains 3,000
synthetic customer and contract records across 34 columns. Its people, contact
details, and contracts are fictional; email addresses use reserved `.example`
domains. `orders.json` is a synthetic shop export: 60 customers with nested
addresses, tags and orders. Its report has one dataset, `$.customers[]`, the only
collection of arrays of objects that Tabalyst Inspect finds in it.
`web-events.jsonl` is a synthetic web analytics log in JSON Lines: 300 events with
nested `user` and `device` objects, tags arrays, null values and an optional
field that appears late, plus three bad lines (a truncated record, a line that
is not JSON and a JSON array instead of an object). Its report is partial on
purpose: the three lines are excluded and counted, the 300 events are analyzed.
Its people and identifiers are fictional. `sales.xlsx` is a synthetic Excel
workbook: a sheet `Orders` of 120 fictional orders under two title lines, a
five-row `Regions` lookup sheet and a `Notes` sheet. Inspect selects `$.Orders`,
which has more than ten times the rows of `$.Regions`, so the report needs no
choice. The workbook is written by `make_sales_workbook.py`, with the same
bytes on every run; it needs `pip install xlsxwriter` and is only to run when the
input itself must be regenerated.

From the repository root, regenerate the outputs with:

```console
tabalyst report examples/input/basic.csv -o examples/output/basic/report.html --config examples/config.json --force
tabalyst report examples/input/insurance-customers.csv -o examples/output/insurance-customers/report.html --config examples/config.json --details --force
tabalyst report examples/input/orders.json -o examples/output/orders/report.html --config examples/config.json --force
tabalyst report examples/input/web-events.jsonl -o examples/output/web-events/report.html --config examples/config.json --force
tabalyst report examples/input/sales.xlsx -o examples/output/sales/report.html --config examples/config.json --force
```

Every output folder is independent and contains its own HTML report, canonical
JSON profile and cumulative `executions.json` history. The insurance example
also has standalone HTML pages under `report/`. Delete an output folder
before regenerating when a fresh one-entry execution history is required.

The input datasets and generated output are public repository examples. The wheel
contains the runtime package, report resources, and packaged copies of the
`examples/generate/input/` YAML definitions. CRM and Insurance are local development
demos. Generate is under development
and is not advertised as a released feature. The CRM data is synthetic, with
reserved `.example` domains and fictional phone numbers. The configured 20,000
rows, generic account names and CRM audit story were approved for the example
on 2026-10-05. Generate remains local development work until a release.

To review the CRM export outside the checkout:

```console
tabalyst generate --example crm --rows 500 --anomaly-profile dirty_realistic -d OUTPUT_DIR
tabalyst scan OUTPUT_DIR/crm-contacts.dirty_realistic.csv -o OUTPUT_DIR/scan.json
tabalyst report OUTPUT_DIR/scan.json --scan -o OUTPUT_DIR/report.html
```

Scan and Report expose missing values, fragmented categories and normalized
variants. The mutation summary counts requested, applied and skipped changes.
Neither tool currently diagnoses cross-column CRM rules such as stage versus
probability.

`examples/generate/input/common-references.yaml` is a lot 3R development fixture.
It generates coherent synthetic Canadian person, address and contact fields
from packaged references. Its prefixes and area codes are synthetic, email
domains end in `.example`, and phone line numbers use reserved `555-01xx`.
The Insurance example is now complete in `examples/generate/input/insurance.yaml`
and the packaged `--example insurance` copy. Its seven domain tables are in
`src/tabalyst/generate_resources/insurance/`; their provenance is in
`insurance/SOURCES.md`. To review 3,000 rows outside the checkout:

```console
tabalyst generate --example insurance --rows 3000 --anomaly-profile dirty_realistic -d OUTPUT_DIR
```

This creates clean files for Principal, Ontario and Quebec, their clean union,
and three anomaly artifacts for that union. The 2,182/273/545 branch allocation
comes from the declared 200,000/25,000/50,000 weights. The new clean CSV has
the same 34 column names as the existing public demo, but places `filiale` last
and has different rows and identifiers. Do not replace
`examples/input/insurance-customers.csv` or its report without a separate
decision to change the published demo.

`examples/generate/input/cohorts-anomalies.yaml` is a lot 4 development fixture. It
shows two normal status conventions in the clean CSV and a separate `dirty`
profile that writes an altered CSV, cell-level change log and summary. Run it
with `tabalyst generate examples/generate/input/cohorts-anomalies.yaml --anomaly-profile dirty -d OUTPUT_DIR`.
Keep `OUTPUT_DIR` outside the repository for one-off local trials. The packaged
Insurance YAML is the same complete example as the visible file.

## Regenerate all Generate examples

Run the script from the repository root with an editable installation of
Tabalyst. It reads every YAML in `examples/generate/input/` and writes into
`examples/generate/output/<definition>/`. The output folder is ignored by Git.
By default it uses each YAML's declared row counts and generates every declared
anomaly profile along with its clean CSV. Insurance therefore writes 275,000
combined rows; allow enough disk space for the clean and altered copies.

```console
python examples/generate/generate_examples.py
```

Existing outputs are protected; pass `--force` to replace generated files.
For a quick review run, `--rows 30` overrides each definition's row count,
and `--output-dir PATH` writes outside the checkout. `--clean-only` skips the
profile passes. A definition with several profiles gets one subfolder per
profile so its clean files cannot collide.

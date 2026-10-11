# Tabalyst examples

The examples are organized by input name so additional public datasets can be
added without mixing source data and generated artifacts.

```text
examples/
|-- config.json
|-- generate/
|   |-- generate_examples.py
|   |-- common-references/ (reference provider fixture)
|   |-- cohorts-anomalies/ (cohort and anomaly fixture)
|   `-- output/ (generated locally; ignored by Git)
|-- input/
|   |-- basic.csv
|   |-- insurance-customers.csv
|   |-- orders.json
|   |-- sales.xlsx
|   `-- web-events.jsonl
`-- output/
    |-- insurance-customers-scan/
    |   |-- insurance-customers.scan.json
    |   |-- insurance-customers.scan.html
    |   |-- insurance-customers.deep.json
    |   |-- smart-plan.txt
    |   |-- insurance-customers.sample.csv
    |   |-- insurance-customers.sample.json
    |   `-- insurance-customers.sample.html
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

The folder `insurance-customers-scan/` shows the three steps of Tabalyst Scan on
`insurance-customers.csv` (see "Simple, Clear and Smart" in the documentation):
the scan (Simple, with its web page, Clear), the second pass and the plan of a
smart sample (Smart), and the smart sample with its report and page. Regenerate it
with:

```console
tabalyst scan examples/input/insurance-customers.csv -o examples/output/insurance-customers-scan/insurance-customers.scan.json --config examples/config.json --deep --yes --force
tabalyst scan examples/input/insurance-customers.csv --plan --smart --sample-size 150 --config examples/config.json > examples/output/insurance-customers-scan/smart-plan.txt
tabalyst sample examples/input/insurance-customers.csv --sample-method smart --rows 150 --seed 42 -o examples/output/insurance-customers-scan/insurance-customers.sample.csv --config examples/config.json --force
```

Every output folder of the reports is independent and contains its own HTML report, canonical
JSON profile and cumulative `executions.json` history. The insurance example
also has standalone HTML pages under `report/`. Delete an output folder
before regenerating when a fresh one-entry execution history is required.

The input datasets and generated output are public repository examples. The wheel
contains the runtime package, report resources, and the CRM, Insurance, and
Computer packages when built from this development checkout. The published 0.6.2 release
uses definition version 1. The CRM data is synthetic, with
reserved `.example` domains and fictional phone numbers. The configured 20,000
rows, generic account names and CRM audit story were approved for the example
on 2026-10-05. Generate is published; the package format and Computer remain
local development work until a later release.

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

`examples/generate/common-references/` is a reference provider fixture.
It generates coherent synthetic Canadian person, address and contact fields
from packaged references. Its prefixes and area codes are synthetic, email
domains end in `.example`, and phone line numbers use reserved `555-01xx`.
The Insurance example lives only in `src/tabalyst/generate_examples/insurance/`
and is available as `--example insurance`. Its seven domain tables and
provenance are in that package's `data/` and `SOURCES.md`. To review 3,000 rows outside the checkout:

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

`examples/generate/cohorts-anomalies/` is a cohort and anomaly fixture. It
shows two normal status conventions in the clean CSV and a separate `dirty`
profile that writes an altered CSV, cell-level change log and summary. Run it
with `tabalyst generate examples/generate/cohorts-anomalies/ --anomaly-profile dirty -d OUTPUT_DIR`.
Keep `OUTPUT_DIR` outside the repository for one-off local trials.

The CRM development package lives only at
`src/tabalyst/generate_examples/crm/` and is available as `--example crm`. It preserves the 400-account
pool, 26 columns, cohorts and measured anomalies.

The Computer development package lives only at
`src/tabalyst/generate_examples/computer/` and is available as
`--example computer`. From an installed development wheel, run:

```console
tabalyst generate --example computer --validate-only
tabalyst generate --example computer -d OUTPUT_DIR/clean --rows 10000 --seed 42 --output-profile extended
tabalyst generate --example computer -d OUTPUT_DIR/dirty --rows 10000 --seed 42 --output-profile extended --anomaly-profile dirty_realistic
tabalyst generate --example computer -d OUTPUT_DIR/units --rows 10000 --seed 42 --unit-style localized
tabalyst generate --example computer -d OUTPUT_DIR/selected-units --rows 10000 --seed 42 --output-profile extended --unit-columns memory_gb,display_size_in,battery_wh,weight_kg
tabalyst generate --example computer -d OUTPUT_DIR/unit-mix --rows 10000 --seed 42 --anomaly-profile unit_variants
tabalyst generate --example computer -d OUTPUT_DIR/unit-mix-extended --rows 10000 --seed 42 --output-profile extended --anomaly-profile unit_variants_extended
```

The command writes aligned `computers-en.csv`, `computers-fr.csv`, and
`computers.meta.json`. The local Computer package offers the 40-column
`compact`, 70-column `standard`, and 111-column `extended`
profiles with paired `en,fr` locales. The extended profile currently adds
hardware, connectivity, physical specifications, and synthetic commerce,
distribution and e-commerce measures. Use `--output-profile extended` to
review these fields.
A JSON `--request FILE` can select
`rows`, `seed`, `as_of_date`, `generation_profile`, `output_profile`, `market`,
`locales`, `unit_style`, `unit_columns`, and `anomaly_profile`; explicit CLI options override
the request. `--unit-style localized` formats physical measurements as text
with localized units (`4 GB` / `4 Go` for memory); the default keeps numeric
cells. `--unit-columns` selects measured fields and implies localized output;
the JSON request uses a list of field names. `unit_variants` injects capacity
suffixes into altered CSVs; `unit_variants_extended` covers all 14 measured
fields and requires `--output-profile extended`.
Computer's `dirty_realistic` and `dirty_stress` profiles add altered EN/FR
CSVs, per-cell change logs, and summaries while preserving clean outputs.
Keep the output folder outside the checkout when testing a wheel.

## Regenerate all Generate examples

Run the script from the repository root with an editable installation of
Tabalyst. It reads the four column packages, then writes into
`examples/generate/output/<package>/`. The output folder is ignored by Git.
By default it uses each package's declared row counts and generates every declared
anomaly profile along with its clean CSV. Insurance therefore writes 275,000
combined rows; allow enough disk space for the clean and altered copies.

```console
python examples/generate/generate_examples.py
```

Existing outputs are protected; pass `--force` to replace generated files.
For a quick review run, `--rows 30` overrides each definition's row count,
and `--output-dir PATH` writes outside the checkout. `--clean-only` skips the
profile passes. A package with several profiles gets one subfolder per
profile so its clean files cannot collide.

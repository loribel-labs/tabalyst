# Tabalyst examples

The examples are organized by role, so source data, published demos, scenarios
and scripts never mix.

```text
examples/
|-- config.json
|-- datasets/ (shared synthetic sources, with their provenance)
|   |-- basic.csv
|   |-- insurance-customers.csv
|   |-- insurance-customers-100k.json (request for a generated 100,000-row file)
|   |-- orders.json
|   |-- sales.xlsx
|   `-- web-events.jsonl
|-- showcase/ (what the website and the documentation publish, nothing else)
|   |-- basic/
|   |-- insurance-customers/ (report.html, report.json, scan.json; 100,000 rows)
|   |-- insurance-customers.scan/ (scan, second pass, smart plan and sample; 100,000 rows)
|   |-- orders/
|   |-- sales/
|   `-- web-events/
|-- tools/
|   |-- make_datasets.py (builds the generated datasets outside the checkout)
|   |-- make_index.py (writes the generated lists of the READMEs)
|   |-- regenerate.py
|   `-- make_sales_workbook.py
`-- generate/
    |-- generate_examples.py
    |-- common-references/ (reference provider fixture)
    |-- cohorts-anomalies/ (cohort and anomaly fixture)
    `-- output/ (generated locally; ignored by Git)
```

## Datasets

`datasets/README.md` describes each source file and who uses it. `basic.csv` is a
five-row smoke example. `insurance-customers.csv` contains 3,000 synthetic
customer and contract records across 34 columns. Its people, contact details, and
contracts are fictional; email addresses use reserved `.example` domains.
`orders.json` is a synthetic shop export: 60 customers with nested addresses, tags
and orders. Its report has one dataset, `$.customers[]`, the only collection of
arrays of objects that Tabalyst Inspect finds in it. `web-events.jsonl` is a
synthetic web analytics log in JSON Lines: 300 events with nested `user` and
`device` objects, tags arrays, null values and an optional field that appears
late, plus three bad lines (a truncated record, a line that is not JSON and a JSON
array instead of an object). Its report is partial on purpose: the three lines
are excluded and counted, the 300 events are analyzed. `sales.xlsx` is a synthetic
Excel workbook: a sheet `Orders` of 120 fictional orders under two title lines, a
five-row `Regions` lookup sheet and a `Notes` sheet. Inspect selects `$.Orders`,
which has more than ten times the rows of `$.Regions`, so the report needs no
choice. The workbook is written by `tools/make_sales_workbook.py`, with the same
bytes on every run; it needs `pip install xlsxwriter` and is only to run when the
input itself must be regenerated.

## Showcase

Each folder of `showcase/` holds a manifest, `demo.json`, next to the files it
generates: the source dataset, the `steps` (the `tabalyst` command lines, written
from the repository root), and `publish`: `site` is true when `tabalyst.com`
copies the folder, `docs` lists the documentation pages that quote it. The list of
demos below is generated from these manifests by `tools/make_index.py` (`--check`
fails when it is stale; `regenerate.py` runs it), so it never drifts.

<!-- index:showcase:start -->
| Demo | Tool | Copied by tabalyst.com | Quoted by |
| --- | --- | --- | --- |
| `showcase/basic/` | `report` | no | `get-started/examples.md`, `reference/history.md` |
| `showcase/insurance-customers/` | `report` | yes | `get-started/examples.md` |
| `showcase/insurance-customers.scan/` | `scan` | no | `get-started/simple-clear-smart.md` |
| `showcase/orders/` | `report` | yes | `get-started/examples.md` |
| `showcase/sales/` | `report` | yes | `get-started/examples.md` |
| `showcase/web-events/` | `report` | yes | `get-started/examples.md` |
<!-- index:showcase:end -->

From the repository root, regenerate every demo with:

```console
python examples/tools/regenerate.py --fresh
```

Name some demos to regenerate only those (`regenerate.py basic sales`), or use
`--list` to print the ids, the tool and the publication of each. `--fresh` deletes
the `executions.json` of a demo first, so its history restarts at one entry; without
it, each run adds an entry. A step stops the run when its command fails.

The commands of the report demos are, with `--config examples/config.json --force`
added to each (`{datasets}` is the folder where `make_datasets.py` builds the generated
datasets, `D:/GIT.test/tabalyst/datasets/` here, or `$TABALYST_DATASETS`):

```console
tabalyst report examples/datasets/basic.csv -o examples/showcase/basic/report.html
tabalyst report {datasets}/insurance-customers-100k.csv -o examples/showcase/insurance-customers/report.html
tabalyst report examples/datasets/orders.json -o examples/showcase/orders/report.html
tabalyst report examples/datasets/web-events.jsonl -o examples/showcase/web-events/report.html
tabalyst report examples/datasets/sales.xlsx -o examples/showcase/sales/report.html
```

The folder `insurance-customers.scan/` shows the three steps of Tabalyst Scan on
`insurance-customers-100k.csv`, the generated base of 100,000 rows (see "Simple, Clear and Smart" in the documentation):
the scan (Simple, with its web page, Clear), the second pass and the plan of a
smart sample (Smart), and the smart sample with its report and page. Its four steps
are in its `demo.json`:

```console
tabalyst scan {datasets}/insurance-customers-100k.csv -o examples/showcase/insurance-customers.scan/insurance-customers.scan.json --config examples/config.json --deep --yes --force
tabalyst scan {datasets}/insurance-customers-100k.csv --config examples/config.json --deep --yes --force --no-html
tabalyst scan {datasets}/insurance-customers-100k.csv --plan --smart --sample-size 3000 --config examples/config.json
tabalyst sample {datasets}/insurance-customers-100k.csv --smart --rows 3000 --seed 42 -o examples/showcase/insurance-customers.scan/insurance-customers.sample.csv --config examples/config.json --force
```

`make_datasets.py` generates the base (45 seconds, 27 MB, SHA-256 checked) and leaves it outside the
checkout; `regenerate.py` calls it first. The plan (third command) is saved as `smart-plan.txt`. The plan and the sample read the
second pass stored in the workspace for the file, not the one written beside `-o`; the
second command stores the full one, with `--no-html` because the first already wrote the
page and a second one would land beside the dataset. Without it, a report made just
before leaves its smaller automatic second pass there and the plan counts fewer targets.

## What is not here

Generated datasets in several sizes, the end-to-end tests of the chain, the reproducible cases
and the demos that are not published live in the private repository `tabalyst-lab`. This
folder keeps what the website and the documentation publish (decision record
`docs/dev/adr/2026-10-15-generated-datasets-layout.md`).

Every report demo is independent and contains its own HTML report, canonical JSON
profile and cumulative `executions.json` history. The insurance example also has
standalone HTML pages under `report/`.

The input datasets and generated output are public repository examples. The wheel
contains the runtime package, report resources, and the CRM, Insurance, and
Computer packages. Tabalyst 0.7.0 reads Generate packages; the
`definition_version: 1` files of 0.6.2 are no longer read. The CRM data is
synthetic, with reserved `.example` domains and fictional phone numbers. The
configured 20,000 rows, generic account names and CRM audit story were approved
for the example on 2026-10-05.

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
`examples/datasets/insurance-customers.csv` or its report without a separate
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

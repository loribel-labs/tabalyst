# Tabalyst examples

The examples are organized by input name so additional public datasets can be
added without mixing source data and generated artifacts.

```text
examples/
|-- config.json
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
`examples/generate/` YAML definitions. These are lot 1 planning fixtures. The
CRM and Insurance definitions become executable in later lots; Generate
currently reports that execution is unavailable after a successful plan.

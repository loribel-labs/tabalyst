# Tabalyst examples

The examples are organized by input name so additional public datasets can be
added without mixing source data and generated artifacts.

```text
examples/
|-- config.json
|-- input/
|   |-- basic.csv
|   |-- insurance-customers.csv
|   `-- orders.json
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
    `-- orders/
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

From the repository root, regenerate the outputs with:

```console
tabalyst report examples/input/basic.csv -o examples/output/basic/report.html --config examples/config.json --force
tabalyst report examples/input/insurance-customers.csv -o examples/output/insurance-customers/report.html --config examples/config.json --details --force
tabalyst report examples/input/orders.json -o examples/output/orders/report.html --config examples/config.json --force
```

Every output folder is independent and contains its own HTML report, canonical
JSON profile and cumulative `executions.json` history. The insurance example
also has standalone HTML pages under `report/`. Delete an output folder
before regenerating when a fresh one-entry execution history is required.

The input datasets and generated output are public repository examples. The wheel
contains only the runtime package and report resources; examples are not installed
as package data.

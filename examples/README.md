# Tabalyst examples

The examples are organized by input name so additional public datasets can be
added without mixing source data and generated artifacts.

```text
examples/
|-- config.json
|-- input/
|   |-- basic.csv
|   `-- insurance-customers.csv
`-- output/
    |-- basic/
    |   |-- report.html
    |   |-- report.json
    |   `-- executions.json
    `-- insurance-customers/
        |-- report.html
        |-- report.json
        `-- executions.json
```

`basic.csv` is a five-row smoke example. `insurance-customers.csv` contains 3,000
synthetic customer and contract records across 34 columns. Its people, contact
details, and contracts are fictional; email addresses use reserved `.example`
domains.

From the repository root, regenerate both outputs with:

```console
tabalyst examples/input/basic.csv examples/output/basic/report.html --config examples/config.json
tabalyst examples/input/insurance-customers.csv examples/output/insurance-customers/report.html --config examples/config.json
```

Every output folder is independent and contains its own HTML report, canonical
JSON profile, and cumulative `executions.json` history. Delete an output folder
before regenerating when a fresh one-entry execution history is required.

The input datasets and generated output are public repository examples. The wheel
contains only the runtime package and report resources; examples are not installed
as package data.

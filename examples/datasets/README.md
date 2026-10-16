# Datasets

The source files shared by the showcase demos and the documentation.
Every file is synthetic: people, addresses and amounts are fictional, and email
addresses use reserved `.example` domains. They hold no real data.

| File                            | Rows         | Content                                                                                                                     |
| ------------------------------- | ------------ | --------------------------------------------------------------------------------------------------------------------------- |
| `basic.csv`                     | 5            | A five-row smoke example                                                                                                    |
| `insurance-customers.csv`       | 3,000        | Fictional customer and contract records across 34 columns                                                                   |
| `insurance-customers-100k.json` | 100,000      | The request that builds a larger insurance file, with 45 kinds of defect, 845 rows in all, outside the checkout (see below) |
| `orders.json`                   | 60 customers | A shop export with nested addresses, tags and orders                                                                        |
| `web-events.jsonl`              | 300 events   | A web analytics log in JSON Lines, with three bad lines on purpose                                                          |
| `sales.xlsx`                    | 120 orders   | A workbook with the sheets `Orders`, `Regions` and `Notes`                                                                  |

Who uses each file (generated from the manifests by `tools/make_index.py`):

<!-- index:users:start -->
| File | Used by |
| --- | --- |
| `basic.csv` | `showcase/basic/` |
| `insurance-customers-100k.json` | `showcase/insurance-customers/`, `showcase/insurance-customers-scan/` |
| `insurance-customers.csv` | none |
| `orders.json` | `showcase/orders/` |
| `sales.xlsx` | `showcase/sales/` |
| `web-events.jsonl` | `showcase/web-events/` |
<!-- index:users:end -->

`sales.xlsx` is written by `examples/tools/make_sales_workbook.py`, with the same
bytes on every run. Do not replace `insurance-customers.csv` without a separate
decision to change the published demo: the website copies its report.

`insurance-customers-100k.json` is a generation request, not data: the example `insurance`,
100,000 rows, a fixed seed and the anomaly profile `dirty_stress`, with the SHA-256 of the two
files it keeps (the altered CSV and its change log). The 27 MB CSV is never committed;
`python examples/tools/make_datasets.py` builds it outside the checkout, in
`D:/GIT.test/tabalyst/datasets/` (or `$TABALYST_DATASETS`), and reuses it while the SHA-256 matches.
`regenerate.py` calls the tool before the demos that read it, as `{datasets}/insurance-customers-100k.csv`.
The 3,000-row `insurance-customers.csv` stays for the documentation walkthroughs, the website and anyone who wants a small file.

## Generated datasets

Generated CSV files are never committed. A JSON file of this folder holds the recipe, and
`examples/tools/make_datasets.py` builds the files outside the checkout and checks their SHA-256.

- A request (`insurance-customers-100k.json`) has one `generate` block and its `files`.
- A category manifest (`"datasets": [...]`, used by `tabalyst-lab`) groups several requests under `datasets`. Its files land in
  `<root>/<category id>/`. A request names the options of `tabalyst generate` it needs
  (`output_profile`, `anomaly_profile`, `unit_style`, ...; the list is `OPTIONS` in the tool) and
  keeps, for each file, the name produced by the run (`from`) and its SHA-256.

```console
python examples/tools/make_datasets.py --list
python examples/tools/make_datasets.py insurance-customers-100k
python examples/tools/make_datasets.py --update-sha insurance-customers-100k
```

The first line lists the ids, the second builds one (or every, without id) and reuses files whose
SHA-256 matches, the third records the new digests after a deliberate generator change. A
mismatch stops with an error: the generator changed, or the Python minor version differs (the
bytes are only guaranteed for one). The root is `$TABALYST_DATASETS`, by default
`<repository parent>.test/tabalyst/datasets` (`D:/GIT.test/tabalyst/datasets`).

The same layout (a manifest per category, files outside the repository) is the one to publish from,
for instance to a Kaggle dataset: a run produces the three files that a dataset page needs (data,
data with defects, ground truth), and the SHA-256 in the manifest identifies the version published.

A dataset is public. Never add a real or confidential file here.

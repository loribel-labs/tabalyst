---
title: Generate computer offers
description: How to create synthetic computer offers in English and French, choose their columns, catalog, market and units, write one CSV with errors, and which defects the four anomaly profiles inject.
---

The Computer example creates offers of computers for sale: laptops, desktops,
mini PCs, all-in-ones, single-board computers and servers, each with its parts,
price, stock and reviews.

```console
tabalyst generate --example computer --rows 10000 -d computer-output/
```

```text
Created: computer-output/computers-en.csv
Created: computer-output/computers-fr.csv
Created: computer-output/computers.meta.json
10,000 rows in 3.5s (2,864 rows/s, 3 processes)
```

`computers-en.csv` and `computers-fr.csv` describe the same 10,000 offers: only
the labels change (`Laptop` and `Ordinateur portable`, `Black` and `Noir`).
`computers.meta.json` records the request, the version of Tabalyst, the anomaly
profile if any, and a SHA-256 digest of every resource file used, so the
files can be reproduced. The default is 10 rows; `--rows` and `--seed` change
the count and the data. The same seed gives the same files. The times come
from one machine and are not a promise.

## One file, with or without errors

`-o` writes a single CSV, in English unless you ask for French with
`--locales fr`. With an anomaly profile, the file holds the errors and a
`.changes.csv` file beside it lists every changed cell:

```console
tabalyst generate --example computer --rows 30000 -o pcs.csv --anomaly-profile dirty_realistic
```

```text
Created: pcs.csv
Created: pcs.changes.csv
30,000 rows in 9.1s (3,286 rows/s, 3 processes), 8,506 cells changed: generating rows 7.9s, injecting errors 1.2s
```

No clean copy, summary or metadata file is written with `-o`: use `-d` to get
them. `--locales en`, `--locales fr` or `--locales en,fr` chooses the
languages; with `-d`, both are written unless you choose one.

## Columns, catalog and market

| Option | What it chooses |
| --- | --- |
| `--output-profile` | The columns: `compact` (40, the default), `standard` (70) or `extended` (111). |
| `--generation-profile` | The kind of product the catalog favors: `balanced` (the default), `consumer`, `business`, `gaming`, `creator`, `workstation`, `enterprise`, `mixed` or `portable_only`. |
| `--market` | The market of the offers: `ca` (Canadian dollars, the default) or `us` (US dollars). |
| `--unit-style` | `numeric` (plain numbers, the default) or `localized` (`64 GB` in English, `64 Go` in French). |
| `--unit-columns` | The measured columns written with units, for example `memory_gb,display_size_in`; it implies `localized`. |

The `compact` profile has 40 columns:

| Group | Columns |
| --- | --- |
| Identity (2) | `product_id`, `sku` |
| Catalog (8) | `brand`, `product_family`, `model`, `generation`, `model_year`, `computer_type`, `form_factor`, `product_segment` |
| Processor (5) | `cpu_brand`, `cpu_family`, `cpu_model`, `cpu_cores`, `cpu_threads` |
| Graphics (5) | `gpu_brand`, `gpu_family`, `gpu_model`, `gpu_type`, `gpu_vram_gb` |
| Memory and storage (4) | `memory_type`, `memory_gb`, `storage_type`, `storage_gb` |
| Display (4) | `display_size_in`, `display_type`, `display_resolution`, `display_refresh_rate_hz` |
| System (3) | `operating_system`, `color`, `weight_kg` |
| Offer (9) | `currency`, `list_price`, `current_price`, `stock_quantity`, `stock_status`, `release_date`, `rating`, `review_count`, `market` |

`standard` adds identifiers such as `mpn` and the product category, wireless
and ports, battery, camera, discount, warranty and lifecycle columns.
`extended` adds the full hardware register (dimensions, memory and storage
slots, docking, audio, security chip) and sales figures (price history, sales
rank, units sold, conversion and return rates, seller and warehouse).

The values follow rules of consistency, not market estimates:

- Each offer takes its parts from a catalog of brands, families, models and
  generations, and a model only has the processors, graphics, memory, storage,
  screens and operating systems that the catalog lists for it.
- A dedicated GPU has memory and an integrated one has none, and a processor
  never has fewer threads than cores.
- `current_price` never exceeds `list_price`. Prices are computed from the
  configuration (more memory, storage, cores or graphics memory cost more)
  and a discount of 0, 5, 10 or 15%; they are not real prices.
- `stock_status` is `out_of_stock` exactly when `stock_quantity` is 0.
- `release_date` falls in the model year and never after the reference date
  (`--as-of-date`, 30 September 2026 by default).
- `rating` is empty when `review_count` is 0.

Many rows share a model, since the catalog is finite: a large file repeats
configurations, with their own identifiers, stock and reviews.

## Add defects on purpose

Computer has four anomaly profiles. They keep the clean file and write an
altered copy, a change log and a summary (with `-d`), or only the altered file
and its log (with `-o`).

| Profile | What it does |
| --- | --- |
| `dirty_realistic` | A few defects on a few percent of the rows (table below). |
| `dirty_stress` | The same kinds of defect on a larger share of the rows. |
| `unit_variants` | Only the units: `16` becomes `16 GB` in some memory, storage and graphics memory cells. |
| `unit_variants_extended` | The same for 14 measured columns (screen size, refresh rate, battery, weight, dimensions and more). It needs `--output-profile extended`. |

`dirty_realistic` and `dirty_stress` change the same columns:

| Column | Defect | `dirty_realistic` | `dirty_stress` |
| --- | --- | ---: | ---: |
| `memory_gb` | Emptied | 2.5% | 12% |
| `cpu_model` | Emptied | 1.5% | 8% |
| `release_date` | Written with slashes | 2% | 10% |
| `current_price` | Replaced by `N/A` | 1% | 6% |
| `stock_status` | Misspelled `in_stok` | 1.5% | 8% |
| `gpu_vram_gb` | Set to `0` on a dedicated GPU | 4% | 18% |
| `stock_quantity` | Set to `0` on an offer in stock | 3% | 15% |
| `memory_gb` | Followed by `GB` (`16 GB`) | 8% | 15% |
| `storage_gb` | Followed by `GB` | 5% | 10% |
| `gpu_vram_gb` | Followed by `GB` | 3% | 6% |

The last two columns are the share of rows each defect is requested on. A
defect with a condition (a dedicated GPU, an offer in stock) is applied only
to the rows that meet it, and the summary counts the others as skipped. Since
`stock_quantity` set to `0` while the status says `in_stock` contradicts the
rule above, such offers are real defects a profile of the file should find.

An unknown profile name stops the command with the list of available names.
To get several levels at once, name several profiles with `-d`: the rows are
generated once and each profile makes its own variant.

```console
tabalyst generate --example computer --rows 30000 -d out/ --locales en --anomaly-profile dirty_realistic,dirty_stress
```

## Large files

From 5,000 rows, Computer generates the rows in several processes, one per
spare processor and at most 6. `--workers N` sets the number, and
`--workers 1` keeps a single process. The files are the same whatever the
number, so a seed still gives the same data. On one machine with four
processors, 1,000,000 offers with an anomaly profile took about three minutes
with three processes.

In a terminal, the command shows its progress on one line with the time left;
`--no-progress` hides it. It always ends with a line giving the rows, the
total time, the rate, the changed cells and where the time went.

## Next steps

- [Tabalyst Generate](index.md) explains packages and how to write your own
  anomaly profile.
- The [CLI reference](../reference/cli/generate.md) lists every option.
- [Generate CRM contacts](crm.md) and
  [Generate insurance customers](insurance.md) describe the other examples.

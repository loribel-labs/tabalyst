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

The three profiles nest: `standard` has every column of `compact`, and
`extended` has every column of `standard`. The text values that name something
(categories, seller types, warehouses, availability, promotions) are translated
in the French file; technical codes such as `wifi_7` or `tpm_2_0` are the same
in both languages.

### Compact profile: 40 columns

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

`product_id` is unique in a file. `sku` identifies a configuration (the parts,
the color, the operating system and the market), so rows with the same
configuration share it.

### Standard profile: 70 columns, 30 more

| Group | Column | What it holds |
| --- | --- | --- |
| Product | `mpn` | Manufacturer part number: `MPN-` and a digest. Like `sku`, it identifies a configuration. |
| Product | `product_category` | One of 7 categories: laptops, desktops, mini PCs, all-in-one computers, workstations, single-board computers, servers. |
| Product | `product_subcategory` | One of 17, such as consumer laptop, gaming laptop, business laptop, small form factor PC. |
| Processor | `cpu_architecture` | `x86_64` or `arm64`. |
| Processor | `cpu_max_clock_ghz` | Maximum clock, from 2.4 to 5.6 GHz. |
| Processor | `npu_tops` | Power of the AI accelerator in TOPS; 0 without one. |
| Processor | `ai_pc_class` | `npu_capable` from 40 TOPS, otherwise `none`. |
| System | `os_family` | `windows`, `macos`, `linux` or `none`. |
| System | `keyboard_layout` | `ca_multilingual` for the `ca` market, `us_english` for `us`. |
| System | `language` | `en_fr` for the `ca` market, `en` for `us`. |
| Display | `display_brightness_nits` | Brightness, from 250 to 1,000 nits. Empty without a built-in display. |
| Display | `display_touch` | `true` or `false`; touch screens are rare. |
| Display | `display_finish` | `matte` or `glossy`. Empty without a built-in display. |
| Connectivity | `wifi_standard` | `wifi_5`, `wifi_6e`, `wifi_7` or `wifi_none`. |
| Connectivity | `bluetooth_version` | `5.0`, `5.3`, `5.4` or `none`. |
| Connectivity | `ethernet_speed` | `1_gbps`, `2.5_gbps`, `10_gbps`, `25_gbps` or `none`. |
| Ports | `usb_a_ports`, `usb_c_ports`, `hdmi_ports` | Number of ports of each kind. |
| Power | `battery_wh` | Battery capacity, from 48 to 100 Wh. Only laptops have one; empty otherwise. |
| Power | `power_adapter_w` | Rating of the adapter or power supply, from 27 to 1,600 W. |
| Chassis | `chassis_material` | `aluminum`, `steel`, `magnesium_alloy`, `aluminum_plastic`, `steel_plastic` and a few more. |
| Camera and security | `camera_type` | `none`, `1080p`, `1080p_ir` or `1440p_ir`. |
| Camera and security | `biometric_type` | `none`, `fingerprint`, `face_recognition` or a combination. |
| Offer | `discount_percent` | 0, 5, 10 or 15: the discount that turns `list_price` into `current_price`. |
| Offer | `price_tier` | `entry` below a list price of 1,500 (1,125 in US dollars), otherwise `premium`. |
| Offer | `condition` | Always `new`. |
| Offer | `warranty_period` | `12_months`, `24_months` or `36_months`. |
| Lifecycle | `product_age_months` | Months between `release_date` and the reference date. |
| Lifecycle | `product_lifecycle_status` | `current` under 24 months, `mature` after. |

### Extended profile: 111 columns, 41 more

| Group | Column | What it holds |
| --- | --- | --- |
| Display | `display_aspect_ratio` | `16:10`, `16:9` or `3:2`. Empty without a built-in display. |
| Display | `display_hdr` | `none`, `hdr10`, `displayhdr_400`, `displayhdr_1000` or `true_black_500`. Empty without a built-in display. |
| Display | `display_color_gamut` | `srgb_62`, `srgb_100` or `dci_p3_100`. Empty without a built-in display. |
| Processor | `npu_brand`, `npu_family` | The maker (Intel, AMD, Apple) and the family of the AI accelerator, such as `intel_ai_boost`. Empty without one. |
| Processor | `copilot_plus_pc` | `true` from 40 TOPS of AI accelerator, otherwise `false`. |
| Connectivity | `cellular_type` | `none` or `5g`. Only laptops can have `5g`. |
| Connectivity | `docking_support` | `none`, `usb_c`, `thunderbolt` or `thunderbolt_4`. |
| Connectivity | `ethernet_port` | `true` when `ethernet_speed` is not `none`. |
| Ports | `thunderbolt_ports`, `displayport_ports` | Number of ports of each kind. |
| Ports | `card_reader_type` | `none`, `sd`, `sdxc`, `sd_uhsii`, `microsd` or `nano_sim`. |
| Slots | `memory_slots_total`, `memory_slots_used` | Memory slots; the slots used never exceed the total. |
| Slots | `m2_slots_total`, `m2_slots_used` | M.2 storage slots, with the same rule. |
| Slots | `upgradeability_level` | `none`, `low`, `medium`, `high` or `very_high`. |
| Dimensions | `width_mm`, `depth_mm`, `height_mm` | Size of the machine, from 85 to 615, 56 to 720 and 9 to 470 mm. |
| Chassis | `chassis_finish` | The finish. In the current catalog it takes the same values as `chassis_material`. |
| Audio and input | `microphone_type` | `none`, `dual_array`, `triple_array` or `quad_array`. |
| Audio and input | `speaker_configuration` | `none`, `internal_mono`, `stereo`, `quad_speaker` or `six_speaker`. |
| Audio and input | `keyboard_type` | One of 8, such as `backlit_chiclet`, `backlit_gaming`, `external_keyboard`, `wireless_keyboard` or `none`. |
| Security | `trusted_platform` | `tpm_2_0`, `apple_secure_enclave` or `none`. |
| Promotion | `promotion_type` | No promotion, percentage discount, seasonal promotion or clearance. There is none when `discount_percent` is 0. |
| Promotion | `promotion_status` | `Active` when there is a discount, otherwise no promotion. |
| Price history | `lowest_price_30d`, `highest_price_30d`, `average_price_30d` | Computed from a short synthetic history: the current price and up to two earlier prices of the list price with a discount of 0 to 15%. |
| Price history | `price_change_30d_percent` | Change of the current price against the last earlier price of that history, in percent. |
| Lifecycle | `product_generation` | `current` under 12 months since release, `previous` under 36, `legacy` after. |
| Sales | `popularity_level` | `high` from 100 units sold in 30 days, `medium` from 30, otherwise `low`. |
| Sales | `units_sold_30d` | Units sold in 30 days: 0 to 5 when out of stock, otherwise about a third of `review_count` plus 0 to 60. |
| Sales | `sales_rank` | Rank derived from the units sold; the more units, the better (lower) the rank. |
| Sales | `conversion_rate` | Share of visits that end in a purchase, from 0.005 to 0.15; 0.005 when out of stock. |
| Sales | `return_rate` | Share of units returned, around 0.06 to 0.11; the better the rating, the lower. |
| Distribution | `seller`, `seller_type` | A seller of the market and its kind (retailer, distributor, refurbisher, authorized reseller, marketplace seller, manufacturer). A manufacturer's own store only sells its brand. |
| Distribution | `warehouse` | A warehouse of the market, such as Canada East, Central or West. |
| Distribution | `shipping_availability` | `Unavailable` when out of stock, `Limited availability` under 5 units, otherwise `Available`. |

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
configurations, each row with its own `product_id`, stock and reviews, while
`sku` and `mpn` repeat with the configuration.

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

---
title: Release notes
description: A short summary of what changed in each Tabalyst release from 0.1.x to 0.7.0.
---

## 0.7.0

Reworks Scan and the JSON formats: samples with stated accuracy, inferred
patterns, observations, a Scan web page and a second pass (`scan --plan`,
`scan --deep`) that Report chooses automatically when it pays. Adds smart
samples (`sample --sample-method smart`). Scan and Report move to format
revision 4, so older documents must be made again. Generate now reads package
directories instead of `definition_version: 1` files and adds the Computer
example.

## 0.6.2

Adds [Tabalyst Generate](../generate/index.md) for synthetic CSV datasets from
YAML definitions, with packaged CRM and insurance examples and optional logged
anomaly variants.

## 0.6.1

Makes choosing an Excel table or collection easier. Reorganizes the documentation.

## 0.6.0

Adds support for Excel workbooks.

## 0.5.1

Chooses a JSON collection from `report` and from `inspect`'s own output.

## 0.5.0

Adds Tabalyst Inspect and JSON Lines support.

## 0.4.4

Fast default CSV scans.

## 0.4.3

First beta release.

## 0.4.2

Makes scans several times faster on large files.

## 0.4.1

Adds adaptive detection for columns with many distinct values and a report time
that includes the scan.

## 0.4.0

Introduces Tabalyst Scan, a streaming analysis engine for CSV and JSON.

## 0.3.0

Introduces Tabalyst Sample.

## 0.2.0

Introduces a command-oriented toolkit: `tabalyst report INPUT... [OPTIONS]`.

## 0.1.x

First packaged releases.

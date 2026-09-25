---
title: Glossary
description: English and French terms used in the Tabalyst documentation and report, and the names that are never translated.
---

This glossary fixes the vocabulary of the Tabalyst documentation. English is the
source language; every French page uses the French terms below.

## Never translated

Keep these exactly as written in every language:

- the product names `Tabalyst`, `Tabalyst Report` and `Tabalyst CSV Report`;
- commands and options, such as `tabalyst report`, `-o`, `--output-dir` or
  `--config`;
- JSON keys and values, such as `format_version`, `with_issues` or `mixed`;
- file names and paths, such as `report.json` or `executions.json`;
- Python modules, functions and parameters, such as `tabalyst.analyze()`.

## Terms

| English | French | Meaning |
| --- | --- | --- |
| toolkit | boîte à outils | What Tabalyst is: a set of tools for unfamiliar data |
| report | rapport | The interactive HTML file produced by `tabalyst report` |
| profile, JSON profile | profil, profil JSON | The `report.json` file describing a dataset |
| column profile | profil de colonne | The part of the profile describing one column |
| dataset | jeu de données | The tabular data being analyzed |
| source file | fichier source | The CSV file given to Tabalyst |
| dataset overview | vue d'ensemble du jeu de données | The report section summarizing the whole dataset |
| data sample | échantillon de données | The first rows shown in the report |
| raw preview | aperçu brut | Source values before normalization |
| missing value | valeur manquante | An empty value or a configured missing marker |
| issue | anomalie | A detected data quality problem |
| with issues | avec anomalies | A column with missing values or of inferred type `mixed` |
| value normalization | normalisation des valeurs | Cleaning applied before analysis, such as whitespace trimming |
| type inference | inférence de type | How Tabalyst decides the type of a column |
| inferred type | type inféré | The type deduced from the values of a column |
| physical type | type physique | The storage type of the values: number, date, text |
| semantic type | type sémantique | The meaning of a column, such as an email or an identifier |
| date analysis | analyse des dates | The report section on date columns |
| numeric analysis | analyse numérique | The report section on numeric columns |
| string analysis | analyse des textes | The report section on text columns |
| analysis settings | paramètres d'analyse | The effective configuration used for a report |
| configuration file | fichier de configuration | The JSON file passed with `--config` |
| delimiter | séparateur | The character separating CSV fields |
| encoding | encodage | The character encoding of the source file |
| execution history | historique d'exécution | The cumulative `executions.json` file |
| format revision | révision du format | The `format_revision` number of the profile format |
| batch | lot | Several source files processed by one command |
| output directory | dossier de sortie | The folder given with `-d` / `--output-dir` |
| alpha | alpha | Early stage where interfaces and formats may change |

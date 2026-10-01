---
title: Glossary
description: English and French terms used in the Tabalyst documentation and report, and the names that are never translated.
---

This glossary fixes the vocabulary of the Tabalyst documentation. English is the
source language; every French page uses the French terms below.

## Never translated

Keep these exactly as written in every language:

- the product names `Tabalyst`, `Tabalyst Report`, `Tabalyst CSV Report`,
  `Tabalyst Scan` and `Tabalyst Inspect`;
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
| with issues | avec anomalies | A column with missing values, ambiguous dates or of inferred type `mixed` |
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
| beta | bêta | Pre-1.0 stage where interfaces and formats may still change |
| scan | analyse | The complete description of a source written by `tabalyst scan` |
| scan document | document d'analyse | The project's `scan.json` or a standalone `.scan.json` export written by `tabalyst scan` |
| stale scan | analyse périmée | A scan document whose source or settings changed since it was written |
| duplicate record | enregistrement en double | A record equal to an earlier record of its dataset |
| record | enregistrement | One CSV row, one element of a JSON collection or one object line of a JSONL file |
| collection | collection | A JSON array whose elements are analyzed as records; a JSONL file is one collection, `$[]` |
| field | champ | A CSV column or a path inside JSON records, such as `orders[].amount` |
| detector | détecteur | A rule that recognizes a kind of value, such as email addresses or dates |
| interpretation | interprétation | A meaning proposed for a field by the detectors that match its values |
| sensitive value | valeur sensible | A value identifying a person, such as an email address, masked by default |
| mask | masque | A value with letters replaced by `A` or `a` and digits by `9` |
| measure envelope | enveloppe de mesure | The `status` wrapper saying whether a measure is complete or limited |
| diagnostic | diagnostic | A technical event of a scan, such as an excluded record or a reached limit |
| configuration layer | couche de configuration | One level of settings: defaults, each configuration file, then options |
| JSONL | JSONL | A file with one JSON object per line, ending in `.jsonl` or `.ndjson` |
| inspect, Tabalyst Inspect | inspection, Tabalyst Inspect | The step that reads a JSON or JSONL source, finds its collection and writes the Inspect file; the command is `tabalyst inspect` |
| Inspect file | fichier Inspect | The `<source>-inspect.json` file beside a source, with the detection and the `config` you may edit |
| detection | détection | The section of an Inspect file that describes what Inspect found |
| candidate collection | collection candidate | An array that Inspect could analyze as the dataset of a source |
| eligible candidate | candidat éligible | A candidate collection that has at least one element, all of them objects |
| selection | sélection | The collection Inspect proposes, or none |
| ambiguous selection, unresolved selection | sélection ambiguë, sélection non résolue | Several collections are equally plausible, or none is usable, so nothing is selected and `tabalyst scan` and `tabalyst report` stop |
| flatten | aplatissement | Reading nested objects as fields named by their path, such as `address.city` |
| complex value | valeur complexe | An object or array kept whole instead of being developed into fields |
| error policy | politique d'erreurs | `strict` or `tolerant`: whether a malformed record stops the scan or is excluded |
| partial scan | analyse partielle | A scan with status `partial`, which excluded some records under the `tolerant` policy |

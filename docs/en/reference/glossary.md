---
title: Glossary
description: Terms used in the Tabalyst documentation and report, with their French equivalents, and the names that are never translated.
---

This glossary fixes the vocabulary of the Tabalyst documentation. English is the
source language; the French terms below are used when Tabalyst is translated, for example on the website.

## Never translated

Keep these exactly as written in every language:

- the product names `Tabalyst`, `Tabalyst Report`, `Tabalyst CSV Report`,
  `Tabalyst Scan`, `Tabalyst Inspect`, `Tabalyst Dedup` and `Tabalyst Generate`;
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
| finding | constat | What a rule found in a column: a count of one unit, out of a population, with its accuracy. An Error, an Issue or an Info |
| Error | erreur | A finding that a rule proves invalid, such as a date that does not exist in the calendar |
| Issue | point d'attention | A finding that is an ambiguity or a deviation worth a look, never proof of an error. The report has no Warning class |
| signal | signal | A tile of the dataset overview that sums one kind of finding over the columns that have it |
| classification | classification | The family and the type of a column (for example Identifier / ID, Text / Short), decided from the evidence of the scan and refined by the second pass |
| Unique ID | identifiant unique | An identifier column with no missing value and an exact count proving that every value is distinct |
| data sample | échantillon de données | The rows of the row sample shown in the report: the start, sampled rows and the end |
| raw values | valeurs brutes | Source values before normalization |
| missing value | valeur manquante | An empty value or a configured missing marker |
| quality issue | anomalie de qualité | An observation that is a confirmed issue or a candidate anomaly; a remark is not one |
| with quality issues | avec anomalies de qualité | A column with a confirmed issue or a candidate anomaly, such as an inferred type `mixed` or ambiguous dates |
| observation | observation | A finding of a scan about the data, with a status: informational, candidate anomaly or confirmed issue |
| limit | limite | What a scan could not establish, such as a count stopped by a scan limit; never a defect of the data |
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
| stale scan | analyse périmée | A scan document whose source, settings or pattern discovery changed since it was written |
| stratum, strata | strate, strates | A group of rows that share the value of the stratification field, or the combination of values of several fields |
| stratification advice | aide à la stratification | What `tabalyst scan --plan --stratify` adds to a plan: which columns make good strata and how risky a combination of columns is |
| smart sample | échantillon smart | A sample that aims to cover the diversity and the rare cases of a file; its proportions do not estimate the population |
| target | cible | A thing a smart sample aims to cover: a value, a pattern, an extreme, a period, a problem the scan found. It has a weight and is mandatory or optional |
| smart sample plan | plan d'échantillon smart | What `tabalyst scan --plan --smart` adds to a plan: the targets, their weights, the sizes, the reserve and the readings of the source |
| coverage (of a smart sample) | couverture | What a smart sample holds of the targets of its plan, by family and weighted by their weights. It is the coverage of the catalog of targets, not of every phenomenon of the data |
| reserve | réserve | The ordinary rows of a smart sample, chosen by a seeded hash of their position, so that it does not hold only rare cases. It gives way to mandatory targets |
| distinct sample | échantillon de valeurs distinctes | The distinct original values of one field kept in `values.samples`, all of them or the bottom-k of smallest priority, each with its exact count over the whole field. It is not a ranking |
| row sample | échantillon de lignes | Whole rows of a dataset kept in `records.sample` (the start, the end and a reproducible choice of the interior), so that two fields can be related on the same rows. It is not a uniform sample of the file |
| estimated figure | valeur estimée | A figure with `accuracy: "estimated"`, such as the KMV estimate of a distinct count, with its expected error. It is never quoted as a count |
| limited result | résultat limité | A measure stopped by a configured limit, written with its `reason` and a proven `lower_bound`, never with an estimate in place of the value |
| fingerprint-based identity | identité par empreinte | `identity_accuracy: "fingerprint_based"`: two long texts are the same entry when their 128-bit digests are equal, not when the full texts were compared |
| analysis plan | plan d'analyses | What `tabalyst scan --plan` shows: the analyses a scan could receive, their cost and the decision on each |
| forced plan | plan forcé | A plan that takes every applicable analysis within the hard memory budget, whatever the limits of an automatic choice (`tabalyst scan --plan --deep`) |
| confirmation | confirmation | The question a costly run asks before it starts; a plan says whether it would, and why |
| second pass | second passage | The reading of a source after its scan, to add analyses such as histograms, patterns counted on every value and dates per period (`tabalyst scan --deep`, and by itself in `tabalyst report`); its result is the second pass document |
| validated pattern | pattern validé | An inferred pattern whose occurrences were counted on every value of the file by the second pass, not only on a sample of the distinct values |
| format | format | The exact form of one value, a symbol per character (`AA-9999`) |
| pattern | pattern | The values of one structure and one set of lengths, with their constants (`'AK-'9999`); a discovered pattern never has a range |
| family | famille | The patterns of one structure that differ only by lengths or constants; shown as the list of its patterns with their counts |
| character map | carte des caractères | The most frequent characters of a field, their scripts and Unicode categories, the case of the ends of the values and the emoji; counted on the scan's samples, and on every value by the second pass |
| facet | facette | A dimension along which a family is specialized: composition, lengths, or the content of a token (head, tail, whole) |
| node | nœud | A pattern plus a constraint on a facet, with its counts in distinct values and occurrences |
| `deep.mode` | mode du second passage | The setting that tells `tabalyst report` whether to plan a second pass by itself (`auto`), never (`off`) or always, as `--deep` does (`force`) |
| second pass document | document de second passage | The `deep.json` or `<stem>.deep.json` written by `tabalyst scan --deep`, beside the scan, which it never changes |
| pair of columns | paire de colonnes | Two numeric columns of one dataset analyzed together. The planner scores the pairs on the row sample, lists the best and the second pass computes their correlation over every row |
| common rows | lignes communes | The rows where both columns of a pair have a number; the means and the coefficient of a pair are those of these rows only (`pairwise_complete`) |
| undefined coefficient | coefficient non défini | A correlation that cannot be computed, because too few common rows or a column that does not vary; the result says why and never writes `0` |
| category | catégorie | A column of a few repeated values, such as a region, whose value is the row of a table; its exact frequencies come from the scan |
| correlation ratio | rapport de corrélation | The share of the variance of a number that the categories of another column explain, from 0 to 1 (`eta_squared`). The second pass also gives it corrected for the number of categories (`epsilon_squared`), and the planner rates a pair by its square root |
| skewness | asymétrie | Whether the long tail of a numeric column is on the right (positive) or on the left (negative); the third standardized moment. The second pass gives it with the excess kurtosis, which grows with the weight of the tails |
| outlier of Tukey | valeur aberrante de Tukey | A number beyond a fence at 1.5 (mild) or 3 (far) interquartile ranges below the first quartile or above the third; it is a candidate anomaly to look at, not an error |
| feature | caractéristique dérivée | What a table reads of a column to make its classes: the `pattern` that reads the value, its `length`, its `prefix` or its `value` (another category) |
| table of a category against a feature | table croisée | The exact count of the rows of each category in each class of a feature of another column, computed by the second pass over every row (`category_crosstab`) |
| class | classe | A column of a table: a pattern, a length or a prefix; the last one is always `other`, what the others do not take |
| purity | pureté | The share of the classified rows of a category that sit in its dominant class; the purity of a table is that of all its categories together, and it differs from category to class and from class to category |
| exception | exception | A row outside the dominant class of its category, counted exactly and shown with its first rows |
| rank correlation | corrélation de rang | The Spearman coefficient of a pair: the Pearson coefficient of the ranks, which sees a relation that always goes up without being a line. The second pass estimates it from a grid of bins and gives certain bounds |
| provided rule | règle fournie | A rule you wrote for a table, such as "region east takes plan basic", checked as it is against the counts with its counterexamples; it is never proposed by itself |
| candidate rule | règle candidate | A relation learned from the data, such as "region QC reads pattern XX9999", that nobody validated; it is not a rule of the data |
| Cramér's V | V de Cramér | The strength of the association of two columns in a table, from 0 to 1, computed from the counts; the corrected form does not grow with the number of classes and is what Tabalyst ranks by. It is not defined, never 0, when a single category or class has rows |
| exact distinct count | nombre exact de valeurs distinctes | The number of different original values of a field, counted exactly by the second pass when the scan only estimated it; `redundant` is the occurrences beyond the first of each value |
| insight card | carte d'analyse | What a Report prints for one analysis of the second pass and one column: figures, distributions and tables, each with its own accuracy label (`exact`, `estimated`, `sample`, `at least`). It is derived from the document when the page is rendered, never stored |
| slice | tranche | One tenth of the records of a dataset, in file order, with the same number of records (one more or fewer): the unit in which the second pass follows a column along the file |
| drift along the file | dérive selon la position | A change of the missing values or of the values of a column from one slice of the file to the next, counted exactly; it shows that the column was filled or exported differently, not why |
| set of keys | ensemble de clés | The keys an object of a JSON file has; objects with the same keys are one set, counted exactly by the second pass |
| fingerprint | empreinte | A 128-bit digest that tells two long values apart; two values are taken for one only if their digests collide, which is about as unlikely as 2^-128 |
| mask | masque | A value with each letter shown as `a` or `A` and each digit as `9`; the form of a sensitive value that the document may hold |
| floor (forms) | seuil | The number of values (`deep.sensitive.min_count`) under which a mask or a class is summed up, so no figure is given about so few values |
| missing together | manquants simultanés | Columns that lack a value in the same records, counted exactly by the second pass; the share where both do among the records where either does ranks the pairs |
| histogram | histogramme | The count of the values of a numeric field per integer or per bin, exact, with a median and quantiles that are exact or estimated |
| already satisfied | déjà satisfaite | An analysis whose answer the scan already holds, so the plan does not select it |
| duplicate record | enregistrement en double | A record equal to an earlier record of its dataset |
| row identity | identité de ligne | In Dedup, the list of the decoded cells of a CSV record, compared without any normalization: case, spaces and leading zeros count |
| distinct row | ligne distincte | One row identity; Dedup counts it once, and writes it once to `unique.csv` |
| duplicate group | groupe de doublons | All the occurrences of one row that occurs at least twice; `records.duplicate_groups` counts the groups |
| repeated row | ligne répétée | The row of a duplicate group, written once to `duplicates.csv` |
| extra copy | occurrence supplémentaire | An occurrence after the first of its row, counted by `records.extra_copies`; a row that occurs three times has two |
| first occurrence | première occurrence | The first record of a row in the order of the source; the one Dedup keeps |
| singleton | ligne unique | A row that occurs exactly once |
| maximum frequency | fréquence maximale | `records.max_occurrences`, the most occurrences of one row; three or more makes Dedup write `duplicates_all.csv` |
| group occurrences | occurrences des groupes | Every occurrence of the rows of the duplicate groups, first ones included; the rows of `duplicates_all.csv` |
| managed output | sortie gérée | A file under an output name of Dedup that a Dedup report proves it published |
| foreign output | sortie étrangère | A file under an output name of Dedup that no report proves it published; Dedup replaces it only with `--force` |
| recovery report | rapport de reprise | The report with the status `in_progress` that Dedup writes before it changes the files of an earlier result |
| verification level | niveau de vérification | `metadata` (size and modification time) or `digest` (SHA-256): how far Dedup checked that a skipped source is unchanged |
| storage mode | mode de stockage | `memory` or `disk`: where Dedup kept the rows it had seen |
| spill | repli sur disque | The automatic switch of Dedup from memory to disk when the memory budget is reached |
| record | enregistrement | One CSV row, one element of a JSON collection, one object line of a JSONL file or one data row of an Excel table |
| collection | collection | A JSON array whose elements are analyzed as records; a JSONL file is one collection, `$[]` |
| field | champ | A CSV column or a path inside JSON records, such as `orders[].amount` |
| detector | détecteur | A rule that recognizes a kind of value, such as email addresses or dates |
| interpretation | interprétation | A meaning proposed for a field by the detectors that match its values |
| sensitive value | valeur sensible | A value identifying a person, such as an email address; shown by default, maskable |
| mask | masque | A value with letters replaced by `A` or `a` and digits by `9` |
| measure envelope | enveloppe de mesure | The `status` wrapper saying whether a measure is complete or limited |
| diagnostic | diagnostic | A technical event of a scan, such as an excluded record or a reached limit |
| configuration layer | couche de configuration | One level of settings: defaults, each configuration file, then options |
| JSONL | JSONL | A file with one JSON object per line, ending in `.jsonl` or `.ndjson` |
| workbook | classeur | An Excel file, `.xlsx` or `.xlsm`, with one or more sheets |
| sheet | feuille | One tab of a workbook; a candidate table of its own unless it holds named tables |
| named table | tableau nommé | An Excel table (list object) defined in a sheet, with its own header and range |
| header row | ligne d'en-tête | The row of a sheet whose cells name the columns, detected or set by `excel.header_row` |
| inspect, Tabalyst Inspect | inspection, Tabalyst Inspect | The step that reads a JSON, JSONL or Excel source, finds its collection or table and writes the Inspect file; the command is `tabalyst inspect` |
| Inspect file | fichier Inspect | The `<source>-inspect.json` file beside a source, with the detection and the `config` you may edit |
| detection | détection | The section of an Inspect file that describes what Inspect found |
| candidate collection | collection candidate | An array, or for a workbook a sheet or named table, that Inspect could analyze as the dataset of a source |
| eligible candidate | candidat éligible | A candidate collection that has at least one element, all of them objects |
| selection | sélection | The collection Inspect proposes, or none |
| ambiguous selection, unresolved selection | sélection ambiguë, sélection non résolue | Several collections are equally plausible, or none is usable, so nothing is selected and `tabalyst scan` and `tabalyst report` stop |
| flatten | aplatissement | Reading nested objects as fields named by their path, such as `address.city` |
| complex value | valeur complexe | An object or array kept whole instead of being developed into fields |
| error policy | politique d'erreurs | `strict` or `tolerant`: whether a malformed record stops the scan or is excluded |
| partial scan | analyse partielle | A scan with status `partial`, which excluded some records under the `tolerant` policy |

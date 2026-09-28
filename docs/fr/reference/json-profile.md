---
title: Profil JSON
description: Structure du profil JSON écrit par tabalyst report, avec ses champs de premier niveau, ses profils de colonne, ses codes d’anomalie et le versionnage du format.
---

Chaque exécution de `tabalyst report` écrit un profil JSON à côté du rapport
HTML, avec le même nom : `orders.html` est accompagné de `orders.json`. Pour une
source JSON, les noms par défaut sont `orders.report.html` et
`orders.report.json`, pour que le profil ne remplace jamais la source. Le
profil contient le résultat complet de l’analyse ; le rapport HTML est produit à
partir de lui. Utilisez-le pour lire les résultats de Tabalyst depuis des
scripts ou d’autres outils.

Le format est **expérimental** : il peut changer de manière incompatible d’une
version à l’autre. Vérifiez toujours d’abord `format_version` et
`format_revision`. Cette page décrit le format `0.1.0a`, révision `5`.

## Exemple

Un profil abrégé pour un fichier `orders.csv` de cinq lignes :

```json
{
  "format_version": "0.1.0a",
  "format_revision": 5,
  "generated_at": "2026-09-25T22:25:07.873024Z",
  "processing_seconds": 0.0098,
  "source": {
    "filename": "orders.csv",
    "format": "csv",
    "size_bytes": 274,
    "sha256": "7d426449e1217d4dbcad1e7e4c862d360c63d927cb775caa48007d70ac36c0c8",
    "encoding": "utf-8-sig",
    "delimiter": ","
  },
  "config": { "...": "effective report and scan settings" },
  "datasets": [
    {
      "id": "rows",
      "kind": "table",
      "summary": {
        "row_count": 5,
        "column_count": 6,
        "missing_count": 2,
        "duplicate_row_count": 1,
        "with_issues_column_count": 2
      },
      "date_summary": { "...": "present when a column contains dates" },
      "columns": [
        {
          "id": "column_3",
          "name": "amount",
          "path": "amount",
          "position": 3,
          "inferred_type": "mixed",
          "type_counts": { "number": 3, "text": 1 },
          "type_confidence": 0.75,
          "missing_count": 1,
          "missing_percent": 20.0,
          "with_issues": true,
          "distinct_count": 3,
          "examples": ["25.00", "12.50", "not available"],
          "semantic_type": null,
          "detectors": [
            {
              "id": "number",
              "status": "complete",
              "primary": false,
              "eligible_count": 4,
              "matched_count": 3,
              "matched_percent": 75.0,
              "ambiguous_count": 0,
              "invalid_count": 0,
              "formats": []
            }
          ]
        }
      ],
      "issues": [
        {
          "code": "duplicate_rows",
          "severity": "warning",
          "message": "Duplicate rows beyond their first occurrence",
          "count": 1,
          "column_ids": [],
          "row_numbers": [4]
        }
      ],
      "preview": [
        {
          "row_number": 1,
          "values": ["001", "Alice", "12.50", "2026-01-01", "true", "First order"],
          "absent": []
        }
      ]
    }
  ]
}
```

## Champs de premier niveau

| Champ | Type | Contenu |
| --- | --- | --- |
| `format_version` | chaîne | Famille du format, `"0.1.0a"` pendant l’alpha |
| `format_revision` | entier | Révision dans la famille, augmentée à chaque changement de structure ou de sens |
| `generated_at` | chaîne | Date et heure UTC de l’analyse (ISO 8601) |
| `processing_seconds` | nombre | Durée de l’analyse et du profil, en secondes ; pour un rapport généré à partir d’un document d’analyse avec `--scan`, le temps de lire le document et de construire le profil, la durée de l’analyse elle-même figurant dans le document |
| `source` | objet | Le fichier analysé (voir ci-dessous) |
| `config` | objet | Les paramètres effectifs, après fusion des valeurs par défaut, des fichiers de configuration et des options de la commande : `string_analysis`, `value_examples` et `scan`, la configuration d’analyse complète ; pour un rapport généré à partir d’un document d’analyse, `scan` est la configuration qui y est enregistrée. Voir la [configuration](configuration.md) |
| `datasets` | tableau | Un profil par jeu de données du fichier (voir ci-dessous) |

## `source`

| Champ | Contenu |
| --- | --- |
| `filename` | Nom du fichier, sans dossier |
| `format` | `csv` ou `json` |
| `size_bytes` | Taille du fichier en octets |
| `sha256` | Empreinte SHA-256 du fichier, pour vérifier que deux profils décrivent le même fichier |
| `encoding` | Encodage utilisé pour lire le fichier |
| `delimiter` | Séparateur de champs utilisé pour lire le fichier ; `null` pour les fichiers JSON |

## `datasets`

Un fichier CSV a un seul jeu de données, `rows`, dont les enregistrements sont
les lignes du fichier. Un fichier JSON a un jeu de données par collection
trouvée par l’analyse, comme `$.customers[]`, et le jeu de données `$` pour le
reste du document, listé seulement lorsqu’il contient des valeurs hors des
collections. Voir le [format d’analyse](scan-format.md) pour le choix des
collections.

| Champ | Type | Contenu |
| --- | --- | --- |
| `id` | chaîne | Identifiant du jeu de données : `rows`, `$` ou un chemin de collection comme `$.customers[]` |
| `kind` | chaîne | `table` (CSV), `document` ou `collection` (JSON) |
| `summary` | objet | Comptages au niveau du jeu de données (voir ci-dessous) |
| `date_summary` | objet ou `null` | Comptages de dates au niveau du jeu de données, lorsqu’au moins une colonne contient des dates |
| `columns` | tableau | Un profil par colonne, dans l’ordre du fichier pour le CSV et dans l’ordre de découverte pour le JSON |
| `issues` | tableau | Problèmes détectés (voir ci-dessous) |
| `preview` | tableau | Les premiers enregistrements, avec leurs valeurs brutes ; les valeurs des colonnes sensibles sont masquées ou cachées |

Dans un jeu de données JSON, une colonne est un champ qui contient des chaînes,
des nombres, des booléens ou des nulls, nommé par son chemin : `email`,
`address.city`, `orders[].total`. Les objets et les tableaux eux-mêmes ne sont
pas des colonnes. Une ligne est un enregistrement du jeu de données.

## `summary`

Comptages sur l’ensemble du jeu de données :

- taille : `row_count` (enregistrements), `column_count`, `cell_count` (les
  emplacements où une valeur peut se trouver : un par ligne et par colonne pour
  le CSV ; pour le JSON, les occurrences de chaque champ plus les objets où il
  est absent) ;
- valeurs manquantes : `missing_count`, `missing_percent` ;
- normalisation : `trim_count`, `collapse_internal_whitespace_count` ;
- structure : `duplicate_row_count`, `empty_row_count`, `empty_column_count`,
  `constant_column_count`, `with_issues_column_count` ;
- `duplicate_row_status` : `complete` ; `limited` lorsque plus de lignes
  distinctes que `scan.limits.max_tracked_records` ont été lues,
  `duplicate_row_count` étant alors une borne inférieure ; ou `disabled`
  lorsque `scan.records.duplicates` vaut `false`, `duplicate_row_count` étant
  alors `null` ;
- familles de colonnes : `numeric_column_count`, `date_column_count`,
  `string_column_count` ;
- répartitions des types : `inferred_type_counts`, `inferred_type_percents`,
  `semantic_type_counts`, `semantic_type_percents`.

Les pourcentages sont des nombres de 0 à 100.

## `columns`

Chaque profil de colonne contient toujours :

| Champ | Contenu |
| --- | --- |
| `id` | Identifiant stable tiré de la position, comme `column_3`. Utilisez-le plutôt que `name`, qui peut être vide ou répété |
| `name` | Texte de l’en-tête pour le CSV ; le chemin du champ pour le JSON |
| `path` | Chemin du champ tel qu’affiché par l’analyse : le texte de l’en-tête pour le CSV, un chemin comme `orders[].total` pour le JSON |
| `position` | Position dans le fichier pour le CSV, dans l’ordre de découverte pour le JSON, à partir de 1 |
| `inferred_type` | `empty`, `boolean`, `integer`, `number`, `date`, `text` ou `mixed`. Une colonne de dates est `date` même avec plusieurs formats ou des valeurs ambiguës |
| `type_counts` | Nombre de valeurs présentes de chaque type |
| `type_confidence` | Part des valeurs présentes acceptées par le type inféré, de 0 à 1. Pour les colonnes `mixed`, la part de la famille de types la plus grande ; `null` pour les colonnes `empty` |
| `type_error_count`, `type_error_percent` | Valeurs hors du type inféré ; `null` pour les colonnes `mixed` |
| `missing_count`, `missing_percent` | Cellules manquantes ; pour le JSON, aussi les objets où le champ est absent |
| `with_issues` | `true` lorsque la colonne a des valeurs manquantes, que son type est `mixed` ou qu’elle contient des dates ambiguës |
| `normalization` | Valeurs modifiées par la suppression et la réduction des espaces ; les cellules manquantes ne sont pas comptées |
| `distinct_count` | Nombre de valeurs distinctes après normalisation, même pour une colonne masquée ; `null` lorsqu’une limite d’analyse a arrêté le comptage |
| `examples` | Quelques valeurs représentatives |
| `value_profile` | Occurrences des valeurs, complètes ou échantillonnées (voir `selection`) |
| `semantic_type` | `date` pour les colonnes de dates, sinon l’identifiant de l’interprétation principale de l’analyse, comme `enumeration`, `email`, `phone` ou `postal_code`, ou `null` |
| `exposure` | `mask`, `hide` ou `show` pour une colonne sensible, la façon dont ses valeurs apparaissent dans `examples`, `value_profile` et `preview` ; `null` sinon |
| `detectors` | Les détecteurs qui ont reconnu des valeurs de la colonne, dans l’ordre de l’analyse (voir ci-dessous) ; vide si aucun ne l’a fait |

Selon la colonne, ces objets sont aussi présents (sinon `null`) :

| Champ | Présent pour | Contenu |
| --- | --- | --- |
| `numeric` | Colonnes `integer` et `number` avec des valeurs finies | `minimum`, `maximum`, `range`, `mean`, `median` (`null` lorsqu’une limite d’analyse l’a arrêtée), sur tous les nombres de la colonne, y compris les virgules décimales comme `12,5` |
| `date_profile` | Colonnes contenant des dates, quel que soit leur type | Comptages des valeurs valides, ambiguës et invalides, formats détectés et leur répartition, et `ambiguity_evidence` : le nombre de valeurs non ambiguës par ordre jour-mois (`DMY`, `MDY`), affiché mais jamais appliqué. `resolved_ambiguous_order` n’est défini que par `scan.detectors.date.ambiguous_order` |
| `string_profile` | Colonnes `text` | Statistiques de longueur, distribution des longueurs et exemples représentatifs |

## `detectors`

Chaque élément décrit ce qu’un détecteur de l’analyse a reconnu dans la
colonne. Sont listés les détecteurs qui ont reconnu des valeurs ou trouvé des
valeurs ambiguës ou invalides, ainsi que ceux qui ont échoué.

| Champ | Contenu |
| --- | --- |
| `id` | Identifiant du détecteur, comme `email`, `date` ou `pattern:order_id` |
| `status` | `complete`, ou `failed` lorsque le détecteur s’est arrêté sur une erreur |
| `primary` | `true` pour l’interprétation principale de l’analyse, affichée comme `semantic_type` |
| `eligible_count` | Valeurs que le détecteur pouvait examiner |
| `matched_count`, `matched_percent` | Valeurs reconnues, et leur part des valeurs éligibles |
| `ambiguous_count` | Valeurs ayant plus d’une lecture, comme `01/02/2026` |
| `invalid_count` | Valeurs ayant la bonne forme mais un contenu impossible, comme `2026-02-30` |
| `formats` | Formats trouvés, chacun avec `format`, `count` et `percent` des valeurs éligibles |

## `issues`

Chaque anomalie a un `code`, une `severity` (`warning` ou `info`), un
`message` en anglais, un `count`, les `column_ids` concernés et jusqu’à 10
`row_numbers`. Les numéros de ligne comptent les enregistrements du jeu de
données à partir de 1 ; l’en-tête d’un CSV n’est pas compté.

| `code` | Gravité | Signification |
| --- | --- | --- |
| `duplicate_rows` | warning | Lignes qui répètent une ligne précédente, au-delà de sa première occurrence |
| `missing_values` | warning | Cellules manquantes |
| `empty_columns` | warning | Colonnes sans aucune valeur présente |
| `mixed_types` | warning | Colonnes avec des types de valeurs mélangés |
| `ambiguous_dates` | warning | Dates correspondant à plus d’un ordre jour-mois |
| `ambiguous_headers` | warning | Noms de colonnes vides ou répétés |
| `constant_columns` | info | Colonnes avec une seule valeur présente distincte |
| `trimmed_cells` | info | Cellules modifiées par la suppression des espaces en début et en fin |
| `collapsed_whitespace` | info | Cellules modifiées par la réduction des espaces internes répétés |
| `limited_measures` | info | Colonnes dont des mesures ont été arrêtées par une limite d’analyse |
| `excluded_records` | warning | Enregistrements exclus par la politique d’erreur `tolerant`, non analysés |

Une anomalie n’est listée que lorsque son comptage est supérieur à zéro, sauf
`trimmed_cells` et `collapsed_whitespace`, qui sont toujours listées.

## `preview`

Les premiers enregistrements du jeu de données (10 par défaut, défini par
`scan.records.preview` dans la [configuration](configuration.md)), chacun avec son
`row_number` et ses `values` brutes dans l’ordre des colonnes. La taille de
l’aperçu n’influe pas sur l’analyse, qui lit toujours tous les
enregistrements. Dans les colonnes sensibles, les valeurs sont masquées
(`mask`) ou `null` (`hide`), selon l’`exposure` de la colonne ; les cellules
manquantes restent telles que lues.

Pour le JSON, un champ absent de l’enregistrement vaut `null` et sa position (à
partir de 0) est listée dans `absent`. Un champ sous un tableau, comme
`tags[]`, joint les valeurs de l’enregistrement avec `, `. Un `null` JSON est le
texte `null`.

## Versionnage

- `format_version` nomme la famille de format expérimentale. Elle reste
  `"0.1.0a"` pendant l’alpha.
- `format_revision` augmente à chaque changement de structure ou de sens. Elle
  ne change pas pour les améliorations du style du rapport ou des performances.
- Les révisions peuvent être incompatibles, et aucune migration n’est fournie.
  Voir le [journal des modifications du format de profil](profile-format-changelog.md).

Le profil contient des valeurs du fichier source, dans `examples`,
`value_profile` et `preview` ; seules les colonnes sensibles sont masquées.
Partagez-le comme vous partageriez les données.

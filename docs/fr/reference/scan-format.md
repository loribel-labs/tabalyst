---
title: Format d’analyse
description: Structure du document JSON écrit par tabalyst scan, avec son niveau supérieur, ses jeux de données, champs, enveloppes de mesure, détecteurs et diagnostics.
---

`tabalyst scan data.csv` écrit `data.scan.json`, un document JSON qui décrit
chaque champ de la source. Cette page décrit le format `tabalyst.scan`, version
`0.1.0a`, révision `1`. Le format est **expérimental** : il peut changer de
manière incompatible d’une version à l’autre. Vérifiez toujours d’abord
`format`, `format_version` et `format_revision` ; les changements sont listés
dans le [journal des modifications du format d’analyse](scan-format-changelog.md).

## Niveau supérieur

```json
{
  "format": "tabalyst.scan",
  "format_version": "0.1.0a",
  "format_revision": 1,
  "engine": {
    "version": "0.4.0",
    "normalization_version": 1,
    "detectors": {"number": 1, "date": 1, "email": 1, "...": 1}
  },
  "status": "complete",
  "started_at": "2026-09-27T05:06:41.369888Z",
  "duration_seconds": 0.0023,
  "source": {
    "format": "csv",
    "name": "orders.csv",
    "size_bytes": 63,
    "modified_at": "2026-09-27T05:06:40.930099Z",
    "sha256": "fe7a56e5...",
    "encoding": "utf-8-sig",
    "csv": {"delimiter": ",", "header": ["id", "amount", "email"]}
  },
  "config": {"...": "effective scan configuration"},
  "config_sha256": "030617af...",
  "scope": {
    "collections": null,
    "records_read": 3,
    "records_analyzed": 3,
    "records_excluded": 0,
    "exclusions": {}
  },
  "datasets": [],
  "diagnostics": []
}
```

- `engine` : la version de Tabalyst, la version de normalisation et la version
  de chaque détecteur exécuté.
- `status` : `complete` lorsque chaque enregistrement du périmètre a été
  analysé, `partial` lorsque des enregistrements ont été exclus avec la
  politique d’erreur `tolerant`. Un fichier illisible ne produit aucun
  document.
- `source` : le fichier tel qu’il a été lu. `size_bytes` et `sha256` couvrent
  chaque octet lu. `encoding` est l’encodage CSV, ou `utf-8` ou `utf-8-sig` pour
  le JSON. `csv` vaut `null` pour les sources JSON.
- `config` : la configuration effective complète, avec toutes les valeurs par
  défaut, comme dans la section `scan` d’un
  [fichier de configuration](configuration.md#scan-settings). `config_sha256`
  est le SHA-256 de son JSON canonique (clés triées, sans espaces, UTF-8) : deux
  analyses ayant la même valeur ont utilisé les mêmes paramètres.
- `scope` : les enregistrements lus, analysés et exclus, avec les exclusions
  comptées par motif (`width_mismatch`, `duplicate_key`, `record_too_large`).
  `collections` vaut `null` pour le CSV ; pour le JSON, il donne le `mode`
  (`auto` ou `explicit`) et les chemins de collection demandés (`requested`).

## Jeux de données

Une source CSV a un seul jeu de données, `rows`. Une source JSON a un jeu de
données par collection d’enregistrements, et un jeu de données `document`
lorsque sa racine n’est pas un tableau.

```json
{
  "id": "$.customers[]",
  "kind": "collection",
  "collection_path": [{"key": "customers"}, {"items": true}],
  "record_count": 4,
  "record_types": {"object": 4},
  "structure": {
    "paths": {"status": "complete", "value": 5},
    "untracked_observations": 0,
    "depth_truncated_observations": 0,
    "max_depth_seen": 3
  },
  "fields": []
}
```

- `kind` : `table` (CSV), `collection` ou `document` (JSON).
- `record_count` : les enregistrements analysés ; `record_types` : les
  enregistrements par type JSON.
- `structure` : le nombre de chemins de champ distincts, et ce que les limites
  `max_fields` et `max_depth` ont laissé de côté.

## Champs

Les champs sont listés dans l’ordre de leur découverte. Un champ est un chemin
à l’intérieur des enregistrements : une colonne CSV, une clé JSON ou les
éléments `[]` d’un tableau.

| Clé | Contenu |
| --- | --- |
| `id`, `path`, `display`, `name`, `parent` | Identité : un identifiant comme `f4`, le chemin sous forme de segments, sa forme lisible comme `orders[].amount`, le dernier segment et l’identifiant du champ parent. |
| `collection` | Pour un tableau JSON promu en jeu de données propre, l’identifiant de ce jeu de données. |
| `first_record`, `occurrences` | Le premier enregistrement ayant une valeur, et le nombre de valeurs à ce chemin. |
| `presence` | `parent_count`, `present` et `absent` : à quelle fréquence le champ existe là où il pourrait exister. |
| `native_types` | Les valeurs par type natif : `string`, `integer`, `number`, `boolean`, `null`, `object`, `array`. |
| `strings` | Les chaînes par catégorie : `empty`, `blank` (espaces uniquement), `marker` (un marqueur de valeur nulle configuré) et `content`. |
| `missing` | Le nombre de valeurs manquantes, les catégories qu’il inclut et chaque composante. |
| `arrays` | Pour les champs tableaux : nombre, tableaux vides, longueur minimale, maximale et totale. |
| `values` | Les valeurs analysables : `count`, `cardinality`, `frequencies`, `samples`, `first` et `last`. |
| `string_characteristics`, `string_lengths` | Casse, caractères non ASCII, sauts de ligne et espaces ; statistiques et histogramme des longueurs. |
| `numeric`, `booleans`, `temporal` | Statistiques numériques exactes, comptages des booléens, plage et formats des dates. |
| `normalization` | Pour chaque étape de normalisation, combien de valeurs elle a modifiées et les valeurs distinctes restantes, ainsi que les groupes de variantes qui se normalisent vers la même valeur. |
| `technical_type` | `integer`, `number`, `date`, `boolean`, `text`, `mixed` ou `empty`, avec `confidence`, `counts` et `outside_count`. |
| `detectors` | Un résultat par détecteur, décrit ci-dessous. |
| `interpretations` | `candidates`, les détecteurs qui reconnaissent au moins 95 % des valeurs, et `primary`, le seul candidat lorsqu’il y en a exactement un. |
| `sensitive`, `exposure` | Si le champ contient des valeurs sensibles, et comment elles sont exposées : `mask`, `hide`, `show`, ou `null` pour les autres champs. |

Les valeurs sont listées sous forme de texte avec leur type natif, par exemple
`{"value": "12.50", "type": "string", "count": 1}`. Les listes utilisent la
valeur analytique : les espaces en début et en fin sont supprimés et les
espaces répétés sont réduits à un seul.

## Enveloppes de mesure

Une mesure qui peut être limitée, désactivée ou sans objet est placée dans une
enveloppe de mesure avec un `status` :

```json
{"status": "complete", "value": 42}
{"status": "limited", "reason": "distinct_limit", "limit": 100000, "lower_bound": 100001}
{"status": "not_applicable", "reason": "no_values"}
{"status": "disabled"}
{"status": "failed", "reason": "detector_error", "diagnostic": 3}
```

- `complete` : exacte pour sa population.
- `limited` : une limite configurée a arrêté la mesure. `lower_bound`, lorsqu’il
  est présent, est un minimum prouvé ; aucune estimation n’est jamais donnée
  comme valeur.
- `not_applicable` : sans signification ici, par exemple en l’absence de
  valeurs.
- `disabled` : désactivée par la configuration, ou masquée parce que le champ
  est sensible.
- `failed` : un échec technique ; `diagnostic` est son index dans
  `diagnostics`.

Une analyse peut être `complete` alors que certaines de ses mesures sont
`limited` : le statut de l’analyse porte sur les enregistrements, l’enveloppe
sur une mesure.

## Détecteurs

```json
{
  "id": "number",
  "version": 1,
  "status": "complete",
  "coverage": {
    "eligible": 2, "tested": 2, "matched": 2, "ambiguous": 0,
    "invalid": 0, "not_matched": 0, "not_tested": 0,
    "share_tested": 1.0, "share_eligible": 1.0
  },
  "formats": [{"format": "0", "count": 1}, {"format": "0.0", "count": 1}],
  "evidence": {"matched": ["12.50", "7"], "ambiguous": [], "invalid": [], "not_matched": []},
  "details": {}
}
```

Chaque détecteur est listé pour chaque champ, avec le statut `complete`,
`not_applicable`, `disabled` ou `failed`.

- `coverage` : les valeurs `eligible` d’un type accepté, réparties en `matched`,
  `ambiguous` (plusieurs lectures possibles, comme `01/02/2026`), `invalid` (la
  bonne forme avec un contenu erroné, comme un 13e mois), `not_matched` et
  `not_tested`. Les parts sont arrondies à quatre décimales.
- `formats` : les formes reconnues, comme `YYYY-MM-DD` ou `#,##0.0`, avec leur
  nombre.
- `evidence` : les premières valeurs distinctes dans chaque état.
- `details` : des comptages propres au détecteur, comme les domaines des
  adresses e-mail ou les indices d’ambiguïté.

Les détecteurs intégrés sont `number`, `date`, `boolean`, `enumeration`,
`email`, `url`, `phone`, `postal_code`, `currency`, `percentage`, `quantity`,
`uuid` et `ip_address`. Les motifs de la configuration apparaissent sous la
forme `pattern:<id>`. Les détecteurs vérifient la syntaxe, jamais l’existence
réelle.

Tabalyst ne résout jamais une ambiguïté en devinant à partir des autres valeurs
du champ : les indices sont publiés, et seule la configuration la résout, par
exemple avec `detectors.date.ambiguous_order`.

## Valeurs sensibles

Un champ est sensible lorsqu’un détecteur sensible (`email`, `phone`,
`ip_address`, ou un motif déclaré `sensitive`) a reconnu l’une de ses valeurs.
Avec l’exposition par défaut `mask`, ses valeurs listées, ses indices et ses
groupes de variantes affichent des masques : les majuscules deviennent `A`, les
autres lettres `a` et les chiffres `9`. Les masques identiques sont fusionnés.
Avec `mask` et `hide`, les blocs `numeric` et `temporal` d’un champ sensible
sont `disabled`, car un minimum ou une plage de dates est déjà une valeur. Les
comptages ne sont jamais masqués.

## Diagnostics

```json
{
  "code": "csv_width_mismatch",
  "level": "error",
  "message": "...",
  "count": 2,
  "dataset": "rows",
  "field": null,
  "detector": null,
  "locations": [{"record": 2, "line": 3}, {"record": 3, "line": 4}]
}
```

Les diagnostics décrivent des événements techniques, pas la qualité des
données : enregistrements exclus, limites atteintes (`field_limit`,
`depth_limit`, `measures_limited`, `global_budget`), collections introuvables et
échecs de détecteurs. `level` vaut `error` ou `warning`. `count` est toujours
complet ; `locations` liste au plus `errors.max_locations` emplacements, avec
`record` et `line` pour le CSV, `record` et `element` pour le JSON.

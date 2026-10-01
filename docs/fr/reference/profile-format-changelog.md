---
title: Journal des modifications du format de profil
description: Comment report.json identifie son format, et les changements de chaque révision du format.
---

Le fichier `report.json` généré identifie son contrat avec deux champs
indépendants :

```json
{
  "format_version": "0.1.0a",
  "format_revision": 10
}
```

`format_version` nomme la famille de compatibilité expérimentale. Elle reste
`0.1.0a` pendant toute la série d’applications Tabalyst `0.1.0aX`.
`format_revision` est un entier monotone augmenté à chaque changement
significatif de structure ou de sens. Il ne change pas pour le style du
rapport, la documentation, les améliorations de performance ou les corrections
qui préservent le contrat JSON.

Les révisions bêta peuvent être incompatibles. Aucune migration automatique
n’est encore fournie.

## Révision 1 - 2026-09-18

- Premier contrat de profil alpha suivi explicitement.
- Comprend les métadonnées du jeu de données et de la source, la configuration
  effective, le résumé de qualité, les anomalies, les lignes de l’aperçu brut
  et les profils de colonne globaux.
- Les profils de colonne comprennent la normalisation, les types inférés et
  sémantiques, les erreurs, les occurrences, des exemples bornés, les
  statistiques numériques, l’analyse des dates et les statistiques de longueur
  des textes.
- Ajout des identifiants `format_version` et `format_revision` monotone.

## Révision 2 - 2026-09-23

- Ajout de `with_issues` pour chaque colonne, défini comme la présence de
  valeurs manquantes ou le type inféré `mixed`.
- Ajout des répartitions des types physiques et sémantiques au niveau du jeu de
  données, et des comptages des sections du rapport.
- Ajout des agrégats de dates au niveau du jeu de données et des résumés
  d’ambiguïté par colonne de dates.
- Ajout des comptages et pourcentages de valeurs présentes aux profils de
  dates, des étendues numériques, et des valeurs de longueur relatives et
  représentatives utilisées par le rapport.

## Révision 3 - 2026-09-27

Le rapport repose sur Tabalyst Scan au lieu du moteur pandas.

- `config` contient les paramètres du rapport (`preview_rows`,
  `string_analysis`, `value_examples` sans `candidate_sample_size` ni
  `random_seed`) et `scan`, la configuration d’analyse effective complète. Les
  autres anciens paramètres ont été déplacés dans `scan`.
- Les colonnes de dates avec plusieurs formats ou des valeurs ambiguës ont
  l’`inferred_type` `date` au lieu de `mixed`. `with_issues` vaut aussi `true`
  pour les colonnes avec des dates ambiguës, et la nouvelle anomalie
  `ambiguous_dates` les compte.
- Les dates ambiguës ne sont plus résolues à partir des autres valeurs de la
  colonne : `ambiguous_order_source` ne vaut que `config`, et le nouveau
  `date_profile.ambiguity_evidence` compte les valeurs non ambiguës par ordre.
  Les formats de date comprennent les dates-heures ISO, les heures et les noms
  de mois ; `order` et `separator` valent `null` pour les formats qui ne sont
  pas des dates numériques. `date_profile.errors` a été supprimé.
- `semantic_type` vaut `date` ou l’identifiant de l’interprétation principale
  de l’analyse (`enumeration` au lieu de `enum`, et de nouvelles valeurs comme
  `email`, `phone` ou `postal_code`). Le bloc `enum` a été supprimé. Les
  énumérations comptent les valeurs présentes, pas les lignes, par rapport à
  leur minimum.
- Nouveau champ `exposure` par colonne ; les valeurs des colonnes sensibles
  sont masquées par défaut dans `examples`, `value_profile` et `preview`, où
  une valeur cachée vaut `null`.
- `distinct_count` et `numeric.median` valent `null` lorsqu’une limite
  d’analyse les a arrêtés ; la nouvelle anomalie `limited_measures` liste ces
  colonnes.
- `type_confidence` vaut `null` pour les colonnes `empty`.
- Les statistiques numériques couvrent tous les nombres de la colonne, y
  compris les virgules décimales et les milliers groupés.
- Les comptages de normalisation ne couvrent que les valeurs présentes : une
  cellule ne contenant que des espaces est manquante, pas raccourcie. Les
  valeurs distinctes appliquent aussi la composition Unicode (NFC).
- Les éléments de `string_profile.length_distribution` n’ont plus de
  `distinct_count` ; leurs exemples viennent des valeurs les plus fréquentes et
  des valeurs échantillonnées.
- Les échantillons de valeurs sont tirés par l’analyse
  (`scan.limits.max_samples`, `scan.random_seed`) : les exemples échantillonnés
  diffèrent donc de la révision 2.

## Révision 4 - 2026-09-27

Le rapport lit les fichiers JSON et liste les détecteurs de chaque colonne.

- Les champs de niveau jeu de données `summary`, `date_summary`, `columns`,
  `issues` et `preview` ont été déplacés dans le nouveau tableau `datasets`, un
  élément par jeu de données avec son `id` et son `kind`. Un fichier CSV a un
  seul jeu de données, `rows`.
- `source` a un nouveau champ `format` ; `delimiter` vaut `null` pour les
  fichiers JSON.
- Les colonnes ont un nouveau `path` et un nouveau tableau `detectors` : les
  détecteurs qui ont reconnu des valeurs, avec leurs comptages et leurs formats.
- Les lignes de l’aperçu ont un nouveau tableau `absent` : les positions des
  champs JSON absents de l’enregistrement.
- Dans les jeux de données JSON, une colonne est un champ contenant des valeurs
  scalaires, nommé par son chemin ; les champs absents comptent comme
  manquants, et `cell_count` compte les emplacements où une valeur peut se
  trouver.

## Révision 5 - 2026-09-28

Le rapport peut être généré à partir d’un document d’analyse, dont le bloc des
enregistrements contient désormais l’aperçu et les lignes en double.

- Nouveau `summary.duplicate_row_status` : `complete` ; `limited` lorsque plus
  de lignes distinctes que `scan.limits.max_tracked_records` ont été lues,
  auquel cas `duplicate_row_count` est une borne inférieure ; ou `disabled`
  lorsque `scan.records.duplicates` vaut `false`, auquel cas
  `duplicate_row_count` vaut `null`.
- Le message de l’anomalie `duplicate_rows` se termine par `at least` lorsque
  le comptage est une borne inférieure.
- La taille de l’aperçu passe de `config.preview_rows` à
  `config.scan.records.preview`.
- Pour un rapport généré à partir d’un document d’analyse,
  `processing_seconds` est le temps de lire le document et de construire le
  profil.

## Révision 6 - 2026-09-28

Le rapport montre chaque étape de normalisation avec ses groupes de variantes,
ce que l’analyse n’a pas pu mesurer complètement, et la structure des jeux de
données JSON.

- La `normalization` d’une colonne reçoit `stages` (`raw`, puis `nfc`, `trim`,
  `collapse_whitespace`, `casefold` et `strip_accents`, chacune avec `enabled`,
  `changed_count`, `changed_percent`, `distinct_count` et `distinct_status`),
  `variant_group_count`, `variant_group_status`, `variant_groups` et
  `variant_groups_truncated`.
- Nouvelle anomalie d’information `variant_groups` : des valeurs écrites de
  plusieurs façons que la normalisation compare comme égales.
- Chaque jeu de données reçoit un nouvel objet `limits` : les `measures`
  arrêtées par une limite de l’analyse, avec leur champ, leur raison, leur
  limite et la borne inférieure prouvée ; `untracked_observations`,
  `depth_truncated_observations` ; et les `diagnostics` de l’analyse pour le
  jeu de données et pour toute l’analyse.
- Les jeux de données JSON reçoivent un nouvel objet `structure` :
  `record_types`, `path_count`, `path_status`, `max_depth_seen` et un élément par
  chemin, conteneurs compris, avec la présence par parent et les longueurs de
  tableaux. Il vaut `null` pour les fichiers CSV.

## Révision 7 - 2026-09-28

L’analyse derrière le rapport utilise par défaut la détection adaptative : sur
les colonnes de plus de 10 000 valeurs distinctes, les détecteurs qui n’ont
reconnu aucune des premières valeurs arrêtent de tester les autres.

- `config.scan.detection` reçoit `warmup_values` (10 000 par défaut ; `0` teste
  chaque valeur) et `probe_interval` (100 par défaut).
- Les types sémantiques et les types inférés sont inchangés sur les colonnes où
  un détecteur reconnaît au moins 95 % des valeurs. Les comptages de
  reconnaissances rares après la chauffe peuvent être plus bas ; un
  avertissement `detector_skipped_reacted` dans les `limits.diagnostics` du jeu
  de données indique quand un sondage en a trouvé une.
- Pour un rapport généré à partir d’un document d’analyse, `processing_seconds`
  ajoute désormais la durée de l’analyse enregistrée dans le document au temps
  de le lire et de construire le profil, ce qui le rend comparable à un rapport
  généré à partir de la source.

## Révision 8 - 2026-09-28

L’analyse derrière le rapport arrête aussi de tester les détecteurs rares : ceux
qui ont reconnu au plus 0,1 % des 10 000 premières valeurs distinctes d’une
colonne, et aucune des 5 000 dernières.

- `config.scan.detection` reçoit `rare_share` (0,001 par défaut ; `0` conserve
  le comportement de la révision 7).
- Les types sémantiques et les types inférés sont inchangés ; seuls les
  comptages des détecteurs à reconnaissances rares peuvent être plus bas. Un
  avertissement `detector_skipped_reacted` dans les `limits.diagnostics` du jeu
  de données indique quand un tel détecteur a reconnu des valeurs sondées plus
  souvent que pendant sa chauffe.

## Révision 9 - 2026-09-29

- La `scan_details` d’une colonne conserve des preuves bornées de l’analyse pour
  les pages de colonne autonomes : présence, types natifs, composantes
  manquantes, premières et dernières valeurs exposées, caractéristiques et
  longueurs des textes, statistiques numériques, comptages de booléens et
  plages temporelles. Les valeurs respectent le paramètre d’exposition de
  l’analyse.
- Les entrées de détecteurs reçoivent la couverture complète, les preuves
  exposées, les détails exposés et les métadonnées de détection adaptative quand
  elles existent.
- Les énumérations primaires incluent toutes les fréquences disponibles même
  quand leur cardinalité dépasse `value_examples.full_distribution_max_distinct`.
- `tabalyst report --details` génère une page HTML autonome par colonne dans le
  dossier du nom du rapport. Les détails sont désactivés par défaut. Cela change
  les artefacts du rapport, pas le sens des autres champs du profil.

## Révision 10 - 2026-09-30

- `config.scan` enregistre les règles appliquées par l’analyse, valeurs par
  défaut résolues : `config.scan.errors.policy` vaut `strict` ou `tolerant`,
  jamais `null`. Le paramètre lui-même accepte `null`, qui signifie la valeur
  par défaut du format de la source.
- `config.scan.json` reçoit `flatten` (`enabled`, `separator`, `max_depth`) et
  `arrays` (`mode`). Leurs valeurs par défaut conservent le comportement
  précédent.
- Un champ JSON qui ne contient que des objets ou des tableaux conservés entiers
  à la limite `config.scan.json.flatten.max_depth` est une colonne dont
  l’`inferred_type` vaut `complex`, avec les comptages `object` et `array` dans
  `type_counts`. Sans limite d’aplatissement, les conteneurs restent de la
  structure et aucune colonne ne change.
- `source.format` peut valoir `jsonl`, pour les fichiers se terminant par
  `.jsonl` ou `.ndjson`. Les lignes exclues avec la politique `tolerant` sont
  comptées par l’anomalie `excluded_records` existante, avec leurs numéros de
  ligne comme `row_numbers`. `config.scan.limits` reçoit `max_line_bytes`.
- Les rapports générés par les commandes ont un jeu de données par collection
  choisie avec [Inspect](inspect-format.md) ou `--collection`, en général un
  seul, et aucun jeu de données `$` pour le reste du document. La structure de
  `datasets` ne change pas.
- Le `path` et le `name` des colonnes des champs JSON sont joints avec
  `config.scan.json.flatten.separator`.

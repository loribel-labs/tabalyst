---
title: Journal des modifications du format de profil
description: Comment report.json identifie son format, et les changements de chaque révision du format.
---

Le fichier `report.json` généré identifie son contrat avec deux champs
indépendants :

```json
{
  "format_version": "0.1.0a",
  "format_revision": 4
}
```

`format_version` nomme la famille de compatibilité expérimentale. Elle reste
`0.1.0a` pendant toute la série d’applications Tabalyst `0.1.0aX`.
`format_revision` est un entier monotone augmenté à chaque changement
significatif de structure ou de sens. Il ne change pas pour le style du
rapport, la documentation, les améliorations de performance ou les corrections
qui préservent le contrat JSON.

Les révisions alpha peuvent être incompatibles. Aucune migration automatique
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

---
title: Journal des modifications du format d’analyse
description: Comment un document d’analyse écrit par tabalyst scan identifie son format, et les changements de chaque révision du format.
---

Un document d’analyse écrit par `tabalyst scan` identifie son contrat avec trois
champs :

```json
{
  "format": "tabalyst.scan",
  "format_version": "0.1.0a",
  "format_revision": 5
}
```

`format` nomme le type de document ; le profil JSON de `tabalyst report` a son
propre [journal des modifications](profile-format-changelog.md).
`format_version` nomme la famille de compatibilité expérimentale, `0.1.0a`,
conservée pendant la phase bêta. `format_revision` est un entier monotone,
incrémenté à chaque changement significatif de structure ou de sémantique. Il ne
change pas pour les améliorations de performance, la documentation ou les
corrections qui conservent le contrat.

Les révisions bêta peuvent être incompatibles. Aucune migration automatique
n’est fournie. `tabalyst report --scan` ne lit que la révision actuelle :
analysez de nouveau la source pour générer le rapport d’un document plus
ancien.

## Révision 5

- `config` enregistre les règles appliquées par l’analyse, valeurs par défaut
  résolues : `errors.policy` vaut `strict` ou `tolerant`, jamais `null` ; le
  paramètre lui-même accepte `null`, qui signifie la valeur par défaut du format
  de la source (`strict` pour CSV et JSON). `config_sha256` est l’empreinte de
  cette configuration résolue.
- `config.json` reçoit `flatten` (`enabled`, `separator`, `max_depth`) et
  `arrays` (`mode`). Leurs valeurs par défaut conservent le comportement
  précédent. Quand `flatten.enabled` vaut `false`, `separator` et `max_depth`
  sont enregistrés à leurs valeurs par défaut, puisqu’ils ne changent rien.
- `source.format` peut valoir `jsonl` : les fichiers se terminant par `.jsonl`
  ou `.ndjson` sont lus comme un seul jeu de données `$[]` dont les
  enregistrements sont les lignes objet. Leur politique par défaut, `tolerant`,
  exclut une ligne qui n’est pas du JSON valide (`jsonl_invalid_line`), qui
  n’est pas un objet (`jsonl_record_not_object`) ou qui dépasse
  `limits.max_line_bytes` (`jsonl_line_too_long`), avec les emplacements
  `{record, line}`. `scope.collections` vaut `null`. `config.limits` reçoit
  `max_line_bytes`.
- Le lecteur JSON applique `flatten` : un conteneur à `max_depth` segments est
  conservé entier (type et longueur du tableau), ses enfants ne sont pas
  observés et ne sont pas comptés comme tronqués. Le `display` du champ est joint
  avec `flatten.separator`.
- `config.json.collections` est enregistré dans son écriture canonique
  (`$.orders[]` pour `$["orders"][]`), si bien que des chemins égaux donnent des
  empreintes égales.
- Les jeux de données d’une analyse JSON faite par `tabalyst scan` ou
  `tabalyst report` viennent d’[Inspect](inspect-format.md) :
  `scope.collections` a le `mode` `explicit` et il n’y a pas de jeu de données
  `document` `$`. `tabalyst.scan()` seule conserve la découverte automatique
  (`mode` `auto`). La structure du document ne change pas.
- L’identité d’une analyse est le SHA-256 de sa source, son `config_sha256` et
  `engine.version`. Une analyse écrite par une autre version du moteur n’est plus
  réutilisée comme analyse stockée, et une source est comparée à
  `source.sha256` quelle que soit sa date de modification ;
  `source.modified_at` reste informatif.

## Révision 4

- Détecteurs rares : après la phase de chauffe, un détecteur qui a reconnu au
  plus `detection.rare_share` de ses valeurs distinctes (0,001 par défaut, soit
  10 valeurs d’une chauffe de 10 000 valeurs), et aucune dans sa seconde moitié,
  est lui aussi ignoré, comme un détecteur qui n’a rien reconnu. Un détecteur
  sensible qui n’a trouvé que des valeurs invalides n’est jamais ignoré de cette
  façon. Réglez `detection.rare_share` sur `0` pour retrouver le comportement de
  la révision 3.
- `adaptive` reçoit `warmup_reactions` : les valeurs de chauffe que le détecteur
  a reconnues, `0` pour un détecteur qui n’a rien reconnu.
- Un détecteur rare ignoré signale `detector_skipped_reacted` quand au moins 10
  occurrences sondées ont été reconnues, plus souvent que `rare_share` ne le
  permet.
- Nouveau paramètre dans `config` : `detection.rare_share`.

## Révision 3

- Détection adaptative : après les `detection.warmup_values` premières valeurs
  distinctes d’un champ (10 000 par défaut), un détecteur qui n’en a reconnu
  aucune ignore les autres valeurs du champ, sauf environ une sur
  `detection.probe_interval` (100 par défaut). Les valeurs ignorées comptent
  comme `not_tested`. `number` et `date` ne sont jamais ignorés. Réglez
  `detection.warmup_values` sur `0` pour la détection exhaustive de la
  révision 2.
- Chaque résultat de détecteur `complete` reçoit `adaptive` : `null`, ou la
  taille de la chauffe, les valeurs non testées et l’indice d’un nouvel
  avertissement `detector_skipped_reacted` quand un sondage a été reconnu.
- Nouveaux paramètres dans `config` : `detection.warmup_values` et
  `detection.probe_interval`.

## Révision 2

- Chaque jeu de données reçoit `records` : les enregistrements avec des
  valeurs manquantes, les enregistrements vides, les enregistrements en double
  et un aperçu des premiers enregistrements, les valeurs sensibles étant
  exposées comme dans le reste du document.
- Les enregistrements en double sont comptés dans le budget du nouveau
  paramètre `limits.max_tracked_records` ; au-delà, le comptage est une borne
  inférieure de raison `record_budget`, et un avertissement `record_budget`
  est signalé.
- Nouveaux paramètres dans `config` : `records.preview`, `records.duplicates`,
  `limits.max_tracked_records` et `limits.max_listed_records`.

## Révision 1

- Premier format d’analyse publié, écrit par `tabalyst scan`.
- Niveau supérieur : versions du moteur et des détecteurs, statut de l’analyse,
  identité de la source avec taille, date de modification et SHA-256,
  configuration effective et son SHA-256, périmètre et diagnostics.
- Jeux de données CSV et JSON, avec des champs identifiés par des chemins, une
  présence exacte, les types natifs, les catégories de chaînes et un nombre de
  valeurs manquantes configurable.
- Mesures des valeurs : cardinalité, fréquences, échantillons, première et
  dernière valeurs, caractéristiques et longueurs des chaînes, statistiques
  numériques exactes, booléens et dates, placées dans des enveloppes de mesure
  lorsqu’elles peuvent être limitées.
- Normalisation version 1 avec compteurs de modifications, valeurs distinctes
  par étape et groupes de variantes.
- Type technique, treize détecteurs intégrés, motifs déclaratifs,
  interprétations et masquage des valeurs sensibles.

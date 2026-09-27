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
  "format_revision": 1
}
```

`format` nomme le type de document ; le profil JSON de `tabalyst report` a son
propre [journal des modifications](profile-format-changelog.md).
`format_version` nomme la famille de compatibilité expérimentale, `0.1.0a`
pendant toute la phase alpha. `format_revision` est un entier monotone,
incrémenté à chaque changement significatif de structure ou de sémantique. Il ne
change pas pour les améliorations de performance, la documentation ou les
corrections qui conservent le contrat.

Les révisions alpha peuvent être incompatibles. Aucune migration automatique
n’est fournie.

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

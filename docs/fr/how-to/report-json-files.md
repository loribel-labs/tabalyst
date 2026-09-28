---
title: Générer le rapport de fichiers JSON
description: Transformez un fichier JSON en rapport HTML interactif et en profil JSON avec tabalyst report, avec une vue par collection d’enregistrements.
---

`tabalyst report` lit les fichiers JSON comme les fichiers CSV :

```console
tabalyst report orders.json
```

Cette commande crée `orders.report.html` (le rapport), `orders.report.json` (le
profil) et `executions.json` à côté de `orders.json`. La partie `.report`
empêche le profil de remplacer la source. `-o` et `-d` fonctionnent comme pour
les fichiers CSV.

## Jeux de données

Tabalyst trouve les enregistrements du fichier comme `tabalyst scan` : un
tableau de premier niveau est une collection, et dans un objet de premier
niveau, chaque tableau accessible à travers des objets, comme `customers` dans
`{"customers": [...]}`, est une collection. Chaque collection est un jeu de
données du rapport, comme `$.customers[]`. Les valeurs du document situées hors
des collections forment le jeu de données `$`, affiché seulement s’il en
existe.

Quand le fichier a plusieurs jeux de données, un sélecteur **Dataset** dans la
navigation du rapport permet de passer de l’un à l’autre. Chaque jeu de données
a sa propre vue d’ensemble, ses colonnes, ses problèmes et son échantillon de
données.

Pour choisir les collections, listez-les dans le paramètre
`scan.json.collections` d’un [fichier de configuration](../reference/configuration.md)
passé avec `--config`. Voir [Analyser des fichiers CSV et JSON](scan-files.md)
pour la façon dont les collections sont trouvées.

## Colonnes

Chaque champ contenant des chaînes, des nombres, des booléens ou des nulls est
une colonne, nommée par son chemin depuis l’enregistrement :

| Enregistrement JSON | Colonnes |
| --- | --- |
| `{"id": 1, "address": {"city": "Paris"}}` | `id`, `address.city` |
| `{"tags": ["a", "b"]}` | `tags[]` |
| `{"orders": [{"total": 3}]}` | `orders[].total` |

Les objets et les tableaux eux-mêmes ne sont pas des colonnes. Un champ absent
d’un enregistrement est manquant, comme un null ou une chaîne vide. Dans
l’échantillon de données, un champ absent affiche `absent`, et les valeurs d’un
champ situé sous un tableau sont jointes par `, `.

## Détecteurs et formats

La section **Detectors** liste, pour chaque colonne des rapports CSV et JSON,
ce que les détecteurs de l’analyse ont reconnu : adresses e-mail, numéros de
téléphone, dates, nombres et les autres détecteurs intégrés, avec la part des
valeurs reconnues et les formats trouvés. Le détecteur marqué **primary** donne
à la colonne son type sémantique.

La structure du profil est décrite dans la
[référence du profil JSON](../reference/json-profile.md).

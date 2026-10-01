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

## Fichiers JSONL

Les fichiers se terminant par `.jsonl` ou `.ndjson` contiennent un objet JSON
par ligne. Ils sont traités de la même façon, comme un seul jeu de données `$[]`
dont les enregistrements sont les lignes :

```console
tabalyst report events.jsonl
```

Cette commande crée `events.report.html` et `events.report.json`. Une ligne qui
n’est pas du JSON valide, qui n’est pas un objet, qui contient un objet avec une
clé en double ou qui dépasse `scan.limits.max_line_bytes` est exclue et comptée ;
le rapport la liste dans son anomalie *excluded records*, avec les numéros de
ligne physiques. Le rapport est alors partiel et la commande affiche un
avertissement. Réglez `errors.policy` sur `strict`, dans la `config` d’un
[fichier Inspect](inspect-json-files.md#fichiers-jsonl-et-ndjson) ou dans
`scan.errors.policy`, pour vous arrêter plutôt à la première de ces lignes. Les
lignes vides sont ignorées, et un fichier sans aucune ligne d’enregistrement est
une erreur.

## Jeu de données

Le rapport analyse une **collection** d’enregistrements, choisie par
[Tabalyst Inspect](inspect-json-files.md) : un tableau de premier niveau, ou un
tableau dans un objet de premier niveau, comme `customers` dans
`{"customers": [...]}`. C’est le jeu de données du rapport, comme
`$.customers[]`. Quand la source n’a pas de fichier Inspect, Tabalyst
l’inspecte lui-même et utilise la collection qu’il sélectionne. Les valeurs
situées hors de la collection ne sont pas analysées.

Quand plusieurs tableaux sont aussi plausibles les uns que les autres, ou que le
fichier n’a aucune collection d’objets, le rapport s’arrête avec le code de
sortie `2` avant d’analyser quoi que ce soit et liste les candidats. Lancez
`tabalyst inspect data.json` et renseignez `config.structure.dataset_path` dans
le fichier qu’il écrit, ou passez la collection avec `--collection`. Un fichier
JSON dont l’unique contenu est un objet, un nombre ou un tableau de valeurs
simples n’a pas de collection.

Pour produire le rapport de plusieurs collections d’un même fichier, passez
`--collection` une fois pour chacune, ou listez-les dans le paramètre
`scan.json.collections` d’un [fichier de configuration](../reference/configuration.md)
passé avec `--config`. Le rapport a alors un jeu de données par collection, et
un sélecteur **Dataset** dans la navigation du rapport permet de passer de l’un
à l’autre. Chaque jeu de données a sa propre vue d’ensemble, ses colonnes, ses
problèmes et son échantillon de données. Les règles définies dans le fichier
Inspect, comme la profondeur d’aplatissement, s’appliquent à la source quelle
que soit la façon dont les collections sont choisies.

## Colonnes

Chaque champ contenant des chaînes, des nombres, des booléens ou des nulls est
une colonne, nommée par son chemin depuis l’enregistrement :

| Enregistrement JSON | Colonnes |
| --- | --- |
| `{"id": 1, "address": {"city": "Paris"}}` | `id`, `address.city` |
| `{"tags": ["a", "b"]}` | `tags[]` |
| `{"orders": [{"total": 3}]}` | `orders[].total` |

Les objets et les tableaux eux-mêmes ne sont pas des colonnes, sauf si la
profondeur d’aplatissement (`config.flatten.max_depth` du fichier Inspect, ou le
paramètre d’analyse `json.flatten.max_depth`) les conserve entiers : à cette
profondeur, un objet ou un tableau est une colonne de type `complex` et son
contenu n’est pas analysé. Un champ absent
d’un enregistrement est manquant, comme un null ou une chaîne vide. Dans
l’échantillon de données, un champ absent affiche `absent`, et les valeurs d’un
champ situé sous un tableau sont jointes par `, `.

## Structure

La section **JSON structure** liste chaque chemin des enregistrements, objets et
tableaux compris, comme `orders`, `orders[]` et `orders[].total`, avec :

- les types JSON trouvés au chemin ;
- la présence : la part des objets parents qui contiennent le champ, et combien
  ne le contiennent pas ;
- pour les tableaux, leurs longueurs (minimum, maximum, moyenne) et combien sont
  vides ;
- le rôle du chemin : une colonne, un conteneur, ou une collection analysée
  comme son propre jeu de données.

Les rapports CSV n’ont pas de section de structure : chaque ligne a les mêmes
colonnes.

## Détecteurs et formats

La section **Detectors** liste, pour chaque colonne des rapports CSV et JSON,
ce que les détecteurs de l’analyse ont reconnu : adresses e-mail, numéros de
téléphone, dates, nombres et les autres détecteurs intégrés, avec la part des
valeurs reconnues et les formats trouvés. Le détecteur marqué **primary** donne
à la colonne son type sémantique.

La structure du profil est décrite dans la
[référence du profil JSON](../reference/json-profile.md).

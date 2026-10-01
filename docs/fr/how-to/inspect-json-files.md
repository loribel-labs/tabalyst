---
title: Inspecter des fichiers JSON et JSONL
description: Laissez tabalyst inspect trouver la collection d’enregistrements d’un fichier JSON, JSONL ou NDJSON, puis modifiez le fichier Inspect pour choisir comment scan et report le lisent.
---

Utilisez `tabalyst inspect` pour voir comment Tabalyst comprend un fichier JSON
ou JSONL avant de l’analyser, et pour changer cette compréhension quand elle est
fausse. **Tabalyst Inspect** lit le fichier une fois, trouve quel tableau
contient les enregistrements et écrit la réponse dans un petit fichier JSON à
côté de la source :

```console
tabalyst inspect orders.json
```

```text
Inspect: orders.json-inspect.json
Selection: $.customers[] (the only eligible collection)
```

Le fichier Inspect porte le nom complet de la source suivi de `-inspect.json` :
`orders.json-inspect.json`, `events.jsonl-inspect.json`,
`events.ndjson-inspect.json`. Sa dernière section, `config`, contient les règles
que `tabalyst scan` et `tabalyst report` appliquent à cette source. Les autres
sections décrivent ce qu’Inspect a trouvé ; Tabalyst les remplace à chaque
inspection. La structure du fichier est décrite dans le
[format Inspect](../reference/inspect-format.md).

`tabalyst inspect` accepte les fichiers dont le nom se termine par `.json`,
`.jsonl` et `.ndjson`, ou des motifs non récursifs, et rien d’autre : un fichier
CSV est refusé avec le code de sortie `2`. La commande ne modifie jamais la
source.

## Inspect est facultatif

`tabalyst scan` et `tabalyst report` fonctionnent sur un fichier JSON sans lui.
Quand la source n’a pas de fichier Inspect, ils l’inspectent eux-mêmes, gardent
le résultat dans le stockage local de Tabalyst et utilisent la collection qu’il
sélectionne :

```console
tabalyst report orders.json
```

Lancez `tabalyst inspect` quand vous voulez voir ou changer les règles, ou
quand Inspect ne peut pas choisir.

## Quand Inspect ne peut pas choisir

Un fichier JSON peut contenir plusieurs tableaux. Inspect ne sélectionne une
collection que si ce choix est clair :

- la racine du fichier est un tableau ;
- un seul tableau contient des objets ; ou
- un tableau contient au moins 10 fois plus d’objets que le suivant.

Sinon, rien n’est sélectionné, et `tabalyst scan` et `tabalyst report`
s’arrêtent avec le code de sortie `2` avant d’analyser quoi que ce soit. Pour un
fichier avec un tableau `customers` et un tableau `orders` de même taille :

```text
Error [shop.json]: 2 collections of shop.json are equally plausible. Nothing was analyzed.
Candidates:
  $.customers[] (2 elements)
  $.orders[] (2 elements)
Pass --collection, or run `tabalyst inspect shop.json` and set config.structure.dataset_path in the file it writes.
```

Lancez `tabalyst inspect shop.json`, ouvrez `shop.json-inspect.json` et
indiquez la collection dans `config` :

```json
"config": {
  "structure": {"dataset_path": "$.orders[]"},
  "flatten": {"enabled": true, "separator": ".", "max_depth": null},
  "arrays": {"mode": "preserve"},
  "errors": {"policy": "strict"}
}
```

`tabalyst report shop.json` analyse alors `$.orders[]`. Tabalyst ne choisit
jamais une collection d’après le nom de sa propriété, comme `results` ou
`data`, et n’en choisit jamais une pour que le travail puisse continuer.

Pour analyser une collection une seule fois sans modifier de fichier, passez-la
sur la ligne de commande ; `--collection` l’emporte sur le fichier Inspect :

```console
tabalyst scan shop.json --collection "$.customers[]"
```

Un fichier sans collection utilisable, comme un objet unique, un nombre ou un
tableau de valeurs simples, est lui aussi non résolu : le fichier Inspect le dit
dans ses `warnings`, et Tabalyst ne transforme pas un objet isolé en jeu de
données d’une ligne.

## Changer la façon de lire le fichier

Tout ce que vous pouvez modifier se trouve dans `config`. Omettez une clé pour
garder la valeur par défaut :

| Clé | Valeur par défaut | Effet |
| --- | --- | --- |
| `structure.dataset_path` | la sélection, ou `null` | La collection analysée, comme `$.customers[]`. Pour JSONL, c’est toujours `$[]`. |
| `flatten.enabled` | `true` | `false` conserve les objets imbriqués entiers, comme valeurs complexes. |
| `flatten.separator` | `.` | Un caractère qui joint les clés imbriquées dans les noms de champs, comme `address.city`. |
| `flatten.max_depth` | `null` | Profondeur, en clés et en `[]`, à partir de laquelle un objet est conservé entier. `null` signifie sans limite. |
| `arrays.mode` | `preserve` | La seule valeur prise en charge : les tableaux n’ajoutent jamais d’enregistrements. |
| `errors.policy` | `strict` pour JSON, `tolerant` pour JSONL | Que faire d’un enregistrement mal formé. |

Par exemple, `"max_depth": 2` fait de `address` et de `address.city` des champs
et conserve entiers les objets plus profonds, si bien que `tabalyst scan orders.json` liste 13 champs au lieu de 23. Une valeur non prise en charge est
une erreur qui nomme la clé :

```text
Error [orders.json]: Invalid Inspect file orders.json-inspect.json: config.arrays.mode: Value error, Array mode 'explode' is not supported in this version; only 'preserve' is
```

Les clés inconnues et les valeurs du mauvais type sont aussi des erreurs, jamais
ignorées. Un fichier Inspect illisible arrête `scan` et `report` avec le code de
sortie `2` ; Tabalyst ne remplace jamais votre fichier par un choix
automatique. La [référence de configuration](../reference/configuration.md#scan-settings)
décrit chaque paramètre.

## Inspecter un fichier de nouveau

Relancez `tabalyst inspect` après un changement de la source. La détection et
les avertissements sont réécrits ; votre `config` est conservée :

```text
Inspect: shop.json-inspect.json
Selection: none (several collections are equally plausible)
Configured collection: $.orders[] (kept from the existing file)
```

- `--reset-config` remplace `config` par celle qui a été détectée.
- `--force` remplace un fichier qui ne peut pas être conservé, comme un fichier
  écrit pour une autre version du format ou dont la `config` est invalide.
- `--config FILE` initialise un nouveau fichier à partir de la section `scan`
  d’un [fichier de configuration](../reference/configuration.md).

Si la source change et que la collection configurée disparaît, `scan` et
`report` s’arrêtent avec le code de sortie `2`, avant d’écrire quoi que ce
soit, et n’utilisent aucune autre collection :

```text
Error [shop.json]: The collection $.orders[] set in the Inspect file shop.json-inspect.json is not an array of shop.json, so nothing was analyzed. Set config.structure.dataset_path in that file to a collection that exists; `tabalyst inspect shop.json` lists the candidates.
```

Une source qui a changé alors que la collection existe toujours garde sa
`config` ; `scan` et `report` signalent que le fichier a été écrit pour une
autre version de la source, et analysent de nouveau : une analyse stockée n’est
réutilisée que si le contenu de la source, les paramètres effectifs et la
version de Tabalyst sont les mêmes.

## Quel paramètre l’emporte

Du moins prioritaire au plus prioritaire :

1. les valeurs par défaut de Tabalyst ;
2. la collection qu’Inspect a détectée, quand la source n’a pas de fichier
   Inspect ;
3. la section `scan` de chaque fichier `--config` ;
4. la `config` du fichier Inspect à côté de la source ;
5. `--collection`, `--delimiter` et `--encoding`.

## Fichiers JSONL et NDJSON

Un fichier `.jsonl` ou `.ndjson` a un seul jeu de données, `$[]` : ses
enregistrements sont les lignes. Inspect compte les lignes au lieu de choisir
une collection :

```console
tabalyst inspect web-events.jsonl --verbose
```

```text
Inspect: web-events.jsonl-inspect.json
Selection: $[] (the lines of the file)
Format: jsonl
Candidates: 1
  $[] (300 elements)
Warning [web-events.jsonl]: 2 lines are not valid JSON or are too long.
Warning [web-events.jsonl]: 1 line is valid JSON but not an object.
```

Inspect n’échoue jamais sur une ligne incorrecte : il les compte dans
`detection.lines` et liste les premières, par numéro de ligne physique, dans
`warnings`. Une analyse suit ensuite la politique d’erreurs de `config` :

- `tolerant`, la valeur par défaut pour JSONL, exclut les lignes incorrectes,
  les compte et se termine avec le statut `partial`. La commande réussit avec un
  avertissement : `partial scan, 3 records excluded (invalid_line: 2, not_object: 1).`
- `strict` s’arrête à la première ligne incorrecte, avec le code de sortie `4` :
  `Record 121 (line 121) of web-events.jsonl is not valid JSON (...)`.

Les lignes vides sont ignorées. `scan` et `report` n’inspectent pas
eux-mêmes un fichier JSONL, puisqu’il n’y a rien à choisir ; un fichier Inspect
ne fixe que les autres règles, comme la politique.

## Messages et codes de sortie

`--verbose` liste chaque collection candidate et les avertissements
informatifs ; `--quiet` ne garde que les avertissements et les erreurs ;
`--no-progress` désactive la progression. Les messages utilisent la sortie
d’erreur standard.

| Code | Signification |
| --- | --- |
| `0` | L’inspection a fonctionné, y compris quand elle n’a rien sélectionné. |
| `2` | Problème de configuration : extension non prise en charge, fichier Inspect invalide, collection non résolue ou collection configurée absente (dans `scan` et `report`). |
| `4` | La source est illisible : JSON invalide, UTF-8 invalide ou source vide. Aucun fichier n’est écrit. |
| `1` | Un autre échec, comme une sortie impossible à écrire. |

Un motif ignore les fichiers nommés `*-inspect.json`, et un fichier Inspect
donné en entrée est refusé : indiquez la source qu’il décrit. Une source dont le
nom se termine par `-inspect.json` doit d’abord être renommée. Sous Windows, la
bibliothèque de ligne de commande développe un joker avant que Tabalyst le
voie, si bien que `tabalyst inspect "*.json"` passe aussi les fichiers Inspect
et est refusé : nommez les sources, ou utilisez un motif qui ne correspond pas
aux fichiers Inspect, comme `*.jsonl`.

## API Python

```python
import tabalyst

result = tabalyst.inspect("orders.json")
print(result.path)
print(result.document.detection.selection.path)

batch = tabalyst.generate_inspections(["data/*.json", "logs/*.jsonl"])
```

`tabalyst.inspect()` inspecte une source comme le fait la commande, écrit le
fichier Inspect et renvoie un `InspectResult`, avec la `source`, le `path` du
fichier et le `document` tel qu’il a été écrit. Elle lève une erreur dérivée de
`tabalyst.TabalystError` quand l’inspection échoue.
`tabalyst.generate_inspections()` inspecte plusieurs sources et renvoie le plan,
les réussites et les échecs. Les deux acceptent `config_path`, `reset_config` et
`force`.

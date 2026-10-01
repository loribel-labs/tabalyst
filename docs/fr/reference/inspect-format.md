---
title: Format Inspect
description: Structure du fichier Inspect écrit par tabalyst inspect, avec ses zones, la détection, les avertissements, la config que vous pouvez modifier et la façon dont Tabalyst le lit.
---

`tabalyst inspect data.json` écrit `data.json-inspect.json` à côté de la source :
un document JSON qui dit comment Tabalyst comprend la source et qui contient les
règles pour la lire. Cette page décrit le format `tabalyst.inspect`, version
`0.1.0a`, révision `1`, type `json`. Le format est **expérimental** : il peut
changer de façon incompatible d’une version à l’autre. Les changements sont
listés dans le [journal des modifications du format Inspect](inspect-format-changelog.md).
Pour les commandes, voir
[Inspecter des fichiers JSON et JSONL](../how-to/inspect-json-files.md).

## Niveau supérieur

```json
{
  "format": "tabalyst.inspect",
  "format_version": "0.1.0a",
  "format_revision": 1,
  "inspect": {
    "kind": "json",
    "tabalyst_version": "0.4.4",
    "generated_at": "2026-10-01T05:34:13Z",
    "note": "Edit only the \"config\" section. Tabalyst replaces every other section each time it inspects this source."
  },
  "source": {
    "name": "orders.json",
    "format": "json",
    "size_bytes": 60720,
    "sha256": "ece53017421aa38fc11f6f7f07a7ad0168ffe606b098618c8fb1e69c59df1a59"
  },
  "detection": {"...": "see below"},
  "warnings": [],
  "config": {
    "structure": {"dataset_path": "$.customers[]"},
    "flatten": {"enabled": true, "separator": ".", "max_depth": null},
    "arrays": {"mode": "preserve"},
    "errors": {"policy": "strict"}
  }
}
```

Les sections apparaissent toujours dans cet ordre, `config` en dernier. Le
fichier est en UTF-8 avec une indentation de deux espaces. Il ne contient aucun
chemin absolu : `source.name` est un nom de fichier, et les autres chemins
pointent à l’intérieur de la source, comme `$.customers[]`.

| Section | Écrite par | Vous la modifiez | Effet sur les analyses |
| --- | --- | --- | --- |
| `format`, `format_version`, `format_revision` | Tabalyst | Non | Une version que Tabalyst ne lit pas est refusée. |
| `inspect` | Tabalyst | Non | Aucun. |
| `source` | Tabalyst | Non | Aucun : elle décrit la source au moment de l’inspection. |
| `detection` | Tabalyst | Non | Aucun. |
| `warnings` | Tabalyst | Non | Aucun. |
| `config` | Tabalyst une fois, puis vous | Oui | Les règles que `tabalyst scan` et `tabalyst report` appliquent. |

Pour la même source, la même version de Tabalyst et les mêmes paramètres, deux
inspections écrivent le même fichier, sauf `inspect.generated_at`.

## `inspect` et `source`

| Clé | Signification |
| --- | --- |
| `inspect.kind` | Le type d’Inspect, `json` pour les sources JSON, JSONL et NDJSON. |
| `inspect.tabalyst_version` | La version de Tabalyst qui a écrit le fichier. |
| `inspect.generated_at` | L’heure UTC de l’inspection, la seule valeur qui varie. |
| `inspect.note` | Un rappel : ne modifiez que `config`. |
| `source.name` | Le nom de fichier de la source, avec son extension. |
| `source.format` | `json`, ou `jsonl` pour les fichiers `.jsonl` et `.ndjson`. |
| `source.size_bytes` | Les octets lus. |
| `source.sha256` | Le SHA-256 de tous les octets lus. |

`source.sha256` enregistre la source au moment de l’inspection. Il ne sert
jamais à décider si une analyse stockée peut être réutilisée.

## `detection`

| Clé | Signification |
| --- | --- |
| `scope.structure` | Toujours `complete` : les candidats, les nombres d’éléments et les types d’éléments viennent de la lecture de toute la source. |
| `scope.detail` | Toujours `bounded` : les champs, les profondeurs et l’imbrication viennent des premiers enregistrements de chaque candidat. |
| `scope.limits` | Les bornes appliquées : `records` (premiers enregistrements observés par candidat, 1 000) et `fields` (champs distincts suivis par candidat, 1 000). |
| `scope.discovery_max_depth` | La profondeur en clés à laquelle les tableaux ont été cherchés, d’après `scan.json.discovery_max_depth` (3 par défaut). |
| `scope.candidates` | `truncated` quand plus de 100 tableaux ont été trouvés. Absent sinon. |
| `root.type` | Le type de la racine : `object`, `array`, `string`, `number`, `boolean`, `null`, ou `lines` pour JSONL. |
| `candidates` | Les collections candidates, dans l’ordre du document. |
| `selection` | La collection proposée, ou aucune. |
| `lines` | JSONL seulement. Nombres exacts de lignes : `read` (non vides), `blank`, `objects`, `invalid`, `not_object`. `invalid` inclut les lignes plus longues que `scan.limits.max_line_bytes`. |

Une **collection candidate** est le tableau racine, ou un tableau accessible
depuis la racine par des clés d’objet seulement, à au plus
`scan.json.discovery_max_depth` clés de profondeur. Les tableaux situés dans les
enregistrements d’un candidat ne sont pas des candidats : ils restent des champs
des enregistrements. Un fichier JSONL a un seul candidat, `$[]`.

| Clé d’un candidat | Signification |
| --- | --- |
| `path` | Le chemin absolu, comme `$.customers[]`. |
| `elements` | Le nombre exact d’éléments ; pour JSONL, le nombre de lignes objet. |
| `element_types` | Le nombre exact d’éléments par type, parmi `object`, `array`, `string`, `number`, `boolean`, `null`. |
| `eligible` | `true` quand le candidat a au moins un élément et que chaque élément est un objet. |
| `ineligible_reason` | Seulement quand il n’est pas éligible : `empty` ou `non_object_elements`. |
| `observation` | Le détail tiré des premiers enregistrements : `records` observés, `fields` distincts, `max_depth` (clés et `[]`), `nested_objects`, `arrays`, et `complete`, à `false` quand une borne a interrompu l’observation. |

Un champ qui apparaît pour la première fois après les enregistrements observés
est absent de `detection` ; l’analyse le trouve. Les observations ne sont jamais
exhaustives quand `complete` vaut `false`.

### Sélection

`selection.path` est la collection proposée, ou `null`. `selection.basis` dit
pourquoi :

| `basis` | Signification |
| --- | --- |
| `root_array` | La racine est un tableau d’objets. |
| `jsonl_records` | La source est JSONL et a au moins une ligne objet. |
| `only_eligible_candidate` | Un seul candidat est éligible. |
| `dominant_candidate` | Plusieurs sont éligibles et le plus grand a au moins 10 fois plus d’éléments que le suivant, indiqué dans `selection.over`. |
| `ambiguous` | Plusieurs sont éligibles et aucun ne se distingue. Rien n’est sélectionné. |
| `no_eligible_candidate` | Aucun candidat n’est éligible, ou la racine n’est ni un objet ni un tableau. Rien n’est sélectionné. |
| `candidates_truncated` | Plus de 100 tableaux existent, donc la liste ne peut pas prouver que l’un d’eux se distingue. Rien n’est sélectionné. |

Les noms de propriétés ne jouent aucun rôle. Une égalité ne sélectionne jamais.
Quand rien n’est sélectionné, `config.structure.dataset_path` vaut `null` et
`tabalyst scan` et `tabalyst report` s’arrêtent tant que vous ne l’avez pas
renseigné.

## `warnings`

Une liste d’entrées avec `code`, `level` (`warning` ou `info`) et `message`,
plus les clés qui s’appliquent : `path`, `reason`, `count`, et `locations`, une
liste de `{"record": n, "line": n}` d’au plus `scan.errors.max_locations`
entrées (le `count` est toujours complet). Les avertissements ne changent jamais
la façon dont une analyse lit la source.

| Code | Niveau | Quand | Clés |
| --- | --- | --- | --- |
| `ambiguous_collections` | warning | `basis` vaut `ambiguous` | `count` de candidats éligibles |
| `no_collection` | warning | `basis` vaut `no_eligible_candidate` | `reason` : `scalar_root`, `no_array` ou `no_eligible_array` |
| `candidates_truncated` | warning | La liste des candidats a été coupée à 100 | `count` conservé |
| `candidate_not_eligible` | info | Une par candidat non éligible, pour les 10 premiers seulement | `path`, `reason` (`empty`, `non_object_elements`) |
| `candidate_not_eligible_truncated` | info | Plus de 10 candidats ne sont pas éligibles | `count` de candidats non éligibles |
| `invalid_lines` | warning | Lignes JSONL qui ne sont pas du JSON valide, ou trop longues | `count`, `locations` |
| `non_object_lines` | warning | Lignes JSONL qui sont du JSON valide mais pas des objets | `count`, `locations` |
| `configured_path_not_found` | warning | Après une nouvelle inspection, le `dataset_path` conservé n’est pas un tableau de la source | `path` |
| `source_name_mismatch` | info | `source.name` du fichier existant diffère de la source inspectée | `path` : le nom enregistré |

Raisons de `no_collection` : `scalar_root` (la racine n’est ni un objet ni un
tableau), `no_array` (un objet sans tableau accessible par des clés) et
`no_eligible_array` (des tableaux existent et aucun n’est éligible, comme un
tableau de valeurs simples). `configured_path_not_found` n’est levé que pour un
chemin que les candidats peuvent juger : un chemin accessible par des clés
seules dans la profondeur de découverte. Un chemin plus profond, ou qui traverse
un tableau, est vérifié par l’analyse.

## `config`

La partie que vous modifiez. Omettez une clé pour garder la valeur par défaut de
la couche inférieure (voir
[Quel paramètre l’emporte](../how-to/inspect-json-files.md#quel-paramètre-lemporte)).

| Clé | Type | Valeur par défaut si omise | Écrite par Inspect |
| --- | --- | --- | --- |
| `structure.dataset_path` | chaîne ou `null` | `null` : non décidé | La sélection, ou `null` |
| `flatten.enabled` | booléen | `true` | La valeur effective |
| `flatten.separator` | chaîne | `"."` | La valeur effective |
| `flatten.max_depth` | entier ou `null` | `null` : sans limite | La valeur effective |
| `arrays.mode` | chaîne | `"preserve"` | `"preserve"` |
| `errors.policy` | `"strict"`, `"tolerant"` ou `null` | `null` : la valeur par défaut du format | La valeur résolue, jamais `null` |

Règles :

- `structure.dataset_path` est un chemin absolu qui commence par `$` et se
  termine par `[]`, comme `$.customers[]` ou `$["a.b"][]`. Pour une source
  JSONL, il doit valoir `$[]` ou `null`. Des chemins égaux écrits différemment
  sont le même chemin. Écrire `null` ne choisit pas la découverte automatique de
  `tabalyst.scan()`.
- `flatten.separator` est exactement un caractère qui n’est ni une lettre, ni un
  chiffre, ni `_`, ni un espace, ni un caractère de contrôle, ni l’un des
  caractères `[ ] " \ $`. Il change les noms des champs, jamais les chemins des
  collections, qui utilisent toujours `.`. Une clé qui contient le séparateur
  s’écrit `["a/b"]`, si bien qu’une clé `a.b` et les clés imbriquées `a` puis
  `b` restent deux champs distincts.
- `flatten.max_depth` vaut `null` ou un entier de 1 à 1 000. La profondeur
  compte les clés et les `[]` : `address` vaut 1, `address.city` vaut 2,
  `orders[].amount` vaut 3. Un objet ou un tableau à cette profondeur est
  conservé entier comme valeur complexe. `enabled: false` équivaut à une
  profondeur de 1.
- `arrays.mode` n’accepte que `preserve`. `ignore` et `explode` sont refusés.
- `errors.policy`, quand il vaut `null`, devient `strict` pour JSON et
  `tolerant` pour JSONL.

Une `config` est conservée telle que vous l’avez écrite quand Inspect est relancé :
les mêmes clés et les mêmes valeurs, sans rien ajouter. Chaque paramètre qui
influence le jeu de données, les champs ou les enregistrements analysés
participe à l’identité d’une analyse.

## Lecture d’un fichier Inspect

Pour le fichier à côté d’une source, Tabalyst valide les `format`,
`format_version` et `format_revision` de niveau supérieur, `inspect.kind` et
`config` ; les autres sections sont informatives, donc une `detection`
endommagée n’arrête jamais une analyse. Il refuse, avec le code de sortie `2` et
le nom du fichier :

| Cas | Le message nomme |
| --- | --- |
| Pas un objet JSON, ou un autre `format` | Le fichier |
| Un `format_version` ou un `format_revision` qu’il ne lit pas | Les deux versions, et les deux issues : modifier le fichier ou `tabalyst inspect --force` |
| Un `inspect.kind` inconnu ou absent | Les types qu’il lit |
| Une `config` absente, une clé inconnue à n’importe quelle profondeur, une valeur du mauvais type (y compris un nombre ou un booléen écrit comme chaîne) ou une valeur hors de l’ensemble pris en charge | La clé, comme `config.flatten.sepator` |

Il n’y a aucune migration pendant la bêta, et Tabalyst ne remplace jamais un
fichier invalide par un choix automatique.

## Copie stockée

Quand une source JSON n’a pas de fichier Inspect et que rien sur la ligne de
commande ni dans un fichier `--config` ne nomme sa collection, `tabalyst scan`
et `tabalyst report` l’inspectent et gardent une copie du résultat dans le
stockage local de Tabalyst, à côté de l’analyse stockée. La copie est
reconstruite dès que le contenu de la source, la version du format, la version
de Tabalyst ou la profondeur de découverte diffèrent. Elle est jetable et n’est
jamais lue quand un fichier Inspect existe à côté de la source.

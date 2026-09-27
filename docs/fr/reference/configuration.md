---
title: Configuration
description: Référence du fichier de configuration JSON lu par tabalyst report, tabalyst sample, tabalyst scan et l’API Python.
---

Tabalyst lit des fichiers de configuration JSON stricts. Le JSON n’autorise pas
les commentaires ; cette page est la référence descriptive des paramètres pris
en charge. Les commandes chargent les fichiers passés avec `--config`, et l’API
Python ceux passés avec `config_path` ; aucun fichier n’est chargé
automatiquement. `tabalyst.json` n’est qu’un nom conventionnel.

Un seul fichier peut configurer toutes les commandes. Les paramètres de
`tabalyst report` et `tabalyst sample` sont au premier niveau ; les paramètres
de `tabalyst scan` sont dans l’objet `scan`, décrit dans
[Paramètres d’analyse](#scan-settings) :

```json
{
  "csv": {"delimiter": ";"},
  "preview_rows": 20,
  "scan": {
    "csv": {"delimiter": ";"},
    "values": {"null_markers": ["N/A"]}
  }
}
```

Chaque commande valide tout le fichier, y compris les sections qu’elle
n’utilise pas : un paramètre mal orthographié ou inconnu est donc toujours une
erreur. Les valeurs explicites de la ligne de commande, comme `--delimiter` et
`--encoding`, ont le dernier mot.

## CSV et aperçu

```json
{
  "csv": {
    "encoding": "utf-8-sig",
    "delimiter": ","
  },
  "missing_values": [""],
  "preview_rows": 10
}
```

- `csv.encoding` : encodage du fichier source. La valeur par défaut accepte
  l’UTF-8 avec ou sans BOM ; `cp1252` est utile pour certains fichiers produits
  sous Windows.
- `csv.delimiter` : séparateur d’un seul caractère, la virgule par défaut.
- `missing_values` : chaînes traitées comme des valeurs manquantes après
  suppression des espaces en début et en fin. Les comparaisons restent sensibles
  à la casse.
- `preview_rows` : nombre de lignes brutes intégrées au rapport, de 0 à 100. Ce
  paramètre ne limite jamais l’analyse du CSV complet.

## Normalisation des valeurs

```json
{
  "normalization": {
    "trim": true,
    "collapse_internal_whitespace": true
  }
}
```

- `trim` : supprime les espaces Unicode en début et en fin avant l’analyse.
- `collapse_internal_whitespace` : remplace chaque suite interne d’espaces
  horizontaux, y compris les tabulations et les espaces insécables, par un seul
  espace ordinaire. Les sauts de ligne sont conservés.

La normalisation influe sur l’inférence de type, les valeurs distinctes, les
occurrences, les exemples et la détection `enum`. Les valeurs CSV brutes restent
disponibles dans l’aperçu des données, et les lignes exactement dupliquées sont
toujours comparées sur les valeurs brutes. Chaque colonne enregistre le nombre
et le pourcentage de cellules modifiées par chaque opération ; le résumé du jeu
de données enregistre aussi les deux comptages globaux. Une cellule modifiée par
les deux opérations compte dans les deux comptages, mais jamais plus d’une fois
pour la même opération.

## Détection des dates

```json
{
  "date_detection": {
    "enabled": true,
    "orders": ["YMD", "MDY", "DMY"],
    "separators": ["-", "/", "."],
    "ambiguous_order": null
  }
}
```

- `enabled` : active ou désactive le profilage strict des dates.
- `orders` : ordres des composantes acceptés. Les années doivent avoir quatre
  chiffres ; les mois et les jours peuvent en avoir un ou deux.
- `separators` : séparateurs d’un seul caractère acceptés. Chaque valeur doit
  utiliser le même séparateur entre les deux paires de composantes.
- `ambiguous_order` : résout éventuellement les valeurs comme `02/03/2025` en
  `MDY` ou en `DMY`. Avec `null`, Tabalyst ne les résout que lorsque la même
  colonne contient des preuves non ambiguës pour un ordre et aucune pour
  l’autre.

Chaque structure reconnue est validée par rapport au calendrier, y compris les
années bissextiles. Les profils comptent séparément les valeurs valides,
ambiguës, invalides et non dates, puis regroupent les occurrences valides par
ordre et par séparateur. `YYYY-MM-DD` est explicitement marqué comme ISO ; les
autres séparateurs utilisant `YMD` restent valides mais ne sont pas étiquetés
ISO. Un texte quelconque n’est pas traité comme une erreur de date.

## Inférence de type

```json
{
  "type_inference": {
    "minimum_confidence": 0.95
  }
}
```

`minimum_confidence` est la proportion de valeurs présentes qui doivent
concorder pour qu’une colonne reçoive un type physique dominant. Les valeurs
hors de ce type sont conservées comme erreurs, avec un nombre et un
pourcentage. Une colonne sans famille dominante reste `mixed` et n’a pas de taux
d’erreur trompeur. Les statistiques numériques n’utilisent que les valeurs
numériques acceptées.

Une colonne de dates avec un seul format valide a le type physique `date`.
Plusieurs formats de date valides donnent `mixed` avec le type sémantique
`date` ; les dates mal formées et les dates ambiguës non résolues contribuent
au taux d’erreur de type.

## Analyse des textes

```json
{
  "string_analysis": {
    "very_short_max_length": 5,
    "short_max_length": 20,
    "medium_max_length": 50,
    "long_max_length": 255,
    "length_distribution_max_length": 50,
    "examples_per_length": 10
  }
}
```

Les valeurs normalisées présentes dans les colonnes de type physique `text` sont
classées d’après leur longueur maximale en `very_short`, `short`, `medium`,
`long` ou `very_long`. Une longueur fixe est enregistrée séparément lorsque le
minimum et le maximum sont égaux. Les valeurs manquantes ne comptent pas dans
les longueurs. La longueur moyenne et la longueur médiane sont calculées pour
chaque colonne de texte ; le rapport les laisse vides lorsque la longueur fixe
donne déjà la même information.

Lorsque le maximum de la colonne ne dépasse pas
`length_distribution_max_length`, le JSON contient aussi le nombre
d’occurrences et de valeurs distinctes pour chaque longueur observée. Chaque
longueur conserve jusqu’à `examples_per_length` valeurs distinctes normalisées,
triées par nombre d’occurrences décroissant, puis par ordre alphabétique.
`distinct_length_count` reste disponible pour chaque colonne de texte, y compris
les colonnes dont la distribution est omise. Le rapport trie les groupes de
longueurs par occurrences et affiche trois exemples conservés par longueur dans
l’infobulle de la section String analysis.

## Exemples et profils de valeurs

```json
{
  "value_examples": {
    "full_distribution_max_distinct": 50,
    "candidate_sample_size": 100,
    "short_text_max_length": 20,
    "short_text_percentile": 0.95,
    "short_text_result_size": 20,
    "long_text_result_size": 20,
    "long_text_truncate_at": 30,
    "truncation_suffix": "...",
    "inline_display_size": 3,
    "random_seed": 42
  }
}
```

- `full_distribution_max_distinct` : jusqu’à cette limite, chaque valeur
  distincte non manquante et son nombre d’occurrences sont conservés dans le
  JSON. À `50`, la distribution est encore complète ; à `51`, Tabalyst
  échantillonne les valeurs.
- `candidate_sample_size` : nombre maximal de valeurs distinctes échantillonnées
  de façon reproductible avant la sélection finale.
- `short_text_max_length` et `short_text_percentile` : une colonne est
  considérée comme du texte court lorsque ce centile de ses longueurs
  échantillonnées ne dépasse pas la longueur configurée.
- `short_text_result_size` : **nombre de valeurs conservées pour l’infobulle
  lorsqu’une colonne de texte court a plus de 50 valeurs distinctes.** Sa valeur
  par défaut est `20`.
- `long_text_result_size` : limite équivalente pour le texte long. Sa valeur par
  défaut est aussi `20`.
- `long_text_truncate_at` et `truncation_suffix` : limite d’affichage des
  valeurs de texte long conservées, dans le JSON comme dans le rapport.
- `inline_display_size` : nombre de valeurs affichées directement dans la
  cellule `Examples`. Ce sont toujours les valeurs conservées les plus
  fréquentes.
- `random_seed` : graine d’échantillonnage, qui rend le JSON et les rapports
  reproductibles pour le même CSV et la même configuration.

La cellule `Examples` affiche `+N` pour une distribution complète. Pour un
profil échantillonné, elle affiche `++` ; l’infobulle affiche alors par exemple
`20 / 2,992`, c’est-à-dire valeurs conservées / valeurs distinctes réelles. Les
valeurs de l’infobulle sont triées par nombre d’occurrences décroissant.

## Candidats enum

```json
{
  "enum_detection": {
    "enabled": true,
    "minimum_row_count": 500,
    "maximum_distinct_values": 49,
    "eligible_types": ["text"],
    "case_sensitive": true
  }
}
```

- `enabled` : active la classification sémantique facultative.
- `minimum_row_count` : taille minimale du jeu de données avant qu’un candidat
  `enum` soit proposé.
- `maximum_distinct_values` : nombre maximal de valeurs non manquantes
  observées. La valeur par défaut est `49`.
- `eligible_types` : types physiques pouvant recevoir le marqueur ; la valeur
  par défaut limite la détection aux colonnes `text`.
- `case_sensitive` : décide si `Open` et `open` sont des valeurs distinctes.

`enum` est une indication sémantique : son type physique reste `text`. Le
rapport présente les types physiques et sémantiques dans des colonnes séparées,
afin que chacun puisse être filtré directement.

<a id="scan-settings"></a>

## Paramètres d’analyse

`tabalyst scan` et `tabalyst.generate_scans()` lisent l’objet `scan` de chaque
fichier de configuration. L’objet complet avec ses valeurs par défaut est :

```json
{
  "scan": {
    "csv": {"encoding": "utf-8-sig", "delimiter": ","},
    "json": {"collections": null, "discovery_max_depth": 3},
    "errors": {"policy": "strict", "max_locations": 10},
    "values": {
      "null_markers": [],
      "null_markers_case_sensitive": true,
      "missing": ["absent", "null", "empty", "blank", "marker"]
    },
    "normalization": {
      "nfc": true, "trim": true, "collapse_whitespace": true,
      "casefold": true, "strip_accents": true
    },
    "limits": {
      "max_fields": 10000, "max_depth": 64, "max_record_observations": 100000,
      "max_distinct_per_field": 100000, "max_tracked_values": 2000000,
      "max_stored_value_length": 1000, "max_listed_frequencies": 100,
      "max_samples": 100, "max_variant_groups": 100,
      "max_variants_per_group": 20, "max_evidence_examples": 10
    },
    "types": {"minimum_confidence": 0.95},
    "detection": {"minimum_share": 0.95},
    "detectors": {"number": {"enabled": true}},
    "patterns": [],
    "exposure": {"sensitive_values": "mask"},
    "random_seed": 42
  }
}
```

L’analyse ne lit pas les paramètres `csv` du premier niveau : indiquez le
séparateur et l’encodage dans `scan.csv`, ou passez `--delimiter` et
`--encoding`.

### Couches et règles de fusion

De la priorité la plus basse à la plus haute : les valeurs par défaut
intégrées, l’objet `scan` de chaque fichier `--config` dans l’ordre indiqué,
puis `--delimiter`, `--encoding` et `--collection`.

- Les objets fusionnent clé par clé, y compris `detectors.<id>` : un fichier qui
  définit `{"detectors": {"number": {"enabled": false}}}` conserve les autres
  paramètres de number.
- Les listes remplacent entièrement la liste précédente, comme `null_markers`,
  `patterns` ou `collections`.
- Les clés inconnues sont des erreurs.
- `null` n’est accepté que là où un paramètre l’autorise ; il n’existe pas de
  syntaxe pour supprimer un paramètre.

Le document d’analyse intègre la configuration effective et son SHA-256
(`config_sha256`).

### Sources et erreurs

- `csv.encoding`, `csv.delimiter` : comme pour les rapports. Le premier
  enregistrement est l’en-tête.
- `json.collections` : `null` pour la découverte automatique, ou une liste de
  chemins de collection absolus comme `"$.customers[]"` ou
  `"$.customers[].orders[]"`. Les chemins doivent se terminer par `[]`, être
  uniques et ne pas se contenir les uns les autres.
- `json.discovery_max_depth` : la profondeur jusqu’à laquelle la découverte
  automatique cherche des tableaux sous un objet racine.
- `errors.policy` : `strict` s’arrête au premier enregistrement mal formé, comme
  un enregistrement CSV avec un mauvais nombre de champs ou un objet JSON avec
  une clé en double. `tolerant` exclut ces enregistrements, les compte et marque
  l’analyse `partial`. Une syntaxe invalide, un texte impossible à décoder et un
  fichier illisible arrêtent l’analyse avec les deux politiques.
- `errors.max_locations` : combien d’emplacements d’enregistrements chaque
  diagnostic liste.

### Valeurs et valeurs manquantes

- `values.null_markers` : chaînes qui représentent une valeur manquante, comme
  `"N/A"`, comparées après suppression des espaces en début et en fin.
- `values.null_markers_case_sensitive` : réglez-le sur `false` pour reconnaître
  aussi `n/a`.
- `values.missing` : les catégories comptées comme manquantes : `absent` (la clé
  ou la colonne n’existe pas dans un enregistrement), `null`, `empty` (`""`),
  `blank` (espaces uniquement) et `marker`. Chaque composante reste listée dans
  le résultat.

### Normalisation

Chaque étape peut être désactivée. Elles s’exécutent dans cet ordre : `nfc`
(composition Unicode), `trim`, `collapse_whitespace`, `casefold` et
`strip_accents`. Les trois premières produisent la valeur analytique utilisée
par les listes et les détecteurs ; toutes les étapes comptent les valeurs
qu’elles modifient et regroupent les variantes qui deviennent égales, comme
`Montréal` et `MONTREAL`. Les valeurs brutes ne sont jamais modifiées.

### Limites

Les limites bornent la mémoire et la taille de la sortie. Une mesure qui atteint
une limite est marquée `limited` dans le résultat, jamais estimée. Les valeurs
supérieures au maximum sont rejetées avant le début de l’analyse.

| Paramètre | Défaut | Maximum | Lorsque la limite est atteinte |
| --- | --- | --- | --- |
| `max_fields` | 10 000 | 1 000 000 | Les nouveaux chemins de champ d’un jeu de données sont comptés mais pas analysés. |
| `max_depth` | 64 | 1 000 | Le contenu JSON plus profond est compté mais pas analysé. |
| `max_record_observations` | 100 000 | 100 000 000 | L’enregistrement est une erreur, ou est exclu avec `tolerant`. |
| `max_distinct_per_field` | 100 000 | 50 000 000 | Les valeurs distinctes du champ ne sont plus stockées ; les fréquences et la cardinalité deviennent limitées. |
| `max_tracked_values` | 2 000 000 | 500 000 000 | Valeurs distinctes stockées pour toute l’analyse ; le champ le plus volumineux est libéré en premier. |
| `max_stored_value_length` | 1 000 | 1 000 000 | Les valeurs plus longues sont comptées, pas stockées. |
| `max_listed_frequencies` | 100 | 100 000 | Valeurs les plus fréquentes listées par champ. |
| `max_samples` | 100 | 10 000 | Valeurs d’échantillon listées par champ. |
| `max_variant_groups` | 100 | 100 000 | Groupes de variantes de normalisation listés par champ. |
| `max_variants_per_group` | 20 | 10 000 | Variantes listées par groupe. |
| `max_evidence_examples` | 10 | 1 000 | Valeurs d’exemple par état de détecteur. |

`max_distinct_per_field` ne peut pas dépasser `max_tracked_values`. Les
compteurs, les statistiques et la couverture des détecteurs restent exacts une
fois une limite atteinte.

### Types et interprétations

- `types.minimum_confidence` : part des valeurs qui doivent concorder pour
  qu’un champ reçoive un type technique comme `integer` ou `date`, sinon
  `mixed`.
- `detection.minimum_share` : part des valeurs qu’un détecteur doit reconnaître
  pour devenir une interprétation candidate du champ.

### Détecteurs

Chaque détecteur a `enabled` (par défaut `true`) et les paramètres ci-dessous.
Les autres identifiants de détecteur sont des erreurs.

| Détecteur | Paramètres et valeurs par défaut |
| --- | --- |
| `number` | `conventions` : `["dot", "comma"]`, les séparateurs décimaux acceptés ; `ambiguous_convention` : `null`, ou `dot` ou `comma` pour lire d’une seule façon les valeurs comme `1,234`. |
| `date` | `orders` : `["YMD", "MDY", "DMY"]` ; `separators` : `["-", "/", "."]` ; `ambiguous_order` : `null`, ou `MDY` ou `DMY` pour lire d’une seule façon les valeurs comme `02/03/2025` ; `month_languages` : `["en", "fr"]`. |
| `boolean` | `pairs` : `[["true", "false"], ["yes", "no"], ["y", "n"], ["oui", "non"], ["vrai", "faux"]]`. |
| `enumeration` | `minimum_values` : 500 ; `maximum_distinct` : 49 ; `case_sensitive` : `true`. |
| `email` | `max_tracked_domains` : 10 000 ; `max_listed_domains` : 20. |
| `url` | `schemes` : `["http", "https", "ftp"]` ; `www` : `true`, accepte les adresses commençant par `www.` ; `max_tracked_hosts` : 10 000 ; `max_listed_hosts` : 20. |
| `phone` | `regions` : `["nanp", "fr"]` ; `nanp` couvre le Canada et les États-Unis. |
| `postal_code` | `regions` : `["ca", "us"]`, codes postaux canadiens et codes ZIP. |
| `currency` | `conventions` et `ambiguous_convention`, comme pour `number`. |
| `percentage` | `conventions` et `ambiguous_convention`, comme pour `number`. |
| `quantity` | `conventions` et `ambiguous_convention`, comme pour `number` ; `max_tracked_units` : 10 000 ; `max_listed_units` : 20. |
| `uuid` | Aucun autre paramètre. |
| `ip_address` | `versions` : `["ipv4", "ipv6"]`. |

Les valeurs ambiguës ne sont jamais résolues à partir des autres valeurs du
champ : seuls `ambiguous_convention` et `ambiguous_order` les résolvent.

### Motifs

`patterns` ajoute vos propres détecteurs, présentés sous la forme
`pattern:<id>` :

```json
{
  "scan": {
    "patterns": [
      {
        "id": "customer_number",
        "regex": "C-\\d{4}",
        "description": "Customer number",
        "accepts": ["string"],
        "sensitive": false,
        "max_input_length": 256
      }
    ]
  }
}
```

- `id` : de 1 à 64 lettres, chiffres, `_` ou `-`, unique.
- `regex` : une expression régulière Python d’au plus 1 000 caractères qui doit
  correspondre à la valeur entière.
- `accepts` : types natifs testés, parmi `string`, `integer`, `number` et
  `boolean` ; par défaut `["string"]`.
- `sensitive` : `true` masque les champs où le motif est reconnu.
- `max_input_length` : les valeurs plus longues ne sont pas testées ; 256 par
  défaut, 10 000 au plus.

Au plus 200 motifs. Les expressions régulières s’exécutent sans délai
d’expiration : n’utilisez que des motifs de confiance, car certaines
expressions peuvent prendre très longtemps sur certaines valeurs.

### Valeurs sensibles et échantillonnage

- `exposure.sensitive_values` : comment les valeurs des champs sensibles
  (adresses e-mail, numéros de téléphone, adresses IP et motifs sensibles)
  apparaissent dans le résultat. `mask` (par défaut) remplace les lettres par
  `A` ou `a` et les chiffres par `9` ; `hide` supprime les valeurs et conserve
  les comptages ; `show` les conserve.
- `random_seed` : graine des échantillons de valeurs, pour que deux analyses du
  même fichier avec les mêmes paramètres soient identiques.

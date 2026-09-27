---
title: Configuration
description: Référence du fichier de configuration JSON lu par tabalyst report, tabalyst sample, tabalyst scan et l’API Python.
---

Tabalyst lit des fichiers de configuration JSON stricts. Le JSON n’autorise pas
les commentaires ; cette page est la référence descriptive des paramètres pris
en charge. Les commandes chargent les fichiers passés avec `--config`, et l’API
Python ceux passés avec `config_path` ; aucun fichier n’est chargé
automatiquement. `tabalyst.json` n’est qu’un nom conventionnel.

Un seul fichier peut configurer toutes les commandes. L’objet `scan` contient
les paramètres d’analyse, lus par `tabalyst scan` et `tabalyst report`, décrits
dans [Paramètres d’analyse](#scan-settings). Le premier niveau contient les
paramètres de présentation du rapport et les paramètres CSV de
`tabalyst sample` :

```json
{
  "preview_rows": 20,
  "csv": {"delimiter": ";"},
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

## Paramètres du rapport

Le rapport repose sur Tabalyst Scan : il lit le CSV et l’analyse avec les
paramètres `scan`, puis présente le résultat avec les paramètres ci-dessous.

```json
{
  "preview_rows": 10,
  "string_analysis": {
    "very_short_max_length": 5,
    "short_max_length": 20,
    "medium_max_length": 50,
    "long_max_length": 255,
    "length_distribution_max_length": 50,
    "examples_per_length": 10
  },
  "value_examples": {
    "full_distribution_max_distinct": 50,
    "short_text_max_length": 20,
    "short_text_percentile": 0.95,
    "short_text_result_size": 20,
    "long_text_result_size": 20,
    "long_text_truncate_at": 30,
    "truncation_suffix": "...",
    "inline_display_size": 3
  }
}
```

### Aperçu

`preview_rows` : nombre de lignes brutes intégrées au rapport, de 0 à 100. Ce
paramètre ne limite jamais l’analyse du CSV complet. Les valeurs des colonnes
sensibles sont masquées ou cachées dans l’aperçu comme dans le reste du rapport
(voir
[Comment le rapport utilise les paramètres d’analyse](#how-the-report-uses-the-scan-settings)).

### Analyse des textes

Les valeurs présentes dans les colonnes `text` sont classées d’après leur
longueur maximale en `very_short`, `short`, `medium`, `long` ou `very_long`.
Une longueur fixe est enregistrée séparément lorsque le minimum et le maximum
sont égaux. Les valeurs manquantes ne comptent pas dans les longueurs. La
longueur moyenne et la longueur médiane sont calculées pour chaque colonne de
texte ; le rapport les laisse vides lorsque la longueur fixe donne déjà la même
information.

Lorsque le maximum de la colonne ne dépasse pas
`length_distribution_max_length`, le JSON contient aussi le nombre exact
d’occurrences de chaque longueur observée. Chaque longueur liste jusqu’à
`examples_per_length` valeurs d’exemple, prises parmi les valeurs les plus
fréquentes de la colonne, puis parmi ses valeurs échantillonnées.
`distinct_length_count` reste disponible pour chaque colonne de texte, y compris
les colonnes dont la distribution est omise. Le rapport trie les groupes de
longueurs par occurrences et affiche trois exemples par longueur dans
l’infobulle de la section String analysis.

### Exemples et profils de valeurs

- `full_distribution_max_distinct` : jusqu’à cette limite, chaque valeur
  distincte présente et son nombre d’occurrences sont conservés dans le JSON.
  À `50`, la distribution est encore complète ; à `51`, Tabalyst choisit les
  valeurs parmi un échantillon reproductible des valeurs distinctes, dont la
  taille est `scan.limits.max_samples` et la graine `scan.random_seed`.
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

La cellule `Examples` affiche `+N` pour une distribution complète. Pour un
profil échantillonné, elle affiche `++` ; l’infobulle affiche alors par exemple
`20 / 2,992`, c’est-à-dire valeurs conservées / valeurs distinctes réelles. Les
valeurs de l’infobulle sont triées par nombre d’occurrences décroissant. Pour
une colonne sensible, la cellule affiche à la place `masked` ou `hidden`, et
l’infobulle liste les valeurs masquées.

<a id="how-the-report-uses-the-scan-settings"></a>

### Comment le rapport utilise les paramètres d’analyse

| Comportement du rapport | Paramètres d’analyse |
| --- | --- |
| Lecture du CSV | `scan.csv`, `--delimiter`, `--encoding` |
| Cellules manquantes | `scan.values` : `null_markers`, `null_markers_case_sensitive` et `missing` |
| Comptages de normalisation et valeurs distinctes | `scan.normalization` : `nfc`, `trim`, `collapse_whitespace` |
| Types inférés | `scan.types.minimum_confidence`, avec les détecteurs `number` et `date` |
| Analyse des dates | `scan.detectors.date` |
| Types sémantiques | `scan.detection.minimum_share` et chaque détecteur |
| Valeurs masquées | `scan.exposure.sensitive_values` |

- **Dates.** Une colonne dont les valeurs présentes sont des dates est `date`,
  même avec plusieurs formats ou des valeurs ambiguës. Les valeurs ambiguës
  comme `02/03/2025` ne sont jamais résolues à partir des autres valeurs de la
  colonne : le rapport les compte comme ambiguës, indique combien de valeurs non
  ambiguës utilisent chaque ordre et, lorsqu’un seul ordre apparaît, suggère de
  définir `scan.detectors.date.ambiguous_order`. L’anomalie `ambiguous_dates`
  les compte.
- **Types sémantiques.** `date` pour les colonnes de dates, sinon
  l’interprétation principale de l’analyse : le seul détecteur qui reconnaît au
  moins `scan.detection.minimum_share` des valeurs présentes, comme
  `enumeration`, `email`, `phone` ou `postal_code`. `number` et `boolean` ne
  sont pas répétés comme types sémantiques.
- **Valeurs sensibles.** Les colonnes où un détecteur sensible est reconnu,
  comme les adresses e-mail et les numéros de téléphone, sont masquées par
  défaut dans les exemples, les profils de valeurs et l’aperçu :
  `jane@example.com` devient `aaaa@aaaaaaa.aaa`. Réglez
  `scan.exposure.sensitive_values` sur `show` pour conserver les valeurs, ou sur
  `hide` pour les supprimer.
- **Limites.** Lorsqu’une limite d’analyse arrête une mesure, comme les valeurs
  distinctes d’une colonne qui en a plus de
  `scan.limits.max_distinct_per_field`, le rapport affiche `limited` au lieu
  d’un nombre et liste la colonne dans l’anomalie `limited_measures`.

Le rapport lit les paramètres `scan.csv`, pas les paramètres `csv` du premier
niveau. Lorsqu’un fichier définit les deux avec des valeurs différentes, le
rapport s’arrête avec une erreur, car le fichier serait sinon lu avec des
paramètres qu’il n’attend pas ; une valeur donnée avec `--delimiter` ou
`--encoding` l’emporte toujours. Le rapport a aussi besoin de toutes les
colonnes : un CSV plus large que `scan.limits.max_fields` est une erreur.

### Paramètres déplacés dans `scan`

Ces paramètres du premier niveau sont rejetés avec un message qui indique leur
nouvel emplacement :

| Ancien paramètre | Nouvel emplacement |
| --- | --- |
| `missing_values` | `scan.values.null_markers` pour des marqueurs comme `"N/A"` ; les cellules vides ou ne contenant que des espaces sont manquantes par défaut (`scan.values.missing`) |
| `normalization.trim` | `scan.normalization.trim` |
| `normalization.collapse_internal_whitespace` | `scan.normalization.collapse_whitespace` |
| `date_detection` | `scan.detectors.date` |
| `type_inference.minimum_confidence` | `scan.types.minimum_confidence` |
| `enum_detection` | `scan.detectors.enumeration` : `maximum_distinct_values` devient `maximum_distinct`, et `minimum_row_count` devient `minimum_values`, qui compte les valeurs présentes, pas les lignes |
| `value_examples.candidate_sample_size` | `scan.limits.max_samples` |
| `value_examples.random_seed` | `scan.random_seed` |

## Paramètres de l’échantillonnage

```json
{
  "csv": {
    "encoding": "utf-8-sig",
    "delimiter": ","
  }
}
```

- `csv.encoding` : encodage du fichier source pour `tabalyst sample`. La valeur
  par défaut accepte l’UTF-8 avec ou sans BOM ; `cp1252` est utile pour
  certains fichiers produits sous Windows.
- `csv.delimiter` : séparateur d’un seul caractère, la virgule par défaut.

<a id="scan-settings"></a>

## Paramètres d’analyse

`tabalyst scan`, `tabalyst report` et leurs fonctions Python lisent l’objet
`scan` de chaque fichier de configuration. L’objet complet avec ses valeurs par
défaut est :

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

Les analyses et les rapports ne lisent pas les paramètres `csv` du premier
niveau : indiquez le séparateur et l’encodage dans `scan.csv`, ou passez
`--delimiter` et `--encoding`.

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

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
  "string_analysis": {"examples_per_length": 5},
  "csv": {"delimiter": ";"},
  "scan": {
    "csv": {"delimiter": ";"},
    "values": {"null_markers": ["N/A"]},
    "records": {"preview": 20}
  }
}
```

Chaque commande valide tout le fichier, y compris les sections qu’elle
n’utilise pas : un paramètre mal orthographié ou inconnu est donc toujours une
erreur. Les valeurs explicites de la ligne de commande, comme `--delimiter` et
`--encoding`, ont le dernier mot.

## Paramètres du rapport

Le rapport repose sur Tabalyst Scan : il réutilise une analyse enregistrée
encore courante lorsque c’est possible, ou lit le CSV et l’analyse avec les
paramètres `scan`, puis présente le résultat avec les paramètres ci-dessous.

```json
{
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

Le rapport affiche l’aperçu de l’analyse : ses `scan.records.preview` premiers
enregistrements, 10 par défaut (voir [Enregistrements](#records)). Il ne limite
jamais l’analyse du fichier complet. Les valeurs des colonnes sensibles sont
masquées ou cachées dans l’aperçu comme dans le reste du rapport (voir
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
| Aperçu | `scan.records.preview` |
| Lignes en double | `scan.records.duplicates` et `scan.limits.max_tracked_records` |
| Limites et diagnostics | `scan.limits` et `scan.errors` |

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
- **Lignes en double.** Avec plus de lignes distinctes que
  `scan.limits.max_tracked_records`, le nombre de doublons est une borne
  inférieure, affichée `≥ 12`. Avec `scan.records.duplicates` réglé sur
  `false`, les doublons ne sont pas recherchés et le rapport affiche `–`.

Le rapport lit les paramètres `scan.csv`, pas les paramètres `csv` du premier
niveau. Lorsqu’un fichier définit les deux avec des valeurs différentes, le
rapport s’arrête avec une erreur, car le fichier serait sinon lu avec des
paramètres qu’il n’attend pas ; une valeur donnée avec `--delimiter` ou
`--encoding` l’emporte toujours. Le rapport a aussi besoin de toutes les
colonnes : un CSV plus large que `scan.limits.max_fields` est une erreur.

Un rapport généré à partir d’un document d’analyse avec `tabalyst report --scan`
utilise les paramètres enregistrés dans le document. Ses fichiers de
configuration donnent toujours les paramètres de présentation ; les paramètres
donnés dans leur objet `scan` doivent avoir les valeurs enregistrées dans le
document, sinon le rapport s’arrête avec une erreur (voir
[Rapport à partir d’une analyse](../how-to/scan-files.md#report-from-a-scan)).

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
| `preview_rows` | `scan.records.preview`, désormais jusqu’à 1 000 |

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
    "json": {"collections": null, "discovery_max_depth": 3,
             "flatten": {"enabled": true, "separator": ".", "max_depth": null},
             "arrays": {"mode": "preserve"}},
    "errors": {"policy": null, "max_locations": 10},
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
      "max_line_bytes": 16777216,
      "max_distinct_per_field": 100000, "max_tracked_values": 2000000,
      "max_stored_value_length": 1000, "max_listed_frequencies": 100,
      "max_samples": 100, "max_variant_groups": 100,
      "max_variants_per_group": 20, "max_evidence_examples": 10,
      "max_tracked_records": 2000000, "max_listed_records": 10
    },
    "records": {"preview": 10, "duplicates": true},
    "types": {"minimum_confidence": 0.95},
    "detection": {
      "minimum_share": 0.95, "warmup_values": 10000, "probe_interval": 100,
      "rare_share": 0.001
    },
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
intégrées, pour une source JSON sans fichier Inspect la collection
qu’[Inspect](../how-to/inspect-json-files.md) détecte, l’objet `scan` de chaque
fichier `--config` dans l’ordre indiqué, la `config` du
[fichier Inspect](inspect-format.md#config) à côté de la source, puis
`--delimiter`, `--encoding` et `--collection`.

- Les objets fusionnent clé par clé, y compris `detectors.<id>` : un fichier qui
  définit `{"detectors": {"number": {"enabled": false}}}` conserve les autres
  paramètres de number.
- Les listes remplacent entièrement la liste précédente, comme `null_markers`,
  `patterns` ou `collections`.
- Les clés inconnues sont des erreurs.
- `null` n’est accepté que là où un paramètre l’autorise ; il n’existe pas de
  syntaxe pour supprimer un paramètre.

Le document d’analyse intègre la configuration effective et son SHA-256
(`config_sha256`). Une analyse stockée n’est réutilisée que si le contenu de la
source, cette configuration et la version de Tabalyst sont tous identiques.

### Sources et erreurs

- `csv.encoding`, `csv.delimiter` : comme pour les rapports. Le premier
  enregistrement est l’en-tête.
- `json.collections` : pour les fichiers JSON, une liste de chemins de
  collection absolus comme `"$.customers[]"` ou `"$.customers[].orders[]"`. Les
  chemins doivent se terminer par `[]`, être uniques et ne pas se contenir les
  uns les autres, et sont stockés dans leur écriture canonique (`$["orders"][]`
  devient `$.orders[]`). `null` signifie qu’aucune collection n’est nommée :
  `tabalyst scan` et `tabalyst report` utilisent alors la collection
  qu’[Inspect](../how-to/inspect-json-files.md) sélectionne, ou s’arrêtent avec
  le code de sortie `2` quand il ne peut pas en sélectionner une. Seule
  `tabalyst.scan()` transforme `null` en découverte automatique de tous les
  tableaux. Pour un fichier JSONL, c’est `null` ou `["$[]"]`. Un fichier qui
  liste `json.collections` est partagé par les sources de tous les formats ; il
  est donc ignoré pour les sources JSONL d’un lot mixte.
- `json.discovery_max_depth` : la profondeur jusqu’à laquelle Inspect, et la
  découverte automatique, cherchent des tableaux sous un objet racine.
- `json.flatten` : comment les objets imbriqués deviennent des champs. `enabled`
  (`true` par défaut) ; `separator` (`.` par défaut) joint les clés d’un nom de
  champ comme `address.city` ; c’est un caractère qui n’est ni une lettre, ni un
  chiffre, ni `_`, ni un espace, ni l’un des caractères `[ ] " \ $`.
  `max_depth` (`null` par défaut, sans limite) compte les segments depuis la
  racine de l’enregistrement, une clé ou `[]` pour chacun : `address` vaut 1,
  `address.city` vaut 2, `orders[].amount` vaut 3. Un conteneur (objet ou
  tableau) à cette profondeur est conservé entier comme valeur complexe et son
  contenu n’est pas analysé : rien n’est perdu, aucun avertissement n’est levé,
  et le rapport l’affiche comme une colonne de type `complex`. `enabled: false`
  équivaut à une profondeur de 1. Le séparateur ne change que les noms affichés :
  une clé qui le contient s’écrit `["a/b"]`, et les chemins de jeux de données
  comme `$.customers[]` utilisent toujours `.`. Ce n’est pas `limits.max_depth`,
  qui protège le lecteur et tronque avec un avertissement. Le contenu situé sous
  la profondeur d’aplatissement n’est pas lu pour détecter les clés en double.
- `json.arrays` (`mode`, seulement `preserve`) : les tableaux n’ajoutent jamais
  d’enregistrements. `ignore` et `explode` sont refusés.

Les paramètres `json.collections`, `json.flatten`, `json.arrays` et
`errors.policy` sont ceux qu’un [fichier Inspect](inspect-format.md#config)
modifie, sous les noms `structure.dataset_path`, `flatten`, `arrays` et
`errors.policy`.
- `errors.policy` : `null` (par défaut) est la valeur par défaut du format de la
  source, `strict` pour CSV et JSON, `tolerant` pour JSONL. `strict` s’arrête au
  premier enregistrement mal formé, comme un enregistrement CSV avec un mauvais
  nombre de champs, un objet JSON avec une clé en double ou une ligne JSONL qui
  n’est pas du JSON valide. `tolerant` exclut ces enregistrements, les compte et
  marque l’analyse `partial`. Une syntaxe invalide dans un fichier JSON, un
  texte impossible à décoder et un fichier illisible arrêtent l’analyse avec les
  deux politiques.
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
| `max_line_bytes` | 16 777 216 (16 Mio) | 268 435 456 (256 Mio) | JSONL seulement : une ligne plus longue n’est pas analysée. C’est une erreur, ou la ligne est exclue avec `tolerant`. La mémoire nécessaire pour analyser une ligne vaut environ 7 à 13 fois sa taille. |
| `max_distinct_per_field` | 100 000 | 50 000 000 | Les valeurs distinctes du champ ne sont plus stockées ; les fréquences et la cardinalité deviennent limitées. |
| `max_tracked_values` | 2 000 000 | 500 000 000 | Valeurs distinctes stockées pour toute l’analyse ; le champ le plus volumineux est libéré en premier. |
| `max_stored_value_length` | 1 000 | 1 000 000 | Les valeurs plus longues sont comptées, pas stockées. |
| `max_listed_frequencies` | 100 | 100 000 | Valeurs les plus fréquentes listées par champ. |
| `max_samples` | 100 | 10 000 | Valeurs d’échantillon listées par champ. |
| `max_variant_groups` | 100 | 100 000 | Groupes de variantes de normalisation listés par champ. |
| `max_variants_per_group` | 20 | 10 000 | Variantes listées par groupe. |
| `max_evidence_examples` | 10 | 1 000 | Valeurs d’exemple par état de détecteur. |
| `max_tracked_records` | 2 000 000 | 500 000 000 | Enregistrements distincts stockés pour toute l’analyse afin de trouver les doublons, environ 80 octets chacun ; les enregistrements suivants sont encore comparés à ceux stockés, et les nombres de doublons deviennent des bornes inférieures. |
| `max_listed_records` | 10 | 10 000 | Numéros d’enregistrement listés par bloc d’enregistrements. |

`max_distinct_per_field` ne peut pas dépasser `max_tracked_values`. Les
compteurs, les statistiques et la couverture des détecteurs restent exacts une
fois une limite atteinte.

<a id="records"></a>

### Enregistrements

- `records.preview` : combien des premiers enregistrements chaque jeu de
  données conserve dans son aperçu, de 0 à 1 000. Les valeurs sensibles sont
  exposées comme ailleurs.
- `records.duplicates` : réglez-le sur `false` pour ne pas rechercher les
  doublons, ce qui stocke une empreinte par enregistrement distinct, jusqu’à
  `limits.max_tracked_records`. Le nombre de doublons est alors `disabled`.

### Types et interprétations

- `types.minimum_confidence` : part des valeurs qui doivent concorder pour
  qu’un champ reçoive un type technique comme `integer` ou `date`, sinon
  `mixed`.
- `detection.minimum_share` : part des valeurs qu’un détecteur doit reconnaître
  pour devenir une interprétation candidate du champ.
- `detection.warmup_values` : 10 000 par défaut, jusqu’à 1 000 000. Les
  premières valeurs distinctes de chaque champ passent par tous les détecteurs.
  Un détecteur qui n’en a reconnu aucune, pas même comme invalide ou ambiguë,
  est ensuite ignoré pour les autres valeurs du champ, qui comptent comme
  `not_tested` dans sa couverture. `number` et `date` ne sont jamais ignorés. Un
  champ avec moins de valeurs distinctes est toujours analysé par tous les
  détecteurs. Réglez-le sur `0` pour tester chaque valeur avec chaque
  détecteur, comme avant l’existence de ce paramètre.
- `detection.rare_share` : 0,001 par défaut, de 0 à 1. Un détecteur qui a reconnu
  au plus cette part des valeurs de chauffe, et aucune de celles de la seconde
  moitié de la chauffe, est lui aussi ignoré : ses reconnaissances étaient rares
  et ont cessé. La valeur par défaut autorise 10 valeurs d’une chauffe de
  10 000 valeurs. Un détecteur qui reconnaît encore des valeurs à la fin de la
  chauffe est conservé, comme dans une colonne triée où les correspondances
  deviennent fréquentes, tout comme un détecteur sensible qui n’a trouvé que des
  valeurs invalides. `0` n’ignore que les détecteurs qui n’ont rien reconnu.
- `detection.probe_interval` : 100 par défaut, jusqu’à 1 000 000. Après la
  chauffe, environ une valeur distincte sur ce nombre, choisie par une empreinte
  de la valeur, passe encore par tous les détecteurs. L’analyse signale un
  avertissement `detector_skipped_reacted`, qui signifie que les comptages d’un
  détecteur ignoré pour le champ sont incomplets, quand il reconnaît l’un de ces
  sondages après n’avoir rien reconnu pendant la chauffe, ou, pour un détecteur
  rare, quand il reconnaît au moins 10 valeurs sondées, plus souvent que
  `detection.rare_share` ne le permet. `0` désactive les sondages.

Un détecteur ignoré après la chauffe peut manquer des valeurs rares qui
apparaissent plus loin dans le fichier, y compris des valeurs sensibles comme
une adresse e-mail dans une colonne de commentaires : une telle valeur ne
serait pas masquée. Réglez `detection.warmup_values` sur `0` quand chaque valeur
sensible doit être trouvée.

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

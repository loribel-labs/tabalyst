---
title: Limites connues
description: Ce que Tabalyst ne fait pas encore pendant sa phase bêta, notamment les limites des rapports JSON, le budget de la détection des doublons et les formats JSON expérimentaux.
---

Tabalyst est en bêta. Cette page liste ce qu’il ne fait pas encore, pour vous
aider à décider s’il convient à vos données. Une limite est retirée de cette
page lorsqu’une version publiée la lève.

## Entrée

- **CSV, JSON et JSONL uniquement.** `tabalyst report` et `tabalyst scan` lisent
  des fichiers CSV, JSON et JSONL (`.jsonl`, `.ndjson`) ; `tabalyst inspect` lit
  des fichiers JSON et JSONL ; `tabalyst sample` ne lit que des fichiers CSV. Les
  classeurs Excel, XML, GeoJSON, JSON compressé, Parquet et les bases de données
  ne sont pas pris en charge ; exportez-les d’abord en CSV.
- **Une seule collection par source JSON par défaut.** Tabalyst analyse la
  collection d’enregistrements qu’[Inspect](../how-to/inspect-json-files.md)
  sélectionne. Quand plusieurs tableaux sont aussi plausibles les uns que les
  autres, `scan` et `report` s’arrêtent jusqu’à ce que vous en choisissiez un
  avec `--collection` ou dans le fichier Inspect. Un fichier JSON qui est un
  objet unique, un scalaire ou un tableau de valeurs simples n’a pas de
  collection et n’est pas transformé en jeu de données d’une ligne. Inspect ne
  cherche des tableaux qu’à travers des clés d’objet, à au plus
  `scan.json.discovery_max_depth` (3) de profondeur, et quand il en trouve plus
  de 100 il n’en sélectionne aucun. Les relations entre collections ne sont pas
  analysées.
- **Inspect sélectionne par la taille, pas par le nom.** Une collection est
  sélectionnée d’elle-même quand c’est le seul tableau d’objets, ou qu’elle a au
  moins 10 fois plus d’éléments que la suivante. Une grande table placée à côté
  d’une table beaucoup plus grande, comme dans un export relationnel, peut être
  sélectionnée sans être celle que vous voulez : vérifiez la `selection` dans le
  fichier Inspect.
- **Inspect observe les premiers enregistrements.** Ses champs, ses profondeurs
  et son imbrication viennent des 1 000 premiers enregistrements de chaque
  collection ; un champ qui apparaît plus tard est trouvé par l’analyse, pas
  listé dans le fichier Inspect. Inspect lit toute la source, donc son temps
  croît avec la taille du fichier ; sur des mesures synthétiques, environ un
  dixième du temps d’une analyse.
- **Pas d’explosion de tableaux, pas de JSONPath.** Les tableaux n’ajoutent
  jamais d’enregistrements (`arrays.mode` vaut `preserve`), et les chemins de
  collection utilisent une syntaxe limitée : des clés depuis la racine, se
  terminant par `[]`.
- **Inspect est pour JSON et JSONL.** `tabalyst inspect` refuse les fichiers CSV.
- **Les rapports JSON montrent les champs scalaires.** Un rapport JSON liste
  les champs contenant des chaînes, des nombres, des booléens ou des nulls ; la
  structure des objets et des tableaux (imbrication, longueur des tableaux)
  n’apparaît que dans les résultats de `tabalyst scan`. Un enregistrement avec
  une valeur manquante n’est compté dans `missing_values` que pour les nulls et
  les valeurs vides, pas pour les champs absents.
- **Entiers JSON.** Les entiers de plus de 4 300 chiffres, la limite de Python,
  rendent un fichier JSON invalide.
- **Un JSON invalide arrête tout.** Une erreur de syntaxe n’importe où dans un
  fichier `.json`, même après les enregistrements qu’Inspect a observés, fait
  échouer l’inspection et l’analyse : Tabalyst ne récupère pas un document
  endommagé. Dans un fichier JSONL, seules les lignes concernées sont exclues.
- **Lignes JSONL.** Une ligne est lue en UTF-8 et analysée en entier, jusqu’à
  `scan.limits.max_line_bytes` (16 Mio, 256 Mio au plus) ; analyser une ligne
  demande environ 7 à 13 fois sa taille en mémoire. Un fichier de texte compressé
  ou non UTF-8 n’est pas lu.
- **Une seule ligne d’en-tête.** Le premier enregistrement est toujours
  l’en-tête.
- **Structure stricte.** Un enregistrement avec trop peu ou trop de champs, ou
  une ligne vide au milieu des données, arrête l’analyse de ce fichier avec une
  erreur. `tabalyst scan` et `tabalyst report` peuvent à la place exclure ces
  enregistrements avec la politique d’erreur `tolerant`
  (`scan.errors.policy`) ; le rapport les liste alors dans son anomalie
  `excluded_records`.
- **Pas de recherche récursive.** `tabalyst report *.csv` lit les fichiers
  correspondants d’un seul dossier ; il ne cherche pas dans les sous-dossiers.
  Il en va de même pour `sample` et `scan`.

## Taille et performance

- **Les lignes en double ont un budget.** Les rapports et les analyses lisent
  le fichier une seule fois en flux, avec une mémoire bornée par les limites
  d’analyse. La détection des lignes en double stocke environ 80 octets par
  ligne distincte, jusqu’à `scan.limits.max_tracked_records` (2 000 000 lignes
  par défaut). Au-delà, les lignes suivantes ne sont comparées qu’à celles
  stockées, et le rapport affiche une borne inférieure comme `≥ 12`. Augmentez
  la limite pour un nombre exact, ou réglez `scan.records.duplicates` sur
  `false` pour ne pas rechercher les doublons.
- **Pas de progression par ligne.** La progression d’un rapport ou d’une
  analyse affiche la part du fichier déjà lue, pas un nombre de lignes.
- **Lots séquentiels.** Plusieurs fichiers sont traités l’un après l’autre, pas
  en parallèle.

## Analyse

- **Les types sont des indications.** Les types détectés décrivent les
  valeurs ; Tabalyst ne convertit jamais les données et ne les valide jamais
  selon des règles métier.
- **Détails des détecteurs absents des rapports.** Le rapport affiche un seul
  type sémantique par colonne, l’interprétation principale de l’analyse, comme
  une énumération, des adresses e-mail ou des codes postaux. La couverture, les
  formats et les preuves de chaque détecteur, ainsi que les variantes de
  normalisation, ne figurent que dans les documents de `tabalyst scan`.
- **Les dates ambiguës restent ambiguës.** Des valeurs comme `02/03/2025` ne
  sont jamais résolues à partir des autres valeurs de la colonne ; définissez
  `scan.detectors.date.ambiguous_order` pour les lire dans un sens donné.
- **Syntaxe uniquement.** Les détecteurs vérifient la forme des valeurs, jamais
  l’existence d’une adresse, d’un numéro ou d’un code.
- **Valeurs rares tardives dans les grandes colonnes.** Dans une colonne de plus
  de `scan.detection.warmup_values` valeurs distinctes (10 000 par défaut), un
  détecteur qui n’a reconnu aucune des premières, ou seulement quelques-unes au
  début (`scan.detection.rare_share`), arrête de tester les autres, sauf environ
  une valeur sur 100. Une adresse e-mail, un numéro de téléphone ou un code rare
  qui n’apparaît que plus tard peut passer inaperçu, et une valeur sensible n’est
  alors pas masquée. Réglez `scan.detection.warmup_values` sur `0` pour tester
  chaque valeur.
- **Valeurs manquantes.** Par défaut, seules les cellules vides ou ne contenant
  que des espaces sont des valeurs manquantes. `NA`, `NULL` ou `NaN` restent du
  texte, sauf si vous les déclarez dans `scan.values.null_markers` dans un
  [fichier de configuration](configuration.md).

## Sortie et interfaces

- **Formats JSON expérimentaux.** Le [profil JSON](json-profile.md), le
  [format d’analyse](scan-format.md) et le [format Inspect](inspect-format.md)
  peuvent changer de manière incompatible d’une version à l’autre. Aucun outil de
  migration n’est fourni : un fichier Inspect d’une autre version est refusé, et
  `tabalyst inspect --force` en écrit un nouveau. Vérifiez `format_version` et
  `format_revision` avant de lire un profil, une analyse ou un fichier Inspect.
- **Les fichiers Inspect vous appartiennent.** `tabalyst scan` et
  `tabalyst report` n’écrivent ni ne modifient jamais le fichier Inspect à côté
  d’une source ; seul `tabalyst inspect` le fait. Une source dont le nom se
  termine par `-inspect.json` ne peut pas être utilisée avant d’être renommée.
- **Commandes susceptibles de changer.** Les commandes et les options peuvent
  changer de manière incompatible tant que Tabalyst est en bêta. Mettez-le à
  jour souvent avec `pip install --upgrade tabalyst` : cette documentation
  décrit la dernière version publiée.
- **Rapport en anglais.** Le rapport HTML n’est disponible qu’en anglais.
- **Données brutes dans les sorties.** Le rapport, le profil JSON et les
  documents d’analyse contiennent des valeurs du fichier source, y compris un
  aperçu des premières lignes dans les rapports. Les valeurs des champs
  sensibles, comme les adresses e-mail et les numéros de téléphone, sont
  masquées par défaut, mais les valeurs de tous les autres champs sont listées.
  Partagez-les comme vous
  partageriez les données.
- **Les motifs sont considérés comme fiables.** Les expressions régulières des
  motifs d’analyse s’exécutent sans délai d’expiration.

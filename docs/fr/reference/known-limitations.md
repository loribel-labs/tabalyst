---
title: Limites connues
description: Ce que Tabalyst ne fait pas encore pendant sa phase alpha, notamment les limites des rapports JSON, la mémoire de la détection des doublons et les formats JSON expérimentaux.
---

Tabalyst est en alpha. Cette page liste ce qu’il ne fait pas encore, pour vous
aider à décider s’il convient à vos données. Une limite est retirée de cette
page lorsqu’une version publiée la lève.

## Entrée

- **CSV et JSON uniquement.** `tabalyst report` et `tabalyst scan` lisent des
  fichiers CSV et JSON ; `tabalyst sample` ne lit que des fichiers CSV. Les
  classeurs Excel, JSON Lines, XML, Parquet et les bases de données ne sont pas
  pris en charge ; exportez-les d’abord en CSV.
- **Les rapports JSON montrent les champs scalaires.** Un rapport JSON liste
  les champs contenant des chaînes, des nombres, des booléens ou des nulls ; la
  structure des objets et des tableaux (imbrication, longueur des tableaux)
  n’apparaît que dans les résultats de `tabalyst scan`. Un enregistrement avec
  une valeur manquante n’est compté dans `missing_values` que pour les nulls et
  les valeurs vides, pas pour les champs absents.
- **Entiers JSON.** Les entiers de plus de 4 300 chiffres, la limite de Python,
  rendent un fichier JSON invalide.
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

- **Les lignes en double utilisent de la mémoire.** Les rapports lisent le
  fichier une seule fois en flux, avec une mémoire bornée par les limites
  d’analyse, sauf pour la détection des lignes en double, qui conserve 16 octets
  par ligne distincte. `tabalyst scan` ne détecte pas les lignes en double.
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
- **Valeurs manquantes.** Par défaut, seules les cellules vides ou ne contenant
  que des espaces sont des valeurs manquantes. `NA`, `NULL` ou `NaN` restent du
  texte, sauf si vous les déclarez dans `scan.values.null_markers` dans un
  [fichier de configuration](configuration.md).

## Sortie et interfaces

- **Formats JSON expérimentaux.** Le [profil JSON](json-profile.md) et le
  [format d’analyse](scan-format.md) peuvent changer de manière incompatible
  d’une version à l’autre. Aucun outil de migration n’est fourni. Vérifiez
  `format_version` et `format_revision` avant de lire un profil ou une analyse.
- **Commandes susceptibles de changer.** Les commandes et les options peuvent
  changer de manière incompatible tant que Tabalyst est en alpha. Mettez-le à
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

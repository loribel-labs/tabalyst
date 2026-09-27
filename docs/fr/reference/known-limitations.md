---
title: Limites connues
description: Ce que Tabalyst ne fait pas encore pendant sa phase alpha, notamment les rapports limités au CSV, le chargement des rapports en mémoire et les formats JSON expérimentaux.
---

Tabalyst est en alpha. Cette page liste ce qu’il ne fait pas encore, pour vous
aider à décider s’il convient à vos données. Une limite est retirée de cette
page lorsqu’une version publiée la lève.

## Entrée

- **CSV et JSON uniquement.** `tabalyst report` et `tabalyst sample` lisent des
  fichiers texte délimités ; `tabalyst scan` lit aussi des fichiers JSON. Les
  classeurs Excel, JSON Lines, XML, Parquet et les bases de données ne sont pas
  pris en charge ; exportez-les d’abord en CSV.
- **Rapports à partir du CSV uniquement.** Un fichier JSON peut être analysé
  avec `tabalyst scan`, mais pas encore transformé en rapport HTML.
- **Entiers JSON.** Les entiers de plus de 4 300 chiffres, la limite de Python,
  rendent un fichier JSON invalide.
- **Une seule ligne d’en-tête.** Le premier enregistrement est toujours
  l’en-tête.
- **Structure stricte.** Un enregistrement avec trop peu ou trop de champs, ou
  une ligne vide au milieu des données, arrête l’analyse de ce fichier avec une
  erreur. `tabalyst scan` peut à la place exclure ces enregistrements avec la
  politique d’erreur `tolerant`.
- **Pas de recherche récursive.** `tabalyst report *.csv` lit les fichiers
  correspondants d’un seul dossier ; il ne cherche pas dans les sous-dossiers.
  Il en va de même pour `sample` et `scan`.

## Taille et performance

- **Les rapports chargent tout le fichier en mémoire.** Les très gros fichiers
  peuvent épuiser la mémoire disponible. `tabalyst scan` et `tabalyst sample`
  lisent les fichiers en flux, avec une mémoire bornée.
- **Pas de progression par ligne pour les rapports.** La progression d’un
  rapport affiche le fichier et la phase en cours (lecture, analyse, rendu,
  écriture), pas un pourcentage de lignes. La progression d’une analyse affiche
  la part du fichier déjà lue.
- **Lots séquentiels.** Plusieurs fichiers sont traités l’un après l’autre, pas
  en parallèle.

## Analyse

- **Les types sont des indications.** Les types détectés décrivent les
  valeurs ; Tabalyst ne convertit jamais les données et ne les valide jamais
  selon des règles métier.
- **Formats de nombres limités dans les rapports.** Les virgules décimales
  (`12,50`) ne sont pas reconnues comme des nombres par le rapport et sont
  traitées comme du texte. `tabalyst scan` les reconnaît.
- **Peu de types sémantiques dans les rapports.** Le rapport ne détecte que les
  énumérations et les dates. `tabalyst scan` détecte aussi les adresses e-mail,
  les URL, les numéros de téléphone (Canada, États-Unis, France), les codes
  postaux canadiens et les codes ZIP, les montants en devise, les pourcentages,
  les quantités, les UUID et les adresses IP, mais le rapport ne les affiche pas
  encore.
- **Syntaxe uniquement.** Les détecteurs vérifient la forme des valeurs, jamais
  l’existence d’une adresse, d’un numéro ou d’un code.
- **Valeurs manquantes.** Par défaut, seules les cellules vides ou ne contenant
  que des espaces sont des valeurs manquantes. `NA`, `NULL` ou `NaN` restent du
  texte, sauf si vous les déclarez dans un
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
- **Données brutes dans les sorties.** Le rapport et le profil JSON contiennent
  des valeurs du fichier source, y compris un aperçu des premières lignes. Un
  document d’analyse masque par défaut les valeurs des champs sensibles, mais
  liste les valeurs de tous les autres champs. Partagez-les comme vous
  partageriez les données.
- **Les motifs sont considérés comme fiables.** Les expressions régulières des
  motifs d’analyse s’exécutent sans délai d’expiration.

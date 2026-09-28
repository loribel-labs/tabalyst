---
title: Glossaire
description: Termes anglais et français utilisés dans la documentation et le rapport de Tabalyst, et les noms qui ne sont jamais traduits.
---

Ce glossaire fixe le vocabulaire de la documentation de Tabalyst. L’anglais est
la langue source ; chaque page en français utilise les termes français
ci-dessous.

## Jamais traduits

Conservez-les exactement tels quels dans toutes les langues :

- les noms de produit `Tabalyst`, `Tabalyst Report`, `Tabalyst CSV Report` et
  `Tabalyst Scan` ;
- les commandes et les options, comme `tabalyst report`, `-o`, `--output-dir`
  ou `--config` ;
- les clés et les valeurs JSON, comme `format_version`, `with_issues` ou
  `mixed` ;
- les noms de fichiers et les chemins, comme `report.json` ou
  `executions.json` ;
- les modules, fonctions et paramètres Python, comme `tabalyst.analyze()`.

## Termes

| Anglais | Français | Signification |
| --- | --- | --- |
| toolkit | boîte à outils | Ce qu’est Tabalyst : un ensemble d’outils pour des données inconnues |
| report | rapport | Le fichier HTML interactif produit par `tabalyst report` |
| profile, JSON profile | profil, profil JSON | Le fichier `report.json` qui décrit un jeu de données |
| column profile | profil de colonne | La partie du profil qui décrit une colonne |
| dataset | jeu de données | Les données tabulaires analysées |
| source file | fichier source | Le fichier CSV fourni à Tabalyst |
| dataset overview | vue d'ensemble du jeu de données | La section du rapport qui résume tout le jeu de données |
| data sample | échantillon de données | Les premières lignes affichées dans le rapport |
| raw preview | aperçu brut | Les valeurs sources avant normalisation |
| missing value | valeur manquante | Une valeur vide ou un marqueur de valeur manquante configuré |
| issue | anomalie | Un problème de qualité des données détecté |
| with issues | avec anomalies | Une colonne avec des valeurs manquantes, des dates ambiguës ou de type inféré `mixed` |
| value normalization | normalisation des valeurs | Le nettoyage appliqué avant l’analyse, comme la suppression des espaces |
| type inference | inférence de type | La façon dont Tabalyst décide du type d’une colonne |
| inferred type | type inféré | Le type déduit des valeurs d’une colonne |
| physical type | type physique | Le type de stockage des valeurs : nombre, date, texte |
| semantic type | type sémantique | La signification d’une colonne, comme une adresse e-mail ou un identifiant |
| date analysis | analyse des dates | La section du rapport sur les colonnes de dates |
| numeric analysis | analyse numérique | La section du rapport sur les colonnes numériques |
| string analysis | analyse des textes | La section du rapport sur les colonnes de texte |
| analysis settings | paramètres d'analyse | La configuration effective utilisée pour un rapport |
| configuration file | fichier de configuration | Le fichier JSON passé avec `--config` |
| delimiter | séparateur | Le caractère qui sépare les champs CSV |
| encoding | encodage | L’encodage des caractères du fichier source |
| execution history | historique d'exécution | Le fichier cumulatif `executions.json` |
| format revision | révision du format | Le numéro `format_revision` du format de profil |
| batch | lot | Plusieurs fichiers sources traités par une seule commande |
| output directory | dossier de sortie | Le dossier indiqué avec `-d` / `--output-dir` |
| alpha | alpha | Stade précoce où les interfaces et les formats peuvent changer |
| scan | analyse | La description complète d’une source écrite par `tabalyst scan` |
| scan document | document d'analyse | Le fichier `.scan.json` écrit par `tabalyst scan` |
| stale scan | analyse périmée | Un document d’analyse dont la source ou les paramètres ont changé depuis son écriture |
| duplicate record | enregistrement en double | Un enregistrement égal à un enregistrement précédent de son jeu de données |
| record | enregistrement | Une ligne CSV ou un élément d’une collection JSON |
| collection | collection | Un tableau JSON dont les éléments sont analysés comme des enregistrements |
| field | champ | Une colonne CSV ou un chemin dans des enregistrements JSON, comme `orders[].amount` |
| detector | détecteur | Une règle qui reconnaît un type de valeur, comme les adresses e-mail ou les dates |
| interpretation | interprétation | Une signification proposée pour un champ par les détecteurs qui reconnaissent ses valeurs |
| sensitive value | valeur sensible | Une valeur qui identifie une personne, comme une adresse e-mail, masquée par défaut |
| mask | masque | Une valeur dont les lettres sont remplacées par `A` ou `a` et les chiffres par `9` |
| measure envelope | enveloppe de mesure | L’enveloppe `status` qui indique si une mesure est complète ou limitée |
| diagnostic | diagnostic | Un événement technique d’une analyse, comme un enregistrement exclu ou une limite atteinte |
| configuration layer | couche de configuration | Un niveau de paramètres : valeurs par défaut, chaque fichier de configuration, puis options |

---
title: Documentation de Tabalyst
description: Tabalyst est une boîte à outils open source et locale qui transforme un fichier CSV en rapport HTML interactif et en profil JSON.
---

Tabalyst est une boîte à outils open source et locale pour comprendre des
données inconnues. Son premier outil, **Tabalyst Report**, analyse un fichier CSV
et produit un rapport HTML interactif et un profil JSON structuré.

```console
pip install --upgrade tabalyst
tabalyst report customers.csv
```

Cette commande crée `customers.html` (le rapport), `customers.json` (le profil)
et `executions.json` (l’historique d’exécution) à côté du fichier CSV. Tout
s’exécute sur votre ordinateur ; aucune donnée n’est envoyée.

La première commande installe Tabalyst, ou le met à jour s’il est déjà
installé. Tabalyst est en alpha et évolue souvent : relancez-la avant chaque
nouvel essai. Les commandes et le format JSON peuvent encore changer d’une
version à l’autre. Cette documentation décrit la dernière version publiée sur
PyPI.

## Pour commencer

- [Installer Tabalyst](how-to/install.md), sous Windows, macOS ou Linux, et
  [le tenir à jour](how-to/install.md#keep-tabalyst-up-to-date).
- [Créer votre premier rapport](tutorials/first-report.md) à partir d’un petit
  fichier CSV.
- [Échantillonner des fichiers CSV](how-to/sample-csv.md) avec une sélection
  first, last, random ou stratified.
- [Analyser des fichiers CSV et JSON](how-to/scan-files.md) pour obtenir une
  description JSON complète de chaque champ.

## Référence

- [Profil JSON](reference/json-profile.md) : la structure du fichier `.json`
  généré.
- [Configuration](reference/configuration.md) : le fichier de configuration
  JSON.
- [Historique d’exécution](reference/execution-history.md) : le fichier
  `executions.json`.
- [Journal des modifications du format de profil](reference/profile-format-changelog.md).
- [Format d’analyse](reference/scan-format.md) : la structure du fichier
  `.scan.json`, et son [journal des modifications](reference/scan-format-changelog.md).
- [Limites connues](reference/known-limitations.md) : ce que Tabalyst ne fait
  pas encore.
- [Glossaire](reference/glossary.md) : les termes anglais et français.

---
title: Documentation de Tabalyst
description: Présentation en français de Tabalyst 0.5.0, ses outils et ses entrées et sorties, avec des liens vers la documentation détaillée, publiée uniquement en anglais pendant la bêta.
---

Tabalyst est une boîte à outils open source, locale d'abord, pour comprendre des
données structurées inconnues. Installez-la une fois et utilisez ses outils en
ligne de commande ou depuis Python :

- **[Tabalyst Report](https://docs.tabalyst.com/report/)** transforme un fichier
  CSV, JSON ou JSONL en rapport HTML interactif et en profil JSON.
- **[Tabalyst Scan](https://docs.tabalyst.com/scan/)** décrit chaque champ d'un
  fichier dans un seul document JSON.
- **[Tabalyst Inspect](https://docs.tabalyst.com/inspect/)** trouve comment lire
  un fichier JSON ou JSONL.
- **[Tabalyst Sample](https://docs.tabalyst.com/sample/)** crée des fichiers CSV
  plus petits.

```console
pip install --upgrade tabalyst
tabalyst report clients.csv
```

Cette commande crée `clients.html` (le rapport), `clients.json` (le profil) et
`executions.json` (l'historique des exécutions) à côté du fichier CSV. Tout
s'exécute sur votre ordinateur : aucune donnée n'est envoyée ailleurs.

Tabalyst est en bêta et évolue souvent : relancez la première commande avant
chaque nouveau test. Les commandes et les formats JSON peuvent encore changer
d'une version à l'autre.

**Pendant la bêta, la documentation détaillée est publiée uniquement en
anglais.** Les liens ci-dessous mènent aux pages anglaises.

## Pour commencer

- [Install Tabalyst](https://docs.tabalyst.com/install/) : installer ou mettre à
  jour Tabalyst.
- [Create your first report](https://docs.tabalyst.com/report/getting-started/) :
  un premier rapport pas à pas.
- [Examples and demos](https://docs.tabalyst.com/examples/) : un rapport terminé
  à parcourir.

## Référence

- [Command line (CLI)](https://docs.tabalyst.com/reference/cli/) : commandes et
  options.
- [Python API](https://docs.tabalyst.com/reference/python-api/) : utiliser
  Tabalyst depuis Python.
- [Configuration](https://docs.tabalyst.com/reference/configuration/) :
  délimiteur, encodage et détection.
- [Known limitations](https://docs.tabalyst.com/about/limitations/) : ce que
  Tabalyst ne fait pas encore.

Le site tabalyst.com est disponible en français : [tabalyst.com/fr/](https://tabalyst.com/fr/).

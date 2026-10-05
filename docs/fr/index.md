---
title: Documentation de Tabalyst
description: Présentation en français de Tabalyst 0.6.1, ses outils et ses entrées et sorties, avec des liens vers la documentation détaillée, publiée uniquement en anglais pendant la bêta.
---

Tabalyst est une boîte à outils open source, locale d'abord, pour comprendre des
données structurées inconnues. Installez-la une fois et utilisez ses outils en
ligne de commande ou depuis Python :

- **[Tabalyst Report](https://docs.tabalyst.com/report/)** transforme un fichier
  CSV, JSON, JSONL ou Excel en rapport HTML interactif et en profil JSON.
- **[Tabalyst Scan](https://docs.tabalyst.com/scan/)** décrit chaque champ d'un
  fichier dans un seul document JSON.
- **[Tabalyst Inspect](https://docs.tabalyst.com/inspect/)** trouve comment lire
  un fichier JSON, JSONL ou Excel.
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

- [Install Tabalyst](https://docs.tabalyst.com/get-started/install/) : installer ou mettre à
  jour Tabalyst.
- [Create your first report](https://docs.tabalyst.com/get-started/first-report/) :
  un premier rapport pas à pas.
- [Examples and demos](https://docs.tabalyst.com/get-started/examples/) : un rapport terminé
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

## Pour les assistants IA

Pour être aidé par un assistant IA, collez ce prompt dans un chat capable de
lire des pages web (la documentation est en anglais) :

```text
Read the complete Tabalyst documentation at
https://docs.tabalyst.com/llms-full.txt, then help me use Tabalyst well.
Ask me what my data looks like and what I want to learn from it, then suggest
the right commands and options. Base your answers only on that documentation.
```

Si l'assistant ne peut pas ouvrir de liens, collez plutôt le contenu du fichier.
Le site publie aussi [llms.txt](https://docs.tabalyst.com/llms.txt), la liste
des pages avec une description d'une ligne.

Le site tabalyst.com est disponible en français : [tabalyst.com/fr/](https://tabalyst.com/fr/).

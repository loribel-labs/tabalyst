---
title: Créer votre premier rapport
description: Tutoriel qui profile un fichier CSV de cinq lignes avec tabalyst report, ouvre le rapport HTML et lit les problèmes trouvés par Tabalyst.
---

Dans ce tutoriel, vous créez un petit fichier CSV, exécutez `tabalyst report`
dessus, ouvrez le rapport HTML et lisez les problèmes que Tabalyst détecte. Il
prend environ cinq minutes. Vous avez besoin de Tabalyst installé et à jour :
voir [Installer Tabalyst](../how-to/install.md). S’il est déjà installé,
mettez-le d’abord à jour, car les sorties montrées ici viennent de la dernière
version :

```console
pip install --upgrade tabalyst
```

## 1. Créer un fichier CSV

Dans votre dossier de travail, créez un fichier nommé `orders.csv` avec ce
contenu :

```text
id,name,amount,joined,active,notes
001,Alice,12.50,2026-01-01,true,First order
002,Bob,,2026-02-01,false,
003,Charlie,25.00,2026-03-01,true,"Two items, one order"
003,Charlie,25.00,2026-03-01,true,"Two items, one order"
004,Dana,not available,2026-04-01,true,Pending review
```

Ce fichier contient des problèmes volontaires : une ligne répétée, des cellules
vides et une valeur texte dans une colonne numérique.

## 2. Exécuter le rapport

```console
tabalyst report orders.csv
```

Tabalyst affiche un résumé et l’emplacement du rapport :

```text
Analyzed 5 rows and 6 columns.
Report: C:\work\orders.html
```

Trois fichiers se trouvent maintenant à côté de `orders.csv` :

```text
orders.csv
orders.html        le rapport interactif
orders.json        le profil JSON, pour les scripts et les autres outils
executions.json    l’historique des exécutions dans ce dossier
```

## 3. Ouvrir le rapport

Ouvrez `orders.html` dans votre navigateur, en double-cliquant dessus ou depuis
le terminal :

```console
start orders.html      # Windows
open orders.html       # macOS
xdg-open orders.html   # Linux
```

Le rapport fonctionne hors ligne. Ajoutez `--details` à la commande pour créer
une page HTML indépendante par colonne sous `orders/`. Le tableau **Columns**
renvoie alors vers ces pages. Dans chaque page de colonne, **Overview** montre
directement les valeurs stockées avec leurs effectifs et tous les formats
détectés. Les fichiers contiennent des valeurs de vos données : partagez-les en
conséquence.

## 4. Lire ce que Tabalyst a trouvé

Le rapport est organisé en sections : **Dataset overview**, **Columns**,
**Transformations**, **Numeric analysis**, **Date analysis**,
**String analysis**, **Detectors and formats**, **Data sample** et
**Analysis settings**. Une section **Limits and diagnostics** apparaît quand
l’analyse a arrêté une mesure à une limite ou enregistré un diagnostic.

Dans **Dataset overview**, la carte **Quality observations** liste les
problèmes de `orders.csv`. Les avertissements viennent en premier ; les deux
observations sur les espaces sont informatives et toujours listées, ici avec un
effectif de 0.

| Problème | Où | Pourquoi |
| --- | --- | --- |
| 1 ligne en double | Enregistrement 4 | Il répète exactement l’enregistrement 3 |
| 2 cellules manquantes | `amount` et `notes`, enregistrement 2 | Les cellules sont vides |
| 1 colonne de types mixtes | `amount` | Trois nombres et le texte `not available` |

Regardez aussi les colonnes :

- `id` est détecté comme **texte**, pas comme entier : des valeurs comme `001`
  ont des zéros en tête, donc Tabalyst les garde comme texte.
- `joined` est détecté comme une **date** au format `YYYY-MM-DD`.
- `active` est détecté comme un **booléen** (`true` / `false`).

Les types sont des indications descriptives : Tabalyst ne modifie jamais votre
fichier CSV.

## 5. Le relancer

Exécutez la même commande une seconde fois :

```console
tabalyst report orders.csv
```

Tabalyst refuse de remplacer le rapport existant :

```text
Error: Report output already exists. Use --force to replace it:
  orders.html
  orders.json
```

Ajoutez `--force` quand le remplacement du rapport est voulu :

```console
tabalyst report orders.csv --force
```

`executions.json` n’est pas remplacé : chaque exécution y ajoute une entrée.

## Ce que vous avez appris

- `tabalyst report FILE.csv` crée un rapport HTML et un profil JSON à côté du
  fichier source.
- Le rapport montre les types détectés, les valeurs manquantes, les doublons et
  d’autres problèmes, sans modifier vos données.
- Les rapports existants sont protégés sauf si vous passez `--force`.

## Étapes suivantes

- Choisissez le nom de sortie avec `-o`, ou traitez plusieurs fichiers à la
  fois avec `tabalyst report *.csv -d reports/`. Exécutez
  `tabalyst report --help` pour toutes les options.
- Utilisez le [profil JSON](../reference/json-profile.md) dans vos propres
  scripts.
- Adaptez l’analyse avec un
  [fichier de configuration](../reference/configuration.md).

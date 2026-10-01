---
title: Analyser des fichiers CSV et JSON
description: Décrivez chaque champ d’un fichier CSV, JSON ou JSONL dans un document d’analyse JSON complet avec tabalyst scan, en une seule lecture en flux.
---

Utilisez `tabalyst scan` pour décrire un fichier CSV, JSON ou JSONL dans un
document JSON : chaque champ, sa présence, ses valeurs, ses statistiques, ses formats et
les significations détectées, comme des adresses e-mail, des dates ou des
montants.

```console
tabalyst scan customers.csv
```

Sans `-o` ni `-d`, quel que soit le format, cette commande conserve un
`scan.json` réutilisable dans le stockage local de Tabalyst, sous
`workspaces/local/scans/` dans un dossier déterminé par le chemin de la source. Elle ne crée pas de base DuckDB. Définissez
`TABALYST_HOME` pour choisir la racine de ce stockage. Le fichier source n’est
jamais modifié. **Tabalyst Scan** lit tout le fichier en une seule
lecture en flux : la mémoire utilisée dépend des limites configurées, pas du
nombre d’enregistrements. La structure du résultat est décrite dans la
[référence du format d’analyse](../reference/scan-format.md).

## Analyser des fichiers JSON

Les fichiers se terminant par `.json` sont lus comme du JSON, ceux qui se
terminent par `.jsonl` ou `.ndjson` (quelle que soit la casse) comme du JSONL,
et tous les autres fichiers comme du CSV.

```console
tabalyst scan orders.json
```

Une analyse porte sur une **collection** d’enregistrements : un tableau de
premier niveau, ou un tableau dans un objet de premier niveau, comme
`customers` dans `{"customers": [...]}`. Les tableaux situés dans des
enregistrements, comme les `orders` de chaque client, restent des champs de
leurs enregistrements. Tabalyst trouve la collection avec
[Inspect](inspect-json-files.md), qui s’exécute de lui-même quand la source n’a
pas de fichier Inspect, et conserve le choix dans le fichier Inspect à côté de
la source quand vous avez lancé `tabalyst inspect`. Quand plusieurs tableaux
sont aussi plausibles les uns que les autres, l’analyse s’arrête avec le code de
sortie `2` et les liste ; choisissez-en un dans le fichier Inspect, ou passez
`--collection` :

```console
tabalyst scan orders.json --collection "$.customers[]"
```

Répétez `--collection` pour analyser plusieurs collections en une seule analyse,
à raison d’un jeu de données chacune :

```console
tabalyst scan orders.json --collection "$.customers[]" --collection "$.products[]"
```

Un chemin de collection commence par `$`, la racine du document, et se termine
par `[]`, les éléments d’un tableau. Les champs imbriqués s’écrivent avec des
points, comme `orders[].amount`. `--collection` l’emporte sur le fichier
Inspect. Une collection définie dans un fichier Inspect qui n’existe plus dans
la source arrête l’analyse avec le code de sortie `2` ; une collection de
`--collection` ou d’un `--config` introuvable est un avertissement, avec un jeu
de données vide.

Une source JSONL a un seul jeu de données, `$[]` : ses enregistrements sont les
lignes. Une ligne invalide, ou qui n’est pas un objet, est exclue et comptée
avec la politique `tolerant` par défaut, et l’analyse est `partial`.

## Choisir l’emplacement des sorties

Utilisez `-o` pour exporter un document d’analyse autonome sous un nom complet
de fichier lorsque vous analysez une
seule source. Le nom doit se terminer par `.json` :

```console
tabalyst scan customers.csv -o scans/customers.json
```

Les caractères génériques sont résolus par Tabalyst, y compris dans les shells
qui ne les développent pas. Utilisez `-d` pour exporter les analyses d’une ou de
plusieurs sources dans un dossier :

```console
tabalyst scan data/*.csv data/*.json -d scans/
```

Les sorties sont nommées `customers.scan.json`, `orders.scan.json`, et ainsi de
suite. `-o` n’accepte qu’une seule entrée résolue ; `-o` et `-d` ne peuvent pas
être combinés. Les motifs récursifs `**` ne sont pas pris en charge.

## Comportement sûr des lots

Avant d’écrire des analyses autonomes, Tabalyst résout chaque entrée et chaque sortie, et rejette
tout le lot lorsque :

- deux sources correspondent à la même sortie, comme `data.csv` et `data.json` ;
- une sortie remplacerait une entrée ou un fichier de configuration ;
- une sortie existe déjà et `--force` n’est pas indiqué.

Chaque résultat est écrit dans un fichier temporaire du dossier cible, puis mis
en place : une analyse interrompue ne laisse jamais de résultat partiel.
Lorsqu’une source échoue, par exemple avec un JSON invalide, Tabalyst signale
l’erreur, continue avec les autres sources et renvoie un code de sortie non nul
à la fin.

Un motif comme `data/*.json` correspond aussi à des résultats autonomes précédents comme
`data/orders.scan.json`. Écrivez les analyses dans un autre dossier avec `-d`
pour les séparer des sources. Les motifs ignorent les fichiers Inspect, nommés
`*-inspect.json`, et un fichier Inspect donné en entrée est refusé. Les jokers sont
résolus par Tabalyst, y compris sous Windows : le même motif les ignore aussi.

## Configurer l’analyse

Les paramètres d’analyse se trouvent dans la section `scan` d’un
[fichier de configuration](../reference/configuration.md#scan-settings) JSON :

```json
{
  "scan": {
    "values": {"null_markers": ["N/A", "NULL"]},
    "errors": {"policy": "tolerant"},
    "exposure": {"sensitive_values": "hide"}
  }
}
```

```console
tabalyst scan customers.csv --config tabalyst.json
```

Répétez `--config` pour combiner plusieurs fichiers : les fichiers suivants
remplacent les précédents. `--delimiter`, `--encoding` et `--collection`
remplacent tous les fichiers. Les paramètres inconnus sont des erreurs : un nom
mal orthographié ne passe jamais inaperçu.

Par défaut, le séparateur CSV est la virgule et l’encodage accepte l’UTF-8 avec
ou sans marque d’ordre des octets :

```console
tabalyst scan data.csv --delimiter ";" --encoding cp1252
```

## Erreurs et analyses partielles

Par défaut, un enregistrement CSV avec un mauvais nombre de champs, ou un objet
JSON avec une clé en double, arrête l’analyse de ce fichier avec une erreur. Un
fichier JSONL est tolérant par défaut : une ligne qui n’est pas du JSON valide
ou pas un objet est exclue. Avec `"errors": {"policy": "tolerant"}`, ces
enregistrements sont exclus et comptés, et l’analyse se termine avec le statut
`partial` ; `"strict"` s’arrête au premier. La commande réussit alors et
affiche un avertissement :

```text
Warning [data.csv]: partial scan, 2 records excluded (width_mismatch: 2).
```

Codes de sortie : `0` en cas de succès, y compris pour les analyses partielles ;
`2` pour les erreurs de configuration ; `4` pour les entrées illisibles ou
invalides ; `1` pour les autres échecs, comme une sortie existante sans
`--force`.

## Valeurs sensibles

Les champs contenant des adresses e-mail, des numéros de téléphone ou des
adresses IP sont sensibles. Par défaut, leurs valeurs sont masquées dans le
résultat : les lettres deviennent `A` ou `a` et les chiffres `9`, si bien que
`jane@example.com` apparaît comme `aaaa@aaaaaaa.aaa`. Les comptages et les
formats restent exacts. Réglez `exposure.sensitive_values` sur `hide` pour
supprimer ces valeurs, ou sur `show` pour les conserver. Les valeurs des autres
champs sont toujours affichées : partagez une analyse comme vous partageriez
les données.

## Fichiers volumineux

Les fichiers de 16 Mio ou plus sont analysés par plusieurs processus : Tabalyst
lit le fichier une seule fois et confie les valeurs de chaque champ à un
processus de travail, un par processeur disponible, au plus 8. Le document
d’analyse est le même quel que soit le nombre de processus. Choisissez ce nombre
avec `--workers`, ou gardez l’analyse dans un seul processus avec `--workers 1`,
par exemple sur une machine partagée :

```console
tabalyst scan big.csv --workers 4
```

La mémoire reste bornée par les limites d’analyse dans chaque processus.
`tabalyst report` accepte aussi `--workers`, sauf avec `--scan`, qui ne lit pas
la source.

## Progression et messages

Les terminaux interactifs affichent le fichier et la part déjà lue :

```text
[2/8] orders.json - Reading 42%
```

La progression et les messages utilisent la sortie d’erreur standard. La
progression est désactivée hors d’un terminal et avec `--no-progress` ou
`--quiet`. `--verbose` ajoute le format détecté, l’encodage, le séparateur, le
statut et le nombre de diagnostics.

<a id="report-from-a-scan"></a>

## Rapport à partir d’une analyse

`tabalyst report customers.csv` utilise l’analyse enregistrée, tout comme un
rapport sur un fichier JSON ou JSONL. Si elle n’existe pas, il la crée.
L’analyse est réutilisée si le contenu de la source n’a pas changé, si les
paramètres d’analyse effectifs correspondent et si la même version de Tabalyst
l’a écrite. Pour un fichier JSON, les paramètres incluent la collection : modifier
`config.structure.dataset_path` dans le [fichier Inspect](inspect-json-files.md)
déclenche donc une nouvelle analyse. Si la source a changé, Tabalyst remplace
`scan.json` de façon atomique. Les projets DuckDB créés par 0.4.3 restent
intacts. Avant de réutiliser une analyse, Report vérifie l’empreinte SHA-256 de
la source, quelles que soient sa taille et sa date de modification. Si aucun
paramètre d’analyse n’est demandé, Report reprend ceux de l’analyse existante.

Générez le rapport HTML à partir d’un document d’analyse autonome au lieu de relire la
source :

```console
tabalyst report --scan customers.scan.json
```

Cette commande écrit `customers.html` et `customers.json` à côté du document
d’analyse, nommés d’après la source qu’il enregistre ; une source JSON
`orders.json` donne `orders.report.html`. Le rapport est celui qu’écrit
`tabalyst report customers.csv` avec les mêmes paramètres d’analyse, car le
document d’analyse contient tout ce dont il a besoin, y compris les lignes en
double et l’aperçu. `-o`, `-d`, `--force` et les caractères génériques
fonctionnent comme pour les sources :

```console
tabalyst report --scan scans/*.scan.json -d reports/
```

Tabalyst refuse une analyse qui ne décrit plus sa source. Il cherche la source
à côté du document d’analyse, sous le nom enregistré par l’analyse :

- une source d’une autre taille, ou dont le contenu a changé (comparé par
  SHA-256, quelle que soit sa date de modification), est une erreur : analysez-la
  de nouveau ;
- une source absente à côté du document d’analyse est acceptée, car l’analyse
  se suffit à elle-même, avec un avertissement indiquant qu’elle n’a pas été
  vérifiée. C’est le cas des analyses écrites avec `-d` dans un autre dossier ;
- une analyse écrite par une autre version de Tabalyst est signalée par un
  avertissement ;
- pour une source JSON ou JSONL, un fichier Inspect à côté de la source qui
  demande des paramètres différents de ceux de l’analyse, ou qui est illisible,
  est signalé par un avertissement. Le rapport suit toujours le document
  d’analyse.

Le rapport utilise les paramètres d’analyse enregistrés dans le document. Les
fichiers de configuration passés avec `--config` donnent les paramètres de
présentation ; les paramètres donnés dans leur objet `scan` doivent avoir les
valeurs enregistrées dans le document, sinon le rapport s’arrête avec le code
de sortie `2`. Les paramètres qu’ils ne donnent pas, comme un `--delimiter`
passé à `tabalyst scan`, sont repris du document. `--delimiter` et `--encoding`
ne peuvent pas être utilisés avec `--scan`. Un document illisible, ou écrit
par une autre révision du format, échoue sans arrêter les autres rapports du
lot ; analysez de nouveau sa source.

## API Python

```python
import tabalyst

result = tabalyst.scan("orders.json")
print(result.scope.records_analyzed)

batch = tabalyst.generate_scans(["data/*.csv"], output_dir="scans")
reports = tabalyst.generate_reports(["scans/*.scan.json"], from_scan=True)
```

`tabalyst.scan()` lit une source et renvoie le résultat sans rien écrire ;
`result.model_dump(mode="json")` donne le document. Elle travaille au niveau du
moteur : elle ne lit pas de fichier Inspect et, pour un fichier JSON sans
paramètre `json.collections`, découvre comme collection chaque tableau
accessible à travers des objets, plus le document lui-même comme jeu de données
`$`. Utilisez `tabalyst.generate_scans()` ou `tabalyst.generate_reports()` pour
appliquer Inspect. Passez `config=tabalyst.ScanConfig(...)` pour modifier les
paramètres, et `workers=` pour choisir le nombre de processus de travail comme
le fait `--workers`.
`tabalyst.generate_scans()` écrit par défaut des documents d’analyse autonomes
et renvoie le plan, les succès et les échecs. Passez `project_storage=True`
pour utiliser le stockage d’analyses sans DuckDB de la commande pour les CSV.
`tabalyst.generate_reports(..., from_scan=True)` génère des rapports à partir
de documents d’analyse, comme `tabalyst report --scan`.

## Cache du projet

Inspectez ou supprimez les dossiers de cache de requêtes jetables des projets
DuckDB existants, pour tous les projets ou pour un seul fichier CSV :

```console
tabalyst cache info
tabalyst cache info customers.csv
tabalyst cache clean
tabalyst cache clean customers.csv
```

`info` indique le nombre de dossiers gérés et leur taille logique en octets,
ainsi que les entrées que Tabalyst ne peut pas gérer. `clean` supprime
uniquement les dossiers de cache jetables dont Tabalyst connaît la propriété ;
il conserve le scan et la base de données du projet sélectionné. Un lecteur
actif empêche le nettoyage jusqu’à sa fermeture. Les analyses et rapports
ordinaires ne créent pas ces caches.

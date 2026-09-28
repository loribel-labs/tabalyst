---
title: Analyser des fichiers CSV et JSON
description: Décrivez chaque champ d’un fichier CSV ou JSON dans un document d’analyse JSON complet avec tabalyst scan, en une seule lecture en flux.
---

Utilisez `tabalyst scan` pour décrire un fichier CSV ou JSON dans un document
JSON : chaque champ, sa présence, ses valeurs, ses statistiques, ses formats et
les significations détectées, comme des adresses e-mail, des dates ou des
montants.

```console
tabalyst scan customers.csv
```

Cette commande crée `customers.scan.json` à côté de `customers.csv`. Le fichier
source n’est jamais modifié. **Tabalyst Scan** lit tout le fichier en une seule
lecture en flux : la mémoire utilisée dépend des limites configurées, pas du
nombre d’enregistrements. La structure du résultat est décrite dans la
[référence du format d’analyse](../reference/scan-format.md).

## Analyser des fichiers JSON

Les fichiers se terminant par `.json` sont lus comme du JSON ; tous les autres
fichiers sont lus comme du CSV.

```console
tabalyst scan orders.json
```

Par défaut, Tabalyst trouve lui-même les enregistrements. Un tableau de premier
niveau est une collection d’enregistrements. Un objet de premier niveau est un
enregistrement document, et chaque tableau atteignable depuis cet objet à
travers des objets, sur trois niveaux au plus, est aussi une collection, comme
`customers` dans `{"customers": [...]}`. Les tableaux situés dans des
enregistrements, comme les `orders` de chaque client, restent des champs de
leurs enregistrements. Nommez les collections explicitement avec
`--collection`, répété pour en indiquer plusieurs :

```console
tabalyst scan orders.json --collection "$.customers[]" --collection "$.products[]"
```

Un chemin de collection commence par `$`, la racine du document, et se termine
par `[]`, les éléments d’un tableau. Les champs imbriqués s’écrivent avec des
points, comme `orders[].amount`. Une collection introuvable est signalée par un
avertissement, avec un jeu de données vide.

## Choisir l’emplacement des sorties

Utilisez `-o` pour le nom complet du fichier de sortie lorsque vous analysez une
seule source. Le nom doit se terminer par `.json` :

```console
tabalyst scan customers.csv -o scans/customers.json
```

Les caractères génériques sont résolus par Tabalyst, y compris dans les shells
qui ne les développent pas. Utilisez `-d` pour placer les analyses d’une ou de
plusieurs sources dans un dossier :

```console
tabalyst scan data/*.csv data/*.json -d scans/
```

Les sorties sont nommées `customers.scan.json`, `orders.scan.json`, et ainsi de
suite. `-o` n’accepte qu’une seule entrée résolue ; `-o` et `-d` ne peuvent pas
être combinés. Les motifs récursifs `**` ne sont pas pris en charge.

## Comportement sûr des lots

Avant d’analyser, Tabalyst résout chaque entrée et chaque sortie, et rejette
tout le lot lorsque :

- deux sources correspondent à la même sortie, comme `data.csv` et `data.json` ;
- une sortie remplacerait une entrée ou un fichier de configuration ;
- une sortie existe déjà et `--force` n’est pas indiqué.

Chaque résultat est écrit dans un fichier temporaire du dossier cible, puis mis
en place : une analyse interrompue ne laisse jamais de résultat partiel.
Lorsqu’une source échoue, par exemple avec un JSON invalide, Tabalyst signale
l’erreur, continue avec les autres sources et renvoie un code de sortie non nul
à la fin.

Un motif comme `data/*.json` correspond aussi à des résultats précédents comme
`data/orders.scan.json`. Écrivez les analyses dans un autre dossier avec `-d`
pour les séparer des sources.

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
JSON avec une clé en double, arrête l’analyse de ce fichier avec une erreur.
Avec `"errors": {"policy": "tolerant"}`, ces enregistrements sont exclus et
comptés, et l’analyse se termine avec le statut `partial`. La commande réussit
alors et affiche un avertissement :

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

Générez le rapport HTML à partir d’un document d’analyse au lieu de relire la
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
  SHA-256 quand sa date de modification a changé), est une erreur : analysez-la
  de nouveau ;
- une source absente à côté du document d’analyse est acceptée, car l’analyse
  se suffit à elle-même, avec un avertissement indiquant qu’elle n’a pas été
  vérifiée. C’est le cas des analyses écrites avec `-d` dans un autre dossier.

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
`result.model_dump(mode="json")` donne le document. Passez
`config=tabalyst.ScanConfig(...)` pour modifier les paramètres.
`tabalyst.generate_scans()` fait la même chose que la commande et renvoie le
plan, les succès et les échecs.
`tabalyst.generate_reports(..., from_scan=True)` génère des rapports à partir
de documents d’analyse, comme `tabalyst report --scan`.

---
title: Échantillonner des fichiers CSV
description: Créez des échantillons CSV plus petits avec les méthodes first, last, random ou stratified de Tabalyst.
---

Utilisez `tabalyst sample` pour créer un CSV plus petit sans modifier le fichier
source. Choisissez exactement une option de taille : `--rows` pour un nombre
fixe ou `--percent` pour un pourcentage.

```console
tabalyst sample customers.csv --sample-method random --rows 1000
```

Cette commande crée `customers.sample.csv` à côté de `customers.csv`. Le fichier
de sortie conserve l’en-tête, l’ordre des colonnes, les valeurs brutes et
l’encodage configuré. Les fichiers existants ne sont remplacés qu’avec
`--force`; le fichier source ne peut jamais être écrasé.

## Choisir une méthode

Conservez les premiers ou les derniers enregistrements :

```console
tabalyst sample customers.csv --sample-method first --rows 1000
tabalyst sample customers.csv --sample-method last --rows 1000
```

Sélectionnez des enregistrements uniformément dans tout le fichier. Ajoutez
`--seed` lorsqu’une autre exécution doit sélectionner les mêmes enregistrements :

```console
tabalyst sample customers.csv --sample-method random --percent 5 --seed 42
```

Préservez approximativement la distribution d’un champ avec un échantillonnage
stratifié proportionnel. Les valeurs vides forment leur propre strate :

```console
tabalyst sample customers.csv --sample-method stratified --field province --rows 1000 --seed 42
```

Les pourcentages sont arrondis au nombre entier supérieur. Un échantillon de
100 % contient tous les enregistrements. Un CSV qui ne contient qu’un en-tête
produit donc une sortie qui ne contient que cet en-tête à 100 %.

## Choisir les emplacements de sortie

Utilisez `-o` pour donner le nom complet du fichier de sortie d’une seule source :

```console
tabalyst sample customers.csv --sample-method first --rows 100 -o test.csv
```

Tabalyst résout les wildcards, même dans les interpréteurs de commandes qui ne
le font pas. Utilisez `-d` pour placer les échantillons d’une ou plusieurs
sources dans un dossier :

```console
tabalyst sample *.csv --sample-method random --percent 5 -d samples/
```

Les sorties se nomment `customers.sample.csv`, `orders.sample.csv`, etc. `-o`
n’accepte qu’une seule source résolue; `-o` et `-d` ne peuvent pas être combinés.
Les motifs récursifs `**` ne sont pas pris en charge.

## Lire d’autres formats CSV

Le séparateur par défaut est la virgule et l’encodage par défaut accepte UTF-8
avec ou sans marque d’ordre des octets. Modifiez ces réglages au besoin :

```console
tabalyst sample data.csv --sample-method random --rows 100 --delimiter ";" --encoding cp1252
```

`--config` lit la même configuration JSON stricte que `tabalyst report`;
`--delimiter` et `--encoding` remplacent ses réglages CSV.

L’échantillonnage valide l’en-tête, les guillemets et le nombre de champs de
chaque enregistrement CSV. Sa mémoire est bornée : la méthode `random` ne garde
que les lignes demandées, tandis que `stratified` conserve aussi un compteur par
valeur distincte du champ.

# Tabalyst - Packaging Python et déploiement PyPI

## Objectif

Tabalyst est distribué sur [PyPI](https://pypi.org/project/tabalyst/) comme
package Python officiel sous le nom `tabalyst`.

Le package permet deux modes d'utilisation :

* comme librairie Python avec l'API publique `tabalyst.analyze()`
* comme application CLI avec la commande `tabalyst`

L'installation utilisateur standard se fait depuis PyPI :

```console
pip install tabalyst
```

Le dépôt source officiel est `loribel-labs/tabalyst`.

## Architecture générale

Le code Python distribuable se trouve dans le layout `src/`.

Le package importable est `tabalyst`.

La configuration du package est centralisée dans `pyproject.toml`.

Le projet utilise actuellement setuptools comme backend de build. Ce choix est volontairement conservé puisque le projet était déjà correctement configuré et qu'aucune migration n'était nécessaire pour la publication sur PyPI.

La CLI et l'utilisation comme librairie utilisent le même moteur Tabalyst.

La CLI constitue uniquement une interface au-dessus de l'API publique et ne possède pas de moteur d'analyse indépendant.

## API publique

Le principal point d'entrée Python est `tabalyst.analyze()`.

Cette fonction centralise notamment :

* la résolution de la configuration
* la lecture du CSV
* l'analyse Tabalyst
* la production du JSON canonique
* la génération du rapport HTML
* la mise à jour du journal `executions.json`

L'objectif est d'éviter que les utilisateurs dépendent directement de la structure interne du package.

## Interface CLI

L'installation du package crée la commande `tabalyst`.

La syntaxe principale utilise la commande `report`, un fichier source et une
sortie HTML explicite.

```console
tabalyst report data.csv -o reports/report.html
```

Le même fonctionnement est également accessible avec `python -m tabalyst`.

Les anciennes syntaxes alpha ne sont pas conservées. La CLI peut évoluer de
manière incompatible tant que le produit reste en phase alpha.

## Fichiers produits

Une analyse génère normalement un rapport HTML et un JSON utilisant le même nom de base.

Par exemple, un rapport nommé `report.html` produit également `report.json`.

Le même dossier contient également `executions.json`.

Contrairement aux deux fichiers précédents, `executions.json` est cumulatif. Il contient l'historique des analyses effectuées dans le dossier.

Plusieurs rapports peuvent donc partager le même journal `executions.json`.

Le champ `schema_version` de ce fichier représente la version du format du journal. Il est indépendant de la version de Tabalyst enregistrée dans chaque exécution.

## Configuration de l'analyse

Tabalyst peut recevoir certains paramètres directement depuis l'API ou la CLI, notamment le séparateur et l'encoding.

Une configuration JSON peut également être fournie.

La priorité de configuration est toujours :

1. valeur explicitement fournie par l'utilisateur
2. valeur provenant du fichier de configuration JSON
3. valeur par défaut de Tabalyst

Cette résolution est centralisée afin que la CLI et l'API Python utilisent exactement le même comportement.

Les valeurs par défaut actuelles sont notamment un séparateur virgule et l'encoding `utf-8-sig`.

## Version du package

La version officielle du package est définie dans `pyproject.toml` et doit être
unique pour chaque publication PyPI.

Cette valeur constitue la source de vérité.

`tabalyst.__version__` récupère la version installée à partir des métadonnées du
package afin d'éviter de maintenir manuellement le numéro de version à plusieurs
endroits. Depuis une copie de développement non installée, Tabalyst peut aussi
lire cette version depuis le `pyproject.toml` du dépôt.

Le projet utilise actuellement une convention de versionnement de type :

`0.1.0` pour une version fonctionnelle initiale ;

`0.1.1`, `0.1.2`, etc. pour des corrections compatibles ;

`0.2.0` pour une évolution fonctionnelle plus importante ;

`1.0.0` lorsque l'API publique sera considérée comme suffisamment stable.

## Build du package

Le processus de build produit deux distributions Python standards :

* un wheel
* une source distribution, ou sdist

Les fichiers sont générés dans le dossier `dist/`.

Ces fichiers sont des artefacts de build et ne doivent pas être versionnés dans Git.

Le package inclut également les ressources nécessaires à la génération du rapport, notamment les templates et ressources statiques utilisées par Tabalyst.

Ces ressources doivent fonctionner depuis le package installé, sans dépendre de chemins relatifs au dépôt Git.

## Tests du package

La validation ne consiste pas uniquement à exécuter les tests du code source.

Le wheel construit doit également être installé et exécuté dans un environnement indépendant du dépôt.

Cette vérification permet notamment de détecter :

* les ressources oubliées dans le package
* les imports qui fonctionnent uniquement depuis le dépôt
* les erreurs de déclaration de dépendances
* les problèmes de point d'entrée CLI

La CI automatise ces vérifications.

## Intégration continue

Le workflow GitHub Actions principal se trouve dans `.github/workflows/ci.yml`.

Il vérifie notamment Tabalyst sur les versions Python supportées, actuellement Python 3.11 à 3.14.

La CI exécute les tests, Ruff, la construction du package et un smoke test du wheel.

Une modification ne devrait normalement pas être publiée si cette CI n'est pas verte.

## Publication PyPI

La publication est réalisée automatiquement sur PyPI avec GitHub Actions. La
version `0.1.0` a validé ce flux de bout en bout.

Le workflow se trouve dans `.github/workflows/release.yml`.

Il n'utilise aucun mot de passe PyPI ni API token permanent.

L'authentification repose sur PyPI Trusted Publishing avec OpenID Connect, ou OIDC.

GitHub fournit au job de publication une identité temporaire que PyPI vérifie avant d'autoriser le dépôt du package.

## Configuration Trusted Publishing

Le projet PyPI `tabalyst` autorise la publication depuis :

GitHub owner : `loribel-labs`

Repository : `tabalyst`

Workflow : `release.yml`

Environment : `pypi`

Le dépôt GitHub possède donc également un environnement nommé `pypi`.

La correspondance entre ces informations est importante. Une modification du nom du dépôt, du workflow ou de l'environnement peut empêcher la publication.

Aucun secret PyPI n'est nécessaire dans GitHub.

## Déclenchement d'une release

Le workflow de publication se déclenche lorsqu'un tag Git commençant par `v` est poussé sur GitHub.

La convention utilisée est par exemple `v0.1.0`.

Avant de publier, le workflow vérifie que le numéro du tag correspond exactement à la version déclarée dans `pyproject.toml`.

Ainsi, un tag `v0.2.0` ne peut pas publier accidentellement un package encore déclaré en version `0.1.0`.

Le job de publication ne démarre qu'après réussite du build et des validations précédentes.

## Flux de publication

Le cycle normal est :

développement sur `main`

→ tests locaux

→ commit et push

→ validation de la CI GitHub

→ mise à jour du numéro de version si nécessaire

→ création du tag correspondant

→ push du tag

→ workflow `release.yml`

→ build du wheel et du sdist

→ publication automatique sur PyPI par OIDC

→ installation disponible avec `pip install tabalyst`

La procédure opérationnelle détaillée est décrite dans `RELEASING.md`.

Après la publication, la version peut être vérifiée depuis un environnement
Python propre :

```console
python -m pip install "tabalyst==X.Y.Z"
tabalyst --version
tabalyst report data.csv -o reports/report.html
```

## Principe de sécurité

Le tag de release constitue l'action qui déclenche réellement une publication.

Il ne doit donc être poussé qu'après validation de la version et de la CI.

Une version publiée sur PyPI ne doit pas être remplacée par un nouveau build portant le même numéro.

En cas de correction après publication, créer une nouvelle version, par exemple `0.1.1`.

## Fichiers importants

Les principaux fichiers liés au packaging et au déploiement sont :

`pyproject.toml` : métadonnées, version, dépendances et configuration du package

`src/tabalyst/` : package Python distribué

`.github/workflows/ci.yml` : validation continue

`.github/workflows/release.yml` : publication PyPI

`README.md` : documentation utilisateur affichée notamment sur PyPI

`RELEASING.md` : procédure pratique de création d'une release

`docs/python-package-and-release.md` : documentation d'architecture du packaging et du déploiement

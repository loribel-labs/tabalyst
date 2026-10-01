---
title: Installer Tabalyst
description: Installez ou mettez à jour Tabalyst depuis PyPI sous Windows, macOS ou Linux, et gardez-le à jour avant chaque test.
---

Tabalyst nécessite Python 3.11, 3.12, 3.13 ou 3.14. La même commande l’installe
depuis PyPI, ou le met à jour s’il est déjà installé :

```console
pip install --upgrade tabalyst
tabalyst --version
```

La seconde commande affiche la version installée, par exemple `0.5.0`.

> **Mettez à jour avant chaque test.** Tabalyst est en bêta et de nouvelles
> versions sortent souvent, avec des corrections et de nouvelles options.
> Exécutez `pip install --upgrade tabalyst` avant de tester, avant de suivre un
> tutoriel et avant de signaler un problème. Voir
> [Garder Tabalyst à jour](#garder-tabalyst-à-jour).

Les sections suivantes donnent les étapes recommandées pour chaque système.

## Windows

1. Installez Python 3.11 ou plus récent depuis
   [python.org](https://www.python.org/downloads/) ou le Microsoft Store. Ouvrez
   ensuite une nouvelle fenêtre PowerShell et vérifiez la version :

   ```powershell
   py --version
   ```

2. Créez un environnement virtuel dans votre dossier de travail. Il garde
   Tabalyst séparé des autres projets Python :

   ```powershell
   py -m venv .venv
   ```

3. Installez Tabalyst dans cet environnement. La même commande le met à jour
   plus tard :

   ```powershell
   .venv\Scripts\python.exe -m pip install --upgrade tabalyst
   ```

4. Vérifiez l’installation :

   ```powershell
   .venv\Scripts\python.exe -m tabalyst --version
   ```

Pour taper directement `tabalyst`, activez d’abord l’environnement dans chaque
nouvelle fenêtre PowerShell :

```powershell
.venv\Scripts\Activate.ps1
tabalyst --version
```

Si PowerShell refuse d’exécuter `Activate.ps1` parce que l’exécution de scripts
est désactivée, continuez à utiliser `.venv\Scripts\python.exe -m tabalyst` : il
accepte exactement les mêmes commandes.

## macOS et Linux

```console
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade tabalyst
tabalyst --version
```

Pour installer la commande `tabalyst` une seule fois pour votre compte
utilisateur, utilisez plutôt [pipx](https://pipx.pypa.io/) :

```console
pipx install tabalyst
```

Avec pipx, mettez à jour avec `pipx upgrade tabalyst`.

## Garder Tabalyst à jour

Tabalyst change souvent pendant sa bêta. Mettez-le à jour avant chaque session
de test, avant de suivre cette documentation et avant de signaler un problème :
la documentation décrit la dernière version publiée, et les versions plus
anciennes peuvent manquer de commandes ou d’options.

```console
python -m pip install --upgrade tabalyst
tabalyst --version
```

Sous Windows sans environnement activé :

```powershell
.venv\Scripts\python.exe -m pip install --upgrade tabalyst
.venv\Scripts\python.exe -m tabalyst --version
```

Comparez la version affichée avec la dernière version sur
[PyPI](https://pypi.org/project/tabalyst/). La mise à jour conserve vos
rapports et vos fichiers de configuration : elle ne remplace que le paquet
installé.

## Dépannage

- **`tabalyst` n’est pas reconnu** : l’environnement n’est pas activé, ou le
  dossier des scripts Python n’est pas dans votre `PATH`. Utilisez
  `python -m tabalyst` (ou `.venv\Scripts\python.exe -m tabalyst` sous
  Windows) : `python -m tabalyst` accepte les mêmes commandes que `tabalyst`.
- **`py` n’est pas reconnu sous Windows** : Python n’est pas installé, ou a été
  installé sans le lanceur. Réinstallez-le depuis python.org.
- **Une commande ou une option de cette documentation est absente** : votre
  version est plus ancienne que celle documentée. Mettez Tabalyst à jour, puis
  vérifiez `tabalyst --version`.
- **Version de Python non prise en charge** : `pip` refuse d’installer Tabalyst
  avec Python 3.10 ou une version antérieure. Installez une version prise en
  charge et recréez l’environnement.

## Étape suivante

[Créer votre premier rapport](../tutorials/first-report.md).

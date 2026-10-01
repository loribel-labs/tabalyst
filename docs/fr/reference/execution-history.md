---
title: Historique d’exécution
description: Référence de executions.json, l’historique cumulatif de performance écrit à côté de chaque rapport.
---

Chaque analyse Tabalyst réussie met à jour `executions.json` dans le dossier de
sortie du rapport HTML. Le fichier fournit un historique de performance léger
pour comparer les rapports à mesure que Tabalyst et sa configuration évoluent.

Avec cette commande :

```console
tabalyst report examples/input/basic.csv -o examples/output/basic/report.html --config examples/config.json
```

Tabalyst écrit `report.html`, `report.json` et `executions.json` dans
`examples/output/basic`. Un rapport nommé ultérieur dans le même dossier ajoute
une entrée à l’historique existant. Seuls les noms de fichiers sont stockés,
car tous les fichiers générés partagent un seul dossier.

## Format

```json
{
  "schema_version": "1.0",
  "executions": [
    {
      "timestamp": "2026-09-18T14:32:10Z",
      "tabalyst_version": "0.1.0",
      "source_file": "data.csv",
      "html_file": "report1.html",
      "json_file": "report1.json",
      "rows": 3000,
      "columns": 34,
      "analysis_seconds": 0.6527,
      "total_seconds": 0.9314,
      "git": {
        "available": true,
        "commit": "a1b2c3d4e5f6...",
        "dirty": true,
        "state": "a1b2c3d4+working"
      }
    }
  ]
}
```

`analysis_seconds` couvre l’ingestion du CSV et le profilage. `total_seconds`
couvre aussi la sérialisation JSON et le rendu HTML. Pour un rapport construit
à partir d’un document d’analyse avec `--scan`, les deux incluent la durée de
l’analyse enregistrée dans le document. La version du paquet Tabalyst est
toujours enregistrée. Les métadonnées Git sont incluses quand la commande
s’exécute dans un dépôt ; une exécution de production installée hors de Git
utilise `available: false` et des valeurs nulles.

L’historique complet est réécrit dans un fichier temporaire puis remplacé de
façon atomique après chaque analyse réussie. Les analyses en échec n’ajoutent
pas d’entrée. Les changements de schéma incompatibles sont réservés à une
prochaine version mineure.

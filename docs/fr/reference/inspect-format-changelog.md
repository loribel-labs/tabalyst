---
title: Journal des modifications du format Inspect
description: Comment un fichier Inspect écrit par tabalyst inspect identifie son format, et les changements de chaque révision du format.
---

Un fichier Inspect écrit par `tabalyst inspect` identifie son contrat avec trois
champs :

```json
{
  "format": "tabalyst.inspect",
  "format_version": "0.1.0a",
  "format_revision": 1
}
```

`format` nomme le type de document ; le [format d’analyse](scan-format-changelog.md)
et le [profil JSON](profile-format-changelog.md) ont leurs propres journaux.
`format_version` nomme la famille de compatibilité expérimentale, `0.1.0a`
conservée pendant la bêta. `format_revision` est un entier monotone incrémenté à
chaque changement structurel ou sémantique significatif. Il ne change pas pour
la documentation ni pour les corrections qui conservent le contrat.

Les révisions bêta peuvent être incompatibles. Aucune migration automatique
n’est fournie : Tabalyst refuse un fichier d’une autre version, et
`tabalyst inspect --force` en écrit un nouveau. Voir le
[format Inspect](inspect-format.md) pour la structure actuelle.

## Révision 1

- Premier format Inspect, type `json`, pour les sources `.json`, `.jsonl` et
  `.ndjson`.
- Sections `inspect`, `source`, `detection`, `warnings` et `config` ; la partie
  que vous modifiez est `config`, avec `structure.dataset_path`, `flatten`
  (`enabled`, `separator`, `max_depth`), `arrays.mode` et `errors.policy`.
- `detection` enregistre les candidats de toute la source et l’observation
  bornée de leurs premiers enregistrements, avec sa portée, la sélection et sa
  base. Il n’y a pas de score de confiance.
- Codes de `warnings` : `ambiguous_collections`, `no_collection`,
  `candidates_truncated`, `candidate_not_eligible`,
  `candidate_not_eligible_truncated`, `invalid_lines`, `non_object_lines`,
  `configured_path_not_found` et `source_name_mismatch`.

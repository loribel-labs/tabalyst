# Tabalyst documentation sources

| Folder | Content | Published |
| --- | --- | --- |
| `en/` | User documentation in English, the source of truth | Yes, on docs.tabalyst.com |
| `fr/` | French translation of `en/`, same file names and folders | Yes, under `/fr/` |
| `dev/` | Maintainer documentation: architecture, progress, packaging, release notes | No |

`en/` follows the Diátaxis structure: `tutorials/`, `how-to/`, `reference/` and
`explanation/`. Pages in `en/` and `fr/` start with a `title` and `description`
frontmatter and have no `# H1` heading; the documentation site renders the title.

Writing and translation rules are in the "Documentation" section of
[`../AGENTS.md`](../AGENTS.md). The vocabulary is fixed by the
[glossary](en/reference/glossary.md).

The contents of `en/` and `fr/` are licensed under CC BY 4.0 (see
[`LICENSE`](LICENSE)); the rest of the repository is MIT.

# Tabalyst documentation sources

| Folder | Content | Published |
| --- | --- | --- |
| `en/` | User documentation in English, the source of truth | Yes, on docs.tabalyst.com |
| `fr/` | French overview of Tabalyst; its links lead to the English pages | Yes, at `/fr/` |
| `dev/` | Maintainer documentation: architecture, progress, packaging, release notes | No |

`en/` is organized by tool: `get-started/`, `report/`, `inspect/`, `scan/`, `sample/`, `reference/` and
`about/`. URLs follow the pattern `/tool/subject/`. Pages in `en/` start with a `title` and
`description` frontmatter and have no `# H1` heading; the documentation site
renders the title.

## Structure and URLs

The first level of a URL is the tool or the main family; the second is a short,
stable subject: `/report/json/`, `/inspect/format/`, `/scan/files/`,
`/reference/cli/`. Titles can be long, slugs stay short. There is no "Tools"
group: each tool has its own space with an overview (`index.md`), its guides and
the reference of its JSON format with its changelog.

| Folder | Content |
| --- | --- |
| `get-started/` | Overview, installation, first report and demos |
| `report/` | Tabalyst Report: overview, report-reading guide, CSV, JSON, JSON profile and its changelog |
| `inspect/` | Tabalyst Inspect: overview, JSON guide, Inspect format |
| `scan/` | Tabalyst Scan: overview, guide, scan format, query caches |
| `sample/` | Tabalyst Sample (one page) |
| `reference/` | Command line (`cli/`), Python API (`python-api/`), shared types and patterns (`types-and-patterns/`), configuration, execution history, glossary |
| `about/` | Overview, concepts, known limitations, release notes, contributing and issues |

To add a page, create it in the folder of its tool with a one-sentence
`description`, link it with relative `.md` paths and add it to
`src/navigation.ts` in `tabalyst-studio`: a page missing there is absent from the
menu, `llms.txt` and the Markdown twins. A new command gets its own folder, an
`index.md` and a menu group, and is documented in the release that ships it.
Renaming a page changes its URL: avoid it after 1.0.

Writing rules are in the "Documentation" section of
[`../AGENTS.md`](../AGENTS.md). The vocabulary is fixed by the
[glossary](en/reference/glossary.md).

The contents of `en/` and `fr/` are licensed under CC BY 4.0 (see
[`LICENSE`](LICENSE)); the rest of the repository is MPL-2.0.

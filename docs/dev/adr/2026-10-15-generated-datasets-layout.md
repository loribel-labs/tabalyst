# Generated datasets are recipes in the repository and files outside it; heavy cases leave for a private repository

Status: accepted on 2026-10-15 (maintainer: the private repository `tabalyst-lab` exists at `D:\GIT\tabalyst-lab`).
Points 1 to 3 are implemented (`examples/tools/make_datasets.py`); points 4 and 5 are done (lot 7: the cases,
the category manifests and the generated computer datasets live in `tabalyst-lab`; the public repository keeps the
six demos, the insurance 100,000-row request and `make_datasets.py`). See the plan `tabalyst-gb/KANBAN/05-PROGRESS/2026-10-15-tabalyst-lab-datasets-plan.md`, where the public repository
keeps only a short list of published examples.

## Context

The Generate engine builds CSV files for three domains (insurance, computers, CRM), in several sizes, widths and
cleanliness levels. The maintainer wants many such files (ten categories of the same kind), to use them in demos and
tests, and later to feed the domain pages of the website and a Kaggle dataset. Committed CSV files would make the
repository heavy and unmanageable: a generator change rewrites them all, the history keeps every version, and a 10,000-row
`extended` file is 9 MB. The reports built from them will change often, and dozens of them (detailed or not) are expected,
of which only a few are meant to be public. Some heavy cases may not be shareable at all.

## Decision

1. **A recipe is committed, the files are not.** A JSON file of `examples/datasets/` is either a request (one run of
   `tabalyst generate`) or a category manifest (`"datasets": [...]`, several runs). Each file a run keeps is named with its
   SHA-256. `examples/tools/make_datasets.py` builds them and reuses those whose digest matches. The digest is both the
   version identifier and a regression test of the generator.
2. **Files live outside the checkout**, in `$TABALYST_DATASETS`, by default `<repository parent>.test/tabalyst/datasets`,
   in a folder named after the category (`computers/`). Nothing generated is written inside the repository (the existing
   rule for test output). A `.gitignore` entry protects the folders a tool could create by mistake.
3. **One naming scheme per run**: `<id>.csv` (clean), `<id>.dirty.csv` (with defects), `<id>.changes.csv` (ground truth of
   the defects). The ids carry the size (`-100`, `-3k`, `-10k`) and the variant (`-compact`, `-units`).
4. **The public repository keeps what the website and the documentation publish**: the recipes, the tools, the demos with
   `publish.site: true` and, for each domain page, one small committed sample (about 100 rows, tens of kilobytes) so that
   the site can show data without a build step. The reports of the published demos are committed; a report that is only a
   work in progress is not.
5. **Heavy and exploratory material goes to a private repository** (`tabalyst-lab`, sibling of `tabalyst-gb` and
   `tabalyst-studio`): cases with large generated files, dozens of reports kept to follow the evolution of the output, deep
   comparisons, anything not shareable. It reads the public recipes through the same tool (`TABALYST_DATASETS`) and holds
   its own manifests and expectations. It can be opened later, piece by piece, by moving a case into `examples/cases/`.

## Consequences

- Regenerating from a clone is one command (`python examples/tools/make_datasets.py`), but a contributor needs the same
  Python minor version to match the digests; otherwise the tool stops with a message, it does not guess.
- The website and a Kaggle upload read the files from the external root after a build. The manifest identifies the
  published version by digest. A Kaggle dataset page needs the three files of a run (data, data with defects, ground
  truth), which the naming scheme already provides.
- The second repository adds one place to keep in sync, in exchange for freeing the public repository from reports and
  files that change daily. If most cases end up public, merge it back; the tool does not depend on the split.
- Changing a generation profile changes the bytes of every dataset that uses it (the unit operations added to
  `dirty_realistic` and `dirty_stress` did); `--update-sha` records the new digests in the same change.
- Moving the existing `insurance-customers-100k.json` into a `datasets/insurance/` manifest, and adding CRM, are follow-ups
  that need no decision beyond this one.

# The detail pages load Apache ECharts from a CDN, `report.html` never does, and `--details` forces the second pass

Date: 2026-11-11 (proposed, not implemented)

## Context

`report.html` and the column pages are self-contained: `report.js` and `theme.css` are inlined by
`reporting.py`, the charts are SVG drawn at render time, and the README promises a report that
works without a network or a CDN. The diagnostics to come, starting with the UpSet plot of the
combinations of missing values (`docs/dev/scan/design.md` 20.44), then charts on the column pages
and the Insights charts, need interaction that hand-written SVG makes costly: grids with linked
axes, zoom over many items, a tooltip per mark, redrawing for the theme and the width.

A charting library inlined in every page would weigh on each of them: the full build of ECharts is
about 1 MB minified, and `--details` writes one page per column. Embedding a copy in the package
also brings a second license (Apache-2.0) into an MPL-2.0 package. The maintainer does not want a
new option for the charts, and the charts read analyses of the second pass, which is not always
run.

## Decision

- **One split.** `report.html` stays self-contained, with no CDN. The detail pages, the column
  pages and the new chart pages (`charts-<topic>.html`, in the same folder), may load the library
  (`docs/dev/report/chart-pages.md`).
- The library is **Apache ECharts**: one library for the diagnostics, the column pages and the
  Insights.
- For now the detail pages load it **from jsDelivr**, at an exact version, with SRI (`integrity`),
  `crossorigin="anonymous"` and `referrerpolicy="no-referrer"`. The URL and the hash are one
  constant. Only a page that draws with it loads it. The data of the charts are inlined in the page;
  only the library is fetched.
- **No new option.** `--details` writes the chart pages with the column pages, and **forces the
  second pass** (it implies `--deep`), with the confirmation of a costly forced pass.
- Every chart has a **table** of its exact figures: it is the reference, readable without the
  library, and the page says so plainly when the library cannot load.

## Consequences

- `report.html` keeps its promise and its size. A detail page needs a network connection to draw
  its ECharts charts; offline, or behind a proxy that blocks the CDN, its tables and what it shows
  today remain. The documentation qualifies "self-contained" for the detail pages, and
  `tabalyst-studio` follows.
- The viewer's browser contacts jsDelivr when a detail page with a chart opens: its address reaches
  the CDN, no data of the report does. The pages share one URL, so the file is fetched once.
- `--details` changes behavior: it now reads each source a second time. On a costly file it asks
  first in a terminal, and a script outside a terminal needs `--yes` (exit code `3` otherwise).
  `--details` with `deep.mode` `off` is an error. The release notes say so.
- A first third-party JavaScript dependency: its version is pinned and its file checked by its
  hash, and upgrading it is a deliberate change of the constant.
- Embedding the library later (a custom build written once beside the detail pages, `LICENSE` and
  `NOTICE`, `static/vendor/` excluded from the license header check, `package-data`, the license
  expression `MPL-2.0 AND Apache-2.0`) changes the constant and the templates only. It waits until
  the size of a custom build is known.

## Rejected

- ECharts in `report.html`: the one page meant to open anywhere would depend on the network.
- ECharts inlined in every detail page: the weight lands on each column page.
- A `--charts` option: one more option for what `--details` already asks for, the detail of the
  data.
- `--details` drawing only what the second pass already holds: `missing_patterns` is never
  automatic, so the charts would be missing on a default run.
- Hand-written SVG for the interactive charts: fine for one static chart, but each chart of the
  column pages and the Insights would repeat the work of axes, zoom and tooltips. The charts of
  `report.html` stay SVG.
- Plotly (a bundle of several MB) and hand-written D3 (every chart coded from its primitives).
- An embedded copy from the start: the license and packaging work comes before the size of a
  custom build is known.

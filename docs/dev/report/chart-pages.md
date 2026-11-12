# The detail pages and their charts

Status: proposed on 2026-11-11, revised the same day after the maintainer's decisions (section 9):
no new option, the chart pages come with `--details`, which then forces the second pass, and the
column pages load the library too; `report.html` never does. Implemented on 2026-11-12:
the blocks (6.1), the card of `report.html` (6.2) with its link, and `charts-missing.html`
(`report_charts.py`, `templates/charts.html`, `static/charts.js`, ECharts 6.1.0). No column page
holds an ECharts chart yet, so none loads the library. The browser check
(`tests/browser/report.cjs`) covers the chart page when the report has one. Left for later: the
embedded copy (section 5). The decision is the ADR
`2026-11-11-report-chart-pages-echarts-cdn`. The first chart page draws the combinations of missing
values (`docs/dev/scan/design.md` 20.44); the Insights charts come later on the same base.
Guiding vision: Simple, Clear, Smart.

## 1. Purpose

Some diagnostics need an interactive chart: linked axes, zoom over many items, a tooltip per
mark. The first are charts for diagnosing and correcting errors (the UpSet plot of the missing
values), then the Insights. They need a charting library, Apache ECharts.

Two kinds of pages, split by one rule:

- **`report.html`** stays self-contained and readable without a network: no CDN, its charts drawn
  as inline SVG at render time, as today.
- **The detail pages** (the column pages and the chart pages) may load ECharts from a CDN.

## 2. Files

- The detail pages are written in the folder named like the report (`report_path.with_suffix("")`,
  `reporting.column_pages`): the column pages as today (`col-NN-slug.html`) and one chart page per
  topic, `charts-<topic>.html`. The first topic is `missing` (`charts-missing.html`). Topic slugs
  are stable once released.
- A chart page covers every dataset of the report that has data for its topic, one section per
  dataset with the anchor `#<dataset id>`, in the order of the report.
- The pages are planned and written by `batch.py` like the other outputs: collision protection,
  atomic writes, `--force` to overwrite.

## 3. Trigger: `--details`

No new option. `--details` (`details=True` in the API) writes the column pages and the chart pages,
and forces the second pass:

- `--details` implies `--deep`: every applicable exact analysis, `missing_patterns` included,
  with the confirmation of a costly forced pass (design 20.11): asked in a terminal, `--yes` to
  skip it, exit code `3` outside a terminal without `--yes`, one question for a batch.
- `--details` with a configuration whose `deep.mode` is `off` is an error: the option would be
  silently ignored otherwise. The same for `--details --no-html`.
- `--scan --details` reads the source next to the scan document, as `--scan --deep` does, and fails
  with exit code `4` when it is not there.
- A topic without data writes no chart page. The progress output and the result name each topic
  left out and why (`too_many_columns`, `no_missing_values`, `withheld_columns`, `analysis_failed`),
  as warnings of the report ("no chart of the missing values for <dataset>: <reason>"). A forced
  report with `--details` removes a chart page it no longer writes; without `--details` it removes
  the chart pages with the column pages. Only a page whose `generator` is `Tabalyst chart page` is
  removed.
- `tabalyst report` has no `--no-html`: the clause of `--details --no-html` concerns no command
  today.
- **Change of behavior.** `--details` was a rendering option and now reads each source a second
  time. A script that used it outside a terminal on a costly file needs `--yes`. The release notes
  and `docs/en/reference/cli/report.md` say so.

## 4. Rendering

- Rendered from the report JSON alone, like `report.html` (`reporting.py`, no source access).
  `report_charts.py` builds the series from `analyses` (pure, tested on its own);
  `templates/charts.html` prints them and computes nothing; `static/charts.js` (MPL header)
  draws them and is inlined like `report.js`.
- The data of each chart is inlined in a `<script type="application/json">` written with
  `tojson`. The page fetches nothing but the library.
- **Tables first.** Each chart has a table of its exact figures, visible next to it, with the
  accuracy words of the insight cards. The table is the reference: it reads without JavaScript,
  in print and with a screen reader, and it carries the limits (`complete` false, `untracked`).
- **Theme.** The page inlines `theme.css` and the theme script of the other pages (same
  `tabalyst-theme` key). `charts.js` reads the colors and fonts from the CSS variables and
  redraws when `data-theme` changes on `<html>` (`MutationObserver`). A `ResizeObserver` redraws
  on a change of width. The renderer is SVG.
- **Links.** A chart page links back to `report.html` (`../<report name>.html`) and to the column
  pages of the columns it names. `report.html` links to each chart page written: from the card of
  the topic in the dataset panel and from the navigation. A column page links to the chart pages
  that name its column (`charts-missing.html#<dataset id>` for a column that lacks values).

## 5. The library

- Apache ECharts, an exact version, from jsDelivr, with `integrity` (SRI, sha384),
  `crossorigin="anonymous"` and `referrerpolicy="no-referrer"`: the file cannot be swapped and
  the CDN does not learn the path of the report. The version and the hash are fixed when the
  page is implemented, computed from the published file.
- One constant holds the URL and the hash (`report_charts.ECHARTS`). A test checks that the URL
  names an exact version and that the hash has the SRI form. Moving to an embedded copy changes
  that constant and the templates, nothing else.
- **Only the pages that draw with it load it.** A chart page always does; a column page only when
  it holds an ECharts chart, so a column page without one makes no request. Every page uses the same
  URL, so the browser fetches the file once for the whole folder.
- **`report.html` never loads it.** A test renders a report with every kind of analysis and checks
  that it holds no external `src` or `href`.
- **Without the library** (offline, a proxy that blocks the CDN, a failed hash), every chart frame
  shows a visible message: the charts of this page need a network connection to load ECharts; the
  tables hold the same figures. Detected by the `onerror` of the script and by `window.echarts`
  being undefined. What a column page shows today (its SVG, its blocks) stays readable offline.
- The viewer's browser contacts the CDN; no data of the report is sent.
- **Later, embedded.** A custom build (bar, scatter, custom, grid, tooltip, dataZoom, SVG
  renderer) written once in the folder of the detail pages, its `LICENSE` and `NOTICE`
  (Apache-2.0), `static/vendor/` excluded from `scripts/license_headers.py`, added to
  `package-data`, and the `license` of `pyproject.toml` as `MPL-2.0 AND Apache-2.0`. Not before its
  size is known.

## 6. The UpSet plot of the missing values

Read from `MissingPatternsResult` (`docs/dev/scan/design.md` 20.44), one plot per dataset.

The reference mockup was shared by the maintainer on 2026-11-11:
`D:\GIT.test\tabalyst\artifacts\charts\mockup\upset-missing-crm-contacts.png` (outside the checkout,
rule of `AGENTS.md`). It draws the `contacts` table of the packaged CRM example (`tabalyst generate`,
200,000 rows, 7 columns that lack a value, 93 patterns), whose fields of an opportunity go missing as a
block: the reproducible case for the tests and the browser check. Its words are French; the page
prints English (`report_labels.py`) and the report's number format.

From top to bottom, as in the mockup:

- **Three figures.** The records with every value and their share (`complete_records`), the
  records that lack at least one (`records - complete_records`), the patterns seen (`distinct`,
  "at least" when `complete` is false).
- **Two controls**, client side, on the data of the page: sort the patterns by count (default) or
  by number of columns then count; show every pattern, only those of two columns or more (the
  values missing together), or those that hold a chosen column.
- **The plot**, described below.
- **Reading notes**, a short list under the plot: exclusive intersections, each record counted in
  one pattern; how many patterns are drawn and how many are grouped (`20 drawn`, then the others
  with their records, "see the table"); what lacking a value means (empty, blank or a null marker
  of the configuration, the Scan's definition); the check against the Scan, passed (a mismatch
  fails the analysis, so the page never shows a failed check).
- **The table** of every listed pattern with its count and share, then the line of the patterns
  not listed and, when `complete` is false, of the records not tracked.

The plot:

- **Three grids.** At the top, a `bar` series of the listed patterns, by decreasing count (the
  exclusive intersections). Below, the matrix: a `scatter` series on the same x categories and a
  y category per column, a full dot when the column is in the pattern and a pale one otherwise,
  and a `custom` series for the segment that joins the dots of a pattern. On the left, a
  horizontal `bar` of the records that lack each column (the set sizes), on the y axis of the
  matrix.
- **Drawn patterns.** The first 20 in the order chosen; the others stay in the table. The count
  is printed over the bars that are tall enough to carry it (the first five in the mockup); the
  others show it in the tooltip.
- **Linked.** `axisPointer.link` on the two x axes: hovering a pattern highlights its bar and its
  column of dots.
- **Columns.** Only the columns that appear in a drawn pattern, by decreasing `missing`. A
  dataset of 100 members does not draw 100 rows of dots.
- **Tooltip.** The columns of the pattern, its count and its share of the records.
- **Narrow screens.** Below 600 px the dot matrix is unreadable: the plot becomes one horizontal
  bar per pattern, labelled with its columns, followed by the table (decided 2026-11-11).
- The plot shows that values go missing together, not why.

### 6.1 The blocks of columns

Decided on 2026-11-11. A sentence above the plot names the columns that go missing as a block,
derived at render time from `MissingPatternsResult` alone (`report_insights.py`, shared with the card
of `report.html`, see 6.2).

- **Records missing a group.** For a group `G` of two columns or more, `all(G)` is the sum of the
  counts of the listed patterns that hold every column of `G`. It is exact when the result lists
  every pattern (`complete` true and `other_patterns` 0), a lower bound otherwise.
- **A block.** `G` is a block when, for each of its columns `c`, `all(G) >= 0.8 * missing(c)`: the
  records that lack the whole group are at least 80 % of the records that lack any one of its
  columns. A lower bound can only miss a block, never invent one.
- **Not a coincidence of rare columns.** `all(G)` is at least 1 % of the records; two columns
  missing once in the same record are not a block.
- **The largest groups only.** Every subset of a block is a block, so only the maximal blocks are
  named, by decreasing `all(G)`, then document order, five at most.
- **The search.** Growing the groups level by level from the pairs would go through every subset
  of a wide block (60 columns that are always empty together hold 2^60 subsets). A maximal block
  `G` is instead read from `C`, the intersection of the listed patterns that hold `G`:
  `all(C) = all(G)`, and `G` is the set of the columns `c` of `C` with
  `all(C) >= 0.8 * missing(c)`. So `missing_blocks` takes out the columns in no block of two,
  goes through the intersections of the patterns (at most `MAX_INTERSECTIONS`, 20,000; past it,
  a block can be missed, never invented), keeps the passing columns of each and names the maximal
  ones. Implemented on 2026-11-12, with `MissingBlock` and `InsightCard.lines`.
- **The sentence**, one per block: the columns, `all(G)` and the smallest share among its columns,
  for example "`opportunity_amount`, `opportunity_close_date` and `opportunity_probability` go
  missing together: 126,000 records lack all three, at least 94 % of the records that lack any one
  of them." (figures read approximately from the mockup). With a lower bound the count reads "at
  least".
- The thresholds (`0.8` and `0.01`) are constants of `report_insights.py`; they are not a setting.
  Checked on 2026-11-12 on the CRM `contacts` table (seed by default, 200,000 rows, 80 patterns): one
  block, `opportunity_amount`, `opportunity_probability` and `opportunity_close_date`, 127,673
  records, at least 95.1%; the same block at 3,000 rows (`tests/report/test_chart_pages.py`).

### 6.2 In `report.html`

The `missing` card of the dataset (design 20.32) prints the same sentences, the table of the first
patterns (20.44) and a link to `charts-missing.html` when `--details` wrote it. Implemented on
2026-11-12 except the link, which waits for the page: the card *Columns missing together* gains
the sentences, the figures (records with every value, those that lack at least one, the
combinations seen, `at least` when `complete` is false), the first `MAX_ROWS` (15) combinations
with their columns, count and share, and a note for the rest; the table of the pairs follows when
`missing_matrix` ran. With the combinations alone, the card has no table of pairs. The sentences need
`missing_patterns`, so they appear after `--details` or `--deep`, not on a default run.

## 7. Documentation and follow-ups

- The promise "self-contained, no CDN" stays for `report.html` and is qualified for the detail
  pages where it is made (`README.md` says `--details` writes "one self-contained HTML page per
  column", `docs/en/report/index.md`, `docs/en/report/csv.md`, `docs/dev/architecture.md`): they
  load ECharts from a CDN to draw their charts.
- `docs/en/reference/cli/report.md`: `--details` forces the second pass, with its confirmation,
  `--yes` and exit code `3`; the error with `deep.mode` `off`; the chart pages it writes. A public page
  `docs/en/report/charts.md`, in the change that ships them.
- Release notes: the change of behavior of `--details` (section 3).
- `tabalyst-studio`: the new page in `src/navigation.ts`, and the website only once the README
  documents the pages.

## 8. Tests

- `report_charts`: the series of a result; the columns limited to the drawn patterns; the
  untracked note; nothing for a withheld column.
- Command: `--details` forces the second pass and writes `charts-missing.html`; outside a terminal
  a costly pass stops with exit code `3` without `--yes`; `--details` with `deep.mode` `off` fails;
  `--details --no-html` fails; a topic without data writes nothing and names its reason; `--force`
  and collisions as the other outputs.
- Templates: `report.html` holds no external `src` or `href`; a page that loads ECharts carries
  `integrity`, `crossorigin` and `referrerpolicy`; a column page without an ECharts chart loads
  nothing; the tables are present; no data in a URL.
- The blocks (6.1): the trio of the CRM `contacts` table is named; a pair of columns missing once
  together is not; a lower bound reads "at least"; a subset of a block is not named beside it.
- Browser check on `insurance-customers` with `--details` and on the CRM `contacts` table, at
  desktop and mobile sizes, in both themes, and with the CDN blocked. Local only: no demo
  publishes the detail pages yet.

## 9. Decisions of the maintainer (2026-11-11)

1. No new option: `--details` writes the chart pages and forces the second pass (section 3).
2. `report.html` never loads the CDN; the detail pages may (section 5).
3. One page per topic, a section per dataset (section 2).
4. Narrow screens: one bar per pattern, then the table (section 6).
5. No demo publishes the detail pages for now; the website keeps `insurance-customers` as it is.
   To decide again once the pages ship.
6. The blocks: 80 % of each column, at least 1 % of the records, maximal groups only, on the chart
   page and in the `missing` card of `report.html` (6.1, 6.2).

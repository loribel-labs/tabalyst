// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

// Usage: node tests/browser/report.cjs report.html report.json [playwright module]
const { chromium } = require(process.argv[4] || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { pathToFileURL } = require('node:url');
const artifactsDirectory = process.env.TABALYST_ARTIFACTS_DIR ||
  path.join(os.tmpdir(), 'tabalyst', 'artifacts');

const visibleRows = async (page, table) =>
  page.locator('#' + table + ' tbody tr:not([hidden])').evaluateAll(rows =>
    rows.map(row => row.cells[0].dataset.v),
  );

async function resetTable(page, table) {
  const button = page.locator('[data-reset="' + table + '"]');
  if (await button.isVisible()) await button.click();
}

const HEADERS = ['Column', 'Type family', 'Type', 'Overview', 'Missing', 'Errors', 'Issues', 'Details'];
const COL = { family: 1, type: 2, missing: 4, errors: 5, issues: 6, details: 7 };

// The Summary table against the JSON: the cells the page prints are the
// document's classification and Missing figure, and the filters work on codes.
async function tableChecks(page, profile, observedFields, label) {
  const headers = await page.locator('#summary-table thead th .ht').evaluateAll(els => els.map(el => el.textContent.trim()));
  assert.deepEqual(headers, HEADERS, label);
  const rows = await page.locator('#summary-table tbody tr').evaluateAll(trs => trs.map(tr => ({
    ds: tr.dataset.ds,
    field: tr.dataset.field,
    name: tr.cells[0].dataset.v,
    family: tr.cells[1].dataset.v,
    type: tr.cells[2].dataset.v,
    missing: tr.cells[4].dataset.v,
    errors: tr.cells[5].dataset.v,
    issues: tr.cells[6].dataset.v,
  })));
  assert.equal(rows.length, profile.columns.length, label);
  profile.columns.forEach(column => {
    const row = rows.find(item => item.field === column.id);
    assert.ok(row, label + ' ' + column.id);
    assert.equal(row.ds, profile.id, label);
    assert.equal(row.family, column.classification.family, label);
    assert.equal(row.type, column.classification.family + '/' + column.classification.type, label);
    assert.equal(Number(row.missing), column.missing_percent, label + ' ' + column.id);
  });
  assert.equal(new Set(rows.map(row => row.ds + '/' + row.field)).size, rows.length, label);

  // The segment reads the Errors and the Issues the table prints.
  const found = rows.filter(row => row.errors === 'detected' || row.issues === 'detected');
  assert.equal(
    await page.locator('[data-seg="summary-table"] [data-mode="issue"] .c').innerText(),
    String(found.length),
    label,
  );
  assert.equal(
    await page.locator('[data-seg="summary-table"] [data-mode="obs"] .c').innerText(),
    String(profile.columns.filter(column => observedFields.has(column.id)).length),
    label,
  );
  await page.locator('[data-seg="summary-table"] [data-mode="issue"]').click();
  assert.deepEqual(await visibleRows(page, 'summary-table'), found.map(row => row.name), label);
  await page.locator('[data-seg="summary-table"] [data-mode="all"]').click();
  await resetTable(page, 'summary-table');

  // Family and Type filter independently, on codes: a family keeps its own types.
  const family = rows[0].family;
  const inFamily = rows.filter(row => row.family === family);
  let menu = await openFilter(page, 'summary-table', COL.family);
  await menu.locator('[data-none]').click();
  await menu.locator('.fm-opt[data-v="' + family + '"]').click();
  await page.keyboard.press('Escape');
  assert.deepEqual(await visibleRows(page, 'summary-table'), inFamily.map(row => row.name), label);
  const others = rows.find(row => row.family !== family);
  if (others) {
    menu = await openFilter(page, 'summary-table', COL.type);
    const options = await menu.locator('.fm-opt').evaluateAll(list => list.map(o => o.dataset.v));
    assert.deepEqual(
      options.sort(),
      [...new Set(rows.map(row => row.type))].sort(),
      label + ': Type options come from every classification present',
    );
    await menu.locator('[data-none]').click();
    await menu.locator('.fm-opt[data-v="' + others.type + '"]').click();
    await page.keyboard.press('Escape');
    assert.deepEqual(await visibleRows(page, 'summary-table'), [], label + ': filters intersect');
  }
  await resetTable(page, 'summary-table');

  // Sorts are independent too: Type by its words, Errors by its number of findings.
  const typeSort = page.locator('#summary-table thead th').nth(COL.type).locator('.hb-s');
  await typeSort.click();
  const typeWords = await page.locator('#summary-table tbody tr').evaluateAll(trs => trs.map(tr => tr.cells[2].dataset.l));
  assert.deepEqual(
    typeWords,
    [...typeWords].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase(), undefined, { numeric: true })),
    label,
  );
  await resetTable(page, 'summary-table');
  const errorSort = page.locator('#summary-table thead th').nth(COL.errors).locator('.hb-s');
  await errorSort.click();
  await errorSort.click();
  const orders = await page.locator('#summary-table tbody tr').evaluateAll(trs => trs.map(tr => Number(tr.cells[5].dataset.s)));
  assert.deepEqual(orders, [...orders].sort((a, b) => b - a), label);
  await resetTable(page, 'summary-table');

  // The states are words. Only a not applicable Errors cell is a dash, and says
  // its word to a screen reader.
  const errors = await page.locator('#summary-table tbody tr td:nth-child(6)').evaluateAll(tds => tds.map(td => [td.dataset.v, td.textContent.trim()]));
  assert.ok(errors.every(([state, text]) => text.length > 1 && (state === 'not_applicable') === text.startsWith('-')), label);
  const issues = await page.locator('#summary-table tbody tr td:nth-child(7)').allInnerTexts();
  assert.ok(issues.every(text => text.trim().length > 1 && !text.trim().startsWith('-')), label);

  // Details: no link to a column page, two lines at most, and a hover that lists every group.
  assert.equal(await page.locator('#summary-table .column-link').count(), 0, label);
  const heights = await page.locator('#summary-table td.c-dt .exs').evaluateAll(els => els.map(el => el.getBoundingClientRect().height));
  assert.ok(heights.every(height => height <= 66), label + ': two lines at most');
  const withVariants = profile.columns.find(column => column.normalization.variant_groups.length > 0);
  if (withVariants) {
    const cell = page.locator('#summary-table tbody tr[data-field="' + withVariants.id + '"] td.c-dt');
    await cell.hover();
    const tip = cell.locator('.tip');
    await tip.waitFor({ state: 'visible' });
    assert.equal(await tip.locator('.vgroup').count(), Math.min(withVariants.normalization.variant_groups.length, 20), label);
    await page.mouse.move(0, 0);
  }

  // The dashboard card: families with their types, then the technical types.
  const card = page.locator('.rcard:has(.rcard-title:text-is("Column types"))');
  assert.equal(
    await card.locator('.legend.fam li').count(),
    Object.keys(profile.summary.type_family_counts).length + Object.keys(profile.summary.type_counts).length,
    label,
  );
  assert.equal(await card.locator('.rcard-sub').count(), 2, label + ': each list says what it counts');
}

async function openFilter(page, table, index) {
  await page.keyboard.press('Escape');
  await page.locator('#' + table + ' thead th').nth(index).locator('.hb-f').click();
  const menu = page.locator('.fmenu');
  await menu.waitFor({ state: 'visible' });
  return menu;
}

(async () => {
  const report = JSON.parse(await fs.readFile(process.argv[3], 'utf8'));
  const profile = report.report.datasets[0];
  const base = report.datasets.find(dataset => dataset.id === profile.id);
  // The page reads the document alone (F01): every figure checked below is
  // recomputed from the JSON, never from the page.
  const observations = report.observations;
  const observedFields = new Set(
    (observations ? observations.items : [])
      .filter(item => !item.dataset || item.dataset === profile.id)
      .filter(item => item.field)
      .map(item => item.field),
  );
  const mine = item => !item.dataset || item.dataset === profile.id;
  const issueFields = new Set(
    (observations ? observations.items : [])
      .filter(item => mine(item) && item.status !== 'informational' && item.field)
      .map(item => item.field),
  );
  const listed = observations ? observations.items.filter(mine) : [];
  const sampleRows = base.records.sample ? base.records.sample.rows : [];
  const browser = await chromium.launch({
    headless: true,
    channel: process.env.TABALYST_BROWSER || 'msedge',
  });
  const errors = [];
  try {
    for (const [name, width, height] of [
      ['desktop', 1440, 1050],
      ['tablet', 820, 1180],
      ['mobile', 390, 844],
    ]) {
      const page = await browser.newPage({ viewport: { width, height }, colorScheme: 'dark' });
      page.on('pageerror', error => errors.push(name + ': ' + error.message));
      page.on('console', message => {
        if (message.type() === 'error') errors.push(name + ': ' + message.text());
      });
      await page.goto(pathToFileURL(path.resolve(process.argv[2])).href, {
        waitUntil: 'load',
      });
      await page.waitForFunction(() =>
        document.querySelector('#columns-table tbody tr')?.dataset.i === '0',
      );

      assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
      assert.equal(await page.locator('.side').evaluate(el => getComputedStyle(el).position), 'sticky');
      assert.equal(await page.locator('.foot').count(), 1);
      assert.ok((await page.locator('.foot').innerText()).includes('Gregory Borelli'));
      assert.ok((await page.locator('.rep-tab').count()) >= 10);
      assert.equal(await page.locator('#columns-table tbody tr').count(), profile.columns.length);
      assert.equal(await page.locator('a.brand[href="https://tabalyst.com/"]').count(), 2);
      const firstColumnRow = page.locator('#columns-table tbody tr').first();
      await firstColumnRow.hover();
      const hoverBackgrounds = await firstColumnRow.locator(':scope > th, :scope > td').evaluateAll(cells =>
        cells.slice(0, 2).map(cell => getComputedStyle(cell).backgroundColor),
      );
      assert.equal(hoverBackgrounds[0], hoverBackgrounds[1]);
      assert.equal(
        await page.locator('[data-seg="columns-table"] [data-mode="issue"] .c').innerText(),
        String(profile.columns.filter(column => issueFields.has(column.id)).length),
      );

      await tableChecks(page, profile, observedFields, name + ' dark');

      // Overview layout: Quality observations over Signals on two thirds, Column types beside them.
      const boxes = await page.evaluate(() => {
        const box = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; };
        return { quality: box('.ov-grid .quality'), signals: box('.ov-grid .signals'), types: box('.ov-grid .types') };
      });
      assert.ok(boxes.quality.y < boxes.signals.y, name + ': Signals sit under Quality observations');
      if (width > 1080) {
        assert.ok(boxes.quality.w > 1.7 * boxes.types.w, name + ': Quality observations take two thirds');
        assert.ok(Math.abs(boxes.quality.w - boxes.signals.w) <= 1, name + ': Signals share that width');
        assert.ok(boxes.types.x > boxes.quality.x + boxes.quality.w - 1, name + ': Column types are beside them');
      } else {
        assert.ok(Math.abs(boxes.quality.w - boxes.types.w) <= 1, name + ': one column on a narrow screen');
      }
      // Overview: the KPIs add up to the columns, a popover opens on the columns behind a
      // figure, stays inside the screen, closes with Escape and gives the focus back.
      const kpis = await page.locator('.quality .kpi-n').allInnerTexts();
      assert.equal(kpis.map(text => Number(text.replace(/,/g, ''))).reduce((a, b) => a + b, 0), profile.columns.length);
      const firstPop = page.locator('.signals .pop-btn').first();
      if (await firstPop.count()) {
        const wanted = Number((await firstPop.innerText()).replace(/[^0-9]/g, ''));
        await firstPop.click();
        assert.equal(await firstPop.getAttribute('aria-expanded'), 'true');
        const dialog = page.locator('.pop:not([hidden])');
        await dialog.waitFor({ state: 'visible' });
        assert.equal(await dialog.count(), 1);
        assert.equal(await dialog.locator('.pop-cols li').count(), wanted);
        const popBox = await dialog.boundingBox();
        assert.ok(popBox.x >= 0 && popBox.x + popBox.width <= width + 1, name + ': popover inside the width ' + JSON.stringify(popBox));
        assert.ok(popBox.y >= 0 && popBox.y + popBox.height <= height + 1, name + ': popover inside the height ' + JSON.stringify(popBox));
        await page.keyboard.press('Escape');
        assert.equal(await page.locator('.pop:not([hidden])').count(), 0);
        assert.equal(await firstPop.getAttribute('aria-expanded'), 'false');
        assert.ok(await page.evaluate(() => document.activeElement.classList.contains('pop-btn')));
      }
      assert.ok(await page.evaluate(() => Boolean(
        document.getElementById('summary').compareDocumentPosition(document.getElementById('observations')) & Node.DOCUMENT_POSITION_FOLLOWING,
      )));

      const percent = page.locator('.pct .l').first();
      assert.equal(await percent.evaluate(el => getComputedStyle(el).justifyContent), 'space-between');
      assert.equal(await percent.evaluate(el => getComputedStyle(el).textAlign), 'left');
      const percentLayout = await percent.evaluate(el => {
        const box = el.getBoundingClientRect();
        const count = el.querySelector('small').getBoundingClientRect();
        return {
          countRightGap: Math.abs(box.right - count.right),
          countIsRightOfCenter: count.left > box.left + box.width / 2,
        };
      });
      assert.ok(percentLayout.countRightGap <= 1, JSON.stringify(percentLayout));
      assert.equal(percentLayout.countIsRightOfCenter, true);

      await page.locator('[data-seg="columns-table"] [data-mode="issue"]').click();
      const expectedIssues = profile.columns.filter(column => issueFields.has(column.id));
      assert.deepEqual(await visibleRows(page, 'columns-table'), expectedIssues.map(column => column.name));

      const firstIssue = expectedIssues[0];
      await page.locator('[data-search="columns-table"]').fill(firstIssue.name);
      assert.deepEqual(await visibleRows(page, 'columns-table'), [firstIssue.name]);
      await resetTable(page, 'columns-table');
      assert.equal(await page.locator('[data-search="columns-table"]').inputValue(), '');
      assert.equal(await page.locator('#columns-table tbody tr:not([hidden])').count(), profile.columns.length);

      const missingSort = page.locator('#columns-table thead th').nth(1).locator('.hb-s');
      await missingSort.click();
      const ascending = await page.locator('#columns-table tbody tr').evaluateAll(rows =>
        rows.map(row => Number(row.cells[1].dataset.v)),
      );
      assert.deepEqual(ascending, [...ascending].sort((a, b) => a - b));
      await missingSort.click();
      const descending = await page.locator('#columns-table tbody tr').evaluateAll(rows =>
        rows.map(row => Number(row.cells[1].dataset.v)),
      );
      assert.deepEqual(descending, [...descending].sort((a, b) => b - a));
      await resetTable(page, 'columns-table');

      const numericMenu = await openFilter(page, 'columns-table', 1);
      await numericMenu.locator('[data-op="greater"]').click();
      await numericMenu.locator('.fm-a').fill('5');
      await page.keyboard.press('Escape');
      const expectedMissing = profile.columns.filter(column => column.missing_percent > 5);
      assert.deepEqual(await visibleRows(page, 'columns-table'), expectedMissing.map(column => column.name));
      await resetTable(page, 'columns-table');

      if (profile.date_summary) {
        // The ambiguous dates are one tile of the signals: the sum of the date columns.
        const tile = page.locator('.signals .sig').filter({ hasText: 'Ambiguous dates' }).first();
        if (profile.date_summary.ambiguous_count > 0) {
          assert.equal(
            await tile.locator('.sig-n').innerText(),
            profile.date_summary.ambiguous_count.toLocaleString('en-US'),
          );
        }
        const formatCell = page.locator('#date-table .fmt').first();
        await formatCell.hover();
        await formatCell.locator('.tip').waitFor({ state: 'visible' });
      }

      const variantGroups = profile.columns.reduce(
        (total, column) => total + column.normalization.variant_groups.length, 0,
      );
      assert.equal(await page.locator('#variant-table tbody tr').count(), variantGroups);
      assert.equal(
        await page.locator('#structure-table tbody tr').count(),
        profile.structure ? profile.structure.fields.length : 0,
      );
      const measures = observations ? observations.limits.filter(mine) : [];
      const diagnostics = report.diagnostics.filter(item => !item.dataset || item.dataset === profile.id);
      assert.equal(
        await page.locator('#limits').count(),
        measures.length || diagnostics.length || base.structure.untracked_observations
          || base.structure.depth_truncated_observations ? 1 : 0,
      );

      // Observations: one row per listed finding, paged by 25 and shown by
      // keyboard; the status is written, never only colored.
      const shownFindings = Math.min(listed.length, 500);
      assert.equal(await page.locator('#observation-table tbody tr').count(), shownFindings);
      assert.equal(
        await page.locator('#observation-table tbody tr:not([hidden])').count(),
        Math.min(shownFindings, 25),
      );
      if (shownFindings > 25) {
        const pager = page.locator('[data-more="observation-table"]');
        await pager.focus();
        await page.keyboard.press('Enter');
        assert.equal(
          await page.locator('#observation-table tbody tr:not([hidden])').count(),
          Math.min(shownFindings, 50),
        );
      }
      if (shownFindings) {
        assert.ok((await page.locator('#observation-table tbody tr .st').first().innerText()).length > 0);
        assert.ok((await page.locator('#observation-table tbody tr .acc').first().innerText()).length > 0);
      }

      // Data sample: the rows of the document, in three labelled parts.
      assert.equal(await page.locator('#sample-table tbody tr').count(), Math.min(sampleRows.length, 300));
      const parts = await page.locator('#sample-table tbody tr td:nth-child(2)').allInnerTexts();
      assert.ok(parts.every(text => ['Start', 'Sampled', 'End'].some(word => text.includes(word))));

      // Escaping: nothing of the data runs, and tags in values stay text.
      assert.equal(await page.evaluate(() => document.querySelectorAll('.dtable td script, .dtable td img').length), 0);

      const firstPanel = page.locator('#overview');
      const collapse = firstPanel.locator('.collapse');
      await collapse.click();
      assert.equal(await firstPanel.locator('.pbody').isHidden(), true);
      await collapse.click();
      assert.equal(await firstPanel.locator('.pbody').isVisible(), true);

      await page.locator('#theme-toggle').click();
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
      await page.reload({ waitUntil: 'load' });
      await page.waitForFunction(() =>
        document.querySelector('#columns-table tbody tr')?.dataset.i === '0',
      );
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
      await tableChecks(page, profile, observedFields, name + ' light');
      await fs.mkdir(artifactsDirectory, { recursive: true });
      await page.locator('#summary').screenshot({
        path: path.join(artifactsDirectory, 'report-summary-' + name + '-light.png'),
      });
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth),
        false,
        name + ' light: no sideways scroll of the page',
      );
      await page.locator('#theme-toggle').click();

      const menu = await openFilter(page, 'columns-table', 0);
      const box = await menu.boundingBox();
      assert.ok(box.x >= 0 && box.x + box.width <= width + 1, JSON.stringify(box));
      assert.ok(box.y >= 0 && box.y + box.height <= height + 1, JSON.stringify(box));
      await page.keyboard.press('Escape');

      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth),
        false,
      );
      assert.equal(await page.evaluate(() => Boolean(globalThis.__tabalystXss)), false);
      await fs.mkdir(artifactsDirectory, { recursive: true });
      await page.screenshot({
        path: path.join(artifactsDirectory, 'report-' + name + '.png'),
        fullPage: false,
      });
      await page.locator('#summary').screenshot({
        path: path.join(artifactsDirectory, 'report-summary-' + name + '-dark.png'),
      });
      console.log(name + ': layout, Summary table (identity, filters, sorts), Columns table and both themes passed');
      await page.close();
    }
    assert.deepEqual(errors, []);
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

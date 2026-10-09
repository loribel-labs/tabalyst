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
      ['mobile', 390, 844],
    ]) {
      const page = await browser.newPage({ viewport: { width, height } });
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
        assert.equal(
          await page.locator('.focus .big').innerText(),
          profile.date_summary.ambiguous_count.toLocaleString('en-US'),
        );
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
      console.log(name + ': layout, JSON-backed issue state, filters and percentage alignment passed');
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

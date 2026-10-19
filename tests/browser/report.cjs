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

  // The "With errors" segment keeps the columns whose Errors list holds a finding.
  const withErrors = rows.filter(row => row.errors === 'detected');
  const errorSegment = page.locator('[data-seg="summary-table"] [data-mode="error"]');
  if (withErrors.length) assert.equal(await errorSegment.count(), 1, label + ': the segment exists');
  if (await errorSegment.count()) {
    assert.equal(await errorSegment.locator('.c').innerText(), String(withErrors.length), label + ': With errors count');
    await errorSegment.click();
    assert.deepEqual(await visibleRows(page, 'summary-table'), withErrors.map(row => row.name), label + ': With errors rows');
    await page.locator('[data-seg="summary-table"] [data-mode="all"]').click();
    await resetTable(page, 'summary-table');
  }

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

// The detail of a Findings row (R12): reachable by keyboard focus, printed from the stored member,
// and kept inside the screen. `expect` gives the chips of the cell and the figures the hover holds.
async function findingDetailCheck(page, label, width, column, rule, expect) {
  // The table shows 25 findings at a time: filter to the column so that its row is on the page.
  const filter = page.locator('#observations input[placeholder="Filter findings"]');
  await filter.fill(column.name);
  const row = page.locator('#observations tbody tr', { has: page.locator('code', { hasText: new RegExp('^' + column.name + '$') }) })
    .filter({ hasText: rule });
  const cell = row.locator('td.c-vd');
  await cell.scrollIntoViewIfNeeded();
  assert.deepEqual(await cell.locator('.vpre .exv').evaluateAll(els => els.map(el => el.firstChild.textContent)), expect.chips, label + ': ' + rule + ' previews its first items');
  // Reached by the Tab key: the popup opens on :focus-visible, which a script focus does not give.
  await cell.focus();
  await page.keyboard.press('Shift+Tab');
  for (let step = 0; step < 3 && !(await cell.evaluate(el => el === document.activeElement)); step++) await page.keyboard.press('Tab');
  assert.ok(await cell.evaluate(el => el === document.activeElement), label + ': the Tab key reaches the ' + rule + ' cell');
  const tip = cell.locator('.tip');
  await tip.waitFor({ state: 'visible' });
  const box = await tip.boundingBox();
  const text = await tip.evaluate(el => el.textContent);
  for (const part of expect.text) assert.ok(text.includes(part), label + ': the ' + rule + ' hover holds "' + part + '"');
  assert.ok(box && box.x >= -1 && box.x + box.width <= width + 1, label + ': the ' + rule + ' hover stays inside the screen');
  await page.keyboard.press('Tab');
  await filter.fill('');
}

async function findingDetailChecks(page, profile, label, width) {
  const count = number => number.toLocaleString('en-US');
  const visible = text => text.replace(/ /g, '\u00b7').replace(/\t/g, '\u2192');
  const withDates = profile.columns.find(item => item.summary.finding_details.dates);
  if (withDates) {
    const dates = withDates.summary.finding_details.dates;
    const first = dates.candidates[0];
    await findingDetailCheck(page, label, width, withDates, 'ambiguous_dates', {
      chips: first.formats,
      text: [first.formats.join(' or '), count(first.count), ...dates.readings.map(item => count(item.count)), 'No order was chosen'],
    });
  }
  const withLengths = profile.columns.find(item => item.summary.finding_details.lengths);
  if (withLengths) {
    const lengths = withLengths.summary.finding_details.lengths;
    const words = item => item.length + (item.length === 1 ? ' character' : ' characters');
    await findingDetailCheck(page, label, width, withLengths, 'minority_length', {
      chips: lengths.lengths.slice(0, 2).map(words),
      text: [
        words(lengths.dominant), count(lengths.dominant.count),
        ...lengths.lengths.flatMap(item => [words(item), count(item.count), ...item.examples.map(example => example.value)]),
      ],
    });
  }
  const withTypes = profile.columns.find(item => item.summary.finding_details.types);
  if (withTypes) {
    const types = withTypes.summary.finding_details.types;
    const words = { integer: 'Integers', number: 'Numbers', date: 'Dates', boolean: 'Booleans', text: 'Text' };
    const share = item => (Math.round(10000 * item.count / types.total) / 100).toString() + '%';
    await findingDetailCheck(page, label, width, withTypes, 'mixed_types', {
      chips: types.types.slice(0, 2).map(item => (words[item.type] || item.type) + ' ' + share(item)),
      text: ['Values by technical type', 'Closest type', ...types.types.map(item => count(item.count))],
    });
  }
  // Whitespace: the marks are written at the render, the stored value is the raw one.
  const withSpaces = profile.columns.find(item => {
    const detail = item.summary.finding_details.whitespace;
    return detail && detail.stages.some(stage => stage.stage === 'trim') && detail.examples.some(example => example.kind !== 'repeated');
  });
  if (withSpaces) {
    const examples = withSpaces.summary.finding_details.whitespace.examples.filter(example => example.kind !== 'repeated');
    await findingDetailCheck(page, label, width, withSpaces, 'trimmed_cells', {
      chips: examples.slice(0, 2).map(example => visible(example.value)),
      text: ['Surrounding whitespace', 'Marks show the whitespace', ...examples.map(example => visible(example.value))],
    });
  }
}

// The previews of the Errors and the Issues (R9b): reachable by keyboard and touch, never by
// hover or colour alone, readable in both themes, and kept inside the screen.
async function previewChecks(page, label, width, height) {
  const table = '#summary-table tbody';
  assert.equal(await page.locator(table + ' td.c-fl[title], ' + table + ' td.c-fl [title]').count(), 0, label + ': no state lives in a title');
  const buttons = page.locator(table + ' .fl-btn');
  assert.ok(await buttons.count() > 0, label + ': findings are buttons');
  const first = buttons.first();
  await first.scrollIntoViewIfNeeded();
  // One dialog serves every preview (contract 20.6): closed and empty until a button opens it.
  assert.equal(await page.locator('[role="dialog"]').count(), 1, label + ': one dialog in the page');
  assert.equal(await page.locator('.pop:not([hidden])').count(), 0, label + ': the dialog starts closed');
  assert.equal(await page.locator('#pop').evaluate(el => el.childElementCount), 0, label + ': the dialog starts empty');
  assert.ok(await first.evaluate(button => document.getElementById(button.getAttribute('data-pop')) instanceof HTMLTemplateElement), label + ': the button names a template');
  assert.ok(await first.locator('.vh').count(), label + ': the class is written, not only coloured');

  // Keyboard: Enter opens, the focus moves into the dialog, Tab walks it and leaves it at the end.
  await first.focus();
  await page.keyboard.press('Enter');
  const dialog = page.locator('.pop:not([hidden])');
  await dialog.waitFor({ state: 'visible' });
  assert.equal(await first.getAttribute('aria-expanded'), 'true', label);
  assert.equal(await dialog.getAttribute('role'), 'dialog', label);
  assert.ok(await dialog.evaluate(el => el === document.activeElement), label + ': focus enters the dialog');
  const text = await dialog.innerText();
  for (const word of ['Counted in', 'Accuracy']) assert.ok(text.includes(word), label + ': ' + word);
  const box = await dialog.boundingBox();
  assert.ok(box.x >= 0 && box.x + box.width <= width + 1, label + ': dialog inside the width ' + JSON.stringify(box));
  assert.ok(box.y >= 0 && box.y + box.height <= height + 1, label + ': dialog inside the height ' + JSON.stringify(box));
  await page.keyboard.press('Tab');
  assert.ok(await page.evaluate(() => document.activeElement.classList.contains('pop-x')), label + ': Tab reaches Close');
  for (let step = 0; step < 40 && (await page.locator('.pop:not([hidden])').count()); step += 1) await page.keyboard.press('Tab');
  assert.equal(await page.locator('.pop:not([hidden])').count(), 0, label + ': Tab past the end closes the dialog');
  assert.equal(await first.getAttribute('aria-expanded'), 'false', label);
  // the focus carries on from the page, it is not lost
  assert.ok(await page.evaluate(() => document.activeElement !== document.body), label + ': focus is kept');

  // Escape closes and gives the focus back.
  await first.focus();
  await page.keyboard.press('Space');
  await page.locator('.pop:not([hidden])').waitFor({ state: 'visible' });
  await page.keyboard.press('Escape');
  assert.equal(await page.locator('.pop:not([hidden])').count(), 0, label);
  assert.ok(await first.evaluate(el => el === document.activeElement), label + ': Escape gives the focus back');

  // Shift+Tab out of the dialog closes it too.
  await first.focus();
  await page.keyboard.press('Enter');
  await page.locator('.pop:not([hidden])').waitFor({ state: 'visible' });
  await page.keyboard.press('Shift+Tab');
  assert.equal(await page.locator('.pop:not([hidden])').count(), 0, label + ': Shift+Tab out closes');

  // Close button and click outside.
  await first.click();
  await page.locator('.pop:not([hidden]) .pop-x').click();
  assert.equal(await page.locator('.pop:not([hidden])').count(), 0, label + ': Close closes');
  await first.click();
  await page.mouse.click(2, 2);
  assert.equal(await page.locator('.pop:not([hidden])').count(), 0, label + ': a click outside closes');

  // A state without finding explains itself check by check; "+N more" holds the other findings.
  const state = page.locator(table + ' .fl-state-btn').first();
  if (await state.count()) {
    await state.scrollIntoViewIfNeeded();
    await state.click();
    assert.ok(await page.locator('.pop:not([hidden]) .pv-checks li').count() > 0, label + ': the state lists its checks');
    await page.keyboard.press('Escape');
  }
  const more = page.locator(table + ' .fl-more .fl-btn').first();
  if (await more.count()) {
    await more.scrollIntoViewIfNeeded();
    const wanted = Number((await more.innerText()).replace(/[^0-9]/g, ''));
    await more.click();
    assert.equal(await page.locator('.pop:not([hidden]) .pv').count(), wanted, label + ': +N more previews N findings');
    await page.keyboard.press('Escape');
  }

  // Contrast of the words the cells print (WCAG AA, 4.5:1; 3:1 for a large figure), as rendered.
  const ratios = await page.evaluate(() => {
    const channels = text => text.match(/[\d.]+/g).map(Number);
    const linear = value => { const c = value / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; };
    const lum = ([r, g, b]) => 0.2126 * linear(r) + 0.7152 * linear(g) + 0.0722 * linear(b);
    const backdrop = el => {
      for (let node = el; node; node = node.parentElement) {
        const [r, g, b, a = 1] = channels(getComputedStyle(node).backgroundColor);
        if (a > 0.9) return [r, g, b];
      }
      return [255, 255, 255];
    };
    const ratio = el => {
      const fore = lum(channels(getComputedStyle(el).color));
      const back = lum(backdrop(el));
      return (Math.max(fore, back) + 0.05) / (Math.min(fore, back) + 0.05);
    };
    const selectors = ['#summary-table .fl-error .fl-btn', '#summary-table .fl-issue .fl-btn', '#summary-table .fl-more .fl-btn',
      '#summary-table .fl-caveat', '#summary-table .fl-state-btn', '#summary-table .fl-state', '.fkpi .fk-n', '.flist .fl-c'];
    return selectors.map(selector => [selector, document.querySelector(selector)])
      .filter(([, el]) => el)
      .map(([selector, el]) => [selector, Math.round(ratio(el) * 100) / 100]);
  });
  assert.ok(ratios.length >= 3, label + ': the contrast probes found their elements');
  for (const [selector, ratio] of ratios) {
    assert.ok(ratio >= (selector.endsWith('.fk-n') ? 3 : 4.5), label + ': contrast of ' + selector + ' is ' + ratio);
  }
}

// Touch: a tap opens the dialog, which sits inside the screen; a tap on Close or outside shuts it.
async function touchChecks(browser, file, label, width, height) {
  const context = await browser.newContext({ viewport: { width, height }, hasTouch: true, isMobile: true, colorScheme: 'dark' });
  const page = await context.newPage();
  await page.goto(pathToFileURL(path.resolve(file)).href, { waitUntil: 'load' });
  const button = page.locator('#summary-table tbody .fl-btn').first();
  await button.scrollIntoViewIfNeeded();
  await button.tap();
  const dialog = page.locator('.pop:not([hidden])');
  await dialog.waitFor({ state: 'visible' });
  const box = await dialog.boundingBox();
  assert.ok(box.x >= 0 && box.x + box.width <= width + 1, label + ': dialog inside the width ' + JSON.stringify(box));
  assert.ok(box.y >= 0 && box.y + box.height <= height + 1, label + ': dialog inside the height ' + JSON.stringify(box));
  const target = await page.locator('.pop:not([hidden]) .pop-x').boundingBox();
  assert.ok(target.height >= 24 && target.width >= 24, label + ': Close is at least 24 by 24 px');
  await page.locator('.pop:not([hidden]) .pop-x').tap();
  assert.equal(await page.locator('.pop:not([hidden])').count(), 0, label + ': a tap on Close closes');
  await page.locator('#summary-table tbody .fl-btn').first().scrollIntoViewIfNeeded();
  const small = await button.boundingBox();
  assert.ok(small.height >= 24, label + ': the label is a target of at least 24 px');
  await button.tap();
  await page.locator('.pop:not([hidden])').waitFor({ state: 'visible' });
  await page.touchscreen.tap(width - 4, 4);
  assert.equal(await page.locator('.pop:not([hidden])').count(), 0, label + ': a tap outside closes');
  await context.close();
}

async function openFilter(page, table, index) {
  await page.keyboard.press('Escape');
  await page.locator('#' + table + ' thead th').nth(index).locator('.hb-f').click();
  const menu = page.locator('.fmenu');
  await menu.waitFor({ state: 'visible' });
  return menu;
}

// The column page (contract docs/dev/report/column-page.md): the blocks in order, the finding
// cards, keyboard and touch, no sideways scroll at four sizes and in both themes. Skipped when
// the report was written without --details.
async function columnPageChecks(browser, reportFile) {
  const directory = path.join(path.dirname(reportFile), path.basename(reportFile, path.extname(reportFile)));
  let pages;
  try {
    pages = (await fs.readdir(directory)).filter(name => /^col-\d+-.*\.html$/.test(name)).sort();
  } catch (error) {
    pages = [];
  }
  if (!pages.length) {
    console.log('column page: skipped, the report has no column pages (--details)');
    return;
  }
  const withFindings = [];
  for (const name of pages) {
    const text = await fs.readFile(path.join(directory, name), 'utf8');
    if (text.includes('class="fnd fnd-')) withFindings.push(name);
  }
  const file = withFindings.find(name => name.includes('postal')) || withFindings[0] || pages[0];
  const url = pathToFileURL(path.join(directory, file)).href;
  for (const [name, width, height] of [
    ['desktop', 1440, 1050],
    ['zoom200', 720, 525],
    ['tablet', 820, 1180],
    ['mobile', 390, 844],
  ]) {
    for (const scheme of ['dark', 'light']) {
      const label = 'column page ' + name + ' ' + scheme;
      const context = await browser.newContext({
        viewport: { width, height }, colorScheme: scheme, hasTouch: name === 'mobile', isMobile: name === 'mobile',
      });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(url);
      assert.equal(
        await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth),
        false, label + ': no sideways scroll of the page',
      );
      const ids = await page.locator('main > section.panel').evaluateAll(els => els.map(el => el.id));
      const order = ['summary', 'findings', 'values', 'shape', 'formats', 'cleaning', 'limits', 'scan-evidence', 'sample'];
      assert.deepEqual(ids, order.filter(id => ids.includes(id)), label + ': blocks in order');
      assert.deepEqual(ids.slice(0, 3), ['summary', 'findings', 'values'], label);
      assert.equal(await page.locator('h1').count(), 1, label + ': one h1');

      // The state is written, never only colored: a class word on every finding card.
      const cards = page.locator('article.fnd');
      for (let i = 0; i < await cards.count(); i += 1) {
        const word = (await cards.nth(i).locator('.fcls').innerText()).trim().toLowerCase();
        assert.ok(['error', 'issue'].includes(word), label + ': card class word ' + word);
        assert.ok((await cards.nth(i).locator('h3').innerText()).length > 0, label);
      }

      // Disclosures are native: Enter on the summary opens them, and the group is reachable.
      const group = page.locator('#findings details.dsc').first();
      if (await group.count()) {
        await group.locator('summary').focus();
        assert.equal(await group.evaluate(el => el.open), false, label + ': folded at the start');
        await page.keyboard.press('Enter');
        assert.equal(await group.evaluate(el => el.open), true, label + ': Enter opens the group');
        const box = await group.locator('summary').boundingBox();
        assert.ok(box.height >= 44, label + ': disclosure head is at least 44 px');
      }

      // The side bar follows the page and its targets are fingers wide on a small screen.
      await page.locator('#limits').scrollIntoViewIfNeeded();
      await page.waitForFunction(() => document.querySelector('.rep-tab[aria-current="true"]') !== null);
      if (width <= 860) {
        const tab = await page.locator('.rep-tab').first().boundingBox();
        assert.ok(tab.height >= 44, label + ': tab target is at least 44 px');
      }
      await page.keyboard.press('Tab');
      assert.equal(await page.locator('a.skip').count(), 1, label + ': skip link');

      // Print opens the folded groups.
      await page.emulateMedia({ media: 'print' });
      await page.evaluate(() => window.dispatchEvent(new Event('beforeprint')));
      assert.equal(
        await page.evaluate(() => document.querySelectorAll('details.dsc:not([open])').length), 0,
        label + ': every group is open on paper',
      );
      assert.deepEqual(errors, [], label);
      if (scheme === 'dark') {
        await fs.mkdir(artifactsDirectory, { recursive: true });
        await page.screenshot({ path: path.join(artifactsDirectory, 'column-page-' + name + '.png') });
      }
      await context.close();
    }
  }
  console.log('column page: blocks, finding cards, keyboard, touch, print, four sizes and both themes passed');
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
      ['zoom200', 720, 525],
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
      await previewChecks(page, name + ' dark', width, height);
      await findingDetailChecks(page, profile, name + ' dark', width);

      // Overview layout: the findings card, the list of kinds and Column types side by side
      // on a wide screen, then two columns with Column types below, then one column.
      const boxes = await page.evaluate(() => {
        const box = selector => { const r = document.querySelector(selector).getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; };
        return { findings: box('.ov-grid .fkpi'), list: box('.ov-grid .flist'), types: box('.ov-grid .types') };
      });
      if (width > 1280) {
        assert.ok(Math.abs(boxes.findings.y - boxes.list.y) <= 1 && Math.abs(boxes.list.y - boxes.types.y) <= 1, name + ': three blocks on one row');
        assert.ok(boxes.list.x > boxes.findings.x + boxes.findings.w - 1, name + ': the list is beside the findings card');
        assert.ok(boxes.types.x > boxes.list.x + boxes.list.w - 1, name + ': Column types are beside the list');
      } else if (width > 1080) {
        assert.ok(Math.abs(boxes.findings.y - boxes.list.y) <= 1, name + ': two blocks on the first row');
        assert.ok(boxes.types.y > boxes.findings.y, name + ': Column types are under them');
      } else {
        assert.ok(Math.abs(boxes.findings.w - boxes.types.w) <= 1, name + ': one column on a narrow screen');
      }
      // Overview: the figures count findings, a popover opens on the columns behind a
      // row, stays inside the screen, closes with Escape and gives the focus back.
      const fkpis = await page.locator('.fkpi .fk-n').allInnerTexts();
      assert.equal(fkpis.length, 2);
      const firstPop = page.locator('.flist button.fl-row').first();
      if (await firstPop.count()) {
        const wanted = Number(((await firstPop.locator('.fl-s').innerText()).match(/([0-9,]+) columns?$/) || [])[1].replace(/,/g, ''));
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
        assert.ok(await page.evaluate(() => document.activeElement.classList.contains('fl-row')));
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
        // The ambiguous dates are one row of the list of findings: the sum of the date columns.
        const tile = page.locator('.flist .fl-row').filter({ hasText: 'Ambiguous dates' }).first();
        if (profile.date_summary.ambiguous_count > 0) {
          assert.equal(
            await tile.locator('.fl-n').innerText(),
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
      await previewChecks(page, name + ' light', width, height);
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
      if (name === 'mobile') await touchChecks(browser, process.argv[2], name, width, height);
      console.log(name + ': layout, Summary table (identity, filters, sorts), previews (keyboard, touch, contrast), Columns table and both themes passed');
      await page.close();
    }
    assert.deepEqual(errors, []);
    await columnPageChecks(browser, process.argv[2]);
  } finally {
    await browser.close();
  }
})().catch(error => {
  console.error(error);
  process.exitCode = 1;
});

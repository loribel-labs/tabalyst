// Usage: node tests/browser/report.cjs report.html dataset.json [playwright module]
const { chromium } = require(process.argv[4] || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { pathToFileURL } = require('node:url');

async function displayedColumns(page, expected) {
  await page.waitForFunction(ids => {
    const actual = [...document.querySelectorAll('#columns-table tbody tr[id]')].map(row => row.id);
    return JSON.stringify(actual.sort()) === JSON.stringify([...ids].sort());
  }, expected.map(column => column.id), { timeout: 5000 });
}

async function popup(page, table, index) {
  await page.keyboard.press('Escape');
  await page.locator(`#${table} thead th`).nth(index).locator('.dtcc-button_dropdown').click();
  return page.locator('.dtcc-dropdown:visible').last();
}

async function numberFilter(page, table, index, operator, value, maximum) {
  const menu = await popup(page, table, index);
  if (await menu.locator('.number-filter').count()) {
    await menu.locator(`[data-operator="${operator}"]`).click();
    await menu.locator('input').first().fill(String(value));
    if (maximum !== undefined) await menu.locator('input').last().fill(String(maximum));
  } else {
    await menu.locator('select').selectOption(operator);
    await menu.locator('input').fill(String(value));
  }
  await page.keyboard.press('Escape');
}

async function reset(page, table = 'columns-table') {
  await page.keyboard.press('Escape');
  await page.locator(`[data-reset-table="${table}"]`).click();
}

(async () => {
  const profile = JSON.parse(await fs.readFile(process.argv[3], 'utf8'));
  const browser = await chromium.launch({ headless: true, channel: process.env.TABALYST_BROWSER || 'msedge' });
  const errors = [];
  try {
    for (const [name, width, height] of [['desktop', 1440, 1050], ['mobile', 390, 844]]) {
      const page = await browser.newPage({ viewport: { width, height } });
      page.on('pageerror', error => errors.push(error.message));
      page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
      await page.goto(pathToFileURL(path.resolve(process.argv[2])).href, { waitUntil: 'networkidle' });
      await page.waitForSelector('#columns-table[data-interactive="true"]');
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
      assert.equal(await page.locator('body').evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(7, 10, 24)');
      assert.ok((await page.locator('body').evaluate(el => getComputedStyle(el).fontFamily)).includes('Roboto'));
      assert.ok((await page.locator('h1').evaluate(el => getComputedStyle(el).fontFamily)).includes('Oswald'));
      assert.ok((await page.locator('#columns-table tbody td').first().evaluate(el => getComputedStyle(el).fontFamily)).includes('Consolas'));
      assert.ok((await page.locator('.eyebrow').evaluate(el => getComputedStyle(el).fontFamily)).includes('Caveat'));
      assert.equal(await page.locator('.topbar').evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(0, 5, 26)');
      assert.equal(await page.locator('.footer').evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(0, 5, 26)');
      await page.locator('#theme-toggle').click();
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
      assert.equal(await page.locator('body').evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(255, 255, 255)');
      await page.reload({ waitUntil: 'networkidle' });
      await page.waitForSelector('#columns-table[data-interactive="true"]');
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
      await page.locator('#theme-toggle').click();
      assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
      assert.equal(await page.evaluate(() => DataTable.version), '3.0.4');
      assert.deepEqual(await page.locator('#columns-table thead .dt-column-title').allTextContents(), ['Column', 'Missing (%)', 'Distinct', 'Inferred type', 'Semantic type', 'Error (%)', 'Examples']);
      for (const header of await page.locator('#columns-table thead th:has(.dtcc-button_dropdown)').all()) {
        const positions = await header.evaluate(cell => ({
          filter: cell.querySelector('.dtcc-button_dropdown').getBoundingClientRect().left,
          filterRight: cell.querySelector('.dtcc-button_dropdown').getBoundingClientRect().right,
          label: cell.querySelector('.dt-column-title').getBoundingClientRect().left,
          labelRight: cell.querySelector('.dt-column-title').getBoundingClientRect().right,
          labelAlign: getComputedStyle(cell.querySelector('.dt-column-title')).textAlign,
          sort: cell.querySelector('.dtcc-button_order').getBoundingClientRect().left,
          sortRight: cell.querySelector('.dtcc-button_order').getBoundingClientRect().right,
        }));
        assert.ok(positions.label < positions.filter && positions.filter < positions.sort, JSON.stringify(positions));
        assert.ok(positions.filter - positions.labelRight <= 7 && positions.sort - positions.filterRight <= 7, JSON.stringify(positions));
        assert.equal(positions.labelAlign, 'left');
      }
      const firstHeader = page.locator('#columns-table thead th').first();
      const firstHeaderControls = firstHeader.locator('.dtcc-button_order, .dtcc-button_dropdown');
      assert.deepEqual(await firstHeaderControls.evaluateAll(nodes => nodes.map(node => getComputedStyle(node).opacity)), ['0', '0']);
      await firstHeader.hover();
      await page.waitForFunction(nodes => nodes.every(node => getComputedStyle(node).opacity === '1'), await firstHeaderControls.elementHandles());
      await page.mouse.move(0, 0);
      await page.waitForFunction(nodes => nodes.every(node => getComputedStyle(node).opacity === '0'), await firstHeaderControls.elementHandles());
      const metrics = await page.locator('.metric-grid').innerText();
      assert.deepEqual(
        await page.locator('.quality-metrics dd').allTextContents(),
        [
          profile.summary.empty_row_count,
          profile.summary.empty_column_count,
          profile.summary.trim_count,
          profile.summary.collapse_internal_whitespace_count,
        ].map(value => value.toLocaleString('en-US')),
      );
      await displayedColumns(page, profile.columns);
      const zeroMissing = profile.columns.find(column => column.missing_percent === 0);
      if (zeroMissing) assert.equal((await page.locator(`#${zeroMissing.id} td`).nth(0).innerText()).trim(), '');
      const typeColors = await page.locator('#columns-table tbody tr[id]').evaluateAll(rows => Object.fromEntries(rows.map(row => {
        const badge = row.cells[3].querySelector('.type-badge');
        return [badge.textContent, getComputedStyle(badge).backgroundColor];
      })));
      assert.equal(new Set(Object.values(typeColors)).size, Object.keys(typeColors).length);

      // Explicit column selection uses stable positions, including repeated names.
      let menu = await popup(page, 'columns-table', 0);
      for (const column of profile.columns.slice(0, 2)) {
        await menu.getByRole('checkbox', { name: `#${column.position} ${column.name || '(unnamed)'}`, exact: true }).click();
      }
      await page.keyboard.press('Escape');
      await displayedColumns(page, profile.columns.slice(0, 2));
      await reset(page);
      menu = await popup(page, 'columns-table', 0);
      const last = profile.columns.at(-1);
      await menu.getByRole('checkbox', { name: `#${last.position} ${last.name || '(unnamed)'}`, exact: true }).click();
      await page.keyboard.press('Escape');
      await displayedColumns(page, [last]);
      await reset(page);

      // Type selections combine with OR; different column filters combine with AND.
      const types = [...new Set(profile.columns.map(column => column.inferred_type))].slice(0, 2);
      menu = await popup(page, 'columns-table', 3);
      for (const type of types) {
        const count = profile.columns.filter(column => column.inferred_type === type).length;
        const option = menu.getByRole('checkbox', { name: `${type} (${count})`, exact: true });
        await option.waitFor();
        assert.equal(await option.locator('.type-badge').innerText(), type);
        await option.click();
      }
      await page.keyboard.press('Escape');
      const byType = profile.columns.filter(column => types.includes(column.inferred_type));
      await displayedColumns(page, byType);
      await numberFilter(page, 'columns-table', 1, 'greater', 5);
      const byMissing = byType.filter(column => column.missing_percent > 5);
      await displayedColumns(page, byMissing);
      await numberFilter(page, 'columns-table', 2, 'less', 100);
      await displayedColumns(page, byMissing.filter(column => column.distinct_count < 100));
      await numberFilter(page, 'columns-table', 2, 'greater', 100);
      await displayedColumns(page, byMissing.filter(column => column.distinct_count > 100));
      await reset(page);

      const semantics = [...new Set(profile.columns.map(column => column.semantic_type || '(none)'))].slice(0, 2);
      menu = await popup(page, 'columns-table', 4);
      for (const semantic of semantics) {
        const count = profile.columns.filter(column => (column.semantic_type || '(none)') === semantic).length;
        await menu.getByRole('checkbox', { name: `${semantic} (${count})`, exact: true }).click();
      }
      await page.keyboard.press('Escape');
      await displayedColumns(page, profile.columns.filter(column => semantics.includes(column.semantic_type || '(none)')));
      await reset(page);

      const expanded = profile.columns.find(column => column.value_profile.values.length > profile.config.value_examples.inline_display_size);
      if (expanded) {
        const more = page.locator(`#${expanded.id} .example-more`);
        const marker = expanded.value_profile.selection === 'complete'
          ? `+${expanded.value_profile.values.length - profile.config.value_examples.inline_display_size}`
          : '++';
        assert.equal(await more.innerText(), marker);
        const cell = page.locator(`#${expanded.id} .examples`);
        await cell.hover();
        const tooltip = cell.locator('.examples-tooltip');
        await tooltip.waitFor({ state: 'visible' });
        const totalLabel = expanded.value_profile.selection === 'complete'
          ? String(expanded.value_profile.values.length)
          : `${expanded.value_profile.values.length} / ${expanded.distinct_count.toLocaleString('en-US')}`;
        assert.equal(await tooltip.locator('.examples-tooltip-title span').innerText(), totalLabel);
        const rows = await tooltip.locator('.examples-tooltip-list > div').evaluateAll(nodes => nodes.map(node => ({
          value: node.querySelector('span').textContent,
          count: Number(node.querySelector('small').textContent.replace(/[^0-9]/g, '')),
        })));
        assert.deepEqual(rows, expanded.value_profile.values.map(item => ({ value: item.value, count: item.count })));
        assert.deepEqual(rows.map(row => row.count), [...rows.map(row => row.count)].sort((a, b) => b - a));
        const box = await tooltip.boundingBox();
        const cellBox = await cell.boundingBox();
        assert.ok(box.x >= 0 && box.x + box.width <= width + 1, JSON.stringify(box));
        assert.ok(box.y >= 0 && box.y + box.height <= height + 1, JSON.stringify(box));
        const verticalGap = Math.max(0, box.y - (cellBox.y + cellBox.height), cellBox.y - (box.y + box.height));
        assert.ok(verticalGap <= 1, JSON.stringify({ box, cellBox, verticalGap }));
        await page.mouse.move(box.x + box.width / 2, box.y + Math.min(20, box.height / 2));
        assert.equal(await tooltip.isVisible(), true);
      }

      // Strict greater-than includes a zero threshold and fractional percentages.
      for (const threshold of [0, 0.1, 100]) {
        await numberFilter(page, 'columns-table', 1, 'greater', threshold);
        await displayedColumns(page, profile.columns.filter(column => column.missing_percent > threshold));
      }
      assert.equal(await page.locator('#filter-result').innerText(), `0 of ${profile.columns.length} columns`);
      await reset(page);

      // Inclusive boundaries, zero, incomplete and reversed ranges, and individual clearing.
      const numericColumns = [
        [1, column => column.missing_percent],
        [2, column => column.distinct_count],
        [5, column => column.type_error_percent ?? -1],
      ];
      for (const [index, valueFor] of numericColumns) {
        const boundary = valueFor(profile.columns[0]);
        for (const [operator, compare] of [
          ['equal', value => value === boundary],
          ['greaterOrEqual', value => value >= boundary],
          ['lessOrEqual', value => value <= boundary],
          ['less', value => value < boundary],
        ]) {
          await numberFilter(page, 'columns-table', index, operator, boundary);
          await displayedColumns(page, profile.columns.filter(column => compare(valueFor(column))));
        }
        for (const [low, high] of [[0, boundary], [boundary, boundary], [0, 0]]) {
          await numberFilter(page, 'columns-table', index, 'between', low, high);
          await displayedColumns(page, profile.columns.filter(column => valueFor(column) >= low && valueFor(column) <= high));
        }
        const trigger = page.locator('#columns-table thead th').nth(index).locator('.dtcc-button_dropdown');
        assert.equal(await trigger.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(118, 82, 212)');
        assert.equal(await trigger.evaluate(el => getComputedStyle(el).color), 'rgb(255, 255, 255)');
        assert.equal(await trigger.evaluate(el => getComputedStyle(el).opacity), '1');
        assert.equal(await trigger.locator('svg:visible').evaluate(el => getComputedStyle(el).stroke), 'rgb(255, 255, 255)');
        assert.equal(await trigger.locator('xpath=ancestor::div[contains(@class,"dt-column-header")]/*[contains(@class,"dt-column-title")]').evaluate(el => getComputedStyle(el).textDecorationColor), 'rgb(118, 82, 212)');
        menu = await popup(page, 'columns-table', index);
        await menu.locator('.dtcc-button_searchClear').click();
        await displayedColumns(page, profile.columns);
        assert.equal(await trigger.evaluate(el => el.classList.contains('dtcc-button_active')), false);
        await numberFilter(page, 'columns-table', index, 'between', 0);
        await displayedColumns(page, profile.columns);
        await numberFilter(page, 'columns-table', index, 'between', 100, 0);
        await displayedColumns(page, profile.columns);
        menu = await popup(page, 'columns-table', index);
        assert.equal(await menu.locator('.number-filter-error').isVisible(), true);
        await reset(page);
      }

      // Sorting must use numbers, not formatted strings (e.g. 2,992 vs 31).
      for (const index of [1, 2, 5]) {
        await reset(page);
        const sort = page.locator('#columns-table thead th').nth(index).locator('.dtcc-button_order');
        for (const direction of [1, -1]) {
          await sort.click();
          await page.waitForFunction(({ index, direction }) => {
            const values = [...document.querySelectorAll('#columns-table tbody tr[id]')].map(row => Number(row.cells[index].dataset.order));
            return values.every((value, i) => i === 0 || direction * (value - values[i - 1]) >= 0);
          }, { index, direction }, { timeout: 5000 });
          await sort.waitFor({ state: 'visible' });
          await page.waitForFunction(element => element.classList.contains('dtcc-button_active'), await sort.elementHandle());
          assert.equal(await sort.evaluate(el => getComputedStyle(el).backgroundColor), 'rgb(118, 82, 212)');
          assert.equal(await sort.evaluate(el => getComputedStyle(el).color), 'rgb(255, 255, 255)');
          assert.equal(await sort.locator('xpath=ancestor::div[contains(@class,"dt-column-header")]/*[contains(@class,"dt-column-title")]').evaluate(el => getComputedStyle(el).textDecorationColor), 'rgb(118, 82, 212)');
          const values = await page.locator('#columns-table tbody tr[id]').evaluateAll((rows, i) => rows.map(row => Number(row.cells[i].dataset.order)), index);
          assert.deepEqual(values, [...values].sort((a, b) => direction * (a - b)));
        }
      }
      await reset(page);
      const first = profile.columns[0];
      await page.locator('#column-search').fill(first.name);
      await displayedColumns(page, profile.columns.filter(column => (`#${column.position} ${column.name || '(unnamed)'}`).toLowerCase().includes(first.name.toLowerCase())));
      await reset(page);

      const transformationDetails = page.locator('.transformation-details');
      const transformationReset = transformationDetails.locator('[data-reset-table="transformations-table"]');
      assert.equal(await transformationReset.isVisible(), false);
      await transformationDetails.locator('summary').click();
      assert.deepEqual(
        await page.locator('#transformations-table thead .dt-column-title').allTextContents(),
        ['Column', 'Missing (%)', 'Trimmed (%)', 'Whitespace collapsed (%)', 'Distinct'],
      );
      assert.deepEqual(
        await page.locator('#transformations-table tbody .column-index').allTextContents(),
        profile.columns.map(column => String(column.position)),
      );
      const transformationAlignment = await transformationDetails.evaluate(details => {
        const summaryBox = details.querySelector('summary').getBoundingClientRect();
        const resetBox = details.querySelector('.details-actions').getBoundingClientRect();
        const tableBox = details.querySelector('.secondary-table-wrap').getBoundingClientRect();
        return { titleTop: summaryBox.top, resetTop: resetBox.top, titleBottom: summaryBox.bottom, tableTop: tableBox.top };
      });
      assert.ok(Math.abs(transformationAlignment.titleTop - transformationAlignment.resetTop) <= 3, JSON.stringify(transformationAlignment));
      assert.ok(transformationAlignment.tableTop - transformationAlignment.titleBottom <= 14, JSON.stringify(transformationAlignment));
      await numberFilter(page, 'transformations-table', 2, 'greater', 0);
      const transformedCount = profile.columns.filter(column => column.normalization.trim_percent > 0).length;
      await page.waitForFunction(text => document.querySelector('[data-table-status="transformations-table"]').textContent === text, `${transformedCount} of ${profile.columns.length} columns`);
      await reset(page, 'transformations-table');
      await transformationDetails.screenshot({ path: `artifacts/transformations-${name}.png` });
      await transformationDetails.locator('summary').click();
      assert.equal(await transformationReset.isVisible(), false);

      if (profile.columns.some(column => column.numeric)) {
        const numericReset = page.locator('.numeric-details [data-reset-table="numeric-table"]');
        assert.equal(await numericReset.isVisible(), false);
        await page.locator('.numeric-details summary').click();
        assert.deepEqual(
          await page.locator('#numeric-table tbody .column-index').allTextContents(),
          profile.columns.filter(column => column.numeric).map(column => String(column.position)),
        );
        const alignment = await page.locator('.numeric-details').evaluate(details => {
          const summaryBox = details.querySelector('summary').getBoundingClientRect();
          const resetBox = details.querySelector('.details-actions').getBoundingClientRect();
          return { titleTop: summaryBox.top, resetTop: resetBox.top };
        });
        assert.ok(Math.abs(alignment.titleTop - alignment.resetTop) <= 3, JSON.stringify(alignment));
        const numericCount = profile.columns.filter(column => column.numeric).length;
        await numberFilter(page, 'numeric-table', 1, 'greater', 0);
        const expected = profile.columns.filter(column => column.numeric && column.numeric.minimum > 0).length;
        await page.waitForFunction(text => document.querySelector('[data-table-status="numeric-table"]').textContent === text, `${expected} of ${numericCount} columns`);
        await reset(page, 'numeric-table');
        await page.locator('.numeric-details summary').click();
        assert.equal(await numericReset.isVisible(), false);
      }

      const dateColumns = profile.columns.filter(column => column.date_profile);
      if (dateColumns.length) {
        const dateReset = page.locator('.date-details [data-reset-table="date-table"]');
        assert.equal(await dateReset.isVisible(), false);
        await page.locator('.date-details summary').click();
        assert.deepEqual(
          await page.locator('#date-table thead .dt-column-title').allTextContents(),
          ['Column', 'Status', 'Valid (%)', 'Ambiguous (%)', 'Invalid (%)', 'Other (%)', 'Formats'],
        );
        assert.deepEqual(
          await page.locator('#date-table tbody .column-index').allTextContents(),
          dateColumns.map(column => String(column.position)),
        );
        await numberFilter(page, 'date-table', 2, 'greater', 0);
        const expected = dateColumns.filter(column => column.date_profile.valid_count > 0).length;
        await page.waitForFunction(text => document.querySelector('[data-table-status="date-table"]').textContent === text, `${expected} of ${dateColumns.length} date columns`);
        await reset(page, 'date-table');
        const firstDate = dateColumns[0];
        const formatCell = page.locator('#date-table tbody tr').first().locator('.date-formats-cell');
        const variantLabel = `${firstDate.date_profile.format_count} variant${firstDate.date_profile.format_count === 1 ? '' : 's'}`;
        assert.equal(await formatCell.locator('.date-format-count').innerText(), variantLabel);
        await formatCell.hover();
        const formatTooltip = formatCell.locator('.date-formats-tooltip');
        await formatTooltip.waitFor({ state: 'visible' });
        assert.equal(await formatTooltip.locator('.examples-tooltip-title').innerText(), variantLabel);
        const formatRows = await formatTooltip.locator('.examples-tooltip-list > div').evaluateAll(nodes => nodes.map(node => ({
          label: node.querySelector('span').textContent,
          count: Number(node.querySelector('small').textContent.split(' ')[0].replace(/[^0-9]/g, '')),
          percent: Number(node.querySelector('small').textContent.match(/\(([-0-9.]+)%\)/)[1]),
        })));
        assert.deepEqual(formatRows, firstDate.date_profile.breakdown.map(item => ({
          label: item.label,
          count: item.count,
          percent: item.percent,
        })));
        assert.deepEqual(formatRows.slice(-2).map(item => item.label), ['Invalid date', 'Not a date']);
        assert.equal(await formatTooltip.locator('.date-breakdown-invalid').evaluate(el => getComputedStyle(el).borderTopWidth), '2px');
        await page.locator('.date-details').screenshot({ path: `artifacts/dates-${name}.png` });
        await page.locator('.date-details summary').click();
        assert.equal(await dateReset.isVisible(), false);
      }

      const stringColumns = profile.columns.filter(column => column.string_profile);
      if (stringColumns.length) {
        const stringDetails = page.locator('.string-details');
        const stringReset = stringDetails.locator('[data-reset-table="string-table"]');
        assert.equal(await stringReset.isVisible(), false);
        await stringDetails.locator('summary').click();
        assert.deepEqual(
          await page.locator('#string-table thead .dt-column-title').allTextContents(),
          ['Column', 'Status', 'Fixed length', 'Length min', 'Length max'],
        );
        assert.deepEqual(
          await page.locator('#string-table tbody .column-index').allTextContents(),
          stringColumns.map(column => String(column.position)),
        );
        const fixedColumnIndex = stringColumns.findIndex(column => column.string_profile.status === 'fixed');
        if (fixedColumnIndex >= 0) {
          const cells = page.locator('#string-table tbody tr').nth(fixedColumnIndex).locator('td');
          assert.equal(await cells.nth(1).innerText(), String(stringColumns[fixedColumnIndex].string_profile.minimum_length));
          assert.equal(await cells.nth(2).innerText(), '');
          assert.equal(await cells.nth(3).innerText(), '');
        }
        await numberFilter(page, 'string-table', 4, 'greater', 20);
        const expected = stringColumns.filter(column => column.string_profile.maximum_length > 20).length;
        await page.waitForFunction(text => document.querySelector('[data-table-status="string-table"]').textContent === text, `${expected} of ${stringColumns.length} string columns`);
        await reset(page, 'string-table');
        await stringDetails.screenshot({ path: `artifacts/strings-${name}.png` });
        await stringDetails.locator('summary').click();
        assert.equal(await stringReset.isVisible(), false);
      }

      if (profile.preview.length) {
        await numberFilter(page, 'sample-table', 0, 'greater', 5);
        const expected = profile.preview.filter(row => row.row_number > 5).length;
        await page.waitForFunction(text => document.querySelector('[data-table-status="sample-table"]').textContent === text, `${expected} of ${profile.preview.length} sample rows`);
        await reset(page, 'sample-table');
        const sort = page.locator('#sample-table thead th').first().locator('.dtcc-button_order');
        await sort.click();
        await sort.click();
        await page.waitForFunction(last => Number(document.querySelector('#sample-table tbody tr').cells[0].textContent) === last, profile.preview.at(-1).row_number);
        const numbers = await page.locator('#sample-table tbody tr').evaluateAll(rows => rows.map(row => Number(row.cells[0].textContent)));
        assert.deepEqual(numbers, profile.preview.map(row => row.row_number).reverse());
        await reset(page, 'sample-table');
      }
      await displayedColumns(page, profile.columns);
      assert.equal(await page.locator('.metric-grid').innerText(), metrics);

      // Capture the checklist itself and ensure its popup fits on small screens.
      menu = await popup(page, 'columns-table', 0);
      const box = await menu.boundingBox();
      assert.ok(box.x >= 0 && box.x + box.width <= width + 1, JSON.stringify(box));
      assert.ok(box.y >= 0 && box.y + box.height <= height + 1, JSON.stringify(box));
      const scrollAreas = await menu.evaluate(el => [el, ...el.querySelectorAll('*')]
        .filter(node => ['auto', 'scroll'].includes(getComputedStyle(node).overflowY) && node.scrollHeight > node.clientHeight)
        .map(node => node.className));
      assert.ok(scrollAreas.length <= 1, JSON.stringify(scrollAreas));
      if (scrollAreas.length) assert.equal(scrollAreas[0], 'dtcc-list-buttons');
      assert.equal(await menu.locator('.dtcc-list-buttons').evaluate(el => getComputedStyle(el).scrollbarWidth), 'thin');
      const backgrounds = await menu.locator('.dtcc-dropdown-liner, .dtcc-list, .dtcc-list-controls, .dtcc-list-buttons, .dtcc-list-buttons button').evaluateAll(nodes => nodes.map(node => getComputedStyle(node).backgroundColor));
      assert.ok(backgrounds.every(color => color === backgrounds[0]), JSON.stringify(backgrounds));
      assert.ok((await menu.locator('input').boundingBox()).height <= 28);
      const filterInput = menu.locator('input').first();
      await filterInput.focus();
      assert.equal(await filterInput.evaluate(el => getComputedStyle(el).borderTopColor), 'rgb(41, 49, 79)');
      assert.equal(await filterInput.evaluate(el => getComputedStyle(el).outlineColor), 'rgb(118, 82, 212)');
      const smallButton = menu.locator('.dtcc-list-selectAll').first();
      await smallButton.hover();
      const smallButtonShadow = await smallButton.evaluate(el => getComputedStyle(el).boxShadow);
      assert.ok(smallButtonShadow.includes('rgb(118, 82, 212)'), smallButtonShadow);
      const handle = menu.locator('.filter-drag-handle');
      const beforeDrag = await menu.boundingBox();
      const handleBox = await handle.boundingBox();
      const targetX = Math.max(24, Math.min(width - beforeDrag.width - 24, beforeDrag.x > 60 ? 24 : beforeDrag.x + 45));
      const targetY = Math.max(24, Math.min(height - beforeDrag.height - 24, beforeDrag.y > 100 ? 24 : beforeDrag.y + 55));
      await page.mouse.move(handleBox.x + handleBox.width / 2, handleBox.y + handleBox.height / 2);
      await page.mouse.down();
      await page.mouse.move(targetX + handleBox.width / 2, targetY + handleBox.height / 2);
      await page.mouse.up();
      const afterDrag = await menu.boundingBox();
      assert.ok(Math.abs(afterDrag.x - beforeDrag.x) > 10 || Math.abs(afterDrag.y - beforeDrag.y) > 10);
      const firstColumn = profile.columns[0];
      await menu.getByRole('checkbox', { name: `#${firstColumn.position} ${firstColumn.name || '(unnamed)'}`, exact: true }).click();
      await displayedColumns(page, [firstColumn]);
      assert.equal(await menu.isVisible(), true);
      const afterFilter = await menu.boundingBox();
      assert.ok(Math.abs(afterFilter.x - afterDrag.x) < 2 && Math.abs(afterFilter.y - afterDrag.y) < 2);
      await reset(page);
      menu = await popup(page, 'columns-table', 0);
      await page.screenshot({ path: `artifacts/filters-${name}.png` });
      await numberFilter(page, 'columns-table', 1, 'between', 0, 25);
      menu = await popup(page, 'columns-table', 1);
      await page.screenshot({ path: `artifacts/numeric-filter-${name}.png` });
      const closeFilter = menu.getByRole('button', { name: 'Close filter' });
      await closeFilter.click();
      await menu.waitFor({ state: 'hidden' });
      assert.equal(await page.locator('#columns-table thead th').nth(1).locator('.dtcc-button_dropdown').getAttribute('aria-expanded'), 'false');
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
      assert.equal(overflow, false);
      assert.equal(await page.evaluate(() => !!globalThis.__tabalystXss), false);
      console.log(`${name}: filters, numeric sorting, reset, row numbers and layout passed`);
      await page.close();
    }
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });

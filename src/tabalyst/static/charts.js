// This Source Code Form is subject to the terms of the Mozilla Public
// License, v. 2.0. If a copy of the MPL was not distributed with this
// file, You can obtain one at https://mozilla.org/MPL/2.0/.

/* Draws the UpSet plots of a chart page with ECharts, from the JSON each section
   inlines (docs/dev/report/chart-pages.md 6). It computes nothing the table does
   not hold: it sorts, filters and draws. */
(() => {
  'use strict';
  const NARROW = 600; // below it the dot matrix is unreadable: one bar per pattern
  const TOP = 190; // height of the bars of the patterns
  const ROW = 26; // height of a column in the matrix
  const sections = Array.from(document.querySelectorAll('[data-upset]'));
  if (!sections.length) return;
  // Without the library (offline, a blocked CDN, a failed hash) the message stays and
  // the tables carry the figures.
  if (!window.echarts) return;

  const root = document.documentElement;
  const css = (name) => getComputedStyle(root).getPropertyValue(name).trim();
  const count = (n) => n.toLocaleString('en-US');
  const share = (part, whole) => (whole ? (100 * part / whole).toFixed(1) + '%' : '0%');

  const palette = () => ({
    bar: css('--orange') || '#f98510',
    dot: css('--text') || '#ddd',
    pale: css('--line-strong') || '#555',
    sets: css('--tb-viz-missing') || '#888',
    text: css('--text-2') || '#bbb',
    faint: css('--text-3') || '#999',
    line: css('--line') || '#333',
    font: css('--f-body') || 'sans-serif',
    mono: css('--f-mono') || 'monospace',
    panel: css('--s1') || '#111',
  });

  const visible = (data, state) => {
    let list = data.patterns.map((p, i) => ({ count: p[0], cols: p[1], i }));
    if (state.show === 'multi') list = list.filter((p) => p.cols.length >= 2);
    else if (state.show.startsWith('col:')) {
      const c = Number(state.show.slice(4));
      list = list.filter((p) => p.cols.includes(c));
    }
    if (state.sort === 'size') list.sort((a, b) => a.cols.length - b.cols.length || b.count - a.count || a.i - b.i);
    return list;
  };

  const tooltip = (data, p) =>
    p.cols.map((c) => data.columns[c]).join(', ') + '<br>' + count(p.count) + ' records, ' + share(p.count, data.records);

  const wide = (data, drawn, width, c) => {
    // The columns of the drawn patterns only, the ones that lack the most first.
    const used = Array.from(new Set(drawn.flatMap((p) => p.cols))).sort((a, b) => data.missing[b] - data.missing[a] || a - b);
    const names = used.map((c2) => data.columns[c2]);
    const rowOf = new Map(used.map((c2, r) => [c2, r]));
    const label = Math.min(200, Math.max(...names.map((n) => n.length), 4) * 7 + 12);
    const sets = Math.max(70, Math.min(160, Math.round(width * 0.16)));
    const left = sets + label + 8;
    const matrixTop = TOP + 28;
    const height = used.length * ROW;
    const x = drawn.map((_, i) => i);
    const cells = [];
    drawn.forEach((p, i) => used.forEach((col, r) => cells.push({ value: [i, r], itemStyle: { color: p.cols.includes(col) ? c.dot : c.pale } })));
    const segments = drawn.map((p, i) => {
      const rows = p.cols.map((col) => rowOf.get(col));
      return [i, Math.min(...rows), Math.max(...rows)];
    });
    const axisText = { color: c.text, fontFamily: c.mono, fontSize: 11 };
    // A count is printed over a bar only where the bars are wide enough to carry it.
    const step = (width - left - 16) / Math.max(drawn.length, 1);
    const labelled = step >= 44 ? 5 : step >= 30 ? 3 : 1;
    return {
      height: matrixTop + height + 24,
      option: {
        animation: false,
        textStyle: { fontFamily: c.font },
        axisPointer: { link: [{ xAxisIndex: [0, 1] }] },
        tooltip: { trigger: 'item', confine: true, backgroundColor: c.panel, borderColor: c.line, textStyle: { color: c.text } },
        grid: [
          { left, right: 16, top: 16, height: TOP - 16 },
          { left, right: 16, top: matrixTop, height },
          { left: 8, width: sets, top: matrixTop, height },
        ],
        xAxis: [
          { gridIndex: 0, type: 'category', data: x, axisLabel: { show: false }, axisTick: { show: false }, axisLine: { lineStyle: { color: c.line } }, axisPointer: { type: 'shadow' } },
          { gridIndex: 1, type: 'category', data: x, show: false, axisPointer: { type: 'shadow' } },
          { gridIndex: 2, type: 'value', inverse: true, splitNumber: 2, axisLabel: { show: false }, splitLine: { show: false } },
        ],
        yAxis: [
          { gridIndex: 0, type: 'value', axisLabel: { ...axisText, formatter: (v) => count(v) }, splitLine: { lineStyle: { color: c.line } } },
          { gridIndex: 1, type: 'category', data: names, inverse: true, axisLabel: { ...axisText, color: c.text }, axisTick: { show: false }, axisLine: { show: false } },
          { gridIndex: 2, type: 'category', data: names, inverse: true, show: false },
        ],
        series: [
          {
            type: 'bar', xAxisIndex: 0, yAxisIndex: 0, barCategoryGap: '30%',
            itemStyle: { color: c.bar },
            data: drawn.map((p, i) => ({ value: p.count, label: { show: i < labelled, position: 'top', color: c.text, fontFamily: c.mono, fontSize: 11, formatter: () => count(p.count) } })),
            tooltip: { formatter: (e) => tooltip(data, drawn[e.dataIndex]) },
          },
          {
            type: 'custom', xAxisIndex: 1, yAxisIndex: 1, silent: true, z: 1,
            data: segments,
            renderItem: (params, api) => {
              const a = api.coord([api.value(0), api.value(1)]);
              const b = api.coord([api.value(0), api.value(2)]);
              return { type: 'line', shape: { x1: a[0], y1: a[1], x2: b[0], y2: b[1] }, style: { stroke: c.dot, lineWidth: 2 } };
            },
          },
          {
            type: 'scatter', xAxisIndex: 1, yAxisIndex: 1, symbolSize: 11, z: 2,
            data: cells,
            tooltip: { formatter: (e) => tooltip(data, drawn[e.value[0]]) },
          },
          {
            type: 'bar', xAxisIndex: 2, yAxisIndex: 2, barCategoryGap: '35%',
            itemStyle: { color: c.sets },
            data: used.map((col) => data.missing[col]),
            tooltip: { formatter: (e) => names[e.dataIndex] + '<br>' + count(e.value) + ' records without a value, ' + share(e.value, data.records) },
          },
        ],
      },
    };
  };

  const narrow = (data, drawn, c) => ({
    height: drawn.length * 30 + 40,
    option: {
      animation: false,
      textStyle: { fontFamily: c.font },
      tooltip: { trigger: 'item', confine: true, backgroundColor: c.panel, borderColor: c.line, textStyle: { color: c.text } },
      grid: { left: 8, right: 56, top: 8, bottom: 24, containLabel: true },
      xAxis: { type: 'value', splitNumber: 2, axisLabel: { color: c.faint, fontFamily: c.mono, fontSize: 10, formatter: (v) => count(v) }, splitLine: { lineStyle: { color: c.line } } },
      yAxis: {
        type: 'category', inverse: true,
        data: drawn.map((p) => p.cols.map((col) => data.columns[col]).join(' + ')),
        axisLabel: { color: c.text, fontFamily: c.mono, fontSize: 10, width: 150, overflow: 'truncate' },
        axisTick: { show: false },
      },
      series: [{
        type: 'bar', itemStyle: { color: c.bar },
        data: drawn.map((p) => p.count),
        label: { show: true, position: 'right', color: c.text, fontFamily: c.mono, fontSize: 10, formatter: (e) => count(e.value) },
        tooltip: { formatter: (e) => tooltip(data, drawn[e.dataIndex]) },
      }],
    },
  });

  const charts = sections.map((section) => {
    const el = section.querySelector('[data-chart]');
    const source = section.querySelector('[data-chart-data]');
    if (!el || !source) return null;
    const data = JSON.parse(source.textContent);
    const state = { sort: 'count', show: 'all' };
    const tools = section.querySelector('[data-tools]');
    const live = section.querySelector('[data-live]');
    const msg = section.querySelector('[data-msg]');
    if (msg) msg.hidden = true;
    if (tools) tools.hidden = false;
    let chart = null;
    const draw = (fresh) => {
      const width = el.clientWidth;
      const list = visible(data, state);
      const drawn = list.slice(0, data.drawn);
      if (live) live.textContent = drawn.length + ' of ' + list.length + ' combinations drawn';
      const c = palette();
      const built = width < NARROW ? narrow(data, drawn, c) : wide(data, drawn, width, c);
      el.style.height = built.height + 'px';
      if (fresh || !chart) {
        if (chart) chart.dispose();
        chart = window.echarts.init(el, null, { renderer: 'svg' });
      } else {
        chart.resize();
      }
      chart.setOption(built.option, true);
    };
    if (tools) {
      tools.querySelector('[data-sort]').addEventListener('change', (e) => { state.sort = e.target.value; draw(false); });
      tools.querySelector('[data-show]').addEventListener('change', (e) => { state.show = e.target.value; draw(false); });
    }
    draw(true);
    if (window.ResizeObserver) {
      let last = el.clientWidth;
      new ResizeObserver(() => {
        const width = el.clientWidth;
        if (width === last) return;
        last = width;
        // The widths of the set bars and of the labels follow the width of the page.
        draw(false);
      }).observe(el);
    }
    return { redraw: () => draw(true) };
  }).filter(Boolean);

  // The theme toggle changes data-theme on <html>: the colours come from the CSS.
  new MutationObserver(() => charts.forEach((chart) => chart.redraw())).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
})();

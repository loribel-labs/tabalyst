
(() => {
  const root = document.documentElement;
  const $ = (s, c = document) => c.querySelector(s);
  const $$ = (s, c = document) => Array.from(c.querySelectorAll(s));

  /* theme */
  const themeBtn = $('#theme-toggle');
  const setTheme = (t) => {
    root.dataset.theme = t;
    if (themeBtn) {
      const next = t === 'dark' ? 'light' : 'dark';
      themeBtn.setAttribute('aria-label', 'Switch to ' + next + ' theme');
      themeBtn.title = 'Switch to ' + next + ' theme';
      $$('[data-icon]', themeBtn).forEach((el) => { el.toggleAttribute('hidden', el.dataset.icon !== t); });
    }
  };
  setTheme(root.dataset.theme || 'dark');
  themeBtn && themeBtn.addEventListener('click', () => {
    const t = root.dataset.theme === 'dark' ? 'light' : 'dark';
    setTheme(t);
    try { localStorage.setItem('tabalyst-theme', t); } catch (e) { /* storage unavailable */ }
  });

  /* print: show every section */
  $$('[data-print]').forEach((b) => b.addEventListener('click', () => window.print()));

  /* collapsible sections */
  $$('.collapse').forEach((b) => b.addEventListener('click', () => {
    const body = document.getElementById(b.getAttribute('aria-controls'));
    const open = b.getAttribute('aria-expanded') === 'true';
    b.setAttribute('aria-expanded', String(!open));
    b.setAttribute('aria-label', (open ? 'Expand ' : 'Collapse ') + b.dataset.name);
    body.hidden = open;
  }));
  const openSection = (id) => {
    const p = document.getElementById(id);
    const b = p && $('.collapse', p);
    if (b && b.getAttribute('aria-expanded') === 'false') b.click();
  };
  $$('a[href^="#"]').forEach((a) => a.addEventListener('click', () => openSection(a.getAttribute('href').slice(1))));

  /* scroll spy */
  const links = $$('.rep-tab');
  const byId = Object.fromEntries(links.map((a) => [a.getAttribute('href').slice(1), a]));
  const panels = $$('.panel');
  const spy = () => {
    const y = window.innerHeight * 0.3;
    let cur = panels[0];
    for (const p of panels) if (p.getBoundingClientRect().top <= y) cur = p;
    if (window.innerHeight + window.scrollY >= document.body.scrollHeight - 4) cur = panels[panels.length - 1];
    links.forEach((a) => a.removeAttribute('aria-current'));
    const a = byId[cur.id];
    if (a) {
      a.setAttribute('aria-current', 'true');
      const nav = a.parentElement;
      if (nav.scrollWidth > nav.clientWidth) {
        const l = a.offsetLeft - nav.offsetLeft;
        if (l < nav.scrollLeft || l + a.offsetWidth > nav.scrollLeft + nav.clientWidth) nav.scrollLeft = l - 16;
      }
    }
  };
  let ticking = false;
  window.addEventListener('scroll', () => { if (!ticking) { ticking = true; requestAnimationFrame(() => { spy(); ticking = false; }); } }, { passive: true });
  window.addEventListener('resize', spy);
  spy();

  /* ===== interactive tables: sort + filter per column, hover popups ===== */
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const EDGE = 20; // minimum gap between a popup and the viewport edge
  const controllers = [];
  const resetAllBtn = $('#reset-all');
  const resetAllCount = $('#reset-all-count');
  const refreshGlobal = () => {
    const n = controllers.filter((c) => c.isActive()).length;
    if (!resetAllBtn) return;
    resetAllBtn.hidden = n === 0;
    resetAllCount.textContent = n ? String(n) : '';
    resetAllBtn.setAttribute('aria-label', 'Reset filters and sorting in ' + n + (n > 1 ? ' tables' : ' table'));
  };

  const OPS = [
    ['equal', '=', 'Equal to'], ['greater', '>', 'Greater than'], ['greaterOrEqual', '≥', 'Greater than or equal'],
    ['less', '<', 'Less than'], ['lessOrEqual', '≤', 'Less than or equal'], ['between', '[··]', 'Between (inclusive)'],
  ];
  const numTest = (f) => (raw) => {
    if (String(raw).trim() === '') return false;
    const x = Number(raw);
    if (!Number.isFinite(x)) return false;
    switch (f.op) {
      case 'equal': return x === f.a;
      case 'greater': return x > f.a;
      case 'greaterOrEqual': return x >= f.a;
      case 'less': return x < f.a;
      case 'lessOrEqual': return x <= f.a;
      default: return x >= f.a && x <= f.b;
    }
  };

  let openMenu = null;
  const closeMenu = () => {
    if (!openMenu) return;
    const { el, btn } = openMenu;
    el.remove();
    btn.setAttribute('aria-expanded', 'false');
    btn.closest('th').classList.remove('menu-open');
    openMenu = null;
  };
  document.addEventListener('pointerdown', (e) => {
    if (openMenu && !openMenu.el.contains(e.target) && !openMenu.btn.contains(e.target)) closeMenu();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && openMenu) { const b = openMenu.btn; closeMenu(); b.focus(); }
  });

  const placeMenu = (el, btn) => {
    if (el.dataset.dragged === 'true') return;
    const a = btn.getBoundingClientRect();
    const left = Math.max(EDGE, Math.min(a.right - el.offsetWidth, innerWidth - el.offsetWidth - EDGE));
    const below = a.bottom + 6;
    const top = below + el.offsetHeight <= innerHeight - EDGE ? below : a.top - el.offsetHeight - 6;
    el.style.left = left + 'px';
    el.style.top = Math.max(EDGE, Math.min(top, innerHeight - el.offsetHeight - EDGE)) + 'px';
  };
  document.addEventListener('scroll', () => { if (openMenu) placeMenu(openMenu.el, openMenu.btn); }, { capture: true, passive: true });
  window.addEventListener('resize', () => { if (openMenu) placeMenu(openMenu.el, openMenu.btn); });

  const makeDraggable = (el, handle) => {
    handle.addEventListener('pointerdown', (ev) => {
      if (ev.button !== 0 || ev.target.closest('button')) return;
      const r = el.getBoundingClientRect();
      const ox = ev.clientX - r.left, oy = ev.clientY - r.top;
      el.dataset.dragged = 'true';
      handle.setPointerCapture(ev.pointerId);
      const move = (p) => {
        el.style.left = Math.max(12, Math.min(p.clientX - ox, innerWidth - el.offsetWidth - 12)) + 'px';
        el.style.top = Math.max(12, Math.min(p.clientY - oy, innerHeight - el.offsetHeight - 12)) + 'px';
      };
      const stop = (p) => { move(p); handle.removeEventListener('pointermove', move); handle.removeEventListener('pointerup', stop); handle.removeEventListener('pointercancel', stop); };
      handle.addEventListener('pointermove', move);
      handle.addEventListener('pointerup', stop);
      handle.addEventListener('pointercancel', stop);
      ev.preventDefault();
    });
  };

  const makeTable = (table, extra) => {
    const heads = $$('thead th', table);
    const tbody = table.tBodies[0];
    const rows = Array.from(tbody.rows);
    rows.forEach((r, i) => { r.dataset.i = i; });
    const noun = table.dataset.noun;
    const live = document.getElementById(table.id + '-live');
    const resetBtns = $$('[data-reset="' + table.id + '"]');
    const filters = new Map();
    let sort = null;
    const cellVal = (r, idx) => { const c = r.cells[idx]; return c.dataset.v !== undefined ? c.dataset.v : c.textContent.trim(); };

    const ctrl = {
      extraActive: () => (extra ? extra.active() : false),
      isActive: () => filters.size > 0 || sort !== null || ctrl.extraActive(),
      apply() {
        let visible = 0;
        rows.forEach((r) => {
          let ok = extra ? extra.test(r) : true;
          if (ok) for (const [idx, f] of filters) { if (!f.test(cellVal(r, idx))) { ok = false; break; } }
          r.hidden = !ok;
          if (ok) visible++;
        });
        let order = rows.slice();
        if (sort) {
          const num = heads[sort.idx].dataset.kind === 'num';
          const key = (r) => { const v = cellVal(r, sort.idx); return num ? (v === '' ? null : parseFloat(v)) : v.toLowerCase(); };
          order.sort((a, b) => {
            const x = key(a), y = key(b);
            if (x === null && y === null) return a.dataset.i - b.dataset.i;
            if (x === null) return 1;            // empty values always last
            if (y === null) return -1;
            const c = num ? x - y : x.localeCompare(y, undefined, { numeric: true });
            return (sort.dir === 'asc' ? c : -c) || a.dataset.i - b.dataset.i;
          });
        }
        order.forEach((r) => tbody.appendChild(r));
        heads.forEach((th, idx) => {
          const s = $('.hb-s', th), f = $('.hb-f', th);
          if (!s) return;
          const sorted = sort && sort.idx === idx;
          s.classList.toggle('on', !!sorted);
          s.dataset.dir = sorted ? sort.dir : '';
          if (sorted) th.setAttribute('aria-sort', sort.dir === 'asc' ? 'ascending' : 'descending'); else th.removeAttribute('aria-sort');
          s.setAttribute('aria-label', 'Sort by ' + th.dataset.label + (sorted ? (sort.dir === 'asc' ? ' (ascending)' : ' (descending)') : ''));
          f.classList.toggle('on', filters.has(idx));
          th.classList.toggle('filtered', filters.has(idx));
          f.setAttribute('aria-label', 'Filter ' + th.dataset.label + (filters.has(idx) ? ' (active)' : ''));
        });
        if (live) live.textContent = visible + ' of ' + rows.length + ' ' + noun;
        resetBtns.forEach((b) => { b.hidden = !ctrl.isActive(); });
        refreshGlobal();
      },
      reset() {
        filters.clear(); sort = null;
        if (extra) extra.reset();
        if (openMenu && table.contains(openMenu.btn)) closeMenu();
        ctrl.apply();
      },
    };

    const buildList = (idx, th, body, setTitleClear) => {
      const counts = new Map();
      rows.forEach((r) => { const v = cellVal(r, idx); counts.set(v, (counts.get(v) || 0) + 1); });
      const values = Array.from(counts.keys());
      const cur = filters.get(idx);
      const selected = new Set(cur ? cur.values : values);
      const pillLike = th.dataset.pill === '1';
      body.innerHTML =
        '<input type="search" class="fm-search" placeholder="Search" aria-label="Search values" autocomplete="off">' +
        '<div class="fm-ctl"><button type="button" data-all>Select all</button><button type="button" data-none>Select none</button></div>' +
        '<div class="fm-list" role="group" aria-label="Values">' +
        values.map((v) => {
          const lab = pillLike ? '<span class="pill' + (v === 'mixed' ? ' attn' : '') + '">' + esc(v.replace(/_/g, ' ')) + '</span>' : '<span class="fm-v">' + esc(v === '' ? '(empty)' : v) + '</span>';
          return '<button type="button" role="checkbox" class="fm-opt" data-v="' + esc(v) + '" aria-checked="' + selected.has(v) + '"><i aria-hidden="true"></i>' + lab + '<small>(' + counts.get(v) + ')</small></button>';
        }).join('') + '</div>';
      const opts = $$('.fm-opt', body);
      const commit = () => {
        const sel = opts.filter((o) => o.getAttribute('aria-checked') === 'true').map((o) => o.dataset.v);
        if (sel.length === values.length) filters.delete(idx);
        else { const set = new Set(sel); filters.set(idx, { values: sel, test: (v) => set.has(v) }); }
        setTitleClear(filters.has(idx));
        ctrl.apply();
      };
      opts.forEach((o) => o.addEventListener('click', () => { o.setAttribute('aria-checked', String(o.getAttribute('aria-checked') !== 'true')); commit(); }));
      $('[data-all]', body).addEventListener('click', () => { opts.forEach((o) => { if (!o.hidden) o.setAttribute('aria-checked', 'true'); }); commit(); });
      $('[data-none]', body).addEventListener('click', () => { opts.forEach((o) => { if (!o.hidden) o.setAttribute('aria-checked', 'false'); }); commit(); });
      $('.fm-search', body).addEventListener('input', (e) => {
        const q = e.target.value.trim().toLowerCase();
        opts.forEach((o) => { o.hidden = q !== '' && !o.dataset.v.toLowerCase().includes(q); });
      });
    };

    const buildNum = (idx, th, body, setTitleClear) => {
      const cur = filters.get(idx) || { op: 'greater', a: NaN, b: NaN };
      let op = cur.op;
      body.innerHTML =
        '<div class="fm-ops" role="group" aria-label="Comparison">' +
        OPS.map(([v, s, l]) => '<button type="button" data-op="' + v + '" title="' + l + '" aria-label="' + l + '">' + s + '</button>').join('') +
        '</div><div class="fm-fields"><input type="number" step="any" autocomplete="off" class="fm-a"><input type="number" step="any" autocomplete="off" class="fm-b" placeholder="Maximum" aria-label="Maximum (inclusive)"></div>' +
        '<div class="fm-err" aria-live="polite" hidden></div>';
      const a = $('.fm-a', body), b = $('.fm-b', body), err = $('.fm-err', body);
      if (Number.isFinite(cur.a)) a.value = cur.a;
      if (Number.isFinite(cur.b)) b.value = cur.b;
      const update = () => {
        const between = op === 'between';
        b.hidden = !between;
        a.placeholder = between ? 'Minimum' : 'Value';
        a.setAttribute('aria-label', between ? 'Minimum (inclusive)' : 'Value');
        $$('[data-op]', body).forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.op === op)));
        const lo = a.valueAsNumber, hi = b.valueAsNumber;
        const reversed = between && Number.isFinite(lo) && Number.isFinite(hi) && lo > hi;
        err.hidden = !reversed;
        err.textContent = reversed ? 'Minimum must not exceed maximum.' : '';
        a.setAttribute('aria-invalid', String(reversed)); b.setAttribute('aria-invalid', String(reversed));
        const active = Number.isFinite(lo) && (!between || Number.isFinite(hi)) && !reversed;
        if (active) { const f = { op, a: lo, b: hi }; f.test = numTest(f); filters.set(idx, f); } else filters.delete(idx);
        setTitleClear(filters.has(idx));
        ctrl.apply();
      };
      $$('[data-op]', body).forEach((x) => x.addEventListener('click', () => { op = x.dataset.op; update(); }));
      [a, b].forEach((x) => x.addEventListener('input', update));
      $$('[data-op]', body).forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.op === op)));
      b.hidden = op !== 'between';
      a.placeholder = op === 'between' ? 'Minimum' : 'Value';
      a.setAttribute('aria-label', op === 'between' ? 'Minimum (inclusive)' : 'Value');
    };

    const buildText = (idx, th, body, setTitleClear) => {
      const cur = filters.get(idx);
      body.innerHTML = '<input type="search" class="fm-search" placeholder="Value" aria-label="Filter values containing" autocomplete="off">';
      const inp = $('input', body);
      if (cur) inp.value = cur.q;
      inp.addEventListener('input', () => {
        const q = inp.value.trim().toLowerCase();
        if (q) filters.set(idx, { q: inp.value, test: (v) => v.toLowerCase().includes(q) }); else filters.delete(idx);
        setTitleClear(filters.has(idx));
        ctrl.apply();
      });
    };

    heads.forEach((th, idx) => {
      const sBtn = $('.hb-s', th), fBtn = $('.hb-f', th);
      if (!sBtn) return;
      sBtn.addEventListener('click', () => {
        if (!sort || sort.idx !== idx) sort = { idx, dir: 'asc' };
        else if (sort.dir === 'asc') sort.dir = 'desc';
        else sort = null;
        ctrl.apply();
      });
      fBtn.addEventListener('click', () => {
        const same = openMenu && openMenu.btn === fBtn;
        closeMenu();
        if (same) return;
        const kind = th.dataset.kind;
        const el = document.createElement('div');
        el.className = 'fmenu';
        el.setAttribute('role', 'dialog');
        el.setAttribute('aria-label', 'Filter ' + th.dataset.label);
        el.innerHTML =
          '<div class="fm-handle" title="Drag to move this filter"><span>Move filter</span><button type="button" class="fm-close" aria-label="Close filter" title="Close filter">×</button></div>' +
          '<div class="fm-in"><div class="fm-top"><span class="fm-title">' + esc(th.dataset.label) + '</span>' +
          '<button type="button" class="fm-clear" hidden>Clear</button></div><div class="fm-body"></div></div>';
        document.body.appendChild(el);
        const body = $('.fm-body', el), clear = $('.fm-clear', el);
        const setTitleClear = (on) => { clear.hidden = !on; };
        const build = () => {
          if (kind === 'list') buildList(idx, th, body, setTitleClear);
          else if (kind === 'num') buildNum(idx, th, body, setTitleClear);
          else buildText(idx, th, body, setTitleClear);
          setTitleClear(filters.has(idx));
        };
        build();
        clear.addEventListener('click', () => { filters.delete(idx); build(); ctrl.apply(); });
        $('.fm-close', el).addEventListener('click', () => { closeMenu(); fBtn.focus(); });
        makeDraggable(el, $('.fm-handle', el));
        fBtn.setAttribute('aria-expanded', 'true');
        th.classList.add('menu-open');
        openMenu = { el, btn: fBtn };
        placeMenu(el, fBtn);
        const first = $('input:not([hidden]), .fm-ops button[aria-pressed="true"]', el);
        if (first) first.focus({ preventScroll: true });
      });
    });

    resetBtns.forEach((b) => b.addEventListener('click', () => ctrl.reset()));
    controllers.push(ctrl);
    return ctrl;
  };

  /* columns table: name search box + "with issues" are part of its filter state */
  const colSearch = $('#col-filter');
  const seg = $$('#col-seg button');
  let segMode = 'all';
  const colExtra = {
    active: () => (colSearch && colSearch.value.trim() !== '') || segMode !== 'all',
    test: (r) => {
      const q = colSearch ? colSearch.value.trim().toLowerCase() : '';
      return (!q || r.dataset.name.includes(q)) && (segMode === 'all' || r.dataset.flag === '1');
    },
    reset: () => {
      if (colSearch) colSearch.value = '';
      segMode = 'all';
      seg.forEach((x) => x.setAttribute('aria-pressed', String(x.dataset.mode === 'all')));
    },
  };
  $$('table[data-table]').forEach((t) => {
    const c = makeTable(t, t.id === 'columns-table' ? colExtra : null);
    if (t.id === 'columns-table') {
      colSearch && colSearch.addEventListener('input', () => c.apply());
      seg.forEach((b) => b.addEventListener('click', () => {
        segMode = b.dataset.mode;
        seg.forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
        c.apply();
      }));
    }
  });
  resetAllBtn && resetAllBtn.addEventListener('click', () => controllers.forEach((c) => { if (c.isActive()) c.reset(); }));
  refreshGlobal();

  /* pinned name column: show its edge only while the table is scrolled sideways */
  $$('.tscroll').forEach((w) => {
    const upd = () => w.classList.toggle('is-scrolled', w.scrollLeft > 0);
    w.addEventListener('scroll', upd, { passive: true });
    upd();
  });

  /* hover / focus popups (values, lengths, formats) */
  let tipCell = null;
  const hideTip = () => {
    if (!tipCell) return;
    const t = $('.tip', tipCell);
    if (t) t.classList.remove('show');
    tipCell = null;
  };
  const showTip = (cell) => {
    const tip = $('.tip', cell);
    if (!tip) return;
    if (tipCell && tipCell !== cell) hideTip();
    tip.classList.add('show');
    tipCell = cell;
    const a = cell.getBoundingClientRect();
    const w = tip.offsetWidth, h = tip.offsetHeight;
    const overlap = 6; // small bridge so the pointer can move from the cell into the popup
    // align on the cell, shift left when it would come closer than EDGE px to the right edge
    let left = a.left;
    if (left + w > innerWidth - EDGE) left = innerWidth - EDGE - w;
    left = Math.max(EDGE, left);
    const below = a.bottom - overlap;
    let top = below + h <= innerHeight - EDGE ? below : a.top - h + overlap;
    top = Math.max(EDGE, Math.min(top, innerHeight - EDGE - h));
    tip.style.left = left + 'px';
    tip.style.top = top + 'px';
    tipRect = a;
  };
  $$('td.ex').forEach((cell) => {
    cell.addEventListener('pointerenter', (e) => { if (e.pointerType !== 'touch') showTip(cell); });
    cell.addEventListener('pointerleave', () => { if (tipCell === cell) hideTip(); if (document.activeElement === cell) cell.blur(); });
    cell.addEventListener('focus', () => { if (cell.matches(':focus-visible')) showTip(cell); });
    cell.addEventListener('blur', () => { if (tipCell === cell) hideTip(); });
    cell.addEventListener('click', () => { if (tipCell === cell) hideTip(); else showTip(cell); });
  });
  // a popup never stays on screen once the page or a table moves
  let tipRect = null;
  const onMove = (e) => {
    if (!tipCell || (e && e.target instanceof Element && e.target.closest('.tip'))) return;
    requestAnimationFrame(() => {
      if (!tipCell || !tipRect) return;
      const r = tipCell.getBoundingClientRect();
      if (Math.abs(r.top - tipRect.top) > 1 || Math.abs(r.left - tipRect.left) > 1) hideTip();
    });
  };
  document.addEventListener('scroll', onMove, { capture: true, passive: true });
  window.addEventListener('resize', () => hideTip());
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') hideTip(); });
  document.addEventListener('pointerdown', (e) => { if (tipCell && !tipCell.contains(e.target)) hideTip(); });

  /* copy hash */
  $$('[data-copy]').forEach((b) => b.addEventListener('click', async () => {
    const text = b.dataset.copy;
    let ok = false;
    try { await navigator.clipboard.writeText(text); ok = true; } catch (e) {
      const t = document.createElement('textarea');
      t.value = text; document.body.appendChild(t); t.select();
      try { ok = document.execCommand('copy'); } catch (e2) { ok = false; }
      t.remove();
    }
    const label = b.textContent;
    b.textContent = ok ? 'Copied' : 'Select to copy';
    setTimeout(() => { b.textContent = label; }, 2200);
  }));

  /* print: temporarily open collapsed sections */
  window.addEventListener('beforeprint', () => $$('.pbody[hidden]').forEach((b) => { b.dataset.wasHidden = '1'; b.hidden = false; }));
  window.addEventListener('afterprint', () => $$('.pbody[data-was-hidden]').forEach((b) => { b.hidden = true; delete b.dataset.wasHidden; }));
})();

(() => {
  const root = document.documentElement;
  const themeToggle = document.getElementById("theme-toggle");

  function setTheme(theme, persist = true) {
    root.dataset.theme = theme;
    root.dataset.bsTheme = theme;
    const dark = theme === "dark";
    const label = dark ? "Switch to light mode" : "Switch to dark mode";
    themeToggle.setAttribute("aria-label", label);
    themeToggle.setAttribute("aria-pressed", String(dark));
    themeToggle.title = label;
    themeToggle.querySelector("[data-theme-icon]").textContent = dark ? "\u2600" : "\u263e";
    if (persist) {
      try {
        localStorage.setItem("tabalyst-theme", theme);
      } catch (error) {
        // Theme switching still works when local files cannot use storage.
      }
    }
  }

  setTheme(root.dataset.theme || "dark", false);
  themeToggle.addEventListener("click", () => {
    setTheme(root.dataset.theme === "dark" ? "light" : "dark");
  });

  const nameSearch = document.getElementById("column-search");
  const summary = document.getElementById("columns-table");

  if (!window.DataTable || !DataTable.ColumnControl) {
    const status = document.getElementById("filter-result");
    status.hidden = false;
    status.textContent = "Interactive filters unavailable. Check your internet connection.";
    nameSearch.addEventListener("input", () => {
      for (const row of summary.tBodies[0].rows) {
        row.hidden = !row.dataset.columnName.includes(nameSearch.value.trim().toLowerCase());
      }
    });
    return;
  }

  const numberOperators = ["equal", "notEqual", "greater", "greaterOrEqual", "less", "lessOrEqual", "empty", "notEmpty"];

  DataTable.ColumnControl.content.compactNumber = {
    defaults: { title: "Numeric filter" },
    init(config) {
      const dt = this.dt();
      const key = `${this.unique()}compactNumber`;
      const root = document.createElement("div");
      root.className = "number-filter";
      const title = document.createElement("div");
      title.className = "number-filter-title";
      title.textContent = config.title;
      const operators = document.createElement("div");
      operators.className = "number-operators";
      operators.setAttribute("role", "group");
      operators.setAttribute("aria-label", "Comparison");
      const fields = document.createElement("div");
      fields.className = "number-fields";
      const minimum = document.createElement("input");
      const maximum = document.createElement("input");
      for (const input of [minimum, maximum]) {
        input.type = "number";
        input.step = "any";
        input.autocomplete = "off";
      }
      maximum.placeholder = "Maximum";
      maximum.setAttribute("aria-label", "Maximum (inclusive)");
      const error = document.createElement("div");
      error.id = `number-error-${dt.table().node().id}-${this.idx()}`;
      error.className = "number-filter-error";
      error.setAttribute("aria-live", "polite");
      for (const input of [minimum, maximum]) input.setAttribute("aria-describedby", error.id);
      fields.append(minimum, maximum);
      root.append(title, operators, fields, error);
      let mode = "greater";

      const update = (draw = true) => {
        const between = mode === "between";
        maximum.hidden = !between;
        minimum.placeholder = between ? "Minimum" : "Value";
        minimum.setAttribute("aria-label", between ? "Minimum (inclusive)" : "Value");
        for (const button of operators.children) {
          button.setAttribute("aria-pressed", String(button.dataset.operator === mode));
        }
        const low = minimum.valueAsNumber;
        const high = maximum.valueAsNumber;
        const reversed = between && Number.isFinite(low) && Number.isFinite(high) && low > high;
        error.textContent = reversed ? "Minimum must not exceed maximum." : "";
        error.hidden = !reversed;
        minimum.setAttribute("aria-invalid", String(reversed));
        maximum.setAttribute("aria-invalid", String(reversed));
        const active = Number.isFinite(low) && (!between || Number.isFinite(high)) && !reversed;
        const compare = value => {
          if (String(value).trim() === "") return false;
          const number = Number(value);
          if (!Number.isFinite(number)) return false;
          if (mode === "equal") return number === low;
          if (mode === "greater") return number > low;
          if (mode === "greaterOrEqual") return number >= low;
          if (mode === "less") return number < low;
          if (mode === "lessOrEqual") return number <= low;
          return number >= low && number <= high;
        };
        dt.column(this.idx()).search.fixed("dtcc", active ? compare : "");
        for (const parent of config._parents || []) parent.activeList(key, active);
        if (draw) dt.draw();
      };
      for (const [value, symbol, label] of [
        ["equal", "=", "Equal to"],
        ["greater", ">", "Greater than"],
        ["greaterOrEqual", "\u2265", "Greater than or equal"],
        ["less", "<", "Less than"],
        ["lessOrEqual", "\u2264", "Less than or equal"],
        ["between", "[\u00b7\u00b7]", "Between (inclusive)"],
      ]) {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.operator = value;
        button.textContent = symbol;
        button.title = label;
        button.setAttribute("aria-label", label);
        button.addEventListener("click", () => { mode = value; update(); });
        operators.append(button);
      }
      for (const input of [minimum, maximum]) input.addEventListener("input", () => update());
      dt.on("cc-search-clear", (event, index) => {
        if (index !== this.idx()) return;
        minimum.value = maximum.value = "";
        mode = "greater";
        update(false);
      });
      update(false);
      return root;
    },
  };

  function numericFilter(operators = numberOperators, title = "") {
    return {
      extend: "searchNumber",
      excludeLogic: numberOperators.filter(operator => !operators.includes(operator)),
      title,
      titleAttr: title || "Numeric filter",
      placeholder: "Value",
    };
  }

  function checkboxFilter(element, index, formatLabel = value => DataTable.util.escapeHtml(value)) {
    const counts = new Map();
    for (const row of element.tBodies[0].rows) {
      const value = row.cells[index].dataset.search;
      counts.set(value, (counts.get(value) || 0) + 1);
    }
    return {
      extend: "searchList",
      search: true,
      select: true,
      // Library labels accept HTML; CSV content must stay escaped in dropdowns too.
      options: [...counts].map(([value, count]) => ({ value, label: formatLabel(value, count) })),
    };
  }

  function controls(filter) {
    return ["order", [filter, "searchClear"]];
  }

  function positionMenus() {
    for (const menu of document.querySelectorAll(".dtcc-dropdown")) {
      if (menu.dataset.dragged === "true") {
        const left = Math.max(12, Math.min(parseFloat(menu.style.left) || 12, innerWidth - menu.offsetWidth - 12));
        const top = Math.max(12, Math.min(parseFloat(menu.style.top) || 12, innerHeight - menu.offsetHeight - 12));
        menu.style.left = `${left}px`;
        menu.style.top = `${top}px`;
        continue;
      }
      const trigger = menu.closest(".dt-container").querySelector(".dtcc-button_dropdown[aria-expanded='true']");
      if (!trigger) continue;
      const anchor = trigger.getBoundingClientRect();
      const left = Math.max(12, Math.min(anchor.right - menu.offsetWidth, innerWidth - menu.offsetWidth - 12));
      const below = anchor.bottom + 6;
      const top = below + menu.offsetHeight <= innerHeight - 12 ? below : anchor.top - menu.offsetHeight - 6;
      menu.style.left = `${left}px`;
      menu.style.top = `${Math.max(12, Math.min(top, innerHeight - menu.offsetHeight - 12))}px`;
      menu.setAttribute("aria-label", trigger.getAttribute("aria-label"));
    }
  }

  function makeMenuMovable(menu) {
    if (menu.querySelector(":scope > .filter-drag-handle")) return;
    const handle = document.createElement("div");
    handle.className = "filter-drag-handle";
    const handleLabel = document.createElement("span");
    handleLabel.textContent = "Move filter";
    const close = document.createElement("button");
    close.type = "button";
    close.className = "filter-close";
    close.textContent = "\u00d7";
    close.title = "Close filter";
    close.setAttribute("aria-label", close.title);
    close.addEventListener("pointerdown", event => event.stopPropagation());
    close.addEventListener("click", event => {
      event.stopPropagation();
      if (typeof menu._close === "function") menu._close();
    });
    handle.append(handleLabel, close);
    handle.title = "Drag to move this filter";
    handle.addEventListener("pointerdown", event => {
      if (event.button !== 0) return;
      const rect = menu.getBoundingClientRect();
      const offsetX = event.clientX - rect.left;
      const offsetY = event.clientY - rect.top;
      menu.dataset.dragged = "true";
      handle.setPointerCapture(event.pointerId);
      const move = pointer => {
        const left = Math.max(12, Math.min(pointer.clientX - offsetX, innerWidth - menu.offsetWidth - 12));
        const top = Math.max(12, Math.min(pointer.clientY - offsetY, innerHeight - menu.offsetHeight - 12));
        menu.style.left = `${left}px`;
        menu.style.top = `${top}px`;
      };
      const stop = pointer => {
        move(pointer);
        handle.releasePointerCapture(pointer.pointerId);
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", stop);
        handle.removeEventListener("pointercancel", stop);
      };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", stop);
      handle.addEventListener("pointercancel", stop);
      event.preventDefault();
    });
    menu.prepend(handle);
  }

  // Preserve accessible checkbox states and viewport positioning in scrollable tables.
  const menuObserver = new MutationObserver(() => {
    for (const menu of document.querySelectorAll(".dtcc-dropdown")) makeMenuMovable(menu);
    for (const button of document.querySelectorAll(".dtcc-list-buttons .dtcc-button")) {
      button.setAttribute("role", "checkbox");
      button.setAttribute("aria-checked", String(button.classList.contains("dtcc-button_active")));
      const badges = [...button.querySelectorAll(".type-badge")].map(badge => badge.textContent);
      const count = button.querySelector(".filter-option-count")?.textContent || "";
      const label = badges.length > 1
        ? `${badges.join(" · ")} ${count}`
        : button.querySelector(".dtcc-button-text").textContent;
      button.setAttribute("aria-label", label);
    }
    positionMenus();
  });
  menuObserver.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["class"] });
  document.addEventListener("scroll", positionMenus, { capture: true, passive: true });
  window.addEventListener("resize", () => requestAnimationFrame(positionMenus));

  function positionExampleTooltip(cell) {
    const tooltip = cell.querySelector(".examples-tooltip");
    if (!tooltip) return;
    const anchor = cell.getBoundingClientRect();
    const overlap = Math.min(32, anchor.height * 0.65);
    const left = Math.max(12, Math.min(anchor.left, innerWidth - tooltip.offsetWidth - 12));
    const below = anchor.bottom - overlap;
    const top = below + tooltip.offsetHeight <= innerHeight - 12
      ? below
      : anchor.top - tooltip.offsetHeight + overlap;
    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${Math.max(12, top)}px`;
  }

  for (const cell of document.querySelectorAll(".examples")) {
    cell.addEventListener("pointerenter", () => positionExampleTooltip(cell));
    cell.addEventListener("focusin", () => positionExampleTooltip(cell));
  }

  function attachTable(element, columns, noun) {
    const table = new DataTable(element, {
      autoWidth: false,
      paging: false,
      info: false,
      order: [],
      ordering: { indicators: false, handler: false },
      layout: { topStart: null, topEnd: null, bottomStart: null, bottomEnd: null },
      // DataTables decodes entities through HTML when building its search cache.
      // Escape raw filter values first so that decoding yields inert text.
      columns: columns.map(column => ({
        ...column,
        render: (value, purpose) => purpose === "filter" ? DataTable.util.escapeHtml(value) : value,
      })),
      language: { emptyTable: "No data available.", zeroRecords: "No matching results." },
    });
    const status = document.querySelector(`[data-table-status="${element.id}"]`);
    const updateStatus = () => {
      const total = table.rows().count();
      const visible = table.rows({ search: "applied" }).count();
      status.hidden = false;
      status.textContent = `${visible} of ${total} ${noun}`;
    };
    table.on("draw", updateStatus);
    updateStatus();

    for (const cell of element.tHead.rows[0].cells) {
      const title = cell.querySelector(".dt-column-title").textContent;
      for (const [selector, action] of [[".dtcc-button_order", "Sort by"], [".dtcc-button_dropdown", "Filter"]]) {
        const button = cell.querySelector(selector);
        if (button) {
          button.title = `${action} ${title}`;
          button.setAttribute("aria-label", button.title);
        }
      }
    }

    const reset = document.querySelector(`[data-reset-table="${element.id}"]`);
    reset.hidden = false;
    reset.addEventListener("click", () => {
      table.columns().columnControl.searchClear();
      table.search("").columns().search("");
      if (element === summary) nameSearch.value = "";
      table.order([]).draw();
    });
    element.dataset.interactive = "true";
    return table;
  }

  const summaryTable = attachTable(summary, [
    { type: "string", columnControl: controls(checkboxFilter(summary, 0)) },
    { type: "num", columnControl: controls({ extend: "compactNumber", title: "Missing (%)" }) },
    { type: "num", columnControl: controls({ extend: "compactNumber", title: "Distinct values" }) },
    { type: "string", columnControl: controls(checkboxFilter(summary, 3, (value, count) => {
      const [physicalType, semanticType] = value.split(" · ");
      const type = DataTable.util.escapeHtml(physicalType);
      const badge = ["text", "integer", "number", "date", "boolean", "mixed", "empty"].includes(physicalType)
        ? `badge-${physicalType}` : "badge-empty";
      const semantic = semanticType
        ? `<span class="semantic-separator" aria-hidden="true">·</span><span class="type-badge semantic-badge">${DataTable.util.escapeHtml(semanticType)}</span>`
        : "";
      return `<span class="type-badge ${badge}">${type}</span>${semantic} <span class="filter-option-count">(${count})</span>`;
    })) },
    { orderable: false, columnControl: [] },
  ], "columns");
  nameSearch.addEventListener("input", () => {
    summaryTable.column(0).search(nameSearch.value, { regex: false, smart: false }).draw();
  });

  const numeric = document.getElementById("numeric-table");
  if (numeric) {
    attachTable(numeric, [
      { type: "string", columnControl: controls(checkboxFilter(numeric, 0)) },
      ...Array.from({ length: 4 }, () => ({ type: "num", columnControl: controls(numericFilter()) })),
    ], "columns");
  }

  const sample = document.getElementById("sample-table");
  if (sample) {
    const columns = [...sample.tHead.rows[0].cells].map((cell, index) => {
      const numeric = ["integer", "number"].includes(cell.dataset.valueType);
      const filter = numeric ? numericFilter() : cell.dataset.valueType === "boolean"
        ? checkboxFilter(sample, index)
        : { extend: "searchText", titleAttr: "Filter values", placeholder: "Value" };
      return { type: numeric ? "num" : "string", columnControl: controls(filter) };
    });
    attachTable(sample, columns, "sample rows");
  }
})();

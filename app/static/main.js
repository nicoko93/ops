// main.js — mini utilitaires pour le portail (tri, filtre, dates locales)
(() => {
  const $ = (sel, el=document) => el.querySelector(sel);
  const $$ = (sel, el=document) => Array.from(el.querySelectorAll(sel));
  const debounce = (fn, ms=200) => { let t; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms)} };

  // Convertit tout élément [data-utc="YYYY-MM-DD HH:mm:ss"] en heure locale
  function toLocalText(s) {
    try {
      const str = s.includes('T') || s.endsWith('Z') ? s : s.replace(' ', 'T') + 'Z';
      const d = new Date(str);
      return isNaN(d) ? s : d.toLocaleString();
    } catch { return s; }
  }
  function initLocalTime() {
    $$('[data-utc]').forEach(el => { el.textContent = toLocalText(el.dataset.utc); });
  }

  // Tri de tableaux : <table data-sortable> + <th data-type="text|number|date">
  function parseCell(td, type) {
    const t = td.textContent.trim();
    if (type === 'number') {
      const m = t.match(/([0-9]+(?:[.,][0-9]+)?)/);
      return m ? parseFloat(m[1].replace(',', '.')) : -Infinity;
    }
    if (type === 'date') {
      const ts = Date.parse(t.includes('T')||t.endsWith('Z') ? t : (t.replace(' ','T')+'Z'));
      return isNaN(ts) ? -Infinity : ts;
    }
    return t.toLowerCase();
  }
  function initSortableTables() {
    $$('table[data-sortable]').forEach(table => {
      const ths = $$('thead th', table);
      ths.forEach((th, idx) => {
        th.style.cursor = 'pointer';
        th.addEventListener('click', () => {
          const type = th.dataset.type || 'text';
          const tbody = $('tbody', table);
          const rows = $$('tr', tbody);
          const asc = th.dataset.asc !== 'true';
          ths.forEach(x => { if (x!==th) x.dataset.asc=''; });
          th.dataset.asc = asc ? 'true':'false';
          rows.sort((a,b) => {
            const va = parseCell(a.children[idx], type);
            const vb = parseCell(b.children[idx], type);
            return (va>vb?1:va<vb?-1:0) * (asc?1:-1);
          });
          tbody.replaceChildren(...rows);
        });
      });
    });
  }

  // Filtre simple : <input data-table-filter="#tableId">
  function initFilter() {
    $$('input[data-table-filter]').forEach(input => {
      const table = $(input.dataset.tableFilter);
      if (!table) return;
      const tbody = $('tbody', table);
      const rows = $$('tr', tbody);
      const run = () => {
        const q = input.value.trim().toLowerCase();
        rows.forEach(r => r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none');
      };
      input.addEventListener('input', debounce(run, 120));
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    initLocalTime();
    initSortableTables();
    initFilter();
  });
})();

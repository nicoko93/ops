// main.js — utilities for the build portal (sort, filter, local dates, mobile menu, toasts)
(() => {
  const $ = (sel, el=document) => el.querySelector(sel);
  const $$ = (sel, el=document) => Array.from(el.querySelectorAll(sel));
  const debounce = (fn, ms=200) => { let t; return (...a)=>{ clearTimeout(t); t=setTimeout(()=>fn(...a), ms)} };

  // Convert [data-utc="YYYY-MM-DD HH:mm:ss"] elements to local time
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

  // Sortable tables: <table data-sortable> + <th data-type="text|number|date">
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

  // Simple filter: <input data-table-filter="#tableId">
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

  // Mobile menu toggle
  function initMobileMenu() {
    const btn = $('#mobile-menu-btn');
    const menu = $('#mobile-menu');
    const hamburgerIcon = $('#hamburger-icon');
    const closeIcon = $('#close-icon');

    if (!btn || !menu) return;

    btn.addEventListener('click', () => {
      const isOpen = !menu.classList.contains('hidden');
      menu.classList.toggle('hidden', isOpen);
      if (hamburgerIcon && closeIcon) {
        hamburgerIcon.classList.toggle('hidden', !isOpen);
        closeIcon.classList.toggle('hidden', isOpen);
      }
    });

    // Close menu when clicking outside
    document.addEventListener('click', (e) => {
      if (!btn.contains(e.target) && !menu.contains(e.target)) {
        menu.classList.add('hidden');
        if (hamburgerIcon && closeIcon) {
          hamburgerIcon.classList.remove('hidden');
          closeIcon.classList.add('hidden');
        }
      }
    });
  }

  // Toast notification system
  const Toast = {
    container: null,
    template: null,

    init() {
      this.container = $('#toast-container');
      this.template = $('#toast-template');
    },

    show(message, type = 'info', duration = 4000) {
      if (!this.container || !this.template) return;

      const toast = this.template.content.cloneNode(true).querySelector('.toast');
      const iconEl = toast.querySelector('.toast-icon');
      const msgEl = toast.querySelector('.toast-message');

      msgEl.textContent = message;

      // Style based on type
      const styles = {
        success: { bg: 'bg-green-50', border: 'border-green-200', text: 'text-green-800', icon: '<svg class="w-5 h-5 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"></path></svg>' },
        error: { bg: 'bg-red-50', border: 'border-red-200', text: 'text-red-800', icon: '<svg class="w-5 h-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>' },
        warning: { bg: 'bg-yellow-50', border: 'border-yellow-200', text: 'text-yellow-800', icon: '<svg class="w-5 h-5 text-yellow-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"></path></svg>' },
        info: { bg: 'bg-blue-50', border: 'border-blue-200', text: 'text-blue-800', icon: '<svg class="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>' }
      };

      const style = styles[type] || styles.info;
      toast.classList.add(style.bg, style.border, style.text);
      iconEl.innerHTML = style.icon;

      this.container.appendChild(toast);

      // Animate in
      requestAnimationFrame(() => {
        toast.classList.remove('translate-x-full', 'opacity-0');
      });

      // Auto-dismiss
      if (duration > 0) {
        setTimeout(() => this.dismiss(toast), duration);
      }

      return toast;
    },

    dismiss(toast) {
      toast.classList.add('translate-x-full', 'opacity-0');
      setTimeout(() => toast.remove(), 300);
    },

    success(message, duration) { return this.show(message, 'success', duration); },
    error(message, duration) { return this.show(message, 'error', duration); },
    warning(message, duration) { return this.show(message, 'warning', duration); },
    info(message, duration) { return this.show(message, 'info', duration); }
  };

  // Expose Toast globally
  window.Toast = Toast;

  // HTMX event listener for toast triggers
  function initHtmxToasts() {
    document.body.addEventListener('htmx:afterRequest', (e) => {
      const trigger = e.detail.xhr?.getResponseHeader('HX-Trigger');
      if (trigger) {
        try {
          const data = JSON.parse(trigger);
          if (data.showToast) {
            Toast.show(data.showToast.message, data.showToast.type || 'info');
          }
        } catch {
          // Not JSON, ignore
        }
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    initLocalTime();
    initSortableTables();
    initFilter();
    initMobileMenu();
    Toast.init();
    initHtmxToasts();
  });
})();

// Adds a "Download CSV" link under every data table on the page, including tables drawn later.
(function () {
  'use strict';
  const cell = s => { s = String(s).replace(/\s+/g, ' ').trim(); return /[",\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s; };
  function csv(table) {
    return [...table.rows].map(r => [...r.cells].map(c => cell(c.innerText)).join(',')).join('\r\n');
  }
  function name(table) {
    const sec = table.closest('section'), cap = table.caption ? table.caption.innerText : '';
    return ((sec && sec.id ? sec.id + '-' : '') + cap).toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 80) || 'table';
  }
  function add(table) {
    if (table.dataset.csv || table.rows.length < 2) return;
    table.dataset.csv = '1';
    const a = document.createElement('a');
    a.href = '#'; a.className = 'small csv-link'; a.textContent = 'Download this table as shown (CSV; full data under Sources)';
    a.addEventListener('click', e => {
      e.preventDefault();
      const blob = new Blob(['﻿' + csv(table) + '\r\n'], { type: 'text/csv;charset=utf-8' });
      const url = URL.createObjectURL(blob), dl = document.createElement('a');
      dl.href = url; dl.download = name(table) + '.csv'; document.body.append(dl); dl.click(); dl.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
    const host = table.parentElement && table.parentElement.classList.contains('table-wrap') ? table.parentElement : table;
    host.after(a);
  }
  const scan = () => document.querySelectorAll('main table').forEach(add);
  let pending = false;
  new MutationObserver(() => { if (!pending) { pending = true; requestAnimationFrame(() => { pending = false; scan(); }); } }).observe(document.querySelector('main') || document.body, { childList: true, subtree: true });
  scan();
})();

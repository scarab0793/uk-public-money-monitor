// Data sources and methodology table, built from data/catalogue.json plus each dataset's own refresh stamp.
(function () {
  'use strict';
  const box = document.getElementById('sources-body'); if (!box) return;
  const STATUS = { verified: 'Verified against the official source', partially_verified: 'Partly verified', imported_unverified: 'Imported, not yet independently verified' };
  const el = (t, txt) => { const e = document.createElement(t); if (txt != null) e.textContent = txt; return e; };
  fetch('./data/catalogue.json', { cache: 'no-store' }).then(r => r.json()).then(async cat => {
    const wrap = el('div'); wrap.className = 'table-wrap';
    const t = el('table'); t.className = 'proc-table sources';
    const head = el('tr'); for (const h of ['Dataset', 'Publisher and basis', 'Refresh', 'Last updated', 'Status', 'Limitations']) head.append(el('th', h));
    t.append(head);
    for (const d of cat.datasets) {
      let stamp = '—';
      if (d.stamp) { try { const x = await fetch('./' + d.file, { cache: 'no-store' }).then(r => r.json()); if (x[d.stamp]) stamp = new Date(x[d.stamp]).toLocaleDateString('en-GB'); } catch (e) { stamp = 'unavailable'; } }
      const tr = el('tr');
      const a = el('a', d.module); a.href = '#' + d.anchor;
      const td1 = el('td'); td1.append(a);
      const src = el('a', d.publisher); src.href = d.source; src.target = '_blank'; src.rel = 'noopener noreferrer';
      const td2 = el('td'); td2.append(src, el('br'), document.createTextNode(d.basis + ' · ' + d.unit));
      const dl = el('a', 'data'); dl.href = './' + d.file; td2.append(document.createTextNode(' · '), dl);
      tr.append(td1, td2, el('td', d.refresh), el('td', stamp), el('td', STATUS[d.verification] || d.verification), el('td', d.limitations));
      t.append(tr);
    }
    wrap.append(t); box.replaceChildren(wrap);
    if (cat.gaps && cat.gaps.length) {
      const g = el('div'); g.append(el('h3', 'Not covered yet, and why'));
      for (const x of cat.gaps) { const p = el('p'); p.append(el('strong', x.module + ' (' + x.status + '): '), document.createTextNode(x.reason + ' ')); const a = el('a', 'Source'); a.href = x.source; a.target = '_blank'; a.rel = 'noopener noreferrer'; p.append(a); g.append(p); }
      box.append(g);
    }
  }).catch(() => { box.textContent = 'Source catalogue unavailable.'; });
})();

// ODA delivery breakdown: bilateral/multilateral split, aid types and in-donor costs (FCDO, latest vintage).
(function () {
  'use strict';
  const box = document.getElementById('fcdo-breakdown');
  const yearSel = document.getElementById('fcdo-year');
  if (!box) return;
  const fmt = n => '£' + (n / 1e9).toLocaleString('en-GB', { maximumFractionDigits: 2 }) + 'bn';
  const el = (t, txt, cls) => { const e = document.createElement(t); if (txt != null) e.textContent = txt; if (cls) e.className = cls; return e; };
  Promise.all(['bilateral_multilateral', 'aid_type', 'channel'].map(k => fetch('./data/fcdo-normalized/' + k + '.json').then(r => { if (!r.ok) throw Error(k); return r.json(); })))
    .then(([bm, aid, channel]) => {
      function sum(rows, y) {
        const t = new Map();
        for (const r of rows) if (!y || String(r.year) === y) t.set(r.category, (t.get(r.category) || 0) + Number(r.oda_gbp));
        return [...t.entries()].sort((a, b) => b[1] - a[1]);
      }
      function render() {
        const y = yearSel && yearSel.value;
        box.replaceChildren(el('h3', 'How the ODA was delivered' + (y ? ' in ' + y : ', 2017 onwards')));
        const total = sum(bm, y).reduce((a, [, v]) => a + v, 0);
        const inDonor = sum(aid, y).filter(([c]) => /in donor countr/i.test(c)).reduce((a, [, v]) => a + v, 0);
        const p = el('p');
        p.textContent = 'Total headline ODA ' + fmt(total) + '. Of this, ' + fmt(inDonor) + ' (' + (100 * inDonor / total).toFixed(1) + '%) was spent inside the UK supporting refugees and asylum seekers (in-donor refugee costs), which OECD rules allow to be counted as ODA; this money was not transferred abroad.';
        box.append(p);
        for (const [title, rows, n] of [['Bilateral and multilateral', sum(bm, y), 5], ['Type of aid', sum(aid, y), 8], ['Delivery channel', sum(channel, y), 8]]) {
          const d = el('details'); d.append(el('summary', title));
          for (const [c, v] of rows.slice(0, n)) d.append(el('p', c + ': ' + fmt(v) + ' (' + (100 * v / total).toFixed(1) + '%)', 'small'));
          box.append(d);
        }
        box.append(el('p', 'Nominal GBP, FCDO Statistics on International Development (latest vintage). Categories are FCDO/OECD classifications as published.', 'small'));
      }
      if (yearSel) yearSel.addEventListener('change', render);
      render();
    })
    .catch(() => { box.textContent = ''; });
})();

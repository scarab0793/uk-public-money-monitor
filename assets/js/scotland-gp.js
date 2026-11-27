// NHS Scotland payments to general practices (Public Health Scotland open data), from data/nhs/scotland-gp-payments.json.
(function () {
  'use strict';
  const box = document.getElementById('scotland-gp-body'); if (!box) return;
  const el = (tag, props, ...kids) => {
    const e = document.createElement(tag);
    if (props) for (const [k, v] of Object.entries(props)) { if (v == null) continue; if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v); }
    for (const k of kids) if (k != null) e.append(k);
    return e;
  };
  const gbp = v => v == null ? 'Not available' : (v < 0 ? '−' : '') + '£' + (Math.abs(v) >= 1e9 ? (Math.abs(v) / 1e9).toLocaleString('en-GB', { maximumFractionDigits: 2 }) + 'bn' : Math.abs(v) >= 1e6 ? (Math.abs(v) / 1e6).toLocaleString('en-GB', { maximumFractionDigits: 2 }) + 'm' : Math.round(Math.abs(v)).toLocaleString('en-GB'));
  const ext = (href, text) => el('a', { href, target: '_blank', rel: 'noopener noreferrer', text });
  const LABEL = { GlobalSum: 'Global sum (core services)', IncomeAndExpensesGuarantee: 'Income and expenses guarantee', DirectEnhancedServices: 'Directed enhanced services', NationalEnhancedServices: 'National enhanced services', LocalEnhancedServices: 'Local enhanced services', Professionalism: 'Professionalism', Premises: 'Premises', Seniority: 'Seniority', OtherPayments: 'Other payments', OptedOutServices: 'Opted-out services', '17CPayments': 'Section 17C payments', '2CPayments': 'Section 2C payments (board-run practices)' };
  fetch('./data/nhs/scotland-gp-payments.json', { cache: 'no-store' }).then(r => { if (!r.ok) throw 0; return r.json(); }).then(d => {
    const years = d.years.slice().reverse(), name = p => p.name || 'Practice ' + p.code + ' (no longer listed)';
    const ySel = el('select', { id: 'sgp-year' }, ...years.map(y => el('option', { value: y, text: y })));
    const hSel = el('select', { id: 'sgp-board' }, el('option', { value: '', text: 'All health boards' }), ...d.hb_names.map(h => el('option', { value: h, text: h })));
    const q = el('input', { id: 'sgp-query', placeholder: 'Practice name or code', autocomplete: 'off' });
    const boards = el('div'), detail = el('div', { class: 'card', hidden: '' }), out = el('div'), more = el('button', { type: 'button', hidden: '', text: 'Show more' });
    let limit = 30;
    const tot = (p, y) => (p.years[y] || {}).total;
    function showDetail(code) {
      const p = d.practices.find(x => x.code === code); if (!p) return;
      const hist = el('table', { class: 'proc-table' }, el('caption', { text: name(p) + ' · payments by year' }), el('tr', null, ...['Year', 'Total payments', 'Registered patients', 'Per patient', 'Dispensing (separate)'].map(h => el('th', { text: h }))));
      for (const y of d.years) { const v = p.years[y]; hist.append(el('tr', null, el('td', { text: y }), ...(v ? [el('td', { text: gbp(v.total) }), el('td', { text: v.list_size == null ? 'Not available' : v.list_size.toLocaleString('en-GB') }), el('td', { text: v.total != null && v.list_size ? '£' + (v.total / v.list_size).toFixed(2) : 'Not available' }), el('td', { text: v.dispensing == null ? '—' : gbp(v.dispensing) })] : [el('td', { text: 'Not in this year\'s data', colspan: '4' })]))); }
      const nodes = [el('h3', { text: name(p) }), el('p', { class: 'small', text: [p.hb, p.type && p.type + ' practice', 'code ' + p.code].filter(Boolean).join(' · ') }), el('div', { class: 'table-wrap' }, hist)];
      if (p.components) {
        const t = el('table', { class: 'proc-table' }, el('caption', { text: 'Payments by type, ' + years[0] }), el('tr', null, el('th', { text: 'Type' }), el('th', { text: 'Amount' })));
        d.components.forEach((c, i) => { if (p.components[i] != null) t.append(el('tr', null, el('td', { text: LABEL[c] || c }), el('td', { text: gbp(p.components[i]) }))); });
        nodes.push(el('div', { class: 'table-wrap' }, t));
      }
      const close = el('button', { type: 'button', text: 'Close' }); close.onclick = () => { detail.hidden = true; };
      detail.replaceChildren(...nodes, close); detail.hidden = false; detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    function renderBoards() {
      const y = ySel.value, sums = {};
      for (const p of d.practices) { const v = tot(p, y); if (v == null) continue; const s = sums[p.hb] ||= { v: 0, n: 0 }; s.v += v; s.n++; }
      const rows = Object.entries(sums).sort((a, b) => b[1].v - a[1].v), max = rows.length ? rows[0][1].v : 1;
      boards.replaceChildren(el('p', { class: 'small', text: 'Sum of the published payments to the practices in each health board, ' + y + '.' }),
        ...rows.map(([h, s]) => el('div', { class: 'barrow', title: s.n + ' practices' }, el('span', { class: 'barlabel', text: h }), el('span', { class: 'bar', style: 'width:' + Math.max(0.5, s.v / max * 100) + '%' }), el('span', { class: 'barval', text: gbp(s.v) }))));
    }
    function render() {
      const y = ySel.value, h = hSel.value, f = q.value.trim().toLowerCase();
      const rows = d.practices.filter(p => p.years[y] && (!h || p.hb === h) && (!f || (name(p) + ' ' + p.code).toLowerCase().includes(f))).sort((a, b) => (tot(b, y) ?? -Infinity) - (tot(a, y) ?? -Infinity));
      const t = el('table', { class: 'proc-table' }, el('caption', { text: 'GP practices · ' + y + ' · sorted by total payments' }), el('tr', null, ...['Practice', 'Health board', 'Registered patients', 'Total payments'].map(x => el('th', { text: x }))));
      for (const p of rows.slice(0, limit)) { const b = el('button', { type: 'button', class: 'linklike', text: name(p) }); b.onclick = () => showDetail(p.code); const v = p.years[y]; t.append(el('tr', null, el('td', null, b), el('td', { text: p.hb || '' }), el('td', { text: v.list_size == null ? 'Not available' : v.list_size.toLocaleString('en-GB') }), el('td', { text: gbp(v.total) }))); }
      out.replaceChildren(el('p', { class: 'small', role: 'status', text: rows.length + ' practices' }), el('div', { class: 'table-wrap' }, t));
      more.hidden = rows.length <= limit;
    }
    more.onclick = () => { limit += 30; render(); };
    ySel.onchange = () => { renderBoards(); render(); }; hSel.onchange = q.oninput = () => { limit = 30; render(); };
    box.replaceChildren(
      el('p', { class: 'small', text: 'Source: ' }, ext(d.page, d.publisher + ': ' + d.dataset), document.createTextNode(' · '), ext(d.attachment, 'Download the official data (CSV, ' + years[0] + ')')),
      el('div', { class: 'filters' }, el('div', null, el('label', { for: 'sgp-year', text: 'Financial year' }), ySel), el('div', null, el('label', { for: 'sgp-board', text: 'Health board' }), hSel), el('div', null, el('label', { for: 'sgp-query', text: 'Find a practice' }), q)),
      boards, detail, out, more,
      el('details', null, el('summary', { text: 'What these figures mean' }), ...d.caveats.filter(Boolean).map(c => el('p', { class: 'small', text: c }))));
    renderBoards(); render();
    const fromHash = () => { const m = location.hash.match(/^#scotland-gp\/(\d+)$/); if (m) showDetail(m[1]); };
    window.addEventListener('hashchange', fromHash); fromHash();
  }).catch(() => { box.textContent = 'Scottish GP payments data is not available yet.'; });
})();

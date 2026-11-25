// NHS trust and foundation trust annual accounts (NHS England TAC data), from data/nhs/trust-accounts.json.
(function () {
  'use strict';
  const box = document.getElementById('nhs-trusts-body'); if (!box) return;
  const el = (tag, props, ...kids) => {
    const e = document.createElement(tag);
    if (props) for (const [k, v] of Object.entries(props)) { if (v == null) continue; if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v); }
    for (const k of kids) if (k != null) e.append(k);
    return e;
  };
  // values are £ thousand
  const k = v => v == null ? 'Not available' : v === 0 ? '£0' : (v < 0 ? '−' : '') + '£' + (Math.abs(v) >= 1e6 ? (Math.abs(v) / 1e6).toLocaleString('en-GB', { maximumFractionDigits: 2 }) + 'bn' : Math.abs(v) >= 1000 ? (Math.abs(v) / 1000).toLocaleString('en-GB', { maximumFractionDigits: 1 }) + 'm' : Math.round(Math.abs(v)).toLocaleString('en-GB') + 'k');
  const S = (p, c) => (p.values.A02CY01 || {})[c];
  const income = p => S(p, 'SCI0100A') == null && S(p, 'SCI0110A') == null ? null : (S(p, 'SCI0100A') || 0) + (S(p, 'SCI0110A') || 0);
  const expenses = p => S(p, 'SCI0125A') == null ? null : -S(p, 'SCI0125A');
  const result = p => S(p, 'SCI0240');
  const SORTS = { income: ['Operating income', income], expenses: ['Operating expenses', expenses], deficit: ['Largest deficit first', p => result(p) == null ? null : -result(p)], surplus: ['Largest surplus first', result] };
  fetch('./data/nhs/trust-accounts.json', { cache: 'no-store' }).then(r => { if (!r.ok) throw 0; return r.json(); }).then(d => {
    const years = Object.keys(d.years).sort().reverse();
    const ySel = el('select', { id: 'nhs-year' }, ...years.map(y => el('option', { value: y, text: y })));
    const sectors = [...new Set(Object.values(d.years).flatMap(y => y.providers.map(p => p.sector)).filter(Boolean))].sort();
    const secSel = el('select', { id: 'nhs-sector' }, el('option', { value: '', text: 'All types of trust' }), ...sectors.map(s => el('option', { value: s, text: s })));
    const sortSel = el('select', { id: 'nhs-sort' }, ...Object.entries(SORTS).map(([v, [t]]) => el('option', { value: v, text: t })));
    const q = el('input', { id: 'nhs-query', placeholder: 'Trust name, region or code, e.g. Barts, Leeds, RR8', autocomplete: 'off' });
    const detail = el('div', { class: 'card', hidden: '' }), out = el('div'), more = el('button', { type: 'button', hidden: '', text: 'Show more' });
    let limit = 30;
    const same = (a, b) => (a.code && b.code && a.code === b.code) || a.name.toLowerCase() === b.name.toLowerCase();
    function lines(p, table, y, filter) {
      const L = (y.labels || {})[table] || {}, vals = p.values[table] || {};
      return Object.entries(vals).filter(([c, v]) => v && filter(c)).map(([c, v]) => [L[c] || c, v]);
    }
    function showDetail(name) {
      const y = d.years[ySel.value], p = y.providers.find(x => x.name === name); if (!p) return;
      const soci = el('table', { class: 'proc-table' }, el('caption', { text: 'Statement of comprehensive income ' + ySel.value + ' (from the accounts)' }));
      for (const [lab, v] of lines(p, 'A02CY01', y, c => /^SCI/.test(c))) soci.append(el('tr', /^[A-Z/ ()]+$/.test(lab) ? { class: 'agg' } : null, el('td', { text: lab }), el('td', { text: k(v) })));
      const exp = lines(p, 'A08CY01', y, c => /^EXP/.test(c)).filter(([lab]) => !/^total/i.test(lab)).sort((a, b) => Math.abs(b[1]) - Math.abs(a[1]));
      const expT = el('table', { class: 'proc-table' }, el('caption', { text: 'Operating expenses by type' }), ...exp.map(([lab, v]) => el('tr', null, el('td', { text: lab }), el('td', { text: k(v) }))));
      const src = lines(p, 'A06CY01', y, c => /^INC1[12]\d\d$/.test(c) && c !== 'INC1220').sort((a, b) => b[1] - a[1]);
      const srcT = el('table', { class: 'proc-table' }, el('caption', { text: 'Income from patient care, by who paid' }), ...src.map(([lab, v]) => el('tr', null, el('td', { text: lab }), el('td', { text: k(v) }))));
      const hist = el('table', { class: 'proc-table' }, el('caption', { text: 'History' }), el('tr', null, ...['Year', 'Operating income', 'Operating expenses', 'Surplus / (deficit)'].map(h => el('th', { text: h }))));
      for (const fy of Object.keys(d.years).sort()) { const b = d.years[fy].providers.find(x => same(x, p)); hist.append(el('tr', null, el('td', { text: fy }), el('td', { text: b ? k(income(b)) : 'Not in this year\'s data' }), el('td', { text: b ? k(expenses(b)) : '' }), el('td', { text: b ? k(result(b)) : '' }))); }
      const close = el('button', { type: 'button', text: 'Close' }); close.onclick = () => { detail.hidden = true; };
      detail.replaceChildren(...[el('h3', { text: p.name }), el('p', { class: 'small', text: [p.type, p.sector, p.region, p.code].filter(Boolean).join(' · ') }),
        el('div', { class: 'table-wrap' }, hist), el('div', { class: 'table-wrap' }, soci), exp.length ? el('div', { class: 'table-wrap' }, expT) : null, src.length ? el('div', { class: 'table-wrap' }, srcT) : null, close].filter(Boolean));
      detail.hidden = false; detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    function render() {
      const y = d.years[ySel.value], f = q.value.trim().toLowerCase(), sec = secSel.value, [label, key] = SORTS[sortSel.value];
      const rows = y.providers.filter(p => (!sec || p.sector === sec) && (!f || [p.name, p.region, p.code].join(' ').toLowerCase().includes(f)));
      rows.sort((a, b) => (key(b) ?? -Infinity) - (key(a) ?? -Infinity));
      const t = el('table', { class: 'proc-table' }, el('caption', { text: ySel.value + ' · sorted by ' + label.toLowerCase() }), el('tr', null, ...['Trust', 'Type', 'Operating income', 'Operating expenses', 'Surplus / (deficit)'].map(h => el('th', { text: h }))));
      for (const p of rows.slice(0, limit)) {
        const b = el('button', { type: 'button', class: 'linklike', text: p.name }); b.onclick = () => showDetail(p.name);
        t.append(el('tr', null, el('td', null, b), el('td', { text: (p.sector || '') + (p.type === 'NHS foundation trust' ? ' · FT' : '') }), el('td', { text: k(income(p)) }), el('td', { text: k(expenses(p)) }), el('td', { text: k(result(p)) })));
      }
      const deficits = y.providers.filter(p => result(p) < 0).length;
      out.replaceChildren(el('p', { class: 'small', role: 'status', text: rows.length + ' trusts shown · ' + y.providers.length + ' in ' + ySel.value + ', of which ' + deficits + ' reported a deficit for the year' }), el('div', { class: 'table-wrap' }, t));
      more.hidden = rows.length <= limit;
    }
    more.onclick = () => { limit += 30; render(); };
    ySel.onchange = () => { detail.hidden = true; render(); }; secSel.onchange = sortSel.onchange = () => { limit = 30; render(); }; q.oninput = () => { limit = 30; render(); };
    const latest = d.years[years[0]];
    box.replaceChildren(
      el('p', { class: 'small', text: 'Source: ' }, el('a', { href: d.page, target: '_blank', rel: 'noopener noreferrer', text: 'NHS England trust accounts consolidation (TAC) data' }), document.createTextNode(' · '), el('a', { href: latest.files.trust, target: '_blank', rel: 'noopener noreferrer', text: 'NHS trusts ' + years[0] }), ...(latest.files.foundation ? [document.createTextNode(' · '), el('a', { href: latest.files.foundation, target: '_blank', rel: 'noopener noreferrer', text: 'foundation trusts ' + years[0] })] : []),
      el('div', { class: 'filters' }, el('div', null, el('label', { for: 'nhs-year', text: 'Financial year' }), ySel), el('div', null, el('label', { for: 'nhs-sector', text: 'Type of trust' }), secSel),
        el('div', null, el('label', { for: 'nhs-sort', text: 'Sort by' }), sortSel), el('div', null, el('label', { for: 'nhs-query', text: 'Find a trust' }), q)),
      detail, out, more,
      el('details', null, el('summary', { text: 'What these figures mean' }), ...d.caveats.map(c => el('p', { class: 'small', text: c })), el('p', { class: 'small', text: 'Values are in pounds as published in thousands. Operating income is income from patient care plus other operating income; the surplus or deficit is the accounts\' result for the year after finance costs. It includes one-off accounting items such as impairments and transfers between trusts when services move, so it differs from the adjusted financial performance NHS England uses for financial targets.' }))));
    render();
    const fromHash = () => { const m = location.hash.match(/^#nhs-trusts\/(.+)$/); if (m) { ySel.value = years[0]; render(); const name = decodeURIComponent(m[1]); const p = d.years[years[0]].providers.find(x => x.code === name || x.name === name); if (p) showDetail(p.name); } };
    window.addEventListener('hashchange', fromHash); fromHash();
  }).catch(() => { box.textContent = 'NHS trust accounts are not available yet.'; });
})();

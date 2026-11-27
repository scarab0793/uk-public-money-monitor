// Welsh council revenue outturn by service (Welsh Government, StatsWales), from data/local-government/revenue-outturn-wales.json.
(function () {
  'use strict';
  const box = document.getElementById('council-spending-wales-body'); if (!box) return;
  const el = (tag, props, ...kids) => {
    const e = document.createElement(tag);
    if (props) for (const [k, v] of Object.entries(props)) { if (v == null) continue; if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v); }
    for (const k of kids) if (k != null) e.append(k);
    return e;
  };
  // values are £ thousand
  const k = v => v == null ? 'Not available' : v === 0 ? '£0' : (v < 0 ? '−' : '') + '£' + (Math.abs(v) >= 1e6 ? (Math.abs(v) / 1e6).toLocaleString('en-GB', { maximumFractionDigits: 2 }) + 'bn' : Math.abs(v) >= 1000 ? (Math.abs(v) / 1000).toLocaleString('en-GB', { maximumFractionDigits: 1 }) + 'm' : Math.round(Math.abs(v)).toLocaleString('en-GB') + 'k');
  const ext = (href, text) => el('a', { href, target: '_blank', rel: 'noopener noreferrer', text });
  fetch('./data/local-government/revenue-outturn-wales.json', { cache: 'no-store' }).then(r => { if (!r.ok) throw 0; return r.json(); }).then(d => {
    const years = d.years.slice().reverse(), TOTAL = d.services[d.services.length - 1];
    const groups = [...new Set(d.authorities.map(a => a.group))];
    const ySel = el('select', { id: 'law-year' }, ...years.map(y => el('option', { value: y, text: y })));
    const sSel = el('select', { id: 'law-service' }, ...d.services.slice().reverse().map(s => el('option', { value: s, text: s === TOTAL ? 'All services (revenue expenditure)' : s })));
    const gSel = el('select', { id: 'law-group' }, ...groups.map(g => el('option', { value: g, text: g === 'total' ? 'Published totals' : g })));
    const detail = el('div', { class: 'card', hidden: '' }), out = el('div');
    function showDetail(name) {
      const a = d.authorities.find(x => x.name === name); if (!a) return;
      const fy = ySel.value, v = a.values[fy] || {};
      const t = el('table', { class: 'proc-table' }, el('caption', { text: a.name + ' · ' + fy + ' revenue outturn' }), el('tr', null, el('th', { text: 'Service' }), el('th', { text: 'Spending' })));
      for (const s of d.services) t.append(el('tr', s === TOTAL ? { class: 'agg' } : null, el('td', { text: s }), el('td', { text: k(v[s]) })));
      const hist = el('table', { class: 'proc-table' }, el('caption', { text: sSel.value + ' by year' }), el('tr', null, el('th', { text: 'Year' }), el('th', { text: 'Spending' })));
      for (const y of d.years) hist.append(el('tr', null, el('td', { text: y }), el('td', { text: k((a.values[y] || {})[sSel.value]) })));
      const close = el('button', { type: 'button', text: 'Close' }); close.onclick = () => { detail.hidden = true; };
      detail.replaceChildren(el('div', { class: 'table-wrap' }, t), el('div', { class: 'table-wrap' }, hist), close);
      detail.hidden = false; detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    function render() {
      const fy = ySel.value, svc = sSel.value, g = gSel.value;
      const val = a => (a.values[fy] || {})[svc];
      const rows = d.authorities.filter(a => a.group === g).sort((a, b) => (val(b) ?? -Infinity) - (val(a) ?? -Infinity));
      const t = el('table', { class: 'proc-table' }, el('caption', { text: (svc === TOTAL ? 'All services' : svc) + ' · ' + fy + ' · £, nominal' }), el('tr', null, el('th', { text: 'Authority' }), el('th', { text: 'Spending' })));
      for (const a of rows) { const b = el('button', { type: 'button', class: 'linklike', text: a.name }); b.onclick = () => showDetail(a.name); t.append(el('tr', null, el('td', null, b), el('td', { text: k(val(a)) }))); }
      const missing = rows.filter(a => val(a) == null).length;
      out.replaceChildren(el('p', { class: 'small', role: 'status', text: rows.length + ' authorities' + (missing ? ' · ' + missing + ' without a figure for this service and year (shown as not available, never as zero)' : '') }), el('div', { class: 'table-wrap' }, t));
    }
    ySel.onchange = sSel.onchange = gSel.onchange = () => { detail.hidden = true; render(); };
    box.replaceChildren(
      el('p', { class: 'small', text: 'Source: ' }, ext(d.statswales, d.publisher + ': ' + d.dataset), document.createTextNode(' · '), ext(d.page, 'Release'), document.createTextNode(' · '), ext(d.attachment, 'Download the official data (CSV)')),
      el('div', { class: 'filters' }, el('div', null, el('label', { for: 'law-year', text: 'Financial year' }), ySel), el('div', null, el('label', { for: 'law-service', text: 'Service' }), sSel), el('div', null, el('label', { for: 'law-group', text: 'Type of authority' }), gSel)),
      detail, out,
      el('details', null, el('summary', { text: 'What these figures mean' }), ...d.caveats.filter(Boolean).map(c => el('p', { class: 'small', text: c }))));
    render();
    const fromHash = () => { const m = location.hash.match(/^#council-spending\/wales\/(.+)$/); if (m) { ySel.value = years[0]; render(); showDetail(decodeURIComponent(m[1])); } };
    window.addEventListener('hashchange', fromHash); fromHash();
  }).catch(() => { box.textContent = 'Welsh council spending data is not available yet.'; });
})();

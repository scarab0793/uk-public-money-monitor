// NHS Wales spending by health condition (Welsh Government programme budgets), from data/nhs/wales-programme-budgets.json.
(function () {
  'use strict';
  const box = document.getElementById('nhs-wales-body'); if (!box) return;
  const el = (tag, props, ...kids) => {
    const e = document.createElement(tag);
    if (props) for (const [k, v] of Object.entries(props)) { if (v == null) continue; if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v); }
    for (const k of kids) if (k != null) e.append(k);
    return e;
  };
  // values are £ thousand
  const k = v => v == null ? 'Not available' : v === 0 ? '£0' : (v < 0 ? '−' : '') + '£' + (Math.abs(v) >= 1e6 ? (Math.abs(v) / 1e6).toLocaleString('en-GB', { maximumFractionDigits: 2 }) + 'bn' : Math.abs(v) >= 1000 ? (Math.abs(v) / 1000).toLocaleString('en-GB', { maximumFractionDigits: 1 }) + 'm' : Math.round(Math.abs(v)).toLocaleString('en-GB') + 'k');
  const ext = (href, text) => el('a', { href, target: '_blank', rel: 'noopener noreferrer', text });
  const COM = 'LHB and PHW total';
  fetch('./data/nhs/wales-programme-budgets.json', { cache: 'no-store' }).then(r => { if (!r.ok) throw 0; return r.json(); }).then(d => {
    const years = d.years.slice().reverse();
    const orgs = Object.keys(d.organisations).sort((a, b) => (a !== 'Wales') - (b !== 'Wales') || a.localeCompare(b));
    const ySel = el('select', { id: 'nhsw-year' }), oSel = el('select', { id: 'nhsw-org' }, ...orgs.map(o => el('option', { value: o, text: o === 'Wales' ? 'All of Wales' : o })));
    const cSel = el('select', { id: 'nhsw-cat' }, ...d.categories.filter(c => c !== 'Total').map(c => el('option', { value: c, text: c })));
    const chart = el('div'), trend = el('div');
    const vals = (o, fy) => ((d.organisations[o] || {})[fy] || {})[COM] || {};
    function fillYears() {
      const ys = years.filter(y => Object.keys(vals(oSel.value, y)).length), cur = ySel.value;
      ySel.replaceChildren(...ys.map(y => el('option', { value: y, text: y })));
      ySel.value = ys.includes(cur) ? cur : ys[0];
    }
    function render() {
      const v = vals(oSel.value, ySel.value), total = v.Total;
      const rows = d.top_level.map(c => [c, v[c]]).sort((a, b) => (b[1] ?? -Infinity) - (a[1] ?? -Infinity));
      const max = Math.max(...rows.map(r => r[1] || 0));
      chart.replaceChildren(el('p', { class: 'small', text: (oSel.value === 'Wales' ? 'All of Wales' : oSel.value) + ', ' + ySel.value + ': total NHS spending analysed ' + k(total) + '. Select a condition below to see its parts and how it changed over time.' }));
      for (const [c, x] of rows) {
        const row = el('div', { class: 'barrow', title: total ? (x / total * 100).toFixed(1) + '% of the total' : null },
          el('span', { class: 'barlabel', text: c }), el('span', { class: 'bar', style: 'width:' + Math.max(0.5, (x || 0) / max * 100) + '%' }), el('span', { class: 'barval', text: k(x) }));
        row.style.cursor = 'pointer'; row.onclick = () => { cSel.value = c; renderTrend(); };
        chart.append(row);
      }
      renderTrend();
    }
    function renderTrend() {
      const c = cSel.value, parts = d.parts[c] || Object.keys(d.of_which).filter(x => d.of_which[x] === c);
      const t = el('table', { class: 'proc-table' }, el('caption', { text: c + ' · ' + (oSel.value === 'Wales' ? 'All of Wales' : oSel.value) + ' · £, nominal' }),
        el('tr', null, el('th', { text: 'Year' }), el('th', { text: c }), ...parts.map(p => el('th', { text: (d.of_which[p] ? 'of which ' : '') + p }))));
      const issues = (d.breakdown_issues || []).filter(i => i.organisation === oSel.value && i.category === c && i.commissioner === COM);
      for (const y of d.years) { const v = vals(oSel.value, y); if (!Object.keys(v).length) continue; const bad = issues.some(i => i.year === y); t.append(el('tr', null, el('td', { text: y + (bad ? ' *' : '') }), el('td', { text: k(v[c]) }), ...parts.map(p => el('td', { text: k(v[p]) })))); }
      trend.replaceChildren(el('div', { class: 'table-wrap' }, t), issues.length ? el('p', { class: 'small', text: '* In ' + issues.map(i => i.year).join(', ') + ' the published breakdown adds up to ' + k(issues[0].parts_sum) + (issues.length > 1 ? ' (first year shown)' : '') + ', not the published ' + k(issues[0].published) + '. The figures are shown as published by the Welsh Government.' }) : null);
    }
    oSel.onchange = () => { fillYears(); render(); }; ySel.onchange = render; cSel.onchange = renderTrend;
    box.replaceChildren(
      el('p', { class: 'small', text: 'Source: ' }, ext(d.statswales, d.publisher + ': ' + d.dataset), document.createTextNode(' · '), ext(d.attachment, 'Download the official data (CSV)')),
      el('div', { class: 'filters' }, el('div', null, el('label', { for: 'nhsw-org', text: 'Health board' }), oSel), el('div', null, el('label', { for: 'nhsw-year', text: 'Financial year' }), ySel), el('div', null, el('label', { for: 'nhsw-cat', text: 'Condition' }), cSel)),
      chart, trend,
      el('details', null, el('summary', { text: 'What these figures mean' }), ...d.caveats.filter(Boolean).map(c => el('p', { class: 'small', text: c }))));
    cSel.value = 'Mental health problems'; fillYears(); render();
  }).catch(() => { box.textContent = 'NHS Wales programme budget data is not available yet.'; });
})();

// Illustrative Income Tax and employee NI calculator (rates in data/tax/income-tax-2025-26.json),
// plus a proportional breakdown of the result by HM Treasury spending function.
(function () {
  'use strict';
  const out = document.getElementById('out'), salary = document.getElementById('salary'), nation = document.getElementById('calc-nation'), yearSel = document.getElementById('calc-year');
  if (!out || !salary || !nation) return;
  const money = x => new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP', maximumFractionDigits: 2 }).format(x);
  const el = (tag, props, ...kids) => { const e = document.createElement(tag); if (props) for (const [k, v] of Object.entries(props)) { if (v == null) continue; if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v); } for (const k of kids) if (k != null) e.append(k); return e; };
  let ALL = null, R = null, tes = null;
  function tax(gross) {
    const pa = R.personal_allowance, allowance = gross > pa.taper_starts ? Math.max(0, pa.amount - (gross - pa.taper_starts) * pa.taper_rate) : pa.amount;
    const taxable = Math.max(0, gross - allowance), bands = R.income_tax[nation.value].bands;
    let lower = 0, total = 0; const parts = [];
    for (const b of bands) {
      const upper = b.upto == null ? Infinity : b.upto, inBand = Math.max(0, Math.min(taxable, upper) - lower);
      if (inBand > 0) { parts.push([b.name + ' ' + Math.round(b.rate * 100) + '%', inBand, inBand * b.rate]); total += inBand * b.rate; }
      lower = upper;
    }
    const n = R.employee_ni, ni = Math.max(0, Math.min(gross, n.upper_earnings_limit) - n.primary_threshold) * n.main_rate + Math.max(0, gross - n.upper_earnings_limit) * n.upper_rate;
    return { allowance, taxable, parts, total, ni };
  }
  function render() {
    if (!R) return;
    const gross = Math.max(0, Number(salary.value) || 0), t = tax(gross), it = R.income_tax[nation.value];
    const table = el('table', { class: 'proc-table' }, el('caption', { text: it.label + ' · ' + R.tax_year }), el('tr', null, el('th', { text: 'Band' }), el('th', { text: 'Income in band' }), el('th', { text: 'Tax' })));
    for (const [name, inBand, due] of t.parts) table.append(el('tr', null, el('td', { text: name }), el('td', { text: money(inBand) }), el('td', { text: money(due) })));
    const nodes = [
      el('p', null, document.createTextNode('Personal Allowance: '), el('strong', { text: money(t.allowance) })),
      el('div', { class: 'table-wrap' }, table),
      el('p', null, document.createTextNode('Income Tax: '), el('strong', { text: money(t.total) })),
      el('p', null, document.createTextNode('Employee National Insurance: '), el('strong', { text: money(t.ni) })),
      el('p', null, document.createTextNode('Take-home pay before pension, student loan and other deductions: '), el('span', { class: 'result', text: money(gross - t.total - t.ni) })),
      el('p', { class: 'small' }, document.createTextNode('Rates: '), el('a', { href: it.source, target: '_blank', rel: 'noopener noreferrer', text: it.label + ' Income Tax' }), document.createTextNode(' · '), el('a', { href: R.employee_ni.source, target: '_blank', rel: 'noopener noreferrer', text: 'National Insurance' }))];
    if (tes && t.total + t.ni > 0) {
      const { year, rows, total } = tes, paid = t.total + t.ni;
      const box = el('details', null, el('summary', { text: 'How public spending was divided in ' + year + ', applied to your ' + money(paid) }),
        el('p', { class: 'small', text: 'Your Income Tax and NI are not earmarked for particular services. This shows each function\'s share of total public sector expenditure on services in ' + year + ' (HM Treasury, outturn) multiplied by what you pay. Spending is also funded by other taxes and by borrowing.' }));
      for (const r of rows) box.append(el('div', { class: 'barrow' }, el('span', { class: 'barlabel', text: r.name }), el('span', { class: 'bar', style: 'width:' + Math.max(0.5, r.v / rows[0].v * 100) + '%' }), el('span', { class: 'barval', text: money(paid * r.v / total) })));
      nodes.push(box);
    }
    out.replaceChildren(...nodes);
  }
  window.calculate = render;
  salary.addEventListener('input', render); nation.addEventListener('change', render);
  if (yearSel) yearSel.addEventListener('change', () => { R = ALL.years[yearSel.value]; render(); });
  fetch('./data/tax/income-tax-rates.json', { cache: 'no-store' }).then(r => r.json()).then(j => { ALL = j; const ys = Object.keys(j.years).sort().reverse(); if (yearSel) { yearSel.replaceChildren(...ys.map(y => Object.assign(document.createElement('option'), { value: y, textContent: y.replace('-', ' to 20') }))); } R = j.years[ys[0]]; render(); }).catch(() => { out.textContent = 'Tax rates are unavailable.'; });
  fetch('./data/treasury/pss-expenditure-on-services.json', { cache: 'no-store' }).then(r => r.json()).then(d => {
    const t = d.tables.Table_9, total = t.rows.find(r => r.level === 'total');
    const i = total.values.map(v => v[1]).lastIndexOf('outturn'); if (i < 0) return;
    const rows = t.rows.filter(r => r.level === 'function' && r.values[i][2] > 0).map(r => ({ name: r.name || r.label, v: r.values[i][2] })).sort((a, b) => b.v - a.v);
    tes = { year: total.values[i][0], total: rows.reduce((a, r) => a + r.v, 0), rows }; render();
  }).catch(() => {});
})();

// Civil Service headcount and pay by department (Cabinet Office Civil Service Statistics), from data/government/civil-service-pay.json.
(function () {
  'use strict';
  const box = document.getElementById('civil-service-pay-body'); if (!box) return;
  const el = (tag, props, ...kids) => {
    const e = document.createElement(tag);
    if (props) for (const [k, v] of Object.entries(props)) { if (v == null) continue; if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v); }
    for (const k of kids) if (k != null) e.append(k);
    return e;
  };
  const pounds = v => v == null ? 'Not available' : '£' + Math.round(v).toLocaleString('en-GB');
  const num = v => v == null ? 'Not available' : Math.round(v).toLocaleString('en-GB');
  const ext = (href, text) => el('a', { href, target: '_blank', rel: 'noopener noreferrer', text });
  fetch('./data/government/civil-service-pay.json', { cache: 'no-store' }).then(r => { if (!r.ok) throw 0; return r.json(); }).then(d => {
    const L = d.levels, ALL = L.length - 1;
    const cs = d.organisations.find(o => o.organisation === 'Overall Civil Service');
    const depts = d.organisations.filter(o => o.overall && o !== cs);
    const SORTS = { headcount: ['Most staff', o => o.headcount[ALL]], median: ['Highest median salary', o => (o.median_salary || [])[ALL]], ratio: ['Widest pay ratio', o => o.pay_ratio] };
    const sortSel = el('select', { id: 'csp-sort' }, ...Object.entries(SORTS).map(([v, [t]]) => el('option', { value: v, text: t })));
    const q = el('input', { id: 'csp-query', placeholder: 'Department or organisation', autocomplete: 'off' });
    const detail = el('div', { class: 'card', hidden: '' }), out = el('div');
    function showDetail(dept) {
      const parts = d.organisations.filter(o => o.department === dept);
      const t = el('table', { class: 'proc-table' }, el('caption', { text: dept + ' · median salary by grade, ' + d.as_at }), el('tr', null, el('th', { text: 'Organisation' }), ...L.map(l => el('th', { text: l }))));
      for (const o of parts) t.append(el('tr', o.overall ? { class: 'agg' } : null, el('td', { text: o.organisation }), ...L.map((l, i) => el('td', { text: pounds((o.median_salary || [])[i]) }))));
      const h = el('table', { class: 'proc-table' }, el('caption', { text: dept + ' · headcount by grade, ' + d.as_at }), el('tr', null, el('th', { text: 'Organisation' }), ...L.map(l => el('th', { text: l }))));
      for (const o of parts) h.append(el('tr', o.overall ? { class: 'agg' } : null, el('td', { text: o.organisation }), ...L.map((l, i) => el('td', { text: num(o.headcount[i]) }))));
      const close = el('button', { type: 'button', text: 'Close' }); close.onclick = () => { detail.hidden = true; };
      detail.replaceChildren(el('h3', { text: dept }), el('p', { class: 'small', text: 'The Overall row includes every organisation listed above it; the rows are not to be added together.' }), el('div', { class: 'table-wrap' }, h), el('div', { class: 'table-wrap' }, t), close);
      detail.hidden = false; detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    function render() {
      const f = q.value.trim().toLowerCase(), key = SORTS[sortSel.value][1];
      const match = o => !f || d.organisations.some(x => x.department === o.department && (x.organisation + ' ' + x.department).toLowerCase().includes(f));
      const rows = depts.filter(match).sort((a, b) => (key(b) ?? -Infinity) - (key(a) ?? -Infinity));
      const t = el('table', { class: 'proc-table' }, el('caption', { text: 'Civil Service departments · ' + d.as_at }), el('tr', null, ...['Department (with its agencies)', 'Civil servants', 'Senior civil servants', 'Median salary', 'Highest earner (pay band mid-point)', 'Highest to median'].map(x => el('th', { text: x }))));
      for (const o of rows) {
        const b = el('button', { type: 'button', class: 'linklike', text: o.department }); b.onclick = () => showDetail(o.department);
        t.append(el('tr', null, el('td', null, b), el('td', { text: num(o.headcount[ALL]) }), el('td', { text: num(o.headcount[0]) }), el('td', { text: pounds((o.median_salary || [])[ALL]) }), el('td', { text: pounds(o.highest_earner) }), el('td', { text: o.pay_ratio == null ? 'Not available' : o.pay_ratio + ' times' })));
      }
      out.replaceChildren(el('p', { class: 'small', role: 'status', text: rows.length + ' departments' }), el('div', { class: 'table-wrap' }, t));
    }
    const S = d.salary_series, iMed = S.columns.findIndex(c => /^Median salary of all/i.test(c)), iMean = S.columns.findIndex(c => /^Mean salary of all/i.test(c));
    const trend = el('table', { class: 'proc-table' }, el('caption', { text: 'Civil Service salary over time (as at 31 March, £, nominal)' }), el('tr', null, ...['Year', 'Median salary', 'Mean salary'].map(x => el('th', { text: x }))));
    for (const r of S.rows) trend.append(el('tr', null, el('td', { text: r[0] }), el('td', { text: pounds(r[1 + iMed]) }), el('td', { text: pounds(r[1 + iMean]) })));
    sortSel.onchange = q.oninput = render;
    box.replaceChildren(
      el('p', { class: 'small', text: 'Source: ' }, ext(d.page, d.publisher + ': ' + d.dataset), document.createTextNode(' · '), ext(d.attachment, 'Download the statistical tables')),
      el('div', { class: 'grid' }, ...[['Civil servants', num(cs.headcount[ALL])], ['Median salary', pounds(cs.median_salary[ALL])], ['Senior civil servants', num(cs.headcount[0])], ['Highest earner to median', cs.pay_ratio + ' times']].map(([a, b]) => el('div', { class: 'card' }, el('div', { class: 'small', text: a }), el('strong', { text: b })))),
      el('div', { class: 'filters' }, el('div', null, el('label', { for: 'csp-sort', text: 'Sort by' }), sortSel), el('div', { style: 'grid-column:span 2' }, el('label', { for: 'csp-query', text: 'Find a department or agency' }), q)),
      detail, out, el('div', { class: 'table-wrap' }, trend),
      el('details', null, el('summary', { text: 'What these figures mean' }), ...d.caveats.map(c => el('p', { class: 'small', text: c }))));
    render();
    const fromHash = () => { const m = location.hash.match(/^#civil-service-pay\/(.+)$/); if (m) showDetail(decodeURIComponent(m[1])); };
    window.addEventListener('hashchange', fromHash); fromHash();
  }).catch(() => { box.textContent = 'Civil Service pay data is not available yet.'; });
})();

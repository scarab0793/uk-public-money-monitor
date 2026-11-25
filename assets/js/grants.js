// UK government grants (Government Grants Information System), from data/grants/government-grants.json.
(function () {
  'use strict';
  const box = document.getElementById('grants-body'); if (!box) return;
  const el = (tag, props, ...kids) => {
    const e = document.createElement(tag);
    if (props) for (const [k, v] of Object.entries(props)) { if (v == null) continue; if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v); }
    for (const k of kids) if (k != null) e.append(k);
    return e;
  };
  const gbp = v => v == null ? 'Not available' : (v < 0 ? '−' : '') + '£' + (Math.abs(v) >= 1e9 ? (Math.abs(v) / 1e9).toLocaleString('en-GB', { maximumFractionDigits: 2 }) + 'bn' : Math.abs(v) >= 1e6 ? (Math.abs(v) / 1e6).toLocaleString('en-GB', { maximumFractionDigits: 1 }) + 'm' : Math.abs(v) >= 1e3 ? (Math.abs(v) / 1e3).toLocaleString('en-GB', { maximumFractionDigits: 1 }) + 'k' : Math.round(Math.abs(v)).toLocaleString('en-GB'));
  const DEPT = { DfE: 'Department for Education', MHCLG: 'Ministry of Housing, Communities and Local Government', HO: 'Home Office', DHSC: 'Department of Health and Social Care', DSIT: 'Department for Science, Innovation and Technology', DfT: 'Department for Transport', DESNZ: 'Department for Energy Security and Net Zero', FCDO: 'Foreign, Commonwealth and Development Office', Defra: 'Department for Environment, Food and Rural Affairs', DWP: 'Department for Work and Pensions', DCMS: 'Department for Culture, Media and Sport', MoJ: 'Ministry of Justice', DBT: 'Department for Business and Trade', CO: 'Cabinet Office', MoD: 'Ministry of Defence', HMT: 'HM Treasury', HMRC: 'HM Revenue and Customs', TNA: 'The National Archives' };
  const ext = (href, text) => el('a', { href, target: '_blank', rel: 'noopener noreferrer', text });
  fetch('./data/grants/government-grants.json', { cache: 'no-store' }).then(r => { if (!r.ok) throw 0; return r.json(); }).then(d => {
    const T = d.departments, yi = T.years.length - 1;
    const depts = T.rows.filter(r => r.department !== 'Total' && (r.values.total || [])[yi] != null).sort((a, b) => b.values.total[yi] - a.values.total[yi]);
    const total = T.rows.find(r => r.department === 'Total');
    const max = Math.max(...depts.map(r => r.values.total[yi]));
    const deptBox = el('div', null, el('h3', { text: 'Grant spending by department, ' + T.years[yi] }),
      el('p', { class: 'small', text: 'Money paid out as grants in the year, £ million as published. Formula grants are allocated by a set formula (for example to councils and schools); general grants are awarded to chosen recipients.' + (total ? ' All departments: ' + gbp(total.values.total[yi] * 1e6) + '.' : '') }));
    for (const r of depts) {
      const v = r.values.total[yi], f = (r.values.formula || [])[yi], g = (r.values.general || [])[yi];
      deptBox.append(el('div', { class: 'barrow', title: 'Formula ' + gbp(f == null ? null : f * 1e6) + ' · general ' + gbp(g == null ? null : g * 1e6) },
        el('span', { class: 'barlabel', text: DEPT[r.department] || r.department }), el('span', { class: 'bar', style: 'width:' + Math.max(0.5, v / max * 100) + '%' }), el('span', { class: 'barval', text: gbp(v * 1e6) })));
    }
    const mode = el('select', { id: 'grants-mode' }, el('option', { value: 'schemes', text: 'Grant schemes' }), el('option', { value: 'recipients', text: 'Recipients' }), el('option', { value: 'awards', text: 'Largest individual awards' }));
    const q = el('input', { id: 'grants-query', placeholder: 'Scheme, recipient, department or company number', autocomplete: 'off' });
    const out = el('div'), more = el('button', { type: 'button', hidden: '', text: 'Show more' });
    let limit = 30;
    const ch = n => ext('https://find-and-update.company-information.service.gov.uk/company/' + n, n);
    const cc = n => ext('https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/' + n, n);
    function render() {
      const m = mode.value, f = q.value.trim().toLowerCase();
      let head, rows, line, note;
      if (m === 'schemes') {
        head = ['Scheme', 'Department', 'Method', 'Spent in ' + d.financial_year];
        rows = d.schemes.rows.filter(r => !f || [r[1], r[2], r[3], r[0], r[6]].join(' ').toLowerCase().includes(f));
        line = r => [el('td', { text: r[1] }), el('td', { text: r[2] + (r[3] && r[3] !== r[2] ? ' (' + r[3] + ')' : '') }), el('td', { text: r[5] || '' }), el('td', { text: gbp(r[4]) })];
        note = d.schemes.rows.length + ' schemes';
      } else if (m === 'recipients') {
        head = ['Recipient', 'Registered number', 'Awards', 'Amount awarded', 'From'];
        rows = d.recipients.rows.filter(r => !f || [r[1], r[2], r[3], r[6].join(' '), r[7].join(' ')].join(' ').toLowerCase().includes(f));
        line = r => [el('td', { text: r[1] }), el('td', null, r[2] ? ch(r[2]) : r[3] && /^\d+$/.test(r[3]) ? cc(r[3]) : document.createTextNode(r[3] || '—')), el('td', { text: r[5] }), el('td', { text: gbp(r[4]) }), el('td', { class: 'small', text: r[6].join(', ') })];
        note = d.recipients.rows.length.toLocaleString('en-GB') + ' recipients awarded £100,000 or more are listed, out of ' + d.recipients.total_recipients.toLocaleString('en-GB') + ' in the register';
      } else {
        head = ['Award', 'Recipient', 'Department', 'Date', 'Amount awarded'];
        rows = d.awards.rows.filter(r => !f || [r[1], r[2], r[3], r[4]].join(' ').toLowerCase().includes(f));
        line = r => [el('td', null, el('strong', { text: r[1] || r[4] }), el('br'), el('span', { class: 'small', text: r[4] })), el('td', { text: r[2] }), el('td', { text: r[3] }), el('td', { text: r[5] }), el('td', { text: gbp(r[0]) })];
        note = 'The ' + d.awards.rows.length.toLocaleString('en-GB') + ' largest of ' + d.awards.total_awards.toLocaleString('en-GB') + ' awards in the register';
      }
      const t = el('table', { class: 'proc-table' }, el('caption', { text: mode.selectedOptions[0].text + ' · ' + d.financial_year }), el('tr', null, ...head.map(h => el('th', { text: h }))));
      for (const r of rows.slice(0, limit)) t.append(el('tr', null, ...line(r)));
      out.replaceChildren(el('p', { class: 'small', role: 'status', text: (f ? rows.length.toLocaleString('en-GB') + ' matches · ' : '') + note }), el('div', { class: 'table-wrap' }, t));
      more.hidden = rows.length <= limit;
    }
    more.onclick = () => { limit += 30; render(); };
    mode.onchange = q.oninput = () => { limit = 30; render(); };
    box.replaceChildren(
      el('p', { class: 'small', text: 'Source: ' }, ext(d.page, 'Cabinet Office ' + d.dataset), document.createTextNode(' · '), ext(d.attachment, 'Download the grants register')),
      deptBox,
      el('div', { class: 'filters' }, el('div', null, el('label', { for: 'grants-mode', text: 'Show' }), mode), el('div', { style: 'grid-column:span 2' }, el('label', { for: 'grants-query', text: 'Search' }), q)),
      out, more,
      el('details', null, el('summary', { text: 'What these figures mean' }), ...d.caveats.map(c => el('p', { class: 'small', text: c }))));
    render();
    const fromHash = () => { const m = location.hash.match(/^#grants\/(schemes|recipients|awards)\/(.*)$/); if (m) { mode.value = m[1]; q.value = decodeURIComponent(m[2]); limit = 30; render(); document.getElementById('grants').scrollIntoView(); } };
    window.addEventListener('hashchange', fromHash); fromHash();
  }).catch(() => { box.textContent = 'Grants data is not available yet.'; });
})();

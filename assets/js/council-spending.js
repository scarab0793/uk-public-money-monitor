// English council revenue outturn by service (MHCLG RSX), from data/local-government/revenue-outturn-england.json.
(function () {
  'use strict';
  const box = document.getElementById('council-spending-body'); if (!box) return;
  const el = (tag, props, ...kids) => {
    const e = document.createElement(tag);
    if (props) for (const [k, v] of Object.entries(props)) { if (v == null) continue; if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v); }
    for (const k of kids) if (k != null) e.append(k);
    return e;
  };
  const CLASSES = { UA: 'Unitary authority', MD: 'Metropolitan district', LB: 'London borough', SC: 'County council', SD: 'District council', O: 'Other (fire, police, transport, parks, combined and waste authorities, GLA)' };
  const k = v => v == null ? 'Not available' : v === 0 ? '£0' : (v < 0 ? '−' : '') + '£' + (Math.abs(v) >= 1e6 ? (Math.abs(v) / 1e6).toLocaleString('en-GB', { maximumFractionDigits: 2 }) + 'bn' : Math.abs(v) >= 1000 ? (Math.abs(v) / 1000).toLocaleString('en-GB', { maximumFractionDigits: 1 }) + 'm' : Math.round(Math.abs(v)).toLocaleString('en-GB') + 'k');
  fetch('./data/local-government/revenue-outturn-england.json', { cache: 'no-store' }).then(r => { if (!r.ok) throw 0; return r.json(); }).then(d => {
    const years = Object.keys(d.years).sort().reverse();
    const ySel = el('select', { id: 'lae-year' }, ...years.map(y => el('option', { value: y, text: y })));
    const sSel = el('select', { id: 'lae-service' });
    const cSel = el('select', { id: 'lae-class' }, el('option', { value: '', text: 'All types' }), ...Object.entries(CLASSES).map(([c, t]) => el('option', { value: c, text: t })));
    const q = el('input', { id: 'lae-query', placeholder: 'Council name, e.g. Leeds, Kent CC, Camden', autocomplete: 'off' });
    const detail = el('div', { class: 'card', hidden: '' }), out = el('div'), more = el('button', { type: 'button', hidden: '', text: 'Show more' });
    let limit = 40;
    function fillServices() {
      const cur = sSel.value, svcs = d.years[ySel.value].services;
      sSel.replaceChildren(...svcs.map(s => el('option', { value: s, text: s })));
      sSel.value = svcs.includes(cur) ? cur : svcs.includes('Total Service Expenditure') ? 'Total Service Expenditure' : svcs[0];
    }
    function showDetail(code) {
      const y = d.years[ySel.value], a = y.authorities.find(x => x.ecode === code); if (!a) return;
      const t = el('table', { class: 'proc-table' }, el('caption', { text: a.name + ' · ' + (CLASSES[a.cls] || a.cls || '') + ' · ' + ySel.value + ' revenue outturn' }),
        el('tr', null, ...['Service', 'Spending', 'Income', 'Net cost'].map(h => el('th', { text: h }))));
      for (const s of y.services) { const v = a.values[s] || []; const tr = el('tr', s === 'Total Service Expenditure' ? { class: 'agg' } : null, el('td', { text: s }), ...[0, 1, 2].map(i => el('td', { text: k(v[i]) }))); t.append(tr); }
      const hist = el('table', { class: 'proc-table' }, el('caption', { text: 'Net cost of all services by year' }), el('tr', null, el('th', { text: 'Year' }), el('th', { text: 'Net cost' })));
      for (const fy of Object.keys(d.years).sort()) { const b = d.years[fy].authorities.find(x => x.ecode === code); const v = b && b.values['Total Service Expenditure']; hist.append(el('tr', null, el('td', { text: fy }), el('td', { text: k(v && v[2]) }))); }
      const note = a.notes === 'M' ? el('p', { class: 'small', text: 'This council did not send its return in time for publication, so no figures are available for this year.' }) : null;
      const close = el('button', { type: 'button', text: 'Close' }); close.onclick = () => { detail.hidden = true; };
      detail.replaceChildren(...[el('div', { class: 'table-wrap' }, t), note, el('div', { class: 'table-wrap' }, hist), close].filter(Boolean));
      detail.hidden = false; detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    function render() {
      const y = d.years[ySel.value], svc = sSel.value, f = q.value.trim().toLowerCase(), cls = cSel.value;
      const rows = y.authorities.filter(a => (!cls || a.cls === cls) && (!f || (a.name || '').toLowerCase().includes(f)));
      const val = a => (a.values[svc] || [])[2];
      rows.sort((a, b) => (val(b) ?? -Infinity) - (val(a) ?? -Infinity));
      const t = el('table', { class: 'proc-table' }, el('caption', { text: svc + ' · ' + ySel.value + ' · £, nominal · sorted by net cost' }),
        el('tr', null, ...['Council', 'Type', 'Spending', 'Income', 'Net cost'].map(h => el('th', { text: h }))));
      for (const a of rows.slice(0, limit)) {
        const v = a.values[svc] || [], b = el('button', { type: 'button', class: 'linklike', text: a.name }); b.onclick = () => showDetail(a.ecode);
        t.append(el('tr', null, el('td', null, b), el('td', { text: a.cls || '' }), ...[0, 1, 2].map(i => el('td', { text: k(v[i]) }))));
      }
      const missing = rows.filter(a => val(a) == null).length;
      out.replaceChildren(el('p', { class: 'small', role: 'status', text: rows.length + ' authorities' + (missing ? ' · ' + missing + ' without figures for this year (shown last, never as zero)' : '') }), el('div', { class: 'table-wrap' }, t));
      more.hidden = rows.length <= limit;
    }
    more.onclick = () => { limit += 40; render(); };
    ySel.onchange = () => { fillServices(); detail.hidden = true; render(); }; sSel.onchange = render; cSel.onchange = () => { limit = 40; render(); }; q.oninput = () => { limit = 40; render(); };
    const latest = d.years[years[0]];
    box.replaceChildren(
      el('p', { class: 'small', text: 'Source: ' }, el('a', { href: latest.page, target: '_blank', rel: 'noopener noreferrer', text: 'MHCLG ' + latest.dataset }), document.createTextNode(' · '), el('a', { href: latest.attachment, target: '_blank', rel: 'noopener noreferrer', text: 'Download the official table' })),
      el('div', { class: 'filters' }, el('div', null, el('label', { for: 'lae-year', text: 'Financial year' }), ySel), el('div', null, el('label', { for: 'lae-service', text: 'Service' }), sSel),
        el('div', null, el('label', { for: 'lae-class', text: 'Council type' }), cSel), el('div', null, el('label', { for: 'lae-query', text: 'Find a council' }), q)),
      detail, out, more,
      el('details', null, el('summary', { text: 'What these figures mean' }), ...d.caveats.map(c => el('p', { class: 'small', text: c }))));
    fillServices(); render();
    const fromHash = () => { const m = location.hash.match(/^#council-spending\/(E\d{4})$/); if (m) { ySel.value = years[0]; fillServices(); render(); showDetail(m[1]); } };
    window.addEventListener('hashchange', fromHash); fromHash();
  }).catch(() => { box.textContent = 'Council spending data is not available yet.'; });
})();

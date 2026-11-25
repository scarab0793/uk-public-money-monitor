// Council Tax in England by billing authority and band (MHCLG Council Tax levels, Table 9).
(function () {
  'use strict';
  const box = document.getElementById('council-tax-body'); if (!box) return;
  const el = (tag, props, ...kids) => { const e = document.createElement(tag); if (props) for (const [k, v] of Object.entries(props)) { if (v == null) continue; if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v); } for (const k of kids) if (k != null) e.append(k); return e; };
  const gbp = v => v == null ? 'Not available' : '£' + v.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const REGION = { NE: 'North East', NW: 'North West', YH: 'Yorkshire and the Humber', EM: 'East Midlands', WM: 'West Midlands', EE: 'East of England', E: 'East of England', L: 'London', SE: 'South East', SW: 'South West' };
  const median = a => { const s = a.filter(v => v != null).sort((x, y) => x - y); return s.length ? (s.length % 2 ? s[(s.length - 1) / 2] : (s[s.length / 2 - 1] + s[s.length / 2]) / 2) : null; };
  fetch('./data/local-government/council-tax-england.json', { cache: 'no-store' }).then(r => { if (!r.ok) throw 0; return r.json(); }).then(d => {
    const rows = d.area_bills.rows, bands = d.area_bills.columns.filter(c => /^Band [A-H]$/.test(c.trim()));
    const med = median(rows.map(r => r['Band D']));
    const q = el('input', { id: 'ct-query', placeholder: 'Type a council, e.g. Leeds, Camden, Cornwall', autocomplete: 'off' });
    const sort = el('select', { id: 'ct-sort' }, el('option', { value: 'name', text: 'Name' }), el('option', { value: 'high', text: 'Highest Band D bill' }), el('option', { value: 'low', text: 'Lowest Band D bill' }));
    const out = el('div', { class: 'table-wrap' }), status = el('p', { class: 'small' });
    function render() {
      const term = q.value.trim().toLowerCase();
      let list = rows.filter(r => !term || [r.Authority, r.Area, REGION[r.Region]].some(x => String(x || '').toLowerCase().includes(term)));
      if (sort.value === 'high') list.sort((a, b) => (b['Band D'] || 0) - (a['Band D'] || 0));
      else if (sort.value === 'low') list.sort((a, b) => (a['Band D'] || 0) - (b['Band D'] || 0));
      else list.sort((a, b) => a.Authority.localeCompare(b.Authority));
      status.textContent = list.length + ' of ' + rows.length + ' billing authorities · middle (median) Band D bill across these councils ' + gbp(med) + ' — not the official England average, which is weighted by dwellings' + (list.length > 60 ? ' · showing 60' : '');
      const t = el('table', { class: 'proc-table' });
      const h = el('tr', null, el('th', { text: 'Council' }), ...bands.map(b => el('th', { text: b.trim() })));
      t.append(el('thead', null, h));
      const body = el('tbody');
      for (const r of list.slice(0, 60)) body.append(el('tr', null, el('td', { text: r.Authority + ' (' + (REGION[r.Region] || r.Region || '') + ')' }), ...bands.map(b => el('td', { text: gbp(r[b]) }))));
      t.append(body); out.replaceChildren(t);
    }
    q.oninput = render; sort.onchange = render;
    const src = el('p', { class: 'small', text: 'Source: ' }, el('a', { href: d.page, target: '_blank', rel: 'noopener noreferrer', text: d.dataset }), document.createTextNode(' (' + d.publisher + ') · '), el('a', { href: d.attachment, target: '_blank', rel: 'noopener noreferrer', text: 'Download the official tables' }));
    box.replaceChildren(src, el('div', { class: 'filters' }, el('div', null, el('label', { for: 'ct-query', text: 'Find your council' }), q), el('div', null, el('label', { for: 'ct-sort', text: 'Sort by' }), sort)), status, out,
      el('details', null, el('summary', { text: 'What these figures mean' }), ...d.caveats.map(c => el('p', { class: 'small', text: c }))));
    render();
  }).catch(() => { box.textContent = 'Council Tax data is not available yet.'; });
})();

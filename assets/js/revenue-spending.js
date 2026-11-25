// HMRC cash receipts by tax and HM Treasury expenditure on services by function.
// Data: data/hmrc/receipts.json and data/treasury/pss-expenditure-on-services.json (scripts/import_official_tables.py).
(function () {
  'use strict';
  const el = (tag, props, ...kids) => {
    const e = document.createElement(tag);
    if (props) for (const [k, v] of Object.entries(props)) { if (v == null) continue; if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v); }
    for (const k of kids) if (k != null) e.append(k);
    return e;
  };
  const ext = (href, text) => el('a', { href, target: '_blank', rel: 'noopener noreferrer', text });
  const bn = (m) => (m < 0 ? '−' : '') + '£' + (Math.abs(m) / 1000).toLocaleString('en-GB', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'bn';
  const mn = (m) => (m < 0 ? '−' : '') + '£' + Math.abs(Math.round(m)).toLocaleString('en-GB') + 'm';
  const fmtM = (m) => m == null ? 'Not available' : (Math.abs(m) >= 1000 ? bn(m) : mn(m));
  const pct = (a, b) => (a == null || b == null || b === 0) ? '' : ((a - b) / Math.abs(b) * 100).toFixed(1).replace(/^(?!-)/, '+') + '%';
  const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

  function bars(points, fmt, label) {
    // points: [[label, value|null]], drawn as an accessible SVG bar chart
    const vals = points.map(p => p[1]).filter(v => v != null);
    if (!vals.length) return el('p', { class: 'small', text: 'No published values.' });
    const w = 720, h = 200, pad = 28, max = Math.max(0, ...vals), min = Math.min(0, ...vals), span = (max - min) || 1;
    const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', `0 0 ${w} ${h + 30}`); svg.setAttribute('width', '100%'); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', label);
    const bw = (w - pad) / points.length, zero = pad / 2 + (max / span) * h;
    const top = document.createElementNS(ns, 'text'); top.setAttribute('x', 0); top.setAttribute('y', 12); top.setAttribute('fill', '#b9c7d9'); top.setAttribute('font-size', '12'); top.textContent = 'max ' + fmt(max); svg.append(top);
    points.forEach(([lab, v], i) => {
      const x = pad + i * bw;
      if (v != null) {
        const r = document.createElementNS(ns, 'rect'), y = v >= 0 ? zero - (v / span) * h : zero, hh = Math.abs(v / span) * h;
        r.setAttribute('x', x + 1); r.setAttribute('y', y); r.setAttribute('width', Math.max(1, bw - 2)); r.setAttribute('height', Math.max(0.5, hh));
        r.setAttribute('fill', v >= 0 ? '#7ac5ff' : '#f2a65a');
        const t = document.createElementNS(ns, 'title'); t.textContent = lab + ': ' + fmt(v); r.append(t); svg.append(r);
      }
      if (i % Math.ceil(points.length / 8) === 0) {
        const t = document.createElementNS(ns, 'text'); t.setAttribute('x', x); t.setAttribute('y', h + 24); t.setAttribute('fill', '#b9c7d9'); t.setAttribute('font-size', '12'); t.textContent = lab; svg.append(t);
      }
    });
    return svg;
  }

  // ---------------- HMRC receipts ----------------
  async function receipts() {
    const box = document.getElementById('receipts-body'); if (!box) return;
    let d;
    try { const r = await fetch('./data/hmrc/receipts.json', { cache: 'no-store' }); if (!r.ok) throw 0; d = await r.json(); } catch (e) { box.textContent = 'HMRC receipts data is not available yet.'; return; }
    const years = [...new Set(d.taxes.flatMap(t => t.annual.map(a => a[0])))].sort().reverse();
    const total = d.taxes.find(t => /^total hmrc receipts/i.test(t.name));
    const [ly, lm] = d.latest_month.split('-').map(Number);
    const fyStart = lm >= 4 ? ly : ly - 1, ytdKey = 'ytd';
    const fyLabel = fyStart + '-' + String(fyStart + 1).slice(2);
    const sel = el('select', { id: 'receipts-year' }, el('option', { value: ytdKey, text: fyLabel + ' so far (April to ' + MONTHS[lm - 1] + ' ' + ly + ')' }), ...years.map(y => el('option', { value: y, text: y })));
    const q = el('input', { id: 'receipts-filter', placeholder: 'Filter taxes, e.g. duty, VAT, levy', autocomplete: 'off' });
    const table = el('div', { class: 'table-wrap' }), chartBox = el('div');
    function ytd(t, startYear) {
      // April of startYear up to the latest month's position in the year
      const n = (lm - 4 + 12) % 12 + 1, months = [];
      for (let i = 0; i < n; i++) { const y = startYear + (3 + i >= 12 ? 1 : 0), m = (3 + i) % 12 + 1; months.push(y + '-' + String(m).padStart(2, '0')); }
      const map = new Map(t.monthly); const vals = months.map(m => map.get(m));
      return vals.some(v => v != null) ? vals.reduce((a, v) => a + (v || 0), 0) : null;
    }
    function value(t, key) { return key === ytdKey ? ytd(t, fyStart) : (t.annual.find(a => a[0] === key) || [])[1] ?? null; }
    function prevKey(key) { if (key === ytdKey) return 'ytd-prev'; const i = years.indexOf(key); return years[i + 1]; }
    function prevValue(t, key) { return key === ytdKey ? ytd(t, fyStart - 1) : value(t, prevKey(key)); }
    function showChart(t) {
      chartBox.replaceChildren(el('h3', { text: t.name + ' · cash receipts by financial year' }), bars(t.annual.map(a => [a[0].slice(2), a[1]]), fmtM, t.name + ' annual receipts'),
        el('h3', { text: t.name + ' · last 36 months' }), bars(t.monthly.slice(-36).map(a => [a[0].slice(2), a[1]]), fmtM, t.name + ' monthly receipts'));
    }
    function render() {
      const key = sel.value, term = q.value.trim().toLowerCase();
      const t = el('table', { class: 'proc-table' });
      t.append(el('caption', { class: 'small', text: (key === ytdKey ? 'Financial year to date compared with the same months a year earlier. ' : 'Full financial year compared with the previous year. ') + 'Indented lines are already included in the line above. Select a tax to see its history.' }));
      t.append(el('thead', null, el('tr', null, el('th', { text: 'Tax or duty' }), el('th', { text: 'Cash receipts' }), el('th', { text: 'Change' }), el('th', { text: 'Share of HMRC total' }))));
      const body = el('tbody'), tot = total ? value(total, key) : null;
      for (const tax of d.taxes) {
        if (term && !tax.name.toLowerCase().includes(term)) continue;
        const v = value(tax, key);
        if (v == null && !term) continue;
        const sub = /included within|^paye nic|^sa nic/i.test(tax.name);
        const name = el('button', { type: 'button', class: 'linklike', text: (sub ? '↳ ' : '') + tax.name.replace(/\s*\(included within [^)]+\)/i, '') });
        name.onclick = () => showChart(tax);
        const tr = el('tr', tax.aggregate ? { class: 'agg' } : null, el('td', null, name), el('td', { text: fmtM(v) }), el('td', { text: pct(v, prevValue(tax, key)) }), el('td', { text: (!tax.aggregate && tot && v != null) ? (v / tot * 100).toFixed(1) + '%' : '' }));
        body.append(tr);
      }
      t.append(body); table.replaceChildren(t);
    }
    sel.onchange = render; q.oninput = render;
    box.replaceChildren(
      el('p', { class: 'small', text: 'Source: ' }, ext(d.page, d.dataset), document.createTextNode(' · release ' + new Date(d.release_updated_at).toLocaleDateString('en-GB') + ' · latest month ' + MONTHS[lm - 1] + ' ' + ly + ' · ' + d.unit.replace('GBP', '£') + ', ' + d.accounting_basis + ', ' + d.price_basis + ' · '), ext(d.attachment, 'Download the official table')),
      el('div', { class: 'filters' }, el('div', null, el('label', { for: 'receipts-year', text: 'Period' }), sel), el('div', null, el('label', { for: 'receipts-filter', text: 'Filter' }), q)),
      table, chartBox,
      el('details', null, el('summary', { text: 'What these figures mean' }), ...d.caveats.map(c => el('p', { class: 'small', text: c })),
        el('p', { class: 'small', text: 'Taxes not listed here are not published as separate lines in this HMRC table (for example newly introduced duties until HMRC adds them, and devolved or local taxes such as Council Tax and Business Rates).' })));
    render();
    if (total) showChart(total);
  }

  // ---------------- Treasury TES ----------------
  async function tes() {
    const box = document.getElementById('tes-body'); if (!box) return;
    let d;
    try { const r = await fetch('./data/treasury/pss-expenditure-on-services.json', { cache: 'no-store' }); if (!r.ok) throw 0; d = await r.json(); } catch (e) { box.textContent = 'Treasury spending data is not available yet.'; return; }
    const tables = d.tables, basisSel = el('select', { id: 'tes-basis' });
    for (const [k, label] of [['Table_9', 'Cash (nominal) £ billion'], ['Table_9a', 'Real terms £ billion (latest year prices)'], ['Table_9b', 'Per cent of GDP']]) if (tables[k]) basisSel.append(el('option', { value: k, text: label }));
    const years = tables.Table_9.rows[0].values.map(v => v[0]).reverse();
    const yearSel = el('select', { id: 'tes-year' }, ...years.map(y => el('option', { value: y, text: y })));
    const out = el('div'), chart = el('div');
    const fmt = (v, k) => v == null ? 'Not available' : k === 'Table_9b' ? v.toFixed(1) + '% of GDP' : (v < 0 ? '−' : '') + '£' + Math.abs(v).toLocaleString('en-GB', { minimumFractionDigits: 1, maximumFractionDigits: 1 }) + 'bn';
    function render() {
      const k = basisSel.value, y = yearSel.value, t = tables[k];
      const get = r => (r.values.find(v => v[0] === y) || []);
      const kind = get(t.rows[0])[1];
      const funcs = t.rows.filter(r => r.level === 'function'), totalRow = t.rows.find(r => /expenditure on services/i.test(r.label));
      const max = Math.max(...funcs.map(r => get(r)[2] || 0));
      const list = el('div');
      list.append(el('p', { class: 'small', text: t.title + ' · ' + y + ' is ' + (kind || 'unlabelled') + (kind === 'plans' ? ' (budgeted, not yet spent)' : '') }));
      for (const r of funcs.slice().sort((a, b) => (get(b)[2] || 0) - (get(a)[2] || 0))) {
        const v = get(r)[2];
        const row = el('div', { class: 'barrow' }, el('span', { class: 'barlabel', text: r.name || r.label }), el('span', { class: 'bar', style: 'width:' + (v ? Math.max(1, v / max * 100) : 0) + '%' }), el('span', { class: 'barval', text: fmt(v, k) }));
        list.append(row);
        const idx = t.rows.indexOf(r), comps = [];
        for (let i = idx + 1; i < t.rows.length && t.rows[i].level === 'component'; i++) comps.push(t.rows[i]);
        if (comps.length) list.append(el('details', { class: 'small' }, el('summary', { text: 'of which' }), ...comps.map(c => el('p', { text: (c.name || c.label) + ': ' + fmt(get(c)[2], k) }))));
        row.onclick = () => chart.replaceChildren(el('h3', { text: (r.name || r.label) + ' over time' }), bars(r.values.map(v => [v[0].slice(2), v[2]]), x => fmt(x, k), r.label));
        row.style.cursor = 'pointer';
      }
      for (const r of t.rows.filter(r => r.level !== 'function' && r.level !== 'component')) list.append(el('p', null, el('strong', { text: (r.name || r.label) + ': ' }), document.createTextNode(fmt(get(r)[2], k))));
      out.replaceChildren(list);
      if (!chart.childNodes.length && totalRow) chart.replaceChildren(el('h3', { text: 'Total expenditure on services over time' }), bars(totalRow.values.map(v => [v[0].slice(2), v[2]]), x => fmt(x, k), 'Total'));
    }
    basisSel.onchange = () => { chart.replaceChildren(); render(); }; yearSel.onchange = render;
    box.replaceChildren(
      el('p', { class: 'small', text: 'Source: ' }, ext(d.page, 'HM Treasury ' + d.dataset), document.createTextNode(' · release ' + new Date(d.release_updated_at).toLocaleDateString('en-GB') + ' · '), ext(d.attachment, 'Download the official tables')),
      el('div', { class: 'filters' }, el('div', null, el('label', { for: 'tes-basis', text: 'Measure' }), basisSel), el('div', null, el('label', { for: 'tes-year', text: 'Financial year' }), yearSel)),
      out, chart,
      el('details', null, el('summary', { text: 'What these figures mean' }), ...d.caveats.map(c => el('p', { class: 'small', text: c }))));
    render();
  }
  // ---------------- Country and Regional Analysis ----------------
  async function regions() {
    const box = document.getElementById('cra-body'); if (!box) return;
    let d;
    try { const r = await fetch('./data/treasury/country-regional-analysis.json', { cache: 'no-store' }); if (!r.ok) throw 0; d = await r.json(); } catch (e) { box.textContent = 'Regional spending data is not available yet.'; return; }
    const T = d.tables, measures = [['A.1b', 'Per person, cash'], ['A.2b', 'Per person, real terms'], ['A.1a', 'Total, cash'], ['A.2a', 'Total, real terms']].filter(m => T[m[0]]);
    const mSel = el('select', { id: 'cra-measure' }, ...measures.map(([k, l]) => el('option', { value: k, text: l })));
    const years = T['A.1b'].rows[0].blocks[0].map(v => v[0]).reverse();
    const ySel = el('select', { id: 'cra-year' }, ...years.map(y => el('option', { value: y, text: y })));
    const out = el('div');
    function render() {
      const t = T[mSel.value], y = ySel.value, perHead = /per head/i.test(t.units[0] || '') || /b$/.test(mSel.value);
      const val = r => (r.blocks[0].find(v => v[0] === y) || [])[2];
      const idx = r => r.blocks[1] ? (r.blocks[1].find(v => v[0] === y) || [])[2] : null;
      const fmt = v => v == null ? 'Not available' : perHead ? '£' + Math.round(v).toLocaleString('en-GB') + ' per person' : '£' + (v / 1000).toLocaleString('en-GB', { maximumFractionDigits: 1 }) + 'bn';
      const uk = t.rows.find(r => /^uk identifiable/i.test(r.area));
      const groups = [['Countries of the UK', t.rows.filter(r => r.level === 'nation')], ['English regions', t.rows.filter(r => r.level === 'english_region')]];
      out.replaceChildren(el('p', { class: 'small', text: t.title.replace(/\s+/g, ' ') + (uk ? ' · UK identifiable: ' + fmt(val(uk)) : '') }));
      for (const [title, rows] of groups) {
        const max = Math.max(...rows.map(r => val(r) || 0));
        out.append(el('h3', { text: title }));
        for (const r of rows.slice().sort((a, b) => (val(b) || 0) - (val(a) || 0))) {
          const i = idx(r);
          out.append(el('div', { class: 'barrow' }, el('span', { class: 'barlabel', text: r.area.replace(/^Total /, '') }), el('span', { class: 'bar', style: 'width:' + Math.max(1, (val(r) || 0) / max * 100) + '%' }),
            el('span', { class: 'barval', text: fmt(val(r)) + (i != null && perHead ? ' · index ' + Math.round(i) : '') })));
        }
      }
    }
    mSel.onchange = render; ySel.onchange = render;
    box.replaceChildren(
      el('p', { class: 'small', text: 'Source: ' }, ext(d.page, 'HM Treasury ' + d.dataset), document.createTextNode(' · release ' + new Date(d.release_updated_at).toLocaleDateString('en-GB') + ' · '), ext(d.attachment, 'Download the official tables')),
      el('div', { class: 'filters' }, el('div', null, el('label', { for: 'cra-measure', text: 'Measure' }), mSel), el('div', null, el('label', { for: 'cra-year', text: 'Financial year' }), ySel)),
      out, el('details', null, el('summary', { text: 'What these figures mean' }), ...d.caveats.map(c => el('p', { class: 'small', text: c })), el('p', { class: 'small', text: 'Index: UK identifiable spending per person = 100.' })));
    render();
  }
  receipts(); tes(); regions();
})();

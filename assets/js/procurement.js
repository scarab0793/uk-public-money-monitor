// Public procurement module: notices, suppliers and buyers from Contracts Finder and Find a Tender.
// Data is built by scripts/build_procurement.py into data/procurement/.
(function () {
  'use strict';
  const ROOT = './data/procurement/';
  const SRC = { cf: 'Contracts Finder', fts: 'Find a Tender' };
  const STAGE = { planning: 'Planned procurement', tender: 'Open or closed tender', award: 'Awarded', contract: 'Contract signed', cancelled: 'Cancelled', terminated: 'Terminated', other: 'Other notice' };
  const PAGE = 40;
  const root = document.getElementById('procurement');
  if (!root) return;
  const $ = id => document.getElementById(id);
  const cache = new Map();
  const gbp = new Intl.NumberFormat('en-GB', { style: 'currency', currency: 'GBP', maximumFractionDigits: 0 });
  const compact = new Intl.NumberFormat('en-GB', { notation: 'compact', maximumFractionDigits: 1 });
  function fmtValue(v) {
    if (!v) return 'Not published';
    const [amt, cur] = v;
    if (cur === 'GBP') return gbp.format(amt);
    return (cur || '?') + ' ' + amt.toLocaleString('en-GB');
  }
  function fmtBig(n) { return '£' + compact.format(n); }
  function el(tag, props, ...kids) {
    const e = document.createElement(tag);
    if (props) for (const [k, v] of Object.entries(props)) { if (v == null) continue; if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v); }
    for (const k of kids) if (k != null) e.append(k);
    return e;
  }
  function ext(href, text) { return el('a', { href, target: '_blank', rel: 'noopener noreferrer', text }); }
  async function get(path) {
    if (!cache.has(path)) cache.set(path, fetch(ROOT + path).then(r => { if (!r.ok) throw Error(path + ' ' + r.status); return r.json(); }).catch(e => { cache.delete(path); throw e; }));
    return cache.get(path);
  }
  async function bucketOf(key) {
    const buf = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(key));
    return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('').slice(0, 2);
  }
  const norm = s => String(s || '').toLowerCase();

  let summary = null;
  const state = { mode: 'notices', months: 3, limit: PAGE };

  function renderSummary() {
    const s = summary, box = $('proc-summary');
    box.replaceChildren();
    const grid = el('div', { class: 'grid' });
    for (const [key, src] of Object.entries(s.sources)) {
      const cov = (s.coverage || {})[key] || {};
      const card = el('div', { class: 'card' },
        el('h3', { text: src.label }),
        el('p', { class: 'result', text: (src.processes || 0).toLocaleString('en-GB') + ' procurements' }),
        el('p', { class: 'small', text: (src.releases || 0).toLocaleString('en-GB') + ' published notice versions · coverage ' + (cov.earliest_complete || '—') + ' to ' + (cov.latest_complete || '—') + ' (' + (cov.window_basis || '') + ')' }),
        ext(src.endpoint.replace(/\/(Published|api).*/, '/'), 'Original source'));
      if (cov.failed_days && cov.failed_days.length) card.append(el('p', { class: 'small', text: '⚠ ' + cov.failed_days.length + ' day(s) failed to import and will be retried' }));
      grid.append(card);
    }
    box.append(grid);
    // per-year table
    const years = [...new Set(Object.values(s.sources).flatMap(x => Object.keys(x.by_year || {})))].filter(y => /^\d{4}$/.test(y)).sort().reverse();
    if (years.length) {
      const t = el('table', { class: 'proc-table' });
      t.append(el('caption', { class: 'small', text: 'Awards by award year and source. Values are published award values for non-framework awards in GBP — not payments. Sources overlap: do not add the two columns together.' }));
      const head = el('tr', null, el('th', { text: 'Year' }));
      for (const src of Object.values(s.sources)) head.append(el('th', { text: src.label + ' awards' }), el('th', { text: 'Award value' }), el('th', { text: 'Frameworks' }));
      t.append(el('thead', null, head));
      const body = el('tbody');
      for (const y of years) {
        const tr = el('tr', null, el('td', { text: y }));
        for (const src of Object.values(s.sources)) {
          const r = (src.by_year || {})[y] || {};
          tr.append(el('td', { text: (r.awards || 0).toLocaleString('en-GB') }), el('td', { text: r.award_value_gbp ? fmtBig(r.award_value_gbp) : '—' }), el('td', { text: (r.framework_awards || 0).toLocaleString('en-GB') }));
        }
        body.append(tr);
      }
      t.append(body);
      box.append(el('div', { class: 'table-wrap' }, t));
    }
    const q = s.quality || {};
    const qtext = Object.entries(s.sources).map(([k, src]) => { const x = q[k] || {}; return src.label + ': ' + (x.awards_without_value || 0) + ' awards without a published value, ' + (x.non_gbp_awards || 0) + ' non-GBP, ' + (x.implausible_award_values || 0) + ' flagged as implausible, ' + (x.quarantined_releases || 0) + ' malformed releases quarantined'; }).join(' · ');
    box.append(el('details', null, el('summary', { text: 'Data quality and method' }),
      el('p', { text: s.basis }),
      el('p', { class: 'small', text: qtext + ' · ' + (q.possible_cross_source_duplicates || 0) + ' Contracts Finder records look like duplicates of Find a Tender records (flagged, not removed) · ' + (q.identifier_conflicts || 0) + ' conflicting supplier identifiers were not merged.' }),
      el('p', { class: 'small', text: 'Suppliers are linked only through identifiers published in the notices (Companies House, Central Digital Platform PPON, Charity Commission and similar). Suppliers named without an identifier are shown on contracts but not merged by name. Raw notices are archived unaltered in the GitHub release "procurement-raw". ' + s.licence }),
      el('p', { class: 'small', text: 'Database built ' + new Date(s.generated_at).toLocaleString('en-GB') + '.' })));
  }

  // ---------- notices ----------
  async function loadMonths(n) {
    const months = summary.months.map(m => m.month).filter(m => /^\d{4}-\d{2}$/.test(m)).sort().reverse().slice(0, n);
    const data = await Promise.all(months.map(m => get('notices/' + m + '.json').then(d => d.rows.map(r => (r._m = m, r)))));
    return data.flat();
  }
  function maxAward(r) { return Math.max(0, ...(r.aw || []).map(a => (a[1] && a[1][1] === 'GBP' && r.fw !== 'framework') ? a[1][0] : 0)); }
  function noticeCard(r, open) {
    const a = el('article', { class: 'project' });
    a.append(el('h3', { text: r.t || '(untitled notice)' }));
    const meta = [STAGE[r.st] || r.st, SRC[r.src], r.b || 'Buyer not published', 'first published ' + (r.fp || '—')];
    if (r.lu && r.lu !== r.fp) meta.push('updated ' + r.lu);
    a.append(el('p', { class: 'muted', text: meta.join(' · ') }));
    const m = el('div', { class: 'metrics' });
    if (r.v) m.append(el('span', { text: 'Estimated value: ' + fmtValue(r.v) }));
    if (r.fw === 'framework') m.append(el('span', { class: 'badge', text: 'Framework agreement — maximum value, not spending' }));
    if (r.fw === 'call_off') m.append(el('span', { class: 'badge', text: 'Call-off from a framework' }));
    if (r.am) m.append(el('span', { text: r.am + ' amendment(s)' }));
    if (r.dup) m.append(el('span', { class: 'badge', text: 'Probably also published on Find a Tender' }));
    a.append(m);
    for (const aw of r.aw || []) {
      const [date, val, cval, sups, start, end] = aw;
      const p = el('p', null, el('strong', { text: 'Award' + (date ? ' ' + date : '') + ': ' }), document.createTextNode(fmtValue(val)));
      if (cval && (!val || cval[0] !== val[0])) p.append(document.createTextNode(' · contract value ' + fmtValue(cval)));
      if (start || end) p.append(document.createTextNode(' · term ' + (start || '?') + ' to ' + (end || '?')));
      if (sups && sups.length) {
        p.append(document.createTextNode(' · '));
        sups.forEach(([name, key], i) => {
          if (i) p.append(document.createTextNode(', '));
          if (key) { const l = el('a', { href: '#procurement/supplier/' + encodeURIComponent(key), text: name || key }); p.append(l); }
          else p.append(document.createTextNode((name || 'Unnamed supplier') + ' (no identifier published)'));
        });
      }
      a.append(p);
    }
    const d = el('details', open ? { open: '' } : null, el('summary', { text: 'Details and source' }));
    if (r.d) d.append(el('p', { text: r.d }));
    const facts = [['OCID', r.ocid], ['Notice status', r.s], ['Category', r.cat], ['CPV code', r.cpv], ['Delivery regions', (r.reg || []).join(', ')], ['Published notice versions', r.n]];
    const dl = el('p', { class: 'small' });
    for (const [k, v] of facts) if (v) dl.append(el('strong', { text: k + ': ' }), document.createTextNode(v + '  '));
    d.append(dl);
    const links = el('p');
    if (r.url) links.append(ext(r.url, 'Original notice on ' + SRC[r.src]), document.createTextNode('  '));
    if (r.bk) links.append(el('a', { href: '#procurement/buyer/' + encodeURIComponent(r.bk), text: 'All notices by this buyer' }), document.createTextNode('  '));
    links.append(el('a', { href: '#procurement/notice/' + (r._m || '') + '/' + encodeURIComponent(r.id), text: 'Link to this record' }));
    d.append(links);
    a.append(d);
    return a;
  }
  async function renderNotices() {
    const out = $('proc-results'), status = $('proc-status');
    status.textContent = 'Loading notices…';
    let rows;
    try { rows = await loadMonths(state.months); } catch (e) { status.textContent = 'Notices could not be loaded. Please retry.'; return; }
    const terms = norm($('proc-query').value).split(/\s+/).filter(Boolean);
    const src = $('proc-source').value, stage = $('proc-stage').value, sort = $('proc-sort').value;
    let found = rows.filter(r => (!src || r.src === src) && (!stage || r.st === stage));
    if (terms.length) found = found.filter(r => { const hay = norm([r.t, r.d, r.b, r.ocid, r.cpv, (r.reg || []).join(' '), (r.aw || []).flatMap(a => (a[3] || []).map(s => s[0])).join(' ')].join(' ')); return terms.every(t => hay.includes(t)); });
    if (sort === 'value') found.sort((a, b) => maxAward(b) - maxAward(a));
    else found.sort((a, b) => (b.fp || '').localeCompare(a.fp || ''));
    const span = summary.months.map(m => m.month).filter(m => /^\d{4}-\d{2}$/.test(m)).sort().reverse().slice(0, state.months);
    status.textContent = found.length.toLocaleString('en-GB') + ' matching procurements first published ' + (span.length ? span[span.length - 1] + ' to ' + span[0] : '') + (found.length > state.limit ? ' · showing ' + state.limit : '');
    out.replaceChildren(...found.slice(0, state.limit).map(r => noticeCard(r)));
    $('proc-more').hidden = found.length <= state.limit;
  }

  // ---------- suppliers & buyers ----------
  async function renderDirectory(kind) {
    const out = $('proc-results'), status = $('proc-status');
    status.textContent = 'Loading ' + kind + '…';
    let idx;
    try { idx = await get(kind + '/index.json'); } catch (e) { status.textContent = 'Directory could not be loaded. Please retry.'; return; }
    const terms = norm($('proc-query').value).split(/\s+/).filter(Boolean);
    let rows = idx.rows;
    if (terms.length) rows = rows.filter(r => { const hay = norm(r[0] + ' ' + r[1]); return terms.every(t => hay.includes(t)); });
    status.textContent = rows.length.toLocaleString('en-GB') + ' ' + (kind === 'suppliers' ? 'suppliers with a published registered identifier' : 'buyers') + (rows.length > state.limit ? ' · showing ' + state.limit : '');
    out.replaceChildren(...rows.slice(0, state.limit).map(r => {
      const a = el('article', { class: 'project' });
      a.append(el('h3', null, el('a', { href: '#procurement/' + (kind === 'suppliers' ? 'supplier' : 'buyer') + '/' + encodeURIComponent(r[0]), text: r[1] || r[0] })));
      a.append(el('p', { class: 'muted', text: kind === 'suppliers'
        ? r[0] + ' · ' + r[2] + ' award(s) · ' + (r[3] ? gbp.format(r[3]) + ' in published award values' : 'no summable award value') + (r[4] ? ' · ' + r[4] + ' framework place(s)' : '') + (r[5] ? ' · latest ' + r[5] : '')
        : r[2] + ' procurement(s) · ' + r[3] + ' award(s) · ' + (r[4] ? gbp.format(r[4]) + ' in published award values' : 'no summable award value') }));
      return a;
    }));
    $('proc-more').hidden = rows.length <= state.limit;
  }

  async function showEntity(kind, key) {
    const panel = $('proc-detail');
    panel.hidden = false;
    panel.replaceChildren(el('p', { text: 'Loading…' }));
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    try {
      const b = await bucketOf(key);
      const rec = (await get((kind === 'supplier' ? 'suppliers' : 'buyers') + '/detail/' + b + '.json'))[key];
      if (!rec) throw Error('not found');
      const close = el('button', { type: 'button', text: 'Close' });
      close.onclick = () => { panel.hidden = true; history.replaceState(null, '', '#procurement'); };
      const head = [el('h3', { text: rec.name }), close];
      if (kind === 'supplier') {
        const ids = el('p', { class: 'small' }, el('strong', { text: 'Published identifiers: ' }));
        rec.identifiers.forEach((id, i) => {
          if (i) ids.append(document.createTextNode(', '));
          const m = id.match(/^GB-COH-(\w{8})$/);
          ids.append(m ? ext('https://find-and-update.company-information.service.gov.uk/company/' + m[1], id + ' (Companies House)') : document.createTextNode(id));
        });
        if (rec.names.length > 1) head.push(el('p', { class: 'small', text: 'Names used in notices: ' + rec.names.join('; ') }));
        head.push(ids,
          el('p', { text: rec.awards_total + ' award(s) involving this supplier · ' + gbp.format(rec.award_value_gbp) + ' across ' + rec.awards_valued + ' award(s) with a published GBP value' + (rec.framework_awards ? ' · ' + rec.framework_awards + ' framework agreement place(s) excluded from the value' : '') }),
          el('p', { class: 'small', text: 'Award values are not payments. Joint awards are shown at their full value for each named supplier. Contracts awarded under a different identifier or with no identifier are not included.' }),
          el('p', { class: 'small', text: 'Main buyers: ' + rec.buyers.slice(0, 10).map(([n, c]) => n + ' (' + c + ')').join('; ') }));
        const list = el('div');
        for (const [id, month, title, buyer, date, val, fw] of rec.awards) {
          list.append(el('p', null, el('a', { href: '#procurement/notice/' + month + '/' + encodeURIComponent(id), text: title || id }),
            document.createTextNode(' · ' + (buyer || '') + ' · ' + (date || '') + ' · ' + fmtValue(val) + (fw === 'framework' ? ' (framework maximum)' : '') + ' · ' + SRC[id.split(':')[0]])));
        }
        if (rec.awards_total > rec.awards.length) list.append(el('p', { class: 'small', text: 'Showing the latest ' + rec.awards.length + ' of ' + rec.awards_total + ' awards.' }));
        panel.replaceChildren(...head, list);
      } else {
        head.push(el('p', { text: rec.notices_total + ' procurement(s) · ' + rec.awards + ' award(s) · ' + gbp.format(rec.award_value_gbp) + ' in published non-framework award values (not payments)' }));
        if (key.startsWith('name:')) head.push(el('p', { class: 'small', text: 'This buyer published no registered identifier; notices are grouped by its published name.' }));
        const list = el('div');
        for (const [id, month, title, stage, date, val] of rec.notices) {
          list.append(el('p', null, el('a', { href: '#procurement/notice/' + month + '/' + encodeURIComponent(id), text: title || id }),
            document.createTextNode(' · ' + (STAGE[stage] || stage) + ' · ' + (date || '') + (val ? ' · estimated ' + fmtValue(val) : '') + ' · ' + SRC[id.split(':')[0]])));
        }
        if (rec.notices_total > rec.notices.length) list.append(el('p', { class: 'small', text: 'Showing the latest ' + rec.notices.length + ' of ' + rec.notices_total + '.' }));
        panel.replaceChildren(...head, list);
      }
    } catch (e) { panel.replaceChildren(el('p', { text: 'Record not available.' })); }
  }
  async function showNotice(month, id) {
    const panel = $('proc-detail');
    panel.hidden = false;
    panel.replaceChildren(el('p', { text: 'Loading…' }));
    panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
    try {
      const d = await get('notices/' + month + '.json');
      const r = d.rows.find(x => x.id === id);
      if (!r) throw Error('not found');
      r._m = month;
      const close = el('button', { type: 'button', text: 'Close' });
      close.onclick = () => { panel.hidden = true; history.replaceState(null, '', '#procurement'); };
      panel.replaceChildren(close, noticeCard(r, true));
    } catch (e) { panel.replaceChildren(el('p', { text: 'Record not available.' })); }
  }

  function render() { state.mode === 'notices' ? renderNotices() : renderDirectory(state.mode); }
  function route() {
    const h = decodeURIComponent(location.hash || '');
    let m;
    if ((m = h.match(/^#procurement\/(supplier|buyer)\/(.+)$/))) showEntity(m[1], m[2]);
    else if ((m = h.match(/^#procurement\/notice\/([\d-]+)\/(.+)$/))) showNotice(m[1], m[2]);
  }

  async function init() {
    try {
      summary = await get('summary.json');
    } catch (e) { $('proc-status').textContent = 'The procurement database has not been published yet.'; return; }
    renderSummary();
    const monthsSel = $('proc-months');
    const total = summary.months.filter(m => /^\d{4}-\d{2}$/.test(m.month)).length;
    for (const [n, label] of [[1, 'Latest month'], [3, 'Last 3 months'], [6, 'Last 6 months'], [12, 'Last 12 months'], [36, 'Last 3 years'], [9999, 'All imported months']]) {
      if (n > 1 && n / 2 >= total && n !== 9999) continue;
      monthsSel.append(el('option', { value: n, text: label }));
    }
    monthsSel.value = String(Math.min(3, total) === 1 ? 1 : 3);
    state.months = Number(monthsSel.value);
    let timer;
    $('proc-query').addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { state.limit = PAGE; render(); }, 200); });
    for (const id of ['proc-source', 'proc-stage', 'proc-sort']) $(id).addEventListener('change', () => { state.limit = PAGE; render(); });
    monthsSel.addEventListener('change', () => { state.months = Number(monthsSel.value); state.limit = PAGE; render(); });
    $('proc-mode').addEventListener('change', e => {
      state.mode = e.target.value; state.limit = PAGE;
      for (const id of ['proc-filters-notices']) $(id).hidden = state.mode !== 'notices';
      $('proc-query').placeholder = state.mode === 'notices' ? 'Title, buyer, supplier, OCID, CPV code or region' : state.mode === 'suppliers' ? 'Supplier name or identifier, e.g. GB-COH-…' : 'Buyer name';
      render();
    });
    $('proc-more').addEventListener('click', () => { state.limit += PAGE; render(); });
    window.addEventListener('hashchange', route);
    render();
    route();
  }
  init();
})();

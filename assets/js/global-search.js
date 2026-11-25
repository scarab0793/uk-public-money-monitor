// Site-wide search across published datasets (data/search/*), plus the '#go/<section>/<input>/<query>' deep-link handler.
(function () {
  'use strict';
  const input = document.getElementById('global-search'), list = document.getElementById('global-suggestions'), status = document.getElementById('global-status');
  const gbp = new Intl.NumberFormat('en-GB', { notation: 'compact', maximumFractionDigits: 1 });
  let data = null, loading = null, active = -1, shown = [];

  function load() {
    if (loading) return loading;
    status.textContent = 'Loading search index…';
    loading = fetch('./data/search/manifest.json', { cache: 'no-store' }).then(r => r.json()).then(m =>
      Promise.all(m.files.map(f => fetch('./data/search/' + f.file).then(r => r.json()).then(p =>
        p.rows.map(r => ({ name: r[0], low: String(r[0]).toLowerCase(), type: f.type, detail: p.details[r[1]], dlow: String(p.details[r[1]]).toLowerCase(), link: p.link_prefix + r[2], amount: r[3], period: r[4] }))
      ).catch(() => [])))).then(parts => { data = parts.flat(); status.textContent = data.length.toLocaleString('en-GB') + ' records searchable'; return data; })
      .catch(() => { status.textContent = 'Search index unavailable'; loading = null; });
    return loading;
  }
  function score(it, terms, q) {
    let s = 0;
    for (const re of terms) {
      const m = re.exec(it.low);
      if (m) s += m.index === 0 ? 6 : 4; else if (re.test(it.dlow)) s += 1; else return 0;
    }
    if (it.low === q) s += 20;
    return s;
  }
  function render() {
    const q = input.value.trim().toLowerCase();
    list.replaceChildren(); active = -1;
    if (q.length < 2 || !data) { list.classList.remove('open'); input.setAttribute('aria-expanded', 'false'); return; }
    // match at the start of a word only, so 'vat' does not match 'innovation'
    const terms = q.split(/\s+/).map(t => new RegExp('(^|[^a-z0-9])' + t.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
    const hits = [];
    for (const it of data) { const s = score(it, terms, q); if (s) hits.push([s, it]); }
    hits.sort((a, b) => b[0] - a[0] || (b[1].amount || 0) - (a[1].amount || 0));
    // keep a mix of types: at most 8 per type among the first 40
    const per = {}; shown = [];
    for (const [, it] of hits) { per[it.type] = (per[it.type] || 0) + 1; if (per[it.type] <= 8) shown.push(it); if (shown.length >= 40) break; }
    if (!shown.length) list.append(Object.assign(document.createElement('div'), { className: 'empty', textContent: 'No matches in the published datasets' }));
    shown.forEach((it, i) => {
      const b = document.createElement('a'); b.className = 'suggestion'; b.href = it.link; b.id = 'gs-' + i; b.setAttribute('role', 'option');
      const strong = document.createElement('strong'); strong.textContent = it.name;
      const small = document.createElement('small');
      small.textContent = it.type + ' · ' + it.detail + (it.amount ? ' · £' + gbp.format(it.amount) : '') + (it.period ? ' · ' + it.period : '');
      b.append(strong, small);
      b.addEventListener('click', () => { list.classList.remove('open'); });
      list.append(b);
    });
    status.textContent = hits.length.toLocaleString('en-GB') + ' matches' + (hits.length > shown.length ? ' · showing the best ' + shown.length : '');
    list.classList.add('open'); input.setAttribute('aria-expanded', 'true');
  }
  if (input) {
    let t;
    input.addEventListener('focus', load);
    input.addEventListener('input', () => { clearTimeout(t); t = setTimeout(() => load().then(render), 120); });
    input.addEventListener('keydown', e => {
      const items = list.querySelectorAll('.suggestion');
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault(); if (!items.length) return;
        active = (active + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length;
        items[active].focus(); input.setAttribute('aria-activedescendant', items[active].id);
      } else if (e.key === 'Enter' && items.length) { e.preventDefault(); items[Math.max(0, active)].click(); }
      else if (e.key === 'Escape') list.classList.remove('open');
    });
    list.addEventListener('keydown', e => { if (e.key === 'Escape') { list.classList.remove('open'); input.focus(); } });
    document.addEventListener('click', e => { if (!e.target.closest('#global-search-wrap')) list.classList.remove('open'); });
  }

  // '#go/<sectionId>/<inputId>/<query>': open a section and run its own search.
  function go() {
    const m = location.hash.match(/^#go\/([\w-]+)\/([\w-]+)\/(.*)$/);
    if (!m) return;
    const section = document.getElementById(m[1]), field = document.getElementById(m[2]), q = decodeURIComponent(m[3]);
    if (!section) return;
    section.scrollIntoView({ behavior: 'smooth', block: 'start' });
    let tries = 0;
    (function fill() {
      const f = field || document.getElementById(m[2]);
      if (f && !f.disabled) {
        f.value = q; f.dispatchEvent(new Event('input', { bubbles: true }));
        // a few sections reset their input once their data has loaded; re-apply if so
        setTimeout(() => { if (f.value !== q) { f.value = q; f.dispatchEvent(new Event('input', { bubbles: true })); } }, 1500);
      } else if (tries++ < 20) setTimeout(fill, 300);
    })();
  }
  window.addEventListener('hashchange', go);
  if (document.readyState === 'complete') go(); else window.addEventListener('load', go);
})();

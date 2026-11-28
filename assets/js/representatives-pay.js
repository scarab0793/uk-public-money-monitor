// MPs' pay and business costs (IPSA) and councillors' allowances (council statements), from data/representatives/.
(function () {
  'use strict';
  const box = document.getElementById('representatives-pay-body'); if (!box) return;
  const el = (tag, props, ...kids) => {
    const e = document.createElement(tag);
    if (props) for (const [k, v] of Object.entries(props)) { if (v == null) continue; if (k === 'class') e.className = v; else if (k === 'text') e.textContent = v; else e.setAttribute(k, v); }
    for (const k of kids) if (k != null) e.append(k);
    return e;
  };
  const pounds = v => v == null ? 'Not published' : (v < 0 ? '−£' : '£') + Math.abs(Math.round(v)).toLocaleString('en-GB');
  const pence = v => v == null ? 'Not published' : (v < 0 ? '−£' : '£') + Math.abs(v).toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const ext = (href, text) => el('a', { href, target: '_blank', rel: 'noopener noreferrer', text });
  const table = (caption, head, rows, cls) => {
    const t = el('table', { class: 'proc-table' + (cls ? ' ' + cls : '') }, caption ? el('caption', { text: caption }) : null, el('tr', null, ...head.map(h => el('th', { text: h }))));
    for (const r of rows) t.append(r instanceof Node ? r : el('tr', null, ...r.map(c => el('td', null, c instanceof Node ? c : document.createTextNode(c == null ? '' : String(c))))));
    return el('div', { class: 'table-wrap' }, t);
  };
  const BUDGETS = [['staffing', 'Staffing (paying the MP’s staff)'], ['office', 'Office costs (constituency office, rent, equipment)'], ['accommodation', 'Accommodation (London or constituency home)'], ['travel', 'Travel and subsistence'], ['winding_up', 'Winding-up (closing the office after leaving)'], ['other', 'Other costs (security, disability support, contingency)']];
  const spend = (m, k) => (m.budgets[k] || {}).spend || 0;
  const businessTotal = m => BUDGETS.reduce((s, [k]) => s + spend(m, k), 0);
  const personal = m => (m.pay.basic_salary || 0) + (m.pay.additional_salary || 0) + (m.pay.lalp || 0) + (m.pay.resettlement || 0);

  const tabs = el('div', { class: 'filters', role: 'tablist' });
  const panes = {};
  function addTab(id, label, render) {
    const b = el('button', { type: 'button', role: 'tab', 'aria-selected': 'false', text: label });
    const pane = el('div', { role: 'tabpanel', hidden: '' });
    let done = false;
    b.onclick = (ev) => {
      for (const [k, p] of Object.entries(panes)) { p.pane.hidden = k !== id; p.btn.setAttribute('aria-selected', String(k === id)); p.btn.style.opacity = k === id ? '1' : '.65'; }
      if (!done) { done = true; render(pane); }
      if (ev && ev.isTrusted) try { history.replaceState(null, '', '#representatives-pay/' + id); } catch (e) { /* ignore */ }
    };
    panes[id] = { btn: b, pane };
    tabs.append(b);
    return pane;
  }
  box.replaceChildren(tabs);

  const load = f => fetch('./data/representatives/' + f, { cache: 'no-store' }).then(r => { if (!r.ok) throw new Error(f); return r.json(); });

  // ---------------------------------------------------------------- MPs
  box.append(addTab('mps', 'MPs', pane => {
    pane.append(el('p', { text: 'Loading MPs’ pay…' }));
    load('mps-index.json').then(idx => {
      const rates = idx.rates || {}, mp = rates.mp_salary || [], ch = rates.committee_chair_salary || [];
      const yearSel = el('select', { id: 'rp-mp-year' }, ...idx.years.map(y => el('option', { value: y.file, text: y.year })));
      const q = el('input', { id: 'rp-mp-query', placeholder: 'MP or constituency', autocomplete: 'off' });
      const SORTS = { name: ['Name', null], personal: ['Highest personal pay', personal], business: ['Highest business costs', businessTotal], accommodation: ['Highest accommodation costs', m => spend(m, 'accommodation')], travel: ['Highest travel costs', m => spend(m, 'travel')] };
      const sortSel = el('select', { id: 'rp-mp-sort' }, ...Object.entries(SORTS).map(([v, [t]]) => el('option', { value: v, text: t })));
      const head = el('div'), out = el('div'), detail = el('div', { class: 'card', hidden: '' });
      const ratesBox = el('div', { class: 'grid' },
        el('div', null, el('h4', { text: 'MP salary, from ' + (mp[0] || [''])[0] }), el('p', { class: 'result', text: pounds((mp[0] || [])[1]) }),
          el('p', { class: 'small', text: 'Set by IPSA, the same for every MP. ' + (mp[1] ? 'From ' + mp[1][0] + ': ' + pounds(mp[1][1]) + '.' : '') })),
        el('div', null, el('h4', { text: 'Extra for select committee chairs' }), el('p', { class: 'result', text: pounds((ch[0] || [])[1]) }),
          el('p', { class: 'small', text: 'An additional salary on top of the MP salary, also set by IPSA (members of the Panel of Chairs get one too).' })));
      const ms = idx.ministerial_salaries;
      let ministers = null;
      if (ms) {
        const rows = [];
        for (const s of ms.sections) for (const r of s.rows) rows.push([r.posts.join('; '), s.title.replace(/^Ministers who are members of the /, ''), pounds(r.entitled), pounds(r.claimed)]);
        ministers = el('details', null, el('summary', { text: 'Ministers: salary paid on top of the MP salary (' + ms.title.replace(/^Salaries of members of His Majesty's Government:\s*/, '') + ')' }),
          el('p', { class: 'small', text: 'Ministers in the Commons get their MP salary plus a ministerial salary. “Claimed” is what ministers actually take; it is lower because ministers have not taken the increases since 2010. Ministers in the Lords receive only the ministerial salary.' }),
          table(null, ['Post', 'House', 'Entitled', 'Claimed'], rows), ext(ms.page, 'Cabinet Office: salaries of members of His Majesty’s Government'));
      }
      pane.replaceChildren(ratesBox, ministers || '', el('div', { class: 'filters' }, el('div', null, el('label', { for: 'rp-mp-year', text: 'Financial year' }), yearSel), el('div', null, el('label', { for: 'rp-mp-query', text: 'Search' }), q), el('div', null, el('label', { for: 'rp-mp-sort', text: 'Sort by' }), sortSel)), head, detail, out,
        el('p', { class: 'small' }, 'Source: ', ext(idx.page, 'IPSA annual publication of MPs’ budgets, costs and claims'), ' and ', ext(rates.page || idx.page, 'IPSA: MPs’ pay and pensions'), '. Business costs pay for running an MP’s office and staff; they are not income to the MP. Accommodation and travel are paid to let MPs work in two places.'));
      let data = null;
      function showDetail(m) {
        const b = BUDGETS.map(([k, label]) => { const x = m.budgets[k] || {}; return [label, x.budget == null ? (x.spend == null ? '—' : 'No cap') : pounds(x.budget), x.spend == null ? '—' : pounds(x.spend), x.reason || '']; });
        const parts = [
          table('Pay received by ' + m.name + ' · ' + data.year, ['Heading', 'Amount'], [
            ['MP salary (basic salary actually paid in the year)', pence(m.pay.basic_salary)],
            ['Additional salary' + (m.pay.additional_salary_reason ? ' (' + m.pay.additional_salary_reason + ')' : ''), pence(m.pay.additional_salary)],
            ['London Area Living Payment' + (m.pay.lalp_period ? ' (' + m.pay.lalp_period + ')' : ''), pence(m.pay.lalp)],
            ['Resettlement / loss-of-office payment', pence(m.pay.resettlement)]]),
          table('Business costs paid by IPSA, by budget', ['Budget', 'Budget available', 'Spent', 'Why this budget'], b)];
        const c = m.claims;
        if (c) {
          const rows = [];
          for (const [cat, types] of Object.entries(c.by_category).sort()) for (const [t, v] of Object.entries(types).sort((a, b) => b[1] - a[1])) rows.push([cat, t, pence(v)]);
          parts.push(el('details', null, el('summary', { text: 'All ' + c.claims.toLocaleString('en-GB') + ' claims, grouped by category and cost type' }),
            el('p', { class: 'small', text: 'Net of amounts repaid. Staffing payroll is the salaries of the MP’s staff. Claims are grouped as IPSA records them, which can differ slightly from the budget a cost was charged to.' + (c.not_paid ? ' Claims not paid: ' + pence(c.not_paid) + '.' : '') }),
            table(null, ['Category', 'Cost type', 'Paid'], rows)));
        }
        const o = m.other || {};
        const extra = [];
        if (o.connected_party && o.connected_party.length) extra.push(['Employs a connected party (relative or partner)', o.connected_party.join(' · ')]);
        if (o.contingency_granted) extra.push(['Contingency funding granted', pence(o.contingency_granted)]);
        if (o.staff_reward_payments) extra.push(['Reward and recognition payments to staff', pence(o.staff_reward_payments)]);
        if (o.debts_written_off) extra.push(['Debts written off by IPSA', pence(o.debts_written_off)]);
        if (extra.length) parts.push(table('Other published details', ['Item', 'Value'], extra));
        const close = el('button', { type: 'button', text: 'Close' }); close.onclick = () => { detail.hidden = true; };
        detail.replaceChildren(el('h3', { text: m.name + (m.constituency ? ' · ' + m.constituency : '') }), ...parts, close);
        detail.hidden = false; detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
      function render() {
        const f = q.value.trim().toLowerCase(), key = SORTS[sortSel.value][1];
        let rows = data.mps.filter(m => (personal(m) || businessTotal(m)) && (!f || (m.name + ' ' + (m.constituency || '')).toLowerCase().includes(f)));
        rows = key ? rows.sort((a, b) => key(b) - key(a)) : rows.sort((a, b) => a.name.localeCompare(b.name));
        const t = data.totals;
        head.replaceChildren(el('p', { class: 'small', role: 'status', text: data.mps.length + ' MPs in ' + data.year + ' (including those who left or arrived during the year). Salaries paid: ' + pounds(t.basic_salary) + '; additional salaries: ' + pounds(t.additional_salary) + '; business costs: ' + pounds(BUDGETS.reduce((s, [k]) => s + (t['spend_' + k] || 0), 0)) + ', of which staffing ' + pounds(t.spend_staffing) + '.' }));
        const trs = rows.slice(0, 700).map(m => {
          const b = el('button', { type: 'button', class: 'linklike', text: m.name }); b.onclick = () => showDetail(m);
          return el('tr', null, el('td', null, b), el('td', { text: m.constituency || '' }), el('td', { text: pounds(m.pay.basic_salary) }),
            el('td', { text: m.pay.additional_salary ? pounds(m.pay.additional_salary) + ' (' + (m.pay.additional_salary_reason || '') + ')' : '—' }),
            el('td', { text: m.pay.lalp ? pounds(m.pay.lalp) : '—' }), el('td', { text: pounds(spend(m, 'accommodation')) }), el('td', { text: pounds(spend(m, 'travel')) }),
            el('td', { text: pounds(spend(m, 'office')) }), el('td', { text: pounds(spend(m, 'staffing')) }));
        });
        out.replaceChildren(table('MPs · ' + data.year + ' · select a name for every heading and claim', ['MP', 'Constituency', 'Salary paid', 'Additional salary', 'London Area Living Payment', 'Accommodation', 'Travel', 'Office', 'Staffing'], trs));
      }
      function loadYear() {
        out.replaceChildren(el('p', { text: 'Loading…' })); detail.hidden = true;
        load(yearSel.value.replace(/^data\/representatives\//, '')).then(d => { data = d; render(); }).catch(() => out.replaceChildren(el('p', { text: 'MP data is not available right now.' })));
      }
      q.addEventListener('input', () => data && render()); sortSel.onchange = () => data && render(); yearSel.onchange = loadYear;
      loadYear();
    }).catch(() => pane.replaceChildren(el('p', { text: 'MP pay data is not available right now.' })));
  }));

  // ---------------------------------------------------------------- councillors
  box.append(addTab('councillors', 'County and city councillors', pane => {
    pane.append(el('p', { text: 'Loading councillors’ allowances…' }));
    load('councillors.json').then(d => {
      const CAT = { basic: 'Basic allowance', special_responsibility: 'Special responsibility allowances', civic: 'Chair / civic allowances', travel: 'Travel', subsistence: 'Subsistence', carers: 'Carers’ and dependants’ allowances', ict: 'Phone, broadband and IT', co_opted: 'Co-opted members', other: 'Other headings' };
      const typeSel = el('select', { id: 'rp-cl-type' }, el('option', { value: '', text: 'County and city councils' }), el('option', { value: 'county', text: 'County councils' }), el('option', { value: 'city', text: 'City councils' }));
      const out = el('div'), detail = el('div', { class: 'card', hidden: '' });
      function showCouncil(c) {
        const heads = c.headings.map(h => h.label);
        const rows = c.councillors.map(x => [x.name, ...heads.map(h => x.amounts[h] == null ? '' : pence(x.amounts[h]))]);
        const cats = Object.entries(c.totals_by_category).map(([k, v]) => [CAT[k] || k, pounds(v)]);
        const close = el('button', { type: 'button', text: 'Close' }); close.onclick = () => { detail.hidden = true; };
        detail.replaceChildren(el('h3', { text: c.name + ' · ' + (c.year || '') }),
          el('p', { class: 'small', text: c.councillors.length + ' councillors (including anyone who served part of the year). Total paid: ' + pounds(c.total) + (c.total_check && c.total_check.column ? '. Every row was checked against the council’s own total column.' : '.') }),
          table('Paid, by heading', ['Heading', 'Total'], cats),
          table('Each councillor, under the council’s own headings', ['Councillor', ...heads], rows),
          el('p', { class: 'small' }, 'Source: ', ext(c.source, c.name + ' statement of allowances paid ' + (c.year || '')), ' (', ext(c.landing, 'council page'), ')'), close);
        detail.hidden = false; detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }
      function render() {
        const list = d.councils.filter(c => !typeSel.value || c.type === typeSel.value);
        const trs = list.map(c => {
          const b = el('button', { type: 'button', class: 'linklike', text: c.name }); b.onclick = () => showCouncil(c);
          const basic = c.councillors.map(x => Object.entries(x.amounts).find(([h]) => (c.headings.find(y => y.label === h) || {}).category === 'basic')).filter(Boolean).map(([, v]) => v);
          const top = basic.length ? Math.max(...basic) : null;
          const sra = c.totals_by_category.special_responsibility || 0;
          return el('tr', null, el('td', null, b), el('td', { text: c.year || '', style: 'white-space:nowrap' }), el('td', { text: String(c.councillors.length) }), el('td', { text: top == null ? '—' : pounds(top) }),
            el('td', { text: pounds(sra) }), el('td', { text: pounds((c.totals_by_category.travel || 0) + (c.totals_by_category.subsistence || 0)) }), el('td', { text: pounds(c.total) }));
        });
        out.replaceChildren(table('Councils · select one to see every councillor', ['Council', 'Year', 'Councillors', 'Basic allowance for a full year', 'Special responsibility allowances', 'Travel and subsistence', 'Total paid'], trs));
      }
      typeSel.onchange = render;
      const fw = (d.frameworks || []).map(f => el('div', null, el('h4', { text: f.title }), el('p', { class: 'result', text: pounds(f.basic) }), el('p', { class: 'small', text: f.note + ' ' }, ext(f.source, f.publisher))));
      const gaps = (d.not_covered || []).length ? el('details', null, el('summary', { text: 'Councils not covered yet, and why' }), el('ul', null, ...d.not_covered.map(g => el('li', null, g.name + ': ' + g.reason + ' ', g.source ? ext(g.source, 'council page') : '')))) : '';
      pane.replaceChildren(
        el('p', { text: 'Councillors are not salaried employees. They receive allowances under their council’s members’ allowances scheme: a basic allowance paid to every councillor, special responsibility allowances for roles such as leader, cabinet member or committee chair, and travel, subsistence and carers’ expenses. In England each council sets its own amounts after advice from an independent remuneration panel, and must publish what each councillor was paid under each heading.' }),
        fw.length ? el('div', { class: 'grid' }, ...fw) : '',
        el('div', { class: 'filters' }, el('div', null, el('label', { for: 'rp-cl-type', text: 'Show' }), typeSel)), detail, out, gaps,
        el('p', { class: 'small', text: d.legal_basis || '' }));
      render();
    }).catch(() => pane.replaceChildren(el('p', { text: 'Councillor data is not available right now.' })));
  }));

  const start = location.hash.startsWith('#representatives-pay/') ? location.hash.split('/')[1] : 'mps';
  (panes[start] || panes.mps).btn.click();
})();

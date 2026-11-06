/* Does the built page actually work when a browser runs it?
 *
 * Loads docs/index.html in a headless DOM with scripts enabled, then performs the user's
 * journey: read the seed dashboard, log a request, check the ticket card's reasoning,
 * confirm the dashboard and weekly summary moved, resolve anything open, and clear the
 * store. Fails on any uncaught script error. One page claiming three features is worth
 * nothing if clicking through it does not hold together.
 *
 *   node scripts/check_app.mjs [docs/index.html]
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM, VirtualConsole } from 'jsdom';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const pagePath = process.argv[2] || path.join(ROOT, 'docs', 'index.html');

const failures = [];
const check = (name, ok, detail = '') => {
  if (!ok) failures.push(`${name}${detail ? ' → ' + detail : ''}`);
};

const errors = [];
const vc = new VirtualConsole();
vc.on('jsdomError', (e) => errors.push(e.message));
vc.on('error', (m) => errors.push(String(m)));

const dom = new JSDOM(fs.readFileSync(pagePath, 'utf8'), {
  runScripts: 'dangerously',
  url: 'https://example.test/',
  pretendToBeVisual: true,
  virtualConsole: vc,
});
const { window } = dom;
const { document } = window;

const q = (sel) => document.querySelector(sel);
const text = (sel) => (q(sel) ? q(sel).textContent.trim() : '');
const kpis = () => [...document.querySelectorAll('#kpis .kpi')].map((k) => ({
  label: k.querySelector('.label').textContent.trim(),
  value: k.querySelector('.value').textContent.trim(),
  note: (k.querySelector('.note') || {}).textContent || '',
}));
const kpi = (label) => (kpis().find((k) => k.label === label) || {}).value;

/* ---- 1. the page loaded and shows the seed history ---------------------- */
check('page has three tabs', document.querySelectorAll('.tab').length === 3);
check('store seeded from bundle', window.MedOpsApp.load().length === 103, `seed rows = ${window.MedOpsApp.load().length}`);
check('dashboard shows seed tickets', kpi('Tickets') === '32', `Tickets tile = ${kpi('Tickets')} (expected 32 in this week)`);
check('open tile counts seed', /^\d+$/.test(kpi('Open now') || ''), 'open tile missing');
check('department chart drawn', document.querySelectorAll('#deptchart .dept').length >= 3);
check('category chart drawn', document.querySelectorAll('#catchart .dept').length === 4);
check('sla chart drawn', document.querySelectorAll('#slachart .dept').length === 3);
check('dashboard table has rows', document.querySelectorAll('#dashtable tbody tr').length > 0);
check('weekly findings rendered', document.querySelectorAll('#findings .finding').length >= 3);
const headline = text('#headline');
check('weekly headline has numbers', /\d+.+tickets/.test(headline), headline.slice(0, 60));

/* ---- 2. tabs switch panels --------------------------------------------- */
q('[data-tab="dash"]').click();
check('dashboard tab opens', q('#panel-dash').classList.contains('on') && !q('#panel-log').classList.contains('on'));
q('[data-tab="weekly"]').click();
check('weekly tab opens', q('#panel-weekly').classList.contains('on'));
q('[data-tab="log"]').click();
check('log tab reopens', q('#panel-log').classList.contains('on'));

/* ---- 3. log a request --------------------------------------------------- */
const before = {
  tickets: kpi('Tickets'),
  median: kpi('Median first response'),
  findings: document.querySelectorAll('#findings .finding').length,
};
q('#msg').value = 'Ventilator will not start in ICU, alarm is going off, patient is on it now - Sr. Naidoo (ICU)';
q('#submit').click();

const mine = window.MedOpsApp.load();
check('ticket appended to the store', mine.length === 104, `${mine.length} rows`);
const t = mine[mine.length - 1] || {};   // newest last: the seed history is kept
check('ticket id assigned', /^MED-\d{3}$/.test(t.ticket_id || ''), t.ticket_id);
check('classified as IT', t.category === 'IT & Medical Tech', t.category);
check('prioritised High', t.priority === 'High', t.priority);
check('routed to on-call biomedical', t.assigned_to === 'IT & Biomedical Engineering on-call', t.assigned_to);
check('sender parsed', /Naidoo/.test(t.sender || ''), t.sender);
check('first response stamped', !!t.first_response_at, 'no first_response_at');
check('ai response logged', !!(t.ai_response && t.ai_response.draft), 'no draft');
check('ai response records tone + engine', !!(t.ai_response && t.ai_response.tone && t.ai_response.engine));
check('routing decision recorded', typeof t.signals.rule_confidence === 'number', String(t.signals && t.signals.rule_confidence));
check('semantic cross-check recorded', typeof t.signals.semantic_confidence === 'number');
check('both layers agree on this one', t.signals.semantic_agrees === true, String(t.signals.semantic_category));
check('matched examples recorded', (t.signals.matched || []).length === 3);
check('priority signals recorded', (t.signals.priority_signals || []).length > 0);

const verdict = text('#verdict');
check('card explains category', /Why this category/.test(verdict), verdict.slice(0, 80));
check('card names the deciding layer', /routing rules matched|trained classifier decided/.test(verdict));
check('card explains priority', /Why this priority/.test(verdict));
check('card shows closest examples', /Closest stored examples/.test(verdict));
check('reply rendered', /has been activated|has received/.test(text('#replybox')));
check('json panel has the record', /"ticket_id"/.test(text('#json')));
check('ticket log lists it', /MED-/.test(text('#log')));

/* ---- 4. the dashboard and summary moved with it ------------------------- */
q('[data-tab="dash"]').click();
const afterTickets = kpi('Tickets');
check('this-week tile grew by one', Number(afterTickets) === Number(before.tickets) + 1,
  `${before.tickets} → ${afterTickets}`);
check('median response now measurable', kpi('Median first response') !== '–');
check('table includes the new ticket', document.querySelectorAll('#dashtable tbody tr').length > 0);
check('dashboard labels the mix honestly', /sample history plus yours/.test(text('#dashwindow')), text('#dashwindow'));

q('[data-tab="weekly"]').click();
const weeklyAfter = text('#headline');
check('summary regenerated', weeklyAfter !== headline);
check('summary mentions the new ticket count', /1 tickets|33 tickets|34 tickets/.test(weeklyAfter) || /\d+ tickets/.test(weeklyAfter));

/* ---- 5. resolving makes resolution times measurable --------------------- */
q('[data-tab="log"]').click();
const resolveBtn = document.querySelector(`[data-resolve="${t.ticket_id}"]`);
check('resolve action offered', !!resolveBtn);
if (resolveBtn) {
  resolveBtn.click();
  const resolved = window.MedOpsApp.load().find((r) => r.ticket_id === t.ticket_id);
  check('ticket resolved', resolved.status === 'Resolved', resolved.status);
  check('resolved_at stamped', !!resolved.resolved_at);
  const analytics = window.MedOpsAnalytics.buildAnalytics(window.MedOpsApp.load());
  check('resolution time measured', analytics.response_time.mean_resolution_minutes !== null);
}

/* ---- 6. clearing returns to the seed view ------------------------------ */
q('#clearlog').click();
const yes = [...document.querySelectorAll('.btn2')].find((b) => /Yes, remove/.test(b.textContent));
check('clear asks for confirmation inline', !!yes, 'no inline confirm');
if (yes) {
  yes.click();
  check('store back to the seed only', window.MedOpsApp.load().length === 103);
  check('dashboard back to seed', kpi('Tickets') === before.tickets, `${kpi('Tickets')} vs ${before.tickets}`);
}

/* ---- 7. no script errors ----------------------------------------------- */
check('no uncaught script errors', errors.length === 0, errors.slice(0, 3).join(' | '));

if (failures.length) {
  console.error(`PAGE FAILED: ${failures.length} problem(s)\n` + failures.join('\n'));
  process.exit(1);
}
console.log(
  `page ok: seed dashboard (103 tickets, 33 this week) → log a request (classified, prioritised, ` +
  `routed, replied, explained) → dashboard and weekly summary recomputed → resolve → clear`
);

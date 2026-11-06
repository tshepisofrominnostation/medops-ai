/* Drive the built console page in a headless DOM and assert what it actually does.
 *
 * The published page is the product: a form, a store and a dashboard that must agree
 * with each other. Checking that by eye is how the row-insertion bug survived a manual
 * pass — the tiles moved, so the page looked correct while the table was untouched.
 *
 * Requires jsdom (dev only, not a runtime dependency):
 *     npm install jsdom
 *     node scripts/check_console.mjs docs/console/index.html
 *
 * Exits non-zero on the first failed expectation. tests/test_console_page.py wraps it.
 */
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
let JSDOM;
let VirtualConsole;
try {
  ({ JSDOM, VirtualConsole } = require('jsdom'));
} catch (error) {
  if (error && error.code === 'MODULE_NOT_FOUND') {
    console.error('jsdom is not installed: npm install');
    process.exit(2);
  }
  throw error;                     // a real failure must not masquerade as "not installed"
}

const pagePath = process.argv[2] || 'docs/console/index.html';
const html = fs.readFileSync(pagePath, 'utf8');
const STORE_KEY = 'medops.console.tickets.v1';

const failures = [];
function expect(label, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (!ok) failures.push(`${label}\n    expected: ${JSON.stringify(expected)}\n    actual:   ${JSON.stringify(actual)}`);
}

const scriptErrors = [];
const virtualConsole = new VirtualConsole();
virtualConsole.on('jsdomError', (e) => scriptErrors.push(e.message));
virtualConsole.on('error', (m) => scriptErrors.push(String(m)));

function open(store) {
  const dom = new JSDOM(html, {
    runScripts: 'dangerously',
    pretendToBeVisual: true,
    virtualConsole,
    url: 'http://localhost/console/',
    beforeParse(window) {
      // start from a known store instead of whatever a previous run left behind
      if (store !== undefined) window.localStorage.setItem(STORE_KEY, store);
      else window.localStorage.removeItem(STORE_KEY);
    }
  });
  return dom.window;
}

const kpi = (doc, id) => doc.querySelector(`#${id} .tvalue`).textContent.trim();
const ticketRows = (doc) =>
  [...doc.querySelectorAll('#rows tr')].filter((r) => r.children[0].textContent.trim().startsWith('MED-WEB'));
const countLine = (doc) => doc.querySelector('#count').textContent.trim();

/* ---------- first visit: generate two tickets ---------- */
let win = open();
let doc = win.document;

const baseRows = doc.querySelectorAll('#rows tr').length;
expect('a clean visit starts with no session tickets', ticketRows(doc).length, 0);
expect('still open before generating', kpi(doc, 'kpi-open'), '2');
expect('count line before generating', countLine(doc), `${baseRows} of ${baseRows} tickets shown`);

doc.getElementById('go').click();
expect('generated ticket is named', doc.querySelector('#out .mono').textContent.trim(), 'MED-WEB-01');
expect('generated ticket is classified', [...doc.querySelectorAll('#out .badges .chip')]
  .map((c) => c.textContent.trim()), ['IT & Medical Tech', 'High priority']);
expect('generated ticket is routed', doc.querySelector('#out .routed').textContent.trim(),
  'Routed to IT & Biomedical Engineering on-call');
expect('generated ticket reaches the table', ticketRows(doc).length, 1);
expect('generated ticket sits at the top of the table', doc.querySelector('#rows tr').children[0].textContent.trim(), 'MED-WEB-01');
expect('still open moved', kpi(doc, 'kpi-open'), '3');
expect('window count moved', kpi(doc, 'kpi-window'), '33');
expect('count line grew', countLine(doc), `${baseRows + 1} of ${baseRows + 1} tickets shown`);

doc.getElementById('msg').value = 'Please send my payslip for October, the overtime line looks wrong.';
doc.getElementById('sender').value = 'Mr Khumalo (Finance query)';
doc.getElementById('go').click();
expect('second ticket uses the next id', doc.querySelector('#out .mono').textContent.trim(), 'MED-WEB-02');
expect('administrative wording lands in HR', [...doc.querySelectorAll('#out .badges .chip')]
  .map((c) => c.textContent.trim()), ['HR', 'Low priority']);
expect('still open counts both', kpi(doc, 'kpi-open'), '4');
expect('both tickets reach the table', ticketRows(doc).length, 2);

const stored = win.localStorage.getItem(STORE_KEY);
expect('both tickets are stored', JSON.parse(stored).length, 2);

/* ---------- reload: the store survives, the dashboard is rebuilt from it ---------- */
win = open(stored);
doc = win.document;
expect('tickets survive a reload', ticketRows(doc).length, 2);
expect('still open after reload', kpi(doc, 'kpi-open'), '4');
expect('session strip names the browser store', doc.querySelector('#session-state').textContent.includes('stored in this browser'), true);

/* ---------- filters must reach the generated rows ---------- */
doc.getElementById('q').value = 'med-web';
doc.getElementById('q').dispatchEvent(new win.Event('input'));
expect('searching finds the generated rows', countLine(doc), `2 of ${baseRows + 2} tickets shown`);

doc.getElementById('q').value = '';
doc.getElementById('q').dispatchEvent(new win.Event('input'));
const statusFilter = doc.getElementById('fs');
statusFilter.value = 'Open';
statusFilter.dispatchEvent(new win.Event('input'));
const openVisible = [...doc.querySelectorAll('#rows tr')].filter((r) => r.style.display !== 'none');
expect('the Open filter keeps only open tickets', openVisible.every((r) => r.dataset.s === 'Open'), true);
expect('the Open filter includes the new tickets', openVisible.filter((r) => r.children[0].textContent.trim().startsWith('MED-WEB')).length, 2);
statusFilter.value = '';
statusFilter.dispatchEvent(new win.Event('input'));

/* ---------- clearing is a two-step, and puts the dashboard back ---------- */
const clearButton = [...doc.querySelectorAll('#session-state button')].find((b) => b.textContent.includes('Clear'));
expect('a clear control exists', Boolean(clearButton), true);
clearButton.click();
expect('clearing asks for confirmation inline', [...doc.querySelectorAll('#session-state button')]
  .map((b) => b.textContent.trim()).slice(0, 2), ['Yes, remove', 'Keep']);
[...doc.querySelectorAll('#session-state button')].find((b) => b.textContent.includes('Yes')).click();
expect('rows are gone', ticketRows(doc).length, 0);
expect('still open is back to baseline', kpi(doc, 'kpi-open'), '2');
expect('count line is back to baseline', countLine(doc), `${baseRows} of ${baseRows} tickets shown`);
expect('store is empty', JSON.parse(win.localStorage.getItem(STORE_KEY)).length, 0);

/* ---------- a page with broken storage must not break ---------- */
const blocked = new JSDOM(html, {
  runScripts: 'dangerously',
  pretendToBeVisual: true,
  virtualConsole,
  url: 'http://localhost/console/',
  beforeParse(window) {
    Object.defineProperty(window, 'localStorage', {
      get() { throw new Error('storage blocked'); }
    });
  }
});
blocked.window.document.getElementById('go').click();
expect('the console still classifies without storage',
  blocked.window.document.querySelector('#out .mono').textContent.trim(), 'MED-WEB-01');

expect('the page raised no script errors', scriptErrors, []);

if (failures.length) {
  console.error(`\n${failures.length} expectation(s) failed:\n- ${failures.join('\n- ')}`);
  process.exit(1);
}
console.log(`console page ok: ${baseRows} seeded + generated tickets, tiles, charts, table, filters, persistence and clear all agree`);

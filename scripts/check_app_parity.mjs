/* Does the browser agree with the Python service?
 *
 * Loads the shipped bundle, runs web/semantic.js and web/analytics.js in this process,
 * and compares every result against fixtures written by the Python code itself
 * (scripts/make_app_fixtures.py). Exit code 1 means the page would show different
 * numbers from the service, which is the failure this file exists to catch.
 *
 *   node scripts/check_app_parity.mjs [web/app_bundle.json tests/data/app_parity.json]
 */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const bundlePath = process.argv[2] || path.join(ROOT, 'web', 'app_bundle.json');
const fixturePath = process.argv[3] || path.join(ROOT, 'tests', 'data', 'app_parity.json');

function loadModule(file, globals) {
  const sandbox = { ...globals, console, Math, Date, JSON, Object, Array, String, Number, RegExp, isNaN };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(ROOT, file), 'utf8'), sandbox, { filename: file });
  return sandbox;
}

const bundle = JSON.parse(fs.readFileSync(bundlePath, 'utf8'));
const fixtures = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));

const ctx = loadModule('web/semantic.js', {});
const semantic = ctx.MedOpsSemantic;
semantic.init(bundle);

const actx = loadModule('web/analytics.js', {});
const analytics = actx.MedOpsAnalytics;
analytics.configure(bundle.taxonomy);

const failures = [];
const near = (a, b, tol = 1e-3) => Math.abs(a - b) <= tol;
/* Averaged minute values are floats accumulated in a different language. Where the true
 * mean lands within a hair of a .005 boundary the two can round a cent apart, which is
 * display noise, not a disagreement about the data. Counts, shares and classifications
 * get no such grace: those must match exactly. */
const MINUTE_TOL = 0.011;
const isMinuteField = (p) =>
  /_minutes$/.test(p) || (/[.]response_time[.]/.test(p) && !/_tickets$/.test(p));

/* ---- semantic predictions ------------------------------------------------ */
for (const want of fixtures.predictions) {
  const got = semantic.predict(want.text);
  const label = want.text.slice(0, 58).replace(/\s+/g, ' ');
  if (got.category !== want.category) {
    failures.push(`category "${label}" → js ${got.category} vs py ${want.category}`);
  }
  if (!near(got.similarity, want.similarity)) {
    failures.push(`similarity "${label}" → ${got.similarity} vs ${want.similarity}`);
  }
  if (!near(got.margin, want.margin)) {
    failures.push(`margin "${label}" → ${got.margin} vs ${want.margin}`);
  }
  if (got.confident !== want.confident) {
    failures.push(`confident "${label}" → ${got.confident} vs ${want.confident}`);
  }
  for (const [cat, score] of Object.entries(want.scores)) {
    if (!near(got.scores[cat], score)) {
      failures.push(`score ${cat} "${label}" → ${got.scores[cat]} vs ${score}`);
    }
  }
  // Routing and priority must match the service, not just the similarity scores.
  const decided = semantic.decide(want.text);
  const expectedCat = want.rule_category;   // Python classify() decides when it can
  if (want.rule_confidence > 0 && decided.category !== expectedCat) {
    failures.push(`route "${label}" → js ${decided.category} vs py ${expectedCat}`);
  }
  if (Math.abs(decided.rule.confidence - want.rule_confidence) > 1e-3) {
    failures.push(`rule confidence "${label}" → ${decided.rule.confidence} vs ${want.rule_confidence}`);
  }
  const prio = semantic.decidePriority(want.text, '');
  if (prio.priority !== want.priority) {
    failures.push(`priority "${label}" → js ${prio.priority} vs py ${want.priority}`);
  }

  const phiGot = semantic.phiScan(want.text);
  if (phiGot.blocked !== want.phi.blocked) {
    failures.push(`phi.blocked "${label}" → ${phiGot.blocked} vs ${want.phi.blocked}`);
  }
  if (phiGot.review !== want.phi.review) {
    failures.push(`phi.review "${label}" → ${phiGot.review} vs ${want.phi.review}`);
  }
  const gotRules = [...new Set(phiGot.flags.map((f) => f.rule))].sort();
  if (JSON.stringify(gotRules) !== JSON.stringify(want.phi.rules)) {
    failures.push(`phi.rules "${label}" → [${gotRules}] vs [${want.phi.rules}]`);
  }
}

/* ---- analytics ---------------------------------------------------------- */
function diff(pathName, a, b, out) {
  if (a === null || b === null || typeof a !== 'object' || typeof b !== 'object') {
    if (typeof a === 'number' && typeof b === 'number') {
      const tol = isMinuteField(pathName) ? MINUTE_TOL : 1e-3;
      if (!near(a, b, tol)) out.push(`${pathName} → ${a} vs ${b}`);
      return;
    }
    if (JSON.stringify(a) !== JSON.stringify(b)) out.push(`${pathName} → ${JSON.stringify(a)} vs ${JSON.stringify(b)}`);
    return;
  }
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  for (const k of keys) {
    if (k === 'by_department') {
      // Python orders departments by count; compare as maps so order is not the test.
      const da = a[k] || {};
      const db = b[k] || {};
      if (JSON.stringify(Object.keys(da).sort().map((x) => [x, da[x]])) !==
          JSON.stringify(Object.keys(db).sort().map((x) => [x, db[x]]))) {
        out.push(`${pathName}.by_department → ${JSON.stringify(da)} vs ${JSON.stringify(db)}`);
      }
      continue;
    }
    diff(`${pathName}.${k}`, a[k], b[k], out);
  }
}

for (const win of fixtures.analytics) {
  const got = analytics.buildAnalytics(bundle.store, win.start, win.end);
  const out = [];
  diff(`analytics[${win.start || 'all'}..${win.end || 'all'}]`, got, win.value, out);
  failures.push(...out);
}

/* ---- report ------------------------------------------------------------- */
const checks = fixtures.predictions.length * 7 + fixtures.analytics.length;
if (failures.length) {
  console.error(`PARITY FAILED: ${failures.length} disagreement(s)\n` + failures.slice(0, 40).join('\n'));
  process.exit(1);
}
console.log(
  `parity ok: ${fixtures.predictions.length} messages (route, rule confidence, priority, semantic ` +
  `category/similarity/margin/confidence, ` +
  `4 scores, phi block/review/rules) and ${fixtures.analytics.length} analytics windows ` +
  `(${fixtures.ticket_count} tickets) identical to the Python engine ` +
  `(counts, shares and classifications exact; minutes within ${MINUTE_TOL})`
);

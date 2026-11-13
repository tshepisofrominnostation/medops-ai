/* Does the browser's governance engine agree with the Python service?
 *
 * Loads web/governance.js in a vm (exactly as the page would), runs it against fixtures
 * written by the real Python functions (scripts/make_governance_fixtures.py), and
 * compares every value. Deterministic values must be IDENTICAL - not close: the numeric
 * helpers in governance.js implement Python's round-half-to-even on exact binaries, so a
 * difference of one cent is a real disagreement, not float noise. The bootstrap interval
 * is exact too, because app/forecast_compare.py and web/governance.js draw from the same
 * mulberry32. The only thing deliberately NOT compared is the message fingerprint, which
 * cannot match (FNV-1a in the browser, SHA-256 in the service) - see fingerprint().
 *
 *   node scripts/check_governance_parity.mjs [tests/data/governance_parity.json]
 */
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..');
const fixturePath = process.argv[2] ||
  path.join(ROOT, 'tests', 'data', 'governance_parity.json');

const fixtures = JSON.parse(fs.readFileSync(fixturePath, 'utf8'));

function loadModule(file) {
  const sandbox = { console, Math, Date, JSON, Object, Array, String, Number, Boolean,
                    RegExp, Error, isNaN, isFinite, BigInt, DataView, ArrayBuffer, Object };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync(path.join(ROOT, file), 'utf8'), sandbox, { filename: file });
  return sandbox;
}

const gov = loadModule('web/governance.js').MedOpsGovernance;
if (!gov) {
  console.error('PARITY FAILED: web/governance.js did not attach MedOpsGovernance');
  process.exit(1);
}

const failures = [];
const checks = { fields: 0 };

/* Strict comparison. Numbers are compared with === (which also catches 0 vs -0 being
 * different only when it matters - see numCmp) and reported with full precision. */
function cmp(label, got, want) {
  checks.fields += 1;
  if (typeof want === 'number' && typeof got === 'number') {
    if (got !== want && !(Number.isNaN(got) && Number.isNaN(want))) {
      failures.push(`${label} → js ${got} vs py ${want} (diff ${got - want})`);
    }
    return;
  }
  if (want === null || got === null || typeof want !== 'object' || typeof got !== 'object') {
    if (got !== want) failures.push(`${label} → js ${JSON.stringify(got)} vs py ${JSON.stringify(want)}`);
    return;
  }
  if (Array.isArray(want) !== Array.isArray(got)) {
    failures.push(`${label} → js ${JSON.stringify(got)} vs py ${JSON.stringify(want)}`);
    return;
  }
  if (Array.isArray(want)) {
    if (got.length !== want.length) {
      failures.push(`${label}.length → js ${got.length} vs py ${want.length}`);
      return;
    }
    for (let i = 0; i < want.length; i++) cmp(`${label}[${i}]`, got[i], want[i]);
    return;
  }
  // Object: same key SET (order is not a contract, except where it is checked below).
  const gk = Object.keys(got).sort();
  const wk = Object.keys(want).sort();
  if (JSON.stringify(gk) !== JSON.stringify(wk)) {
    failures.push(`${label} keys → js [${gk}] vs py [${wk}]`);
    return;
  }
  for (const k of wk) cmp(`${label}.${k}`, got[k], want[k]);
}

/* ---- forecast ------------------------------------------------------------ */
for (const c of fixtures.forecasts) {
  const got = gov.forecastVolume(c.by_day, c.horizon, c.history_days === null ? undefined : c.history_days);
  cmp(`forecast[${c.label}]`, got, c.value);
}

/* ---- method comparison --------------------------------------------------- */
for (const c of fixtures.comparisons) {
  const got = gov.compareMethods(c.by_day, c.seed);
  cmp(`compare[${c.label}]`, got, c.value);
}

/* ---- prioritizer --------------------------------------------------------- */
for (const p of fixtures.prioritizer) {
  cmp(`prioritize("${p.message}".slice(0,40), "${p.sender}")`,
      gov.prioritize(p.message, p.sender), p.priority);
}

/* ---- bias audit ---------------------------------------------------------- */
// The pair list itself must be the same six pairs, in the same order, word for word.
cmp('MATCHED_PAIRS', gov.MATCHED_PAIRS.map((p) => [p.need, p.a_label, p.a_text, p.b_label, p.b_text]),
    fixtures.bias_audit.pairs.map((p) => [p.need, p.a_label, p.a_text, p.b_label, p.b_text]));

// And the default (no pairs argument) must be the exported list, not a stale copy.
cmp('runBiasAudit(prioritize) default pairs',
    gov.runBiasAudit((t) => ({ priority: gov.prioritize(t, '') })),
    gov.runBiasAudit((t) => ({ priority: gov.prioritize(t, '') }), gov.MATCHED_PAIRS));

const classifiers = {
  'real prioritizer': (t) => ({ priority: gov.prioritize(t, '') }),
  'keyword-biased classifier': (t) => {
    const s = t.toLowerCase();
    const hit = ['urgent', 'emergency', 'immediately', 'critical', 'now', 'asap']
      .some((w) => s.includes(w));
    return { priority: hit ? 'High' : 'Low' };
  },
  'always high (fair)': () => ({ priority: 'High' })
};
for (const a of fixtures.bias_audit.audits) {
  const fn = classifiers[a.label];
  if (!fn) { failures.push(`bias audit "${a.label}": no matching JS classifier in the check`); continue; }
  cmp(`biasAudit[${a.label}]`, gov.runBiasAudit(fn), a.value);
}

/* Words that legitimately appear in a record's own vocabulary (signal-group names,
 * priorities, categories): a match on those is not a leak. */
const ALLOWED_LEAK_WORDS = new Set([
  'urgent', 'urgency', 'critical', 'dialysis', 'ventilator', 'meter', 'medium',
  'signals', 'clinical', 'equipment', 'context', 'hazard', 'routine', 'words', 'review',
  'priority', 'english', 'afrikaans', 'isizulu', 'likely', 'unknown', 'medical',
  'finance', 'operations', 'supply', 'supplier', 'biomed', 'facilities', 'helpdesk',
  'shared', 'services', 'engineer', 'engineering', 'on-call', 'blood'
]);

/* ---- decision records ---------------------------------------------------- */
for (const r of fixtures.records) {
  const label = r.message.slice(0, 46).replace(/\s+/g, ' ');
  cmp(`signalsFor("${label}")`, gov.signalsFor(r.message), r.signals);
  cmp(`languageHint("${label}")`, gov.languageHint(r.message), r.language_hint);

  const got = gov.buildDecisionRecord(r.message, r.ticket);
  // `at` is a wall-clock timestamp; it cannot be compared. Everything else must match.
  const want = r.record;
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00$/.test(got.at)) {
    failures.push(`buildDecisionRecord("${label}").at → js ${got.at} is not an ISO second stamp`);
  }
  // The fingerprint is a 12-hex-char token and nothing more; the VALUE cannot match
  // Python's sha256 and is not claimed to. Stability and shape are checked instead.
  if (!/^[0-9a-f]{12}$/.test(got.message_fingerprint)) {
    failures.push(`fingerprint("${label}") → js ${got.message_fingerprint} is not 12 hex chars`);
  }
  if (got.message_fingerprint !== gov.buildDecisionRecord(r.message, r.ticket).message_fingerprint) {
    failures.push(`fingerprint("${label}") is not stable across calls`);
  }
  const jsRest = { ...got };
  delete jsRest.at;
  delete jsRest.message_fingerprint;
  const pyRest = { ...want };
  delete pyRest.message_fingerprint;
  cmp(`buildDecisionRecord("${label}")`, jsRest, pyRest);

  // Privacy: no field may carry the message, or any distinctive word from it. The scan
  // looks at the values a leak could hide in - ids, category, priority, signals, hint,
  // fingerprint - and deliberately not at `note`, which is this project's own sentence.
  const words = r.message.split(/[^\p{L}\p{N}]+/u)
    .map((w) => w.toLowerCase())
    .filter((w) => w.length >= 5 && !ALLOWED_LEAK_WORDS.has(w));
  const leakFields = ['ticket_id', 'category', 'priority', 'assigned_to', 'language_hint',
                      'message_fingerprint', 'note'].filter((k) => k !== 'note');
  const blob = leakFields.map((k) => String(got[k])).join(' ').toLowerCase() +
    ' ' + got.signals_fired.join(' ');
  for (const w of words) {
    if (blob.includes(w)) {
      failures.push(`buildDecisionRecord("${label}") leaks the word "${w}"`);
    }
  }
}

/* ---- transparency note --------------------------------------------------- */
const recs = fixtures.records.map((r) => {
  const js = gov.buildDecisionRecord(r.message, r.ticket);
  delete js.at;
  // The fixture's fingerprint is Python's; substitute JS's so only the aggregate
  // arithmetic is under test here.
  js.message_fingerprint = r.record.message_fingerprint;
  return js;
});
cmp('transparencyNote(empty)', gov.transparencyNote([]), fixtures.transparency.empty);
cmp('transparencyNote(all)', gov.transparencyNote(recs), fixtures.transparency.all);
cmp('transparencyNote(flagged only)',
    gov.transparencyNote(recs.filter((r) => r.needs_bias_review)),
    fixtures.transparency.only_flagged);

/* ---- rounding helper, directly ------------------------------------------- */
// A handful of values where Math.round and Python's round disagree. If this block ever
// fails, every number above is suspect: it is the foundation the rest stands on.
const ROUNDING = [
  [2.675, 2, 2.67], [1.005, 2, 1.0], [0.125, 2, 0.12], [0.135, 2, 0.14],
  [2.5, 0, 2], [3.5, 0, 4], [-0.5, 0, 0], [-2.5, 0, -2], [0.5, 0, 0],
  [12.345, 2, 12.35], [1.0000000000000002, 2, 1.0], [0.075, 2, 0.07],
  [1.45, 1, 1.4], [1.55, 1, 1.6], [247.545, 2, 247.54], [-1.5, 0, -2]
];
for (const [value, digits, want] of ROUNDING) {
  cmp(`roundHalfEven(${value}, ${digits})`, gov.roundHalfEven(value, digits), want);
}

/* ---- report -------------------------------------------------------------- */
const summary =
  `${fixtures.forecasts.length} forecast cases (incl. empty/short/zero-horizon), ` +
  `${fixtures.comparisons.length} method comparisons (walk-forward MAE, ranking, verdict, ` +
  `bootstrap interval_95 and deterministic interval_95_exact), ` +
  `${fixtures.prioritizer.length} prioritizer messages, ` +
  `${fixtures.bias_audit.audits.length} bias audits over ${fixtures.bias_audit.pairs.length} ` +
  `matched pairs, ${fixtures.records.length} decision records (signals, language hint, ` +
  `length, review flag, note) and 3 transparency notes over ${fixtures.records.length} rows ` +
  `from ${fixtures.demo_ticket_count} demo tickets`;
if (failures.length) {
  console.error(`PARITY FAILED: ${failures.length} disagreement(s) of ${checks.fields} fields\n` +
    failures.slice(0, 40).join('\n'));
  process.exit(1);
}
console.log(`parity ok: ${checks.fields} values identical to the Python engine — ${summary}. ` +
  `Fingerprints are NOT compared by value: the browser uses FNV-1a, the service SHA-256 ` +
  `(checked for shape and stability only).`);

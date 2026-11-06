/* Hold the browser engine to the Python engine's answers.
 *
 * Replays every recorded message through web/engine.js and compares all six fields
 * against what app/ actually produced. Any difference is a failure: the page must not
 * tell a nurse something the console would not.
 *
 * Run:  python scripts/dump_engine_fixture.py && node scripts/check_engine_parity.mjs
 */
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
// Absolute paths (as the pytest wrapper passes) must not be joined onto the repo root.
const read = (p) => fs.readFileSync(path.isAbsolute(p) ? p : path.join(root, p), 'utf8');

const [bundlePath = 'web/engine_bundle.json', fixturePath = 'tests/data/engine_parity.json'] =
  process.argv.slice(2);
const bundle = JSON.parse(read(bundlePath));
const engine = new Function(read('web/engine.js') + '; return MedOpsEngine;')();
const fixture = JSON.parse(read(fixturePath)).cases;

const fields = ['body', 'sender', 'category', 'confidence', 'priority', 'assigned_to', 'summary'];
let failures = 0;

for (const { message, expect } of fixture) {
  const ticket = engine.generate(message, bundle);
  const got = {
    body: ticket.message,
    sender: ticket.sender,
    category: ticket.category,
    confidence: ticket.confidence,
    priority: ticket.priority,
    assigned_to: ticket.assigned_to,
    summary: ticket.summary,
  };
  for (const field of fields) {
    if (got[field] !== expect[field]) {
      failures++;
      console.error(
        `MISMATCH ${field}\n  message: ${JSON.stringify(message.slice(0, 80))}` +
        `\n  python:  ${JSON.stringify(expect[field])}` +
        `\n  browser: ${JSON.stringify(got[field])}`
      );
    }
  }
}

const total = fixture.length;
if (failures) {
  console.error(`\n${failures} mismatch(es) across ${total} messages.`);
  process.exit(1);
}
const categories = new Set(fixture.map((c) => c.expect.category));
const priorities = new Set(fixture.map((c) => c.expect.priority));
console.log(
  `parity ok: ${total} messages x ${fields.length} fields identical to the Python engine` +
  ` (categories: ${[...categories].join(', ')}; priorities: ${[...priorities].join(', ')})`
);

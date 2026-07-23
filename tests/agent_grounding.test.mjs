import { test } from 'node:test';
import assert from 'node:assert';
import { createRequire } from 'node:module';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const require = createRequire(import.meta.url);
const ROOT = path.dirname(require.resolve('../server.js'));

test('seedAgentContext seeds AGENTS.md/CLAUDE.md/examples, idempotently', () => {
  const ws = fs.mkdtempSync(path.join(os.tmpdir(), 'bpground-'));
  process.env.BLOCKPY_WORKSPACE = ws;
  const { seedAgentContext } = require('../server.js');
  seedAgentContext();

  const agents = fs.readFileSync(path.join(ws, 'AGENTS.md'), 'utf8');
  for (const tok of ['tm.Model', 'add_example', 'predict', 'MagicianLite', 'move_to', 'MagicianGO', 'DobotLink']) {
    assert.ok(agents.includes(tok), `AGENTS.md should mention ${tok}`);
  }
  const claude = fs.readFileSync(path.join(ws, 'CLAUDE.md'), 'utf8');
  assert.ok(claude.includes('@AGENTS.md'), 'CLAUDE.md should import AGENTS.md');
  assert.ok(fs.existsSync(path.join(ws, 'examples', 'm1_ai_sorting.py')), 'examples copied');

  // 멱등: 사용자 편집 보존
  fs.writeFileSync(path.join(ws, 'AGENTS.md'), 'USER EDIT', 'utf8');
  seedAgentContext();
  assert.strictEqual(fs.readFileSync(path.join(ws, 'AGENTS.md'), 'utf8'), 'USER EDIT');
});

test('AGENTS.md API list matches real signatures (robotSpecs.json + tm.py)', () => {
  const agents = fs.readFileSync(path.join(ROOT, 'agent-context', 'AGENTS.md'), 'utf8');
  const robotSpecs = require('../src/data/robotSpecs.json');
  const names = new Set();
  for (const mod of robotSpecs) for (const e of mod.entries) if (e.name) names.add(e.name);

  // Explicit lower-bound (regression guard): the API names we know about today must still be
  // present. Kept alongside the derived check below, which is the real enforcement.
  for (const m of ['home', 'move_to', 'move_relative', 'suck', 'grip', 'set_speed', 'get_pose',
                   'forward', 'backward', 'spin', 'strafe', 'move', 'drive_for', 'stop',
                   'buzzer', 'battery', 'ultrasonic', 'imu_angle']) {
    if (agents.includes(m + '(') || agents.includes('.' + m)) {
      assert.ok(names.has(m), `AGENTS.md references dobotkit.${m} not present in robotSpecs.json`);
    }
  }

  // Derived check: extract every arm./car. instance-method CALL actually written in AGENTS.md
  // (scoped to those two receiver prefixes so prose like print(...)/range(...)/os.environ.get(...)
  // can't match) and assert each one is a real robotSpecs.json entry. This is what catches a
  // FUTURE invented method (e.g. arm.rotate_to(...)) that the hardcoded list above would silently
  // miss.
  const dobotCalls = new Set();
  for (const mm of agents.matchAll(/(?:arm|car)\.([a-z_][a-z0-9_]*)\s*\(/g)) dobotCalls.add(mm[1]);
  assert.ok(dobotCalls.size > 0, 'extraction found no arm./car. calls in AGENTS.md — regex/scoping broke');
  for (const name of dobotCalls) {
    assert.ok(names.has(name), `AGENTS.md calls dobotkit method '${name}(...)' not present in robotSpecs.json`);
  }

  const tmpy = fs.readFileSync(path.join(ROOT, 'runtime', 'tm.py'), 'utf8');

  // Explicit lower-bound (tm)
  for (const m of ['add_example', 'train', 'predict', 'predict_proba', 'save']) {
    assert.ok(new RegExp('def ' + m + '\\b').test(tmpy), `tm.py should define ${m}`);
  }

  // Derived check: tm.<Name> (module-level refs: Model, load_model, ...) and m.<name>( (instance
  // methods on a tm.Model, e.g. add_example/train/predict/predict_proba/save) — each must match a
  // real `def`/`class` in tm.py.
  const tmRefs = new Set();
  for (const mm of agents.matchAll(/\btm\.([A-Za-z_][A-Za-z0-9_]*)/g)) tmRefs.add(mm[1]);
  for (const mm of agents.matchAll(/\bm\.([a-z_][a-z0-9_]*)\s*\(/g)) tmRefs.add(mm[1]);
  assert.ok(tmRefs.size > 0, 'extraction found no tm./m. references in AGENTS.md — regex/scoping broke');
  for (const name of tmRefs) {
    const ok = new RegExp('\\bdef ' + name + '\\b').test(tmpy) || new RegExp('\\bclass ' + name + '\\b').test(tmpy);
    assert.ok(ok, `AGENTS.md references tm.${name} not defined (def/class) in tm.py`);
  }
});

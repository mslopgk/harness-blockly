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
  for (const m of ['home', 'move_to', 'move_relative', 'suck', 'grip', 'set_speed', 'get_pose',
                   'forward', 'backward', 'spin', 'strafe', 'move', 'drive_for', 'stop',
                   'buzzer', 'battery', 'ultrasonic', 'imu_angle']) {
    if (agents.includes(m + '(') || agents.includes('.' + m)) {
      assert.ok(names.has(m), `AGENTS.md references dobotkit.${m} not present in robotSpecs.json`);
    }
  }
  const tmpy = fs.readFileSync(path.join(ROOT, 'runtime', 'tm.py'), 'utf8');
  for (const m of ['add_example', 'train', 'predict', 'predict_proba', 'save']) {
    assert.ok(new RegExp('def ' + m + '\\b').test(tmpy), `tm.py should define ${m}`);
  }
});

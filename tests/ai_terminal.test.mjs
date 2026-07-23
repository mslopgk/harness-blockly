import { test } from 'node:test';
import assert from 'node:assert';
import { createRequire } from 'node:module';
import { WebSocket } from 'ws';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';

const require = createRequire(import.meta.url);

test('WS /api/terminal relays shell output', async (t) => {
  process.env.BLOCKPY_WORKSPACE = fs.mkdtempSync(path.join(os.tmpdir(), 'bpterm-'));
  const { start } = require('../server.js');
  const { server, port } = await start(0);
  t.after(() => new Promise((r) => server.close(r)));

  const marker = 'BLOCKPY_TERMINAL_OK_' + process.pid;
  const ws = new WebSocket(`ws://127.0.0.1:${port}/api/terminal`);
  const buf = await new Promise((resolve, reject) => {
    let acc = '';
    const timer = setTimeout(() => reject(new Error('timeout; got: ' + acc)), 25000);
    ws.on('open', () => {
      ws.send(JSON.stringify({ t: 'r', cols: 80, rows: 24 }));
      ws.send(JSON.stringify({ t: 'i', d: `echo ${marker}\r` }));
    });
    ws.on('message', (d) => { acc += d.toString(); if (acc.includes(marker)) { clearTimeout(timer); resolve(acc); } });
    ws.on('error', (e) => { clearTimeout(timer); reject(e); });
  });
  assert.ok(buf.includes(marker), 'shell output should echo the marker');
  ws.close();
});

test('WS upgrade rejects non-loopback Host', async (t) => {
  const { start } = require('../server.js');
  const { server, port } = await start(0);
  t.after(() => new Promise((r) => server.close(r)));

  const ws = new WebSocket(`ws://127.0.0.1:${port}/api/terminal`, { headers: { host: 'evil.example.com' } });
  const result = await new Promise((resolve) => {
    ws.on('open', () => resolve('opened'));
    ws.on('error', () => resolve('error'));
    ws.on('close', () => resolve('closed'));
  });
  assert.notStrictEqual(result, 'opened', 'non-loopback Host must not open a terminal');
});

// Regression: a raw `null` JSON frame (`JSON.parse('null') === null`) must not crash the whole
// backend. Before the fix, `msg.t` on a null `msg` threw a TypeError inside the ws message
// handler, which escaped as an uncaughtException and killed the entire Node process (taking
// run-python/fs/health/AI down with it, not just this one terminal connection). This test sends
// a bare `null` frame, then proves the server is still alive (HTTP health check succeeds) and
// this very connection's message handler is still working (a subsequent valid frame still echoes).
test('WS null frame does not crash the server', async (t) => {
  const { start } = require('../server.js');
  const { server, port } = await start(0);
  t.after(() => new Promise((r) => server.close(r)));

  const marker = 'BLOCKPY_NULLFRAME_OK_' + process.pid;
  const ws = new WebSocket(`ws://127.0.0.1:${port}/api/terminal`);
  await new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error('ws did not open')), 10000);
    ws.on('open', () => { clearTimeout(timer); resolve(); });
    ws.on('error', reject);
  });

  ws.send('null'); // JSON.parse('null') === null — the crashing frame

  // Give the (formerly crashing) handler a tick, then confirm the process is still alive: a
  // crashed backend would refuse/error this HTTP request, not just the WS connection.
  await new Promise((r) => setTimeout(r, 300));
  const health = await fetch(`http://127.0.0.1:${port}/api/health`);
  assert.strictEqual(health.status, 200, 'server must survive a null WS frame (health check)');
  const healthBody = await health.json();
  assert.strictEqual(healthBody.status, 'ok');

  // Also confirm this same connection's handler kept working afterward (not just the process).
  const buf = await new Promise((resolve, reject) => {
    let acc = '';
    const timer = setTimeout(() => reject(new Error('timeout; got: ' + acc)), 25000);
    ws.on('message', (d) => { acc += d.toString(); if (acc.includes(marker)) { clearTimeout(timer); resolve(acc); } });
    ws.send(JSON.stringify({ t: 'i', d: `echo ${marker}\r` }));
  });
  assert.ok(buf.includes(marker), 'connection should still relay shell output after the null frame');
  ws.close();
});

test('terminal PTY env exposes RUNTIME_DIR on PYTHONPATH (import tm works)', async (t) => {
  process.env.BLOCKPY_WORKSPACE = fs.mkdtempSync(path.join(os.tmpdir(), 'bpterm-pp-'));
  const { start } = require('../server.js');
  const { server, port } = await start(0);
  t.after(() => new Promise((r) => server.close(r)));

  const ws = new WebSocket(`ws://127.0.0.1:${port}/api/terminal`);
  const buf = await new Promise((resolve, reject) => {
    let acc = '';
    const timer = setTimeout(() => reject(new Error('timeout; got: ' + acc)), 25000);
    ws.on('open', () => {
      ws.send(JSON.stringify({ t: 'r', cols: 120, rows: 24 }));
      ws.send(JSON.stringify({ t: 'i', d: `python -c "import os;print('PYPATH::'+os.environ.get('PYTHONPATH',''))"\r` }));
    });
    // 'PYPATH::' 는 입력 명령 자체에도 있어(pty 가 에코함) 그것만으론 실제 출력을 못 가른다.
    // 실제 python 출력의 PYTHONPATH 값에만 나타나는 'runtime' 이 함께 보일 때 resolve 한다.
    ws.on('message', (d) => { acc += d.toString(); if (acc.includes('PYPATH::') && /runtime/i.test(acc)) { clearTimeout(timer); resolve(acc); } });
    ws.on('error', (e) => { clearTimeout(timer); reject(e); });
  });
  // RUNTIME_DIR 이 PYTHONPATH 에 실렸으면 출력 값에 'runtime' 이 포함된다(배너/프롬프트/에코엔 없음).
  assert.ok(/runtime/i.test(buf), `terminal PYTHONPATH should contain RUNTIME_DIR; got tail: ${buf.slice(-300)}`);
  ws.close();
});

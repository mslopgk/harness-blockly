import { test } from 'node:test';
import assert from 'node:assert';
import { createRequire } from 'node:module';
import { WebSocket } from 'ws';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';

const require = createRequire(import.meta.url);

// 아래 대부분의 테스트는 **셸에 명령을 타이핑해서** 에코를 확인한다. 그런데 실제 제품의 터미널은
// 열리자마자 AI 도우미(opencode) TUI 를 띄우므로, 타이핑한 문자가 셸이 아니라 TUI 로 들어가
// 영원히 에코되지 않는다. 이 파일이 검증하려는 것은 "PTY 중계·env·크래시 내구성" 이지
// AI 도우미가 아니므로, 그 스위치를 끄고 순수 셸로 검사한다.
// (자동 실행 자체는 아래 'boots the AI helper …' 테스트가 따로 검증한다.)
process.env.BLOCKPY_TERMINAL_AI = '0';

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

// 터미널을 열면 **입력을 보내지 않아도** 부트 명령이 저절로 실행되어야 한다. 제품 기본값은
// opencode(AI 도우미)지만, 그것이 깔려 있지 않은 기계에서도 이 계약을 검증할 수 있게
// BLOCKPY_TERMINAL_CMD 로 확인 가능한 명령을 넣어 시험한다.
// 왜 중요한가: 학생 화면의 목적은 "AI 에게 물어보는 곳" 이다. 빈 프롬프트가 뜨면 기능이 없는 것과 같다.
test('boots the AI helper command automatically (no input sent)', async (t) => {
  process.env.BLOCKPY_WORKSPACE = fs.mkdtempSync(path.join(os.tmpdir(), 'bpterm-boot-'));
  const prevAi = process.env.BLOCKPY_TERMINAL_AI;
  const prevCmd = process.env.BLOCKPY_TERMINAL_CMD;
  const marker = 'BLOCKPY_BOOT_OK_' + process.pid;
  process.env.BLOCKPY_TERMINAL_AI = '1';
  process.env.BLOCKPY_TERMINAL_CMD = `echo ${marker}`;
  t.after(() => {
    if (prevAi === undefined) delete process.env.BLOCKPY_TERMINAL_AI; else process.env.BLOCKPY_TERMINAL_AI = prevAi;
    if (prevCmd === undefined) delete process.env.BLOCKPY_TERMINAL_CMD; else process.env.BLOCKPY_TERMINAL_CMD = prevCmd;
  });

  const { start } = require('../server.js');
  const { server, port } = await start(0);
  t.after(() => new Promise((r) => server.close(r)));

  const ws = new WebSocket(`ws://127.0.0.1:${port}/api/terminal`);
  const buf = await new Promise((resolve, reject) => {
    let acc = '';
    const timer = setTimeout(() => reject(new Error('부트 명령이 실행되지 않았다; got: ' + acc)), 25000);
    // 크기만 알려주고 **아무 입력도 보내지 않는다** — 그래도 마커가 나와야 통과.
    ws.on('open', () => ws.send(JSON.stringify({ t: 'r', cols: 100, rows: 30 })));
    ws.on('message', (d) => { acc += d.toString(); if (acc.includes(marker)) { clearTimeout(timer); resolve(acc); } });
    ws.on('error', (e) => { clearTimeout(timer); reject(e); });
  });
  assert.ok(buf.includes(marker), '입력 없이도 부트 명령의 출력이 보여야 한다');
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

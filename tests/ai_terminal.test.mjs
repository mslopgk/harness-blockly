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

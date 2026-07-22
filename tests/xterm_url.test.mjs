import { test } from 'node:test';
import assert from 'node:assert';
import { terminalWsUrl } from '../src/components/terminalWs.mjs';

test('http -> ws', () => {
  assert.strictEqual(terminalWsUrl({ protocol: 'http:', host: '127.0.0.1:3000' }), 'ws://127.0.0.1:3000/api/terminal');
});
test('https -> wss', () => {
  assert.strictEqual(terminalWsUrl({ protocol: 'https:', host: 'example:8443' }), 'wss://example:8443/api/terminal');
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {
  packEnvelope, unpackEnvelope, abToBase64, base64ToAb, FORMAT,
} from '../src/utils/tmPack.js';

test('abToBase64/base64ToAb 는 바이트를 왕복 보존한다', () => {
  const src = new Uint8Array([0, 1, 2, 254, 255, 128]).buffer;
  const out = new Uint8Array(base64ToAb(abToBase64(src)));
  assert.deepEqual([...out], [0, 1, 2, 254, 255, 128]);
});

test('packEnvelope/unpackEnvelope 는 labels·base·imageSize·가중치를 보존한다', () => {
  const weightData = new Uint8Array([10, 20, 30, 40]).buffer;
  const artifacts = {
    modelTopology: { a: 1 },
    weightSpecs: [{ name: 'w', shape: [2, 2], dtype: 'float32' }],
    weightData,
  };
  const json = packEnvelope({ labels: ['캔', '페트'], imageSize: 224, base: 'mobilenet-v2', artifacts });
  const parsed = JSON.parse(json);
  assert.equal(parsed.format, FORMAT);
  assert.equal(typeof parsed.head.weightData, 'string');

  const back = unpackEnvelope(json);
  assert.deepEqual(back.labels, ['캔', '페트']);
  assert.equal(back.imageSize, 224);
  assert.equal(back.base, 'mobilenet-v2');
  assert.deepEqual(back.artifacts.modelTopology, { a: 1 });
  assert.deepEqual([...new Uint8Array(back.artifacts.weightData)], [10, 20, 30, 40]);
});

test('packEnvelope 는 라벨 2개 미만을 거부한다', () => {
  assert.throws(
    () => packEnvelope({ labels: ['only'], imageSize: 224, base: 'x', artifacts: { weightData: new ArrayBuffer(0) } }),
    /라벨/,
  );
});

test('unpackEnvelope 는 알 수 없는 format 을 거부한다', () => {
  assert.throws(() => unpackEnvelope(JSON.stringify({ format: 'nope' })), /형식/);
});

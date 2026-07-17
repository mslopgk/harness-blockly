# Teachable Machine 인앱 (1단계: 학습 + 저장) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 플랫폼 안에서 웹캠으로 이미지 분류 모델을 학습하고, 라이브 미리보기 후 특정 파일명(`<이름>.json`)으로 워크스페이스에 저장하는 기능을 추가한다.

**Architecture:** 브라우저 내 TF.js + MobileNet v2 전이학습(구글 Teachable Machine과 동일 방식). MobileNet은 임베딩 추출기로만 쓰고(오프라인 vendored), 작은 dense head만 학습·저장한다. 저장은 head 아티팩트를 단일 JSON(`blockpy-tm-v1`)으로 직렬화해 기존 키리스 `/api/fs/file`로 워크스페이스에 쓴다(백엔드 미가동 시 브라우저 다운로드 폴백). 학습·미리보기·저장 전부 프론트 완결.

**Tech Stack:** React 19 + Vite, `@tensorflow/tfjs`(동적 import 로 지연 로드), `@tensorflow-models/mobilenet`(로컬 modelUrl), Playwright(가짜 카메라 + 가짜 featurizer), Node `node --test`(순수 봉투 로직).

## Global Constraints

- **오프라인 필수 · CDN 금지.** MobileNet 가중치는 `public/vendor/mobilenet/` 로 vendored; 런타임은 `/vendor/mobilenet/model.json` 만 로드한다. tf.js 는 npm→Vite 번들.
- **블록 코어 · 로봇 백엔드 · 파이썬 로직 무수정.** `irBlocks.js`/`irToBlockly.js`/`blocklyToIr.js`/`irToolbox.js`/`server.js` 등 변환 코어와 로봇 관련 파일을 건드리지 않는다. 이번 단계에 블록/파이썬 연동 없음.
- **util 모듈 관례:** ESM `import` 로 소비되는 신규 순수 헬퍼는 **순수 ESM `export { … }`** 로 작성한다. 절대 bare `module.exports = …` 를 쓰지 않는다(Vite dev 에서 `module is not defined` → 흰 화면). affineCalib.js 와 동일 패턴.
- **저장 형식** = 단일 JSON `blockpy-tm-v1`: `{ format, labels, imageSize, base:"mobilenet-v2", head:{ modelTopology, weightSpecs, weightData(base64) } }`. head(분류기)만 저장, MobileNet 은 런타임 재사용.
- **파일명:** 사용자가 입력한 이름 → `<이름>.json` 워크스페이스 루트 저장. 저장 경로/이름은 `basename` 안전화(서버가 `/api/fs/file` 에서 처리).
- **테스트 포트:** Playwright 는 `PORT=3100` 으로 실행(사용자의 :3000 Vite 와 충돌 방지, 서버 재사용 비활성화). Node 봉투 테스트는 포트 무관.
- **테스트는 실제 MobileNet 불필요:** 모든 자동 테스트는 가짜 featurizer/직접 임베딩을 쓴다 → vendored 가중치나 네트워크에 의존하지 않는다.

---

## File Structure

- `src/utils/tmPack.js` (신규, **순수 ESM, tf 의존 없음**) — `blockpy-tm-v1` 봉투 직렬화/역직렬화 + ArrayBuffer↔base64. 브라우저·Node 양쪽에서 동작. 단위 테스트 대상.
- `src/utils/teachable.js` (신규, ESM, tf 의존) — TF.js 래퍼: 지연 tf 로드, MobileNet 로드(로컬 url), 특징추출, head 빌드/학습/예측, 모델 직렬화/역직렬화(tmPack 사용). 테스트용 featurizer 훅. `window.BlockPyTM` 노출.
- `src/components/TeachableMachine.jsx` (신규) — TM 패널 UI + 상태기계(idle→collecting→trained/preview→saved). teachable.js 소비.
- `src/App.jsx` (수정) — `TeachableMachine` import + 좌패널 **"TM"** 탭 버튼/패널 추가(Robot 탭 뒤).
- `scripts/vendor-assets.cjs` (수정) — MobileNet v2 파일을 `public/vendor/mobilenet/` 로 내려받는 단계 추가(멱등·존재 시 skip·오프라인 비치명).
- `package.json` (수정) — `@tensorflow/tfjs`, `@tensorflow-models/mobilenet` 의존 + `test:tm` 스크립트.
- `tests/tm_pack.test.mjs` (신규) — 봉투 pack/unpack 순수 로직 Node 테스트.
- `tests/tm_core.spec.js` (신규) — teachable+tmPack 통합(UI 없이 `window.BlockPyTM` 구동, 직접 임베딩): build→train→serialize→deserialize 왕복.
- `tests/tm_ui.spec.js` (신규) — 전체 UI 흐름(가짜 카메라+가짜 featurizer): 클래스·샘플·학습·미리보기·저장.

---

### Task 1: 의존성 + MobileNet vendoring

**Files:**
- Modify: `package.json` (dependencies + scripts)
- Modify: `scripts/vendor-assets.cjs`

**Interfaces:**
- Consumes: 없음.
- Produces: 런타임 자산 `public/vendor/mobilenet/model.json`(+ weight shard 들). npm 의존 `@tensorflow/tfjs`, `@tensorflow-models/mobilenet`. npm 스크립트 `test:tm`.

> 이 태스크에는 자동 게이트가 없다(네트워크 다운로드는 런타임 전용이며 어떤 테스트도 여기에 의존하지 않는다). 검증은 `npm run vendor` 출력과 파일 존재로 수동 확인한다.

- [ ] **Step 1: tf 의존성 설치**

Run:
```bash
cd "C:/Users/user/busan-robotics/플랫폼개발/blockly프로젝트"
npm install --save @tensorflow/tfjs@^4.22.0 @tensorflow-models/mobilenet@^2.1.1
```
Expected: `package.json` dependencies 에 두 패키지가 추가되고 설치 성공.

- [ ] **Step 2: `package.json` 에 `test:tm` 스크립트 추가**

`scripts` 블록에서 `"test:ir"` 줄 아래에 한 줄 추가:
```json
    "test:tm": "node --test tests/tm_pack.test.mjs",
```
(주변 콤마 유지. 예: `"test:ir": "...",` 다음 줄에 위 줄을 넣는다.)

- [ ] **Step 3: `vendor-assets.cjs` 에 MobileNet 다운로드 함수 추가**

`scripts/vendor-assets.cjs` 의 마지막 `console.log(...)` / `process.exitCode` 블록 **바로 앞**(파일 하단, `for (const [from, to] of DIRS)` 루프가 끝난 뒤)에 아래를 삽입한다:

```js
// ─── MobileNet v2 (Teachable Machine 임베딩 추출기) 오프라인 vendoring ──────────
// @tensorflow-models/mobilenet 은 기본적으로 storage.googleapis.com 에서 가중치를
// 내려받는다(온라인 전용). 오프라인 구동을 위해 model.json + weight shard 들을
// public/vendor/mobilenet 으로 한 번 복사해 둔다. 존재하면 skip, 오프라인이면 경고만.
async function vendorMobileNet() {
  const base = 'https://storage.googleapis.com/tfjs-models/tfjs/mobilenet_v2_1.0_224/';
  const outDir = path.join(OUT, 'mobilenet');
  const modelJson = path.join(outDir, 'model.json');
  if (fs.existsSync(modelJson)) {
    console.log('[vendor] mobilenet: already present, skipped');
    return;
  }
  if (typeof fetch !== 'function') {
    console.warn('[vendor] mobilenet: global fetch 없음(Node<18) — 건너뜀. 온라인 Node18+ 에서 `npm run vendor` 재실행 필요');
    return;
  }
  try {
    fs.mkdirSync(outDir, { recursive: true });
    const mjRes = await fetch(base + 'model.json');
    if (!mjRes.ok) throw new Error('model.json HTTP ' + mjRes.status);
    const mjText = await mjRes.text();
    fs.writeFileSync(modelJson, mjText, 'utf8');
    const manifest = JSON.parse(mjText).weightsManifest || [];
    const shards = manifest.flatMap((g) => g.paths || []);
    for (const shard of shards) {
      const r = await fetch(base + shard);
      if (!r.ok) throw new Error(shard + ' HTTP ' + r.status);
      const buf = Buffer.from(await r.arrayBuffer());
      fs.writeFileSync(path.join(outDir, shard), buf);
    }
    console.log(`[vendor] mobilenet: downloaded model.json + ${shards.length} shard(s)`);
  } catch (e) {
    console.warn('[vendor] mobilenet: 다운로드 실패(오프라인?) — TM 학습은 온라인에서 `npm run vendor` 후 가능:', e.message);
  }
}
```

- [ ] **Step 4: 스크립트 하단을 async 로 감싸 `vendorMobileNet` 호출**

`vendor-assets.cjs` 의 최종 `console.log(...)` 및 `process.exitCode` 두 줄을 아래로 교체한다:

```js
(async () => {
  await vendorMobileNet();
  console.log(`[vendor] copied ${copied} item(s) into public/vendor${missing ? `, ${missing} missing` : ''}`);
  if (missing) process.exitCode = 0; // non-fatal: build can still proceed (CDN fallback at runtime)
})();
```
(기존 `let copied`, `let missing`, 두 for 루프는 그대로 둔다. `vendorMobileNet` 는 이 IIFE 앞에 정의되어 있으므로 호이스팅 문제 없음.)

- [ ] **Step 5: vendor 실행 및 확인**

Run:
```bash
cd "C:/Users/user/busan-robotics/플랫폼개발/blockly프로젝트"
npm run vendor
ls public/vendor/mobilenet/
```
Expected: 온라인이면 `[vendor] mobilenet: downloaded model.json + N shard(s)` 출력 + `model.json` 및 `group1-shard*` 파일 존재. 오프라인이면 경고 한 줄만 출력되고 프로세스는 실패하지 않음(비치명).

- [ ] **Step 6: Commit**

```bash
git add package.json package-lock.json scripts/vendor-assets.cjs
git commit -m "feat(tm): TF.js/MobileNet 의존성 추가 + MobileNet 오프라인 vendoring"
```

---

### Task 2: `tmPack.js` — 단일 JSON 봉투(순수 로직) + Node 테스트

**Files:**
- Create: `src/utils/tmPack.js`
- Create: `tests/tm_pack.test.mjs`

**Interfaces:**
- Consumes: 없음(순수).
- Produces (모두 `export`):
  - `FORMAT = 'blockpy-tm-v1'` (string)
  - `abToBase64(buf: ArrayBuffer) -> string`
  - `base64ToAb(b64: string) -> ArrayBuffer`
  - `packEnvelope({ labels: string[], imageSize: number, base: string, artifacts: { modelTopology, weightSpecs, weightData: ArrayBuffer } }) -> string` (JSON 문자열)
  - `unpackEnvelope(jsonStringOrObj) -> { labels, imageSize, base, artifacts: { modelTopology, weightSpecs, weightData: ArrayBuffer } }`

- [ ] **Step 1: 실패하는 테스트 작성 — `tests/tm_pack.test.mjs`**

```js
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run:
```bash
cd "C:/Users/user/busan-robotics/플랫폼개발/blockly프로젝트"
node --test tests/tm_pack.test.mjs
```
Expected: FAIL — `Cannot find module '.../src/utils/tmPack.js'` (아직 미작성).

- [ ] **Step 3: `src/utils/tmPack.js` 작성**

```js
// tmPack.js — Teachable Machine 모델 봉투(blockpy-tm-v1) 직렬화/역직렬화. 순수 로직(tf 의존 없음).
//
// 저장 형식: { format, labels, imageSize, base, head:{ modelTopology, weightSpecs, weightData(base64) } }
// head(분류기)만 담는다. MobileNet 특징추출기는 저장하지 않고 런타임에 로컬 vendored 를 재사용한다.
//
// 브라우저·Node 양쪽 동작: base64 는 Buffer(있으면) 아니면 btoa/atob 사용.
// 레포 관례상 순수 ESM export (bare module.exports 금지 — Vite dev 흰화면 원인).

const FORMAT = 'blockpy-tm-v1';

// ArrayBuffer -> base64 문자열.
function abToBase64(buf) {
  const bytes = new Uint8Array(buf);
  if (typeof Buffer !== 'undefined') return Buffer.from(bytes).toString('base64');
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

// base64 문자열 -> ArrayBuffer.
function base64ToAb(b64) {
  if (typeof Buffer !== 'undefined') {
    const buf = Buffer.from(b64, 'base64');
    return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
  }
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

// tf.io save handler 가 준 artifacts({modelTopology, weightSpecs, weightData:ArrayBuffer})를 단일 JSON 문자열로.
function packEnvelope({ labels, imageSize, base, artifacts }) {
  if (!Array.isArray(labels) || labels.length < 2) {
    throw new Error('라벨(클래스)은 2개 이상이어야 저장할 수 있습니다.');
  }
  return JSON.stringify({
    format: FORMAT,
    labels,
    imageSize,
    base,
    head: {
      modelTopology: artifacts.modelTopology,
      weightSpecs: artifacts.weightSpecs,
      weightData: abToBase64(artifacts.weightData),
    },
  });
}

// 단일 JSON(문자열/객체) -> {labels, imageSize, base, artifacts:{modelTopology, weightSpecs, weightData:ArrayBuffer}}.
function unpackEnvelope(jsonStringOrObj) {
  const j = typeof jsonStringOrObj === 'string' ? JSON.parse(jsonStringOrObj) : jsonStringOrObj;
  if (!j || j.format !== FORMAT) {
    throw new Error('지원하지 않는 모델 형식입니다: ' + (j && j.format));
  }
  const h = j.head || {};
  return {
    labels: j.labels,
    imageSize: j.imageSize,
    base: j.base,
    artifacts: {
      modelTopology: h.modelTopology,
      weightSpecs: h.weightSpecs,
      weightData: base64ToAb(h.weightData),
    },
  };
}

export { FORMAT, abToBase64, base64ToAb, packEnvelope, unpackEnvelope };
```

- [ ] **Step 4: 테스트 통과 확인**

Run:
```bash
node --test tests/tm_pack.test.mjs
```
Expected: PASS — 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/utils/tmPack.js tests/tm_pack.test.mjs
git commit -m "feat(tm): blockpy-tm-v1 봉투 직렬화(tmPack) + Node 왕복 테스트"
```

---

### Task 3: `teachable.js` — TF.js 래퍼 + 통합 테스트

**Files:**
- Create: `src/utils/teachable.js`
- Create: `tests/tm_core.spec.js`

**Interfaces:**
- Consumes: `packEnvelope`, `unpackEnvelope` (Task 2). `@tensorflow/tfjs`, `@tensorflow-models/mobilenet` (동적 import).
- Produces (모두 `export`, 또한 `window.BlockPyTM` 로 노출):
  - `ensureTf() -> Promise<tf>` — tf.js 지연 로드.
  - `featurize(input) -> Promise<tf.Tensor2D [1,D]>` — input=HTMLVideo/Image/Canvas. 테스트 featurizer(`window.__TM_TEST_FEATURIZER`)가 있으면 그것을 사용(MobileNet 미로드).
  - `buildHead(inputDim, numClasses) -> Promise<tf.LayersModel>`
  - `trainHead(head, samples, numClasses, opts?) -> Promise<History>` — `samples: {classIndex:number, embedding: tf.Tensor2D [1,D]}[]`; `opts: {epochs?, batchSize?, onEpoch?(epoch,logs)}`.
  - `predictTop(head, embedding, labels) -> Promise<{index, label, confidence, all:number[]}>`
  - `serializeModel({ head, labels, imageSize?, base? }) -> Promise<string>` — blockpy-tm-v1 JSON.
  - `deserializeModel(jsonString) -> Promise<{head, labels, imageSize, base}>`
  - `IMAGE_SIZE = 224`, `BASE_ID = 'mobilenet-v2'`

- [ ] **Step 1: 실패하는 통합 테스트 작성 — `tests/tm_core.spec.js`**

```js
const { test, expect } = require('@playwright/test');

// teachable.js + tmPack.js 통합. UI 없이 window.BlockPyTM 을 직접 구동한다.
// 실제 MobileNet 은 로드하지 않고(직접 임베딩 텐서 주입) tf.js 로만 head 학습/직렬화/역직렬화 왕복을 검증.
test.describe('Teachable Machine core (teachable+tmPack)', () => {
  test('build → train → serialize(blockpy-tm-v1) → deserialize 왕복', async ({ page }) => {
    await page.goto('/');
    await expect.poll(async () => page.evaluate(() => !!window.BlockPyTM), { timeout: 30000 }).toBe(true);

    const result = await page.evaluate(async () => {
      const TM = window.BlockPyTM;
      const tf = await TM.ensureTf();
      const mk = (cls, a, b) => ({ classIndex: cls, embedding: tf.tensor2d([[a, b, a * 0.5, 1 - b]], [1, 4]) });
      const samples = [mk(0, 0.9, 0.1), mk(0, 0.8, 0.2), mk(1, 0.1, 0.9), mk(1, 0.2, 0.8)];
      const head = await TM.buildHead(4, 2);
      await TM.trainHead(head, samples, 2, { epochs: 5 });
      const json = await TM.serializeModel({ head, labels: ['A', 'B'] });
      const parsed = JSON.parse(json);
      const back = await TM.deserializeModel(json);
      const pred = await TM.predictTop(back.head, tf.tensor2d([[0.9, 0.1, 0.45, 0.9]], [1, 4]), back.labels);
      return {
        format: parsed.format,
        labels: parsed.labels,
        base: parsed.base,
        imageSize: parsed.imageSize,
        weightsIsString: typeof parsed.head.weightData === 'string' && parsed.head.weightData.length > 0,
        backLabels: back.labels,
        predLabel: pred.label,
        predConfIsNum: typeof pred.confidence === 'number',
      };
    });

    expect(result.format).toBe('blockpy-tm-v1');
    expect(result.labels).toEqual(['A', 'B']);
    expect(result.base).toBe('mobilenet-v2');
    expect(result.imageSize).toBe(224);
    expect(result.weightsIsString).toBe(true);
    expect(result.backLabels).toEqual(['A', 'B']);
    expect(['A', 'B']).toContain(result.predLabel);
    expect(result.predConfIsNum).toBe(true);
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run:
```bash
cd "C:/Users/user/busan-robotics/플랫폼개발/blockly프로젝트"
PORT=3100 npx playwright test tests/tm_core.spec.js
```
Expected: FAIL — `window.BlockPyTM` 이 undefined 라 `expect.poll` 타임아웃(아직 teachable.js 없음).

- [ ] **Step 3: `src/utils/teachable.js` 작성**

```js
// teachable.js — Teachable Machine(TF.js + MobileNet 전이학습) 래퍼. 브라우저 전용.
//   - MobileNet(v2)은 임베딩 추출기로만 사용, 로컬 vendored(/vendor/mobilenet/model.json) 로드.
//   - 작은 dense head 만 학습/저장. 저장 형식은 tmPack 의 blockpy-tm-v1.
//   - tf.js 는 동적 import 로 지연 로드(메인 번들 비대화 방지).
//   - 테스트 훅: window.__TM_TEST_FEATURIZER(input)->number[] 가 있으면 MobileNet 대신 사용.
import { packEnvelope, unpackEnvelope } from './tmPack.js';

const MOBILENET_URL = '/vendor/mobilenet/model.json';
const IMAGE_SIZE = 224;
const BASE_ID = 'mobilenet-v2';

let _tf = null;
let _base = null; // 로드된 mobilenet 모델

async function ensureTf() {
  if (_tf) return _tf;
  _tf = await import('@tensorflow/tfjs');
  return _tf;
}

function testFeaturizer() {
  return (typeof window !== 'undefined' && window.__TM_TEST_FEATURIZER) || null;
}

async function ensureBase() {
  if (_base) return _base;
  await ensureTf();
  const mobilenet = await import('@tensorflow-models/mobilenet');
  try {
    _base = await mobilenet.load({ version: 2, alpha: 1.0, modelUrl: MOBILENET_URL });
  } catch (e) {
    throw new Error('MobileNet 로드 실패 — 오프라인 자산이 없습니다. `npm run vendor` 를 온라인에서 실행하세요. (' + e.message + ')');
  }
  return _base;
}

// input(HTMLVideo/Image/Canvas) -> 임베딩 텐서 [1, D].
async function featurize(input) {
  const tf = await ensureTf();
  const fake = testFeaturizer();
  if (fake) {
    const vec = await fake(input);
    return tf.tensor2d(Array.from(vec), [1, vec.length]);
  }
  const base = await ensureBase();
  return tf.tidy(() => {
    const img = tf.browser.fromPixels(input);
    return base.infer(img, true); // embedding=true → pre-logits 특징벡터
  });
}

async function buildHead(inputDim, numClasses) {
  const tf = await ensureTf();
  const model = tf.sequential();
  model.add(tf.layers.dense({ inputShape: [inputDim], units: 100, activation: 'relu' }));
  model.add(tf.layers.dense({ units: numClasses, activation: 'softmax' }));
  model.compile({ optimizer: tf.train.adam(0.001), loss: 'categoricalCrossentropy', metrics: ['accuracy'] });
  return model;
}

// samples: [{classIndex, embedding: tf.Tensor2D [1,D]}, ...]
async function trainHead(head, samples, numClasses, opts = {}) {
  const tf = await ensureTf();
  const xs = tf.concat(samples.map((s) => s.embedding), 0);
  const ys = tf.oneHot(tf.tensor1d(samples.map((s) => s.classIndex), 'int32'), numClasses);
  try {
    return await head.fit(xs, ys, {
      epochs: opts.epochs || 20,
      batchSize: Math.min(opts.batchSize || 16, samples.length),
      shuffle: true,
      callbacks: opts.onEpoch ? { onEpochEnd: (e, logs) => opts.onEpoch(e, logs) } : undefined,
    });
  } finally {
    xs.dispose();
    ys.dispose();
  }
}

// embedding [1,D] -> {index, label, confidence, all}
async function predictTop(head, embedding, labels) {
  const logits = head.predict(embedding);
  const data = await logits.data();
  logits.dispose();
  let best = 0;
  for (let i = 1; i < data.length; i++) if (data[i] > data[best]) best = i;
  return { index: best, label: labels[best], confidence: data[best], all: Array.from(data) };
}

// {head, labels, imageSize?, base?} -> blockpy-tm-v1 JSON 문자열
async function serializeModel({ head, labels, imageSize = IMAGE_SIZE, base = BASE_ID }) {
  const tf = await ensureTf();
  let captured = null;
  await head.save(tf.io.withSaveHandler(async (artifacts) => {
    captured = artifacts;
    return { modelArtifactsInfo: { dateSaved: new Date(), modelTopologyType: 'JSON' } };
  }));
  return packEnvelope({
    labels,
    imageSize,
    base,
    artifacts: {
      modelTopology: captured.modelTopology,
      weightSpecs: captured.weightSpecs,
      weightData: captured.weightData,
    },
  });
}

// blockpy-tm-v1 JSON -> {head, labels, imageSize, base}
async function deserializeModel(jsonString) {
  const tf = await ensureTf();
  const { labels, imageSize, base, artifacts } = unpackEnvelope(jsonString);
  const head = await tf.loadLayersModel(tf.io.fromMemory({
    modelTopology: artifacts.modelTopology,
    weightSpecs: artifacts.weightSpecs,
    weightData: artifacts.weightData,
  }));
  return { head, labels, imageSize, base };
}

const api = {
  ensureTf, featurize, buildHead, trainHead, predictTop, serializeModel, deserializeModel, IMAGE_SIZE, BASE_ID,
};
if (typeof window !== 'undefined') window.BlockPyTM = api;

export { ensureTf, featurize, buildHead, trainHead, predictTop, serializeModel, deserializeModel, IMAGE_SIZE, BASE_ID };
```

- [ ] **Step 4: teachable.js 를 앱 로드시 평가되도록 import (window.BlockPyTM 노출)**

`tests/tm_core.spec.js` 는 UI 없이 `window.BlockPyTM` 을 쓰므로, teachable.js 모듈이 앱 로드 때 평가되어야 한다. Task 5 에서 `src/App.jsx` 가 `TeachableMachine.jsx`(→ teachable.js) 를 static import 하면 충족되지만, Task 3 를 독립 검증하기 위해 `src/main.jsx` 에 side-effect import 를 추가한다.

`src/main.jsx` 를 열어 기존 `import './utils/*.js'` side-effect import 들이 모여 있는 곳 **맨 아래**에 한 줄 추가:
```js
import './utils/teachable.js'; // window.BlockPyTM (Teachable Machine) 노출
```
(정확한 위치: 다른 `import './utils/...'` 줄들 바로 다음. 없으면 마지막 import 문 뒤.)

- [ ] **Step 5: 통합 테스트 통과 확인**

Run:
```bash
PORT=3100 npx playwright test tests/tm_core.spec.js
```
Expected: PASS — 1 test. (tf.js 청크가 동적 로드되며 head 학습/직렬화/역직렬화 왕복 성공. MobileNet 은 로드하지 않음.)

- [ ] **Step 6: Commit**

```bash
git add src/utils/teachable.js src/main.jsx tests/tm_core.spec.js
git commit -m "feat(tm): TF.js/MobileNet 래퍼(teachable) + 학습·직렬화 통합 테스트"
```

---

### Task 4: `TeachableMachine.jsx` UI 패널

**Files:**
- Create: `src/components/TeachableMachine.jsx`

**Interfaces:**
- Consumes: `teachable.js` (`featurize`, `buildHead`, `trainHead`, `predictTop`, `serializeModel`).
- Produces: `export default function TeachableMachine()` — props 없음. 안정적 DOM id:
  - `#tm-status`, `#tm-classes`, `#tm-class-0`/`#tm-class-1`(+동적), `#tm-classname-<i>`(이름 입력), `#tm-count-<i>`(샘플 수), `#tm-capture-<i>`(수집 버튼), `#tm-add-class`, `#tm-webcam-wrap`, `#tm-train`, `#tm-trained`, `#tm-preview-label`, `#tm-filename`, `#tm-save`, `#tm-save-status`, `#tm-cam-error`.

> 이 태스크는 Task 5(App 탭 연결 + UI 흐름 테스트)와 함께 검증된다. 여기서는 컴포넌트만 만들고, App 배선/테스트는 Task 5 에서 한다.

- [ ] **Step 1: `src/components/TeachableMachine.jsx` 작성**

```jsx
import React, { useState, useRef, useEffect, useCallback } from 'react';
import { featurize, buildHead, trainHead, predictTop, serializeModel } from '../utils/teachable';

// Teachable Machine 패널 (TM 탭). 프론트 전용.
//  idle → collecting(클래스별 웹캠 샘플 수집) → trained(라이브 미리보기) → 저장.
//  MobileNet 임베딩 + 작은 dense head 학습. 저장은 <이름>.json (blockpy-tm-v1) → /api/fs/file.
//  블록/파이썬 연동 없음(후속 단계).

const CAPTURE_MS = 100; // 누르는 동안 프레임 캡처 간격

export default function TeachableMachine() {
  const [classes, setClasses] = useState([
    { name: '클래스 1', samples: [] }, // samples: tf.Tensor2D [1,D]
    { name: '클래스 2', samples: [] },
  ]);
  const [mode, setMode] = useState('idle');        // 'idle' | 'collecting' | 'training' | 'trained'
  const [capturingIdx, setCapturingIdx] = useState(-1);
  const [status, setStatus] = useState('클래스별로 웹캠 샘플을 모은 뒤 학습하세요.');
  const [camError, setCamError] = useState('');
  const [preview, setPreview] = useState(null);    // {label, confidence}
  const [filename, setFilename] = useState('my-model');
  const [saveStatus, setSaveStatus] = useState('');
  const [trainedInfo, setTrainedInfo] = useState(null); // {epochs}

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const headRef = useRef(null);
  const captureTimer = useRef(null);
  const previewRAF = useRef(null);

  const camActive = mode === 'collecting' || mode === 'trained';

  // ── 웹캠: 수집/미리보기 중에만 켠다 ──
  useEffect(() => {
    let cancelled = false;
    if (!camActive) return undefined;
    setCamError('');
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setCamError('이 환경에서 카메라를 쓸 수 없습니다(getUserMedia 미지원).');
      return undefined;
    }
    navigator.mediaDevices.getUserMedia({ video: true })
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => {});
        }
      })
      .catch(() => { if (!cancelled) setCamError('카메라를 열 수 없습니다(권한 거부 또는 장치 없음).'); });
    return () => {
      cancelled = true;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
    };
  }, [camActive]);

  // ── 한 프레임 → 임베딩 → 해당 클래스에 추가 ──
  const captureOne = useCallback(async (idx) => {
    const vid = videoRef.current;
    if (!vid || !vid.videoWidth) return;
    try {
      const emb = await featurize(vid);
      setClasses((prev) => {
        const next = prev.map((c, i) => (i === idx ? { ...c, samples: [...c.samples, emb] } : c));
        return next;
      });
    } catch (e) {
      setCamError(e.message || '샘플 수집 실패');
    }
  }, []);

  const startCapture = useCallback((idx) => {
    if (mode === 'idle') setMode('collecting');
    setCapturingIdx(idx);
    captureOne(idx);
    captureTimer.current = setInterval(() => captureOne(idx), CAPTURE_MS);
  }, [mode, captureOne]);

  const stopCapture = useCallback(() => {
    if (captureTimer.current) { clearInterval(captureTimer.current); captureTimer.current = null; }
    setCapturingIdx(-1);
  }, []);

  const addClass = useCallback(() => {
    setClasses((prev) => [...prev, { name: `클래스 ${prev.length + 1}`, samples: [] }]);
  }, []);

  const renameClass = useCallback((idx, name) => {
    setClasses((prev) => prev.map((c, i) => (i === idx ? { ...c, name } : c)));
  }, []);

  // ── 학습 ──
  const canTrain = classes.length >= 2 && classes.every((c) => c.samples.length > 0);

  const train = useCallback(async () => {
    if (!canTrain) { setStatus('클래스가 2개 이상이고, 각 클래스에 샘플이 1개 이상 있어야 학습할 수 있습니다.'); return; }
    stopCapture();
    setMode('training');
    setStatus('학습 중…');
    try {
      const inputDim = classes[0].samples[0].shape[1];
      const head = await buildHead(inputDim, classes.length);
      const samples = classes.flatMap((c, ci) => c.samples.map((embedding) => ({ classIndex: ci, embedding })));
      const epochs = 20;
      await trainHead(head, samples, classes.length, {
        epochs,
        onEpoch: (e) => setStatus(`학습 중… epoch ${e + 1}/${epochs}`),
      });
      headRef.current = head;
      setTrainedInfo({ epochs });
      setMode('trained');
      setStatus('학습 완료 — 카메라로 실시간 예측을 확인하세요.');
    } catch (e) {
      setMode('idle');
      setStatus('학습 실패: ' + (e.message || e));
    }
  }, [canTrain, classes, stopCapture]);

  // ── 라이브 미리보기 루프 (trained 동안) ──
  useEffect(() => {
    if (mode !== 'trained' || !headRef.current) return undefined;
    let stop = false;
    const labels = classes.map((c) => c.name);
    const tick = async () => {
      if (stop) return;
      const vid = videoRef.current;
      if (vid && vid.videoWidth) {
        try {
          const emb = await featurize(vid);
          const p = await predictTop(headRef.current, emb, labels);
          emb.dispose();
          if (!stop) setPreview({ label: p.label, confidence: p.confidence });
        } catch (_) { /* 프레임 스킵 */ }
      }
      previewRAF.current = setTimeout(tick, 250);
    };
    tick();
    return () => { stop = true; if (previewRAF.current) clearTimeout(previewRAF.current); };
  }, [mode, classes]);

  // ── 저장: <이름>.json → /api/fs/file, 실패 시 브라우저 다운로드 폴백 ──
  const save = useCallback(async () => {
    if (!headRef.current) { setSaveStatus('먼저 학습을 완료하세요.'); return; }
    const cleaned = String(filename || '').trim().replace(/\.json$/i, '');
    if (!cleaned) { setSaveStatus('파일 이름을 입력하세요.'); return; }
    const fname = cleaned + '.json';
    setSaveStatus('저장 중…');
    try {
      const json = await serializeModel({ head: headRef.current, labels: classes.map((c) => c.name) });
      try {
        const r = await fetch('/api/fs/file', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: fname, content: json }),
        });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        setSaveStatus(`저장됨: ${fname} (워크스페이스)`);
      } catch (backendErr) {
        // 백엔드 미가동 → 브라우저 다운로드 폴백
        const blob = new Blob([json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = fname; a.click();
        URL.revokeObjectURL(url);
        setSaveStatus(`다운로드됨: ${fname} (백엔드 미가동 — 폴백)`);
      }
    } catch (e) {
      setSaveStatus('저장 실패: ' + (e.message || e));
    }
  }, [filename, classes]);

  return (
    <div className="tm-panel" style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontWeight: 600 }}>Teachable Machine</div>
      <div id="tm-status" style={{ fontSize: 13, opacity: 0.85 }}>{status}</div>

      {/* 웹캠 미리보기 */}
      {camError ? (
        <div id="tm-cam-error" style={{ color: '#c0392b', fontSize: 13 }}>{camError}</div>
      ) : (
        <div
          id="tm-webcam-wrap"
          style={{ position: 'relative', width: '100%', maxWidth: 320, aspectRatio: '4 / 3', background: '#000', borderRadius: 6, overflow: 'hidden', display: camActive ? 'block' : 'none' }}
        >
          <video ref={videoRef} muted playsInline style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }} />
          {mode === 'trained' && preview && (
            <div id="tm-preview-overlay" style={{ position: 'absolute', left: 8, bottom: 8, background: 'rgba(0,0,0,0.6)', color: '#fff', padding: '4px 8px', borderRadius: 6, fontSize: 13 }}>
              <span id="tm-preview-label">{preview.label}</span> · {(preview.confidence * 100).toFixed(0)}%
            </div>
          )}
        </div>
      )}

      {/* 클래스 목록 */}
      <div id="tm-classes" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {classes.map((c, i) => (
          <div id={`tm-class-${i}`} key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <input
              id={`tm-classname-${i}`}
              value={c.name}
              onChange={(e) => renameClass(i, e.target.value)}
              style={{ flex: '1 1 100px', minWidth: 80 }}
            />
            <span id={`tm-count-${i}`} style={{ fontSize: 12, opacity: 0.7, minWidth: 48 }}>샘플 {c.samples.length}</span>
            <button
              id={`tm-capture-${i}`}
              className="btn btn-secondary btn-sm"
              onMouseDown={() => startCapture(i)}
              onMouseUp={stopCapture}
              onMouseLeave={() => { if (capturingIdx === i) stopCapture(); }}
              disabled={mode === 'training'}
            >
              {capturingIdx === i ? '수집 중…' : '누르는 동안 수집'}
            </button>
          </div>
        ))}
        <button id="tm-add-class" className="btn btn-secondary btn-sm" onClick={addClass} disabled={mode === 'training'}>
          <i className="fa-solid fa-plus"></i> 클래스 추가
        </button>
      </div>

      {/* 학습 */}
      <button id="tm-train" className="btn btn-primary btn-sm" onClick={train} disabled={!canTrain || mode === 'training'}>
        {mode === 'training' ? '학습 중…' : '학습'}
      </button>

      {/* 학습 완료 + 저장 */}
      {mode === 'trained' && (
        <div id="tm-trained" style={{ display: 'flex', flexDirection: 'column', gap: 8, borderTop: '1px solid rgba(0,0,0,0.08)', paddingTop: 8 }}>
          <div style={{ fontSize: 13, color: '#166534' }}>학습 완료 (epoch {trainedInfo ? trainedInfo.epochs : ''})</div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <input id="tm-filename" value={filename} onChange={(e) => setFilename(e.target.value)} placeholder="모델 파일 이름" style={{ flex: '1 1 120px', minWidth: 100 }} />
            <span style={{ fontSize: 12, opacity: 0.6 }}>.json</span>
            <button id="tm-save" className="btn btn-primary btn-sm" onClick={save}>저장</button>
          </div>
          {saveStatus && <div id="tm-save-status" style={{ fontSize: 13 }}>{saveStatus}</div>}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: 빌드가 깨지지 않는지 확인(구문/import 검증)**

Run:
```bash
cd "C:/Users/user/busan-robotics/플랫폼개발/blockly프로젝트"
npx vite build
```
Expected: 빌드 성공(에러 없음). tf.js 는 별도 청크로 분리(동적 import). 경고(청크 크기) 는 무방.

- [ ] **Step 3: Commit**

```bash
git add src/components/TeachableMachine.jsx
git commit -m "feat(tm): Teachable Machine UI 패널(수집·학습·미리보기·저장)"
```

---

### Task 5: App.jsx TM 탭 연결 + 전체 UI 흐름 테스트

**Files:**
- Modify: `src/App.jsx` (import + 탭 버튼 + 패널)
- Create: `tests/tm_ui.spec.js`

**Interfaces:**
- Consumes: `TeachableMachine` (Task 4), teachable.js 의 `window.__TM_TEST_FEATURIZER` 훅.
- Produces: 좌패널 새 탭 `#tab-btn-tm` (activeAuxTab === 'tm').

- [ ] **Step 1: 실패하는 UI 흐름 테스트 작성 — `tests/tm_ui.spec.js`**

```js
const { test, expect } = require('@playwright/test');

// TM 전체 UI 흐름. 실제 MobileNet/카메라 없이:
//  - featurize 는 가짜(window.__TM_TEST_FEATURIZER) → 고정 4차원 벡터
//  - 카메라는 Chromium 가짜 미디어스트림
//  - 저장 /api/fs/file 은 라우트 목으로 200 처리(백엔드 불필요)
// 검증: TM 탭 → 클래스 2개 → 각 샘플 수집 → 학습 → 미리보기 라벨 → 파일명 저장 성공.
test.use({
  launchOptions: {
    args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
  },
});

test.describe('Teachable Machine UI', () => {
  test('탭 → 샘플 수집 → 학습 → 미리보기 → 저장', async ({ page }) => {
    await page.addInitScript(() => {
      // MobileNet 대체: 어떤 입력이든 고정 4차원 벡터 반환(흐름 검증용).
      window.__TM_TEST_FEATURIZER = () => [0.11, 0.22, 0.33, 0.44];
    });
    // 저장 백엔드 목
    await page.route('**/api/fs/file', (route) => {
      if (route.request().method() === 'POST') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, path: 'my-model.json' }) });
      }
      return route.continue();
    });

    await page.goto('/');
    await page.locator('#tab-btn-tm').click();

    await expect(page.locator('#tm-class-0')).toBeVisible();
    await expect(page.locator('#tm-class-1')).toBeVisible();

    // 각 클래스 샘플 수집: capture 버튼 누른 채로 잠깐 대기 → 놓기
    for (const idx of [0, 1]) {
      const btn = page.locator(`#tm-capture-${idx}`);
      await btn.hover();
      await page.mouse.down();
      await page.waitForTimeout(450); // CAPTURE_MS=100 → 최소 4프레임
      await page.mouse.up();
      await expect.poll(async () => {
        const txt = await page.locator(`#tm-count-${idx}`).textContent();
        return Number((txt || '').replace(/[^0-9]/g, '')) || 0;
      }, { timeout: 10000 }).toBeGreaterThanOrEqual(1);
    }

    // 학습
    await page.locator('#tm-train').click();
    await expect(page.locator('#tm-trained')).toBeVisible({ timeout: 30000 });

    // 라이브 미리보기 라벨(두 클래스 중 하나)
    await expect(page.locator('#tm-preview-label')).toHaveText(/클래스 1|클래스 2/, { timeout: 15000 });

    // 저장
    await page.locator('#tm-filename').fill('my-model');
    await page.locator('#tm-save').click();
    await expect(page.locator('#tm-save-status')).toContainText('my-model.json', { timeout: 15000 });
  });
});
```

- [ ] **Step 2: 테스트 실패 확인**

Run:
```bash
cd "C:/Users/user/busan-robotics/플랫폼개발/blockly프로젝트"
PORT=3100 npx playwright test tests/tm_ui.spec.js
```
Expected: FAIL — `#tab-btn-tm` 로케이터 없음(아직 App 미배선).

- [ ] **Step 3: `src/App.jsx` 에 import 추가**

`src/App.jsx:10` 의 `import RobotCalibrate from './components/RobotCalibrate';` **바로 다음 줄**에 추가:
```jsx
import TeachableMachine from './components/TeachableMachine';
```

- [ ] **Step 4: TM 탭 버튼 추가**

`src/App.jsx` 의 Robot 탭 버튼 블록(아래) 바로 뒤, 그리고 탭 목록을 닫는 `</div>` 앞에 TM 버튼을 넣는다.

찾을 기존 코드:
```jsx
              <button
                id="tab-btn-robot"
                className={`tab-btn ${activeAuxTab === 'robot' ? 'active' : ''}`}
                onClick={() => setActiveAuxTab('robot')}
              >
                Robot
              </button>
            </div>
```
교체 후:
```jsx
              <button
                id="tab-btn-robot"
                className={`tab-btn ${activeAuxTab === 'robot' ? 'active' : ''}`}
                onClick={() => setActiveAuxTab('robot')}
              >
                Robot
              </button>
              <button
                id="tab-btn-tm"
                className={`tab-btn ${activeAuxTab === 'tm' ? 'active' : ''}`}
                onClick={() => setActiveAuxTab('tm')}
              >
                TM
              </button>
            </div>
```

- [ ] **Step 5: TM 패널 추가**

`src/App.jsx` 의 Robot 패널 블록(아래) 바로 뒤에 TM 패널을 넣는다.

찾을 기존 코드:
```jsx
              {activeAuxTab === 'robot' && (
                <div className="robot-tab-scroll" style={{ overflowY: 'auto', height: '100%' }}>
                  <RobotConnect />
                  <RobotCalibrate />
                </div>
              )}
```
교체 후:
```jsx
              {activeAuxTab === 'robot' && (
                <div className="robot-tab-scroll" style={{ overflowY: 'auto', height: '100%' }}>
                  <RobotConnect />
                  <RobotCalibrate />
                </div>
              )}
              {activeAuxTab === 'tm' && (
                <div className="tm-tab-scroll" style={{ overflowY: 'auto', height: '100%' }}>
                  <TeachableMachine />
                </div>
              )}
```

- [ ] **Step 6: UI 흐름 테스트 통과 확인**

Run:
```bash
PORT=3100 npx playwright test tests/tm_ui.spec.js
```
Expected: PASS — 1 test. (가짜 카메라·가짜 featurizer·목 백엔드로 수집→학습→미리보기→저장까지 성공.)

- [ ] **Step 7: 회귀 확인 — 기존 IR 게이트가 여전히 통과**

Run:
```bash
PORT=3100 npx playwright test tests/ir_toolbox.spec.js tests/ir_coverage.spec.js
```
Expected: PASS — TM 추가가 블록/변환 코어에 영향 없음 확인.

- [ ] **Step 8: Commit**

```bash
git add src/App.jsx tests/tm_ui.spec.js
git commit -m "feat(tm): App 좌패널 TM 탭 연결 + 전체 UI 흐름 테스트"
git tag tm-inapp
```

---

## Self-Review

**1. Spec coverage** (design spec: `DOCS/superpowers/specs/2026-07-16-teachable-machine-design.md`):
- 목표(학습→미리보기→파일명 저장): Task 4(UI)+Task 5(흐름). ✔
- TF.js + MobileNet 전이학습: Task 1(deps)+Task 3(featurize/head). ✔
- 오프라인 vendored MobileNet + vendor 스크립트: Task 1. ✔
- 동작 흐름 1~5(로드→수집→train→미리보기→저장): Task 4 상태기계. ✔
- 저장 형식 blockpy-tm-v1(head만): Task 2(tmPack)+Task 3(serializeModel). ✔
- 컴포넌트/파일 목록(TeachableMachine.jsx, teachable.js, vendor-assets.cjs, package.json, App.jsx): 모두 태스크 존재. 단, spec 은 `teachable.js` 안에 직렬화까지 포함했으나 순수 로직을 `tmPack.js` 로 분리(테스트 용이, 관례). ✔(개선)
- 에러 처리(웹캠 없음/거부, MobileNet 로드 실패, 클래스<2/샘플0, 저장 실패 폴백): Task 3(ensureBase throw)+Task 4(camError, canTrain, 다운로드 폴백). ✔
- 테스트(pack/unpack 단위 + Playwright 테스트모드 featurizer): Task 2(Node)+Task 3(core)+Task 5(UI). ✔
- 범위 밖(블록/파이썬 연동, 추론 소비, .h5): 계획에 없음. ✔

**2. Placeholder scan:** "TBD/TODO/적절히" 없음. 모든 코드 스텝에 완전한 코드 포함. ✔

**3. Type consistency:**
- `packEnvelope`/`unpackEnvelope` 인자·반환 형태가 Task 2 정의와 Task 3 `serializeModel`/`deserializeModel` 사용처에서 일치(`artifacts.{modelTopology,weightSpecs,weightData}`). ✔
- `trainHead(head, samples, numClasses, opts)` 시그니처가 Task 3 정의와 Task 4 호출에서 일치. samples 원소 `{classIndex, embedding}` 일치. ✔
- `predictTop` 반환 `{index,label,confidence,all}` — Task 4 는 `.label`/`.confidence` 만 사용. ✔
- `buildHead(inputDim, numClasses)` — Task 4 는 `classes[0].samples[0].shape[1]` 로 inputDim 산출. ✔
- DOM id (`#tm-*`) 가 Task 4 렌더와 Task 5 테스트에서 일치. ✔

이슈 없음.

---

## 주의 / 리스크 노트

- **MobileNet 다운로드 URL**: `storage.googleapis.com/tfjs-models/tfjs/mobilenet_v2_1.0_224/model.json` 는 널리 쓰이는 안정 경로다. 만약 404 면 설치된 `@tensorflow-models/mobilenet` 소스에서 현재 `BASE_PATH`/버전 경로를 확인해 URL 만 바꾼다(로직 동일).
- **tf.js 헤드리스 백엔드**: Playwright(Chromium)에서 WebGL 미가용 시 CPU 백엔드로 자동 폴백 — 소형 head 학습은 수십 ms. 문제되면 core/ui 테스트 상단에서 `await tf.setBackend('cpu')` 를 고려(현재 불필요 예상).
- **번들 크기**: tf.js 는 동적 import 로 별도 청크 → 메인 앱/변환 경로 성능 영향 없음. TM 탭을 처음 열 때만 로드.
- **테스트 실행 위치**: 명령은 Git Bash(Bash 도구) 기준. PowerShell 이면 `PORT=3100 npx ...` 대신 `$env:PORT=3100; npx ...`.

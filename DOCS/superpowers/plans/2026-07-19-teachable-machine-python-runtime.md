# Teachable Machine 파이썬 런타임 + 고정 블록 (옵션 B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** `tm` 파이썬 모듈이 파이썬 안에서 이미지 분류기를 수집·학습·추론(MobileNet 특징 + 소형 keras head)하고, 그 API를 마운트 시 builtin으로 등록되는 "tm" 토크박스 블록으로 제공한다. 블록 → 실제 파이썬 실행 → dobotkit 제어.

**Architecture:** ① `runtime/tm.py`(Model 클래스 + load_model + featurizer) ② tm 고정 블록(`src/data/tmSpecs.json` + App `bundledSpecs`, dobotkit와 동일 패턴). 학습·추론이 같은 파이썬 featurizer라 자기일관 — 패리티/변환 불필요. 변환 코어 불변.

**Tech Stack:** Python(tensorflow 2.21 / numpy 2.4, 확인됨) · Node(gen script) · React/Vite · Playwright · 기존 `BlockPyLibRegistry`/`BlockPyLibImport`.

## Global Constraints

- **변환 코어 불변:** `irToBlockly.js`/`blocklyToIr.js`/`irBlocks.js` 수정 금지.
- **기존 번들 불변:** `stdlibSpecs.json`/`robotSpecs.json`/`gen-*` 수정 금지. tm은 별도 `tmSpecs.json`.
- **TM 패널/브라우저 학습 불변:** `TeachableMachine.jsx`/`teachable.js`/`tmPack.js` 읽기만.
- **no hardcoded recognition tables** · **무손실 라운드트립**(ast.dump 동치) · **불필요 파일 손대지 않기.**
- 블록 lower(검증필): `tm.Model(labels)` · `model.add_example(frame,label)`(명령) · `model.train()`(명령) · `model.predict(frame)`(값) · `model.predict_proba(frame)`(값) · `model.save(path)`(명령) · `model.labels`(값 속성) · `tm.load_model(path)`(값). 수신자 변수 `model`.
- featurizer: keras MobileNetV2(alpha1.0, include_top=False, pooling='avg') + preprocess_input((x/127.5)−1), frame 224 리사이즈, BGR(cv2)→RGB. head: dense(100,relu)→dense(N,softmax), adam, sparse-CE.

## File Structure

- **Create** `runtime/tm.py` — Model(add_example/train/predict/predict_proba/labels/save) + load_model + `_embed` featurizer + friendly 오류.
- **Create** `runtime/tm_test.py` — stdlib unittest(학습→예측, save/load, 오류 경로).
- **Create** `scripts/gen-tm-blocks.cjs`, `src/data/tmSpecs.json`(생성물).
- **Create** `tests/tm_blocks.spec.js` — node lower + 브라우저 카테고리/round-trip + PYTHONPATH import.
- **Modify** `server.js` — `RUNTIME_DIR` 상수 + `/api/run-python` spawn env에 `PYTHONPATH`.
- **Modify** `src/App.jsx` — `bundledSpecs`에 `tmSpecs` 추가(+import).

---

### Task 1: `runtime/tm.py` 런타임 + 파이썬 단위 테스트

**Files:** Create `runtime/tm.py`, `runtime/tm_test.py`.

**Interfaces (Produces):** `tm.Model(labels)`, `Model.add_example(frame,label)`, `Model.train(epochs=30)`, `Model.predict(frame)->(str,float)`, `Model.predict_proba(frame)->dict`, `Model.labels`(property), `Model.save(path)`, `tm.load_model(path)->Model`. `frame`=numpy uint8 (H,W,3).

- [ ] **Step 1: 실패 테스트 작성** — `runtime/tm_test.py`

```python
import os, sys, tempfile, unittest
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tm

rng = np.random.default_rng(0)
def frames(channel, n):
    a = np.zeros((n, 224, 224, 3), np.uint8); a[..., channel] = 200
    return np.clip(a + rng.integers(-30, 30, (n, 224, 224, 3)), 0, 255).astype(np.uint8)

class TMTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.red = frames(2, 6)   # BGR ch2 = red after BGR->RGB flip
        cls.blue = frames(0, 6)
        cls.model = tm.Model(["red", "blue"])
        for f in cls.red: cls.model.add_example(f, "red")
        for f in cls.blue: cls.model.add_example(f, "blue")
        cls.model.train(epochs=30)

    def test_predict_holdout(self):
        for f in frames(2, 3): self.assertEqual(self.model.predict(f)[0], "red")
        for f in frames(0, 3): self.assertEqual(self.model.predict(f)[0], "blue")

    def test_predict_proba_and_labels(self):
        p = self.model.predict_proba(self.red[0])
        self.assertEqual(set(p.keys()), {"red", "blue"})
        self.assertAlmostEqual(sum(p.values()), 1.0, places=3)
        self.assertEqual(self.model.labels, ["red", "blue"])

    def test_save_load_roundtrip(self):
        d = tempfile.mkdtemp(); path = os.path.join(d, "m.npz")
        self.model.save(path)
        m2 = tm.load_model(path)
        self.assertEqual(m2.labels, ["red", "blue"])
        self.assertEqual(m2.predict(frames(2, 1)[0])[0], "red")

    def test_errors(self):
        with self.assertRaises(ValueError): tm.Model(["only"])            # <2 classes
        m = tm.Model(["a", "b"])
        with self.assertRaises(ValueError): m.add_example(self.red[0], "z")  # unknown label
        with self.assertRaises(RuntimeError): m.predict(self.red[0])         # not trained
        m.add_example(self.red[0], "a")
        with self.assertRaises(RuntimeError): m.train()                      # class 'b' empty

if __name__ == "__main__":
    unittest.main(verbosity=2)
```

- [ ] **Step 2: 실행 → 실패 확인**

Run: `python runtime/tm_test.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'tm'`.

- [ ] **Step 3: `runtime/tm.py` 작성**

```python
"""tm — 파이썬 네이티브 Teachable Machine.

MobileNetV2(전이학습) 특징 + 소형 head(dense100-relu→denseN-softmax)를 파이썬 안에서 수집·학습·
추론한다. 브라우저 TM 패널과 같은 개념이나 전 과정 파이썬이라 자기일관적(크로스-환경 패리티 없음).
frame 은 numpy uint8 (H,W,3) 이미지(cv2 로 캡처, BGR). server.js 가 PYTHONPATH 로 실어 `import tm`.
의존성: tensorflow, numpy. tensorflow 미설치 시 friendly 오류로 degrade.
"""
import os
import numpy as np

_IMAGE_SIZE = 224
_base = None  # lazy MobileNet featurizer (프로세스당 1회)


def _ensure_tf():
    try:
        import tensorflow as tf
        return tf
    except ImportError as e:
        raise RuntimeError(
            "tm: tensorflow 가 필요합니다. `pip install tensorflow` 후 다시 실행하세요."
        ) from e


def _resolve_weights():
    # 번들 가중치(runtime/mobilenet_v2_weights.h5) 우선, 없으면 keras 'imagenet'(캐시/다운로드).
    here = os.path.dirname(os.path.abspath(__file__))
    bundled = os.path.join(here, "mobilenet_v2_weights.h5")
    return bundled if os.path.exists(bundled) else "imagenet"


def _ensure_base():
    global _base
    if _base is not None:
        return _base
    tf = _ensure_tf()
    from tensorflow.keras.applications import MobileNetV2
    _base = MobileNetV2(input_shape=(_IMAGE_SIZE, _IMAGE_SIZE, 3), alpha=1.0,
                        include_top=False, weights=_resolve_weights(), pooling="avg")
    return _base


def _embed(frame):
    """frame(numpy uint8 H,W,3, BGR) -> MobileNet 임베딩 [1,1280]."""
    tf = _ensure_tf()
    from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
    a = np.asarray(frame)
    if a.ndim != 3 or a.shape[2] != 3:
        raise ValueError("tm: frame 은 (H,W,3) numpy 이미지여야 합니다.")
    a = a[:, :, ::-1]  # cv2 BGR -> RGB
    img = tf.image.resize(tf.convert_to_tensor(a[np.newaxis].astype("float32")),
                          [_IMAGE_SIZE, _IMAGE_SIZE])
    x = preprocess_input(img)
    return np.asarray(_ensure_base().predict(x, verbose=0))


def _build_head(tf, dim, n):
    m = tf.keras.Sequential([
        tf.keras.layers.Input((dim,)),
        tf.keras.layers.Dense(100, activation="relu"),
        tf.keras.layers.Dense(n, activation="softmax"),
    ])
    m.compile(optimizer="adam", loss="sparse_categorical_crossentropy", metrics=["accuracy"])
    return m


class Model:
    def __init__(self, labels):
        if not isinstance(labels, (list, tuple)) or len(labels) < 2:
            raise ValueError("tm.Model: labels 는 2개 이상의 클래스 이름 리스트여야 합니다.")
        self._labels = [str(l) for l in labels]
        self._idx = {l: i for i, l in enumerate(self._labels)}
        self._X, self._y, self._head = [], [], None

    @property
    def labels(self):
        return list(self._labels)

    def add_example(self, frame, label):
        if label not in self._idx:
            raise ValueError(f"tm: 알 수 없는 라벨 {label!r} (labels={self._labels})")
        self._X.append(_embed(frame)[0])
        self._y.append(self._idx[label])

    def train(self, epochs=30):
        if not self._X:
            raise RuntimeError("tm: 학습할 예시가 없습니다. 먼저 add_example 로 수집하세요.")
        counts = np.bincount(self._y, minlength=len(self._labels))
        if (counts == 0).any():
            missing = [self._labels[i] for i in np.where(counts == 0)[0]]
            raise RuntimeError(f"tm: 각 클래스에 예시가 1개 이상 필요합니다. 부족: {missing}")
        tf = _ensure_tf()
        X = np.asarray(self._X, dtype="float32")
        y = np.asarray(self._y)
        self._head = _build_head(tf, X.shape[1], len(self._labels))
        self._head.fit(X, y, epochs=epochs, verbose=0)

    def _proba(self, frame):
        if self._head is None:
            raise RuntimeError("tm: 아직 학습되지 않았습니다. train() 을 먼저 호출하세요.")
        return np.asarray(self._head.predict(_embed(frame), verbose=0))[0]

    def predict(self, frame):
        p = self._proba(frame)
        i = int(np.argmax(p))
        return self._labels[i], float(p[i])

    def predict_proba(self, frame):
        p = self._proba(frame)
        return {l: float(p[i]) for i, l in enumerate(self._labels)}

    def save(self, path):
        if self._head is None:
            raise RuntimeError("tm: 학습 후 저장할 수 있습니다. train() 을 먼저 호출하세요.")
        W1, b1, W2, b2 = self._head.get_weights()
        np.savez(path, labels=np.array(self._labels, dtype=object), W1=W1, b1=b1, W2=W2, b2=b2)


def load_model(path):
    d = np.load(path, allow_pickle=True)
    labels = [str(l) for l in d["labels"]]
    tf = _ensure_tf()
    m = Model(labels)
    head = _build_head(tf, int(d["W1"].shape[0]), len(labels))
    head.set_weights([d["W1"], d["b1"], d["W2"], d["b2"]])
    m._head = head
    return m
```

- [ ] **Step 4: 실행 → 통과**

Run: `python runtime/tm_test.py`
Expected: PASS (4 tests, OK). (MobileNet 로드로 수십 초 소요 가능.)

- [ ] **Step 5: 커밋**

```bash
git add runtime/tm.py runtime/tm_test.py
git commit -m "feat(tm): 파이썬 네이티브 TM 런타임(runtime/tm.py) — MobileNet 특징+head 수집/학습/추론"
```

---

### Task 2: server.js PYTHONPATH 배선 + import 검증

**Files:** Modify `server.js`. Test: `tests/tm_blocks.spec.js`(node describe).

**Interfaces:** `/api/run-python` spawn env(server.js:620 근처)에 `PYTHONPATH`로 레포 `runtime/`를 실어 임의 워크스페이스에서 `import tm` 가능.

- [ ] **Step 1: 실패 테스트 작성** — `tests/tm_blocks.spec.js` 상단(node)

```javascript
const { test, expect } = require('@playwright/test');
const APP_URL = 'http://localhost:' + (process.env.PORT || '3000') + '/';
const path = require('path');
const { spawnSync } = require('child_process');

// tm 런타임이 PYTHONPATH(runtime/)로 import 되는지 — server.js 가 쓰는 것과 동일 메커니즘.
test.describe('tm runtime import via PYTHONPATH (node)', () => {
  test('import tm 성공(runtime/ 를 PYTHONPATH 에 실으면)', () => {
    const repo = path.join(__dirname, '..');
    const runtime = path.join(repo, 'runtime');
    const PY = process.env.PYTHON_CMD || 'python';
    const r = spawnSync(PY, ['-c', 'import tm; print("TMOK", hasattr(tm, "Model"), hasattr(tm, "load_model"))'], {
      env: { ...process.env, PYTHONPATH: [runtime, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter), PYTHONIOENCODING: 'utf-8' },
      encoding: 'utf-8',
    });
    expect(r.stdout || '').toContain('TMOK True True');
  });
});
```

- [ ] **Step 2: 실행 → 통과 확인(런타임은 Task 1에서 이미 존재)**

Run: `npx playwright test tests/tm_blocks.spec.js -g "import tm" --project=chromium`
Expected: PASS — Task 1의 `runtime/tm.py`가 PYTHONPATH로 import됨. (이 테스트는 메커니즘 증명; server.js 배선은 Step 3에서.)

- [ ] **Step 3: server.js — RUNTIME_DIR + run-python PYTHONPATH**

`WORKSPACE_DIR` 정의(45행) 근처에 상수 추가:

```javascript
const RUNTIME_DIR = path.join(__dirname, 'runtime');   // `import tm` 등 플랫폼 런타임 모듈
```

`/api/run-python` spawn(약 620행) env를 교체:

```javascript
    child = spawn(PYTHON_CMD, ['-u', file], {
      cwd: MEDIA_DIR, // so cv2.imread('name.jpg') finds uploaded/sample images
      env: {
        ...process.env,
        PYTHONIOENCODING: 'utf-8',
        PYTHONUNBUFFERED: '1',
        PYTHONPATH: [RUNTIME_DIR, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
      },
    });
```

- [ ] **Step 4: 배선 검증(백엔드 경유, 수동)**

`npm run server` 가동 상태에서:
```bash
curl -s -X POST http://127.0.0.1:3001/api/run-python -H 'Content-Type: application/json' \
  -d '{"code":"import tm\nprint(\"tm-ok\", hasattr(tm,\"Model\"))"}' | tail -3
```
Expected: 출력에 `tm-ok True`. (run-python 응답 형식에 맞춰 stdout 확인.)

- [ ] **Step 5: 커밋**

```bash
git add server.js tests/tm_blocks.spec.js
git commit -m "feat(tm): run-python 에 runtime/ PYTHONPATH 배선 → import tm 가능"
```

---

### Task 3: tm 고정 블록 (스펙 번들 + App 등록 + 검증)

**Files:** Create `scripts/gen-tm-blocks.cjs`, `src/data/tmSpecs.json`. Modify `src/App.jsx`. Test: `tests/tm_blocks.spec.js`(추가).

**Interfaces (검증필 매핑):** `lib_tm_Model`(값), `lib_model_add_example_stmt`(명령), `lib_model_train_stmt`(명령), `lib_model_predict`(값), `lib_model_predict_proba`(값), `lib_model_save_stmt`(명령), `lib_tm_load_model`(값), 속성 `model.labels`(owner Model). 전부 lib='tm' → "tm" 탭.

- [ ] **Step 1: gen script 작성** — `scripts/gen-tm-blocks.cjs`

```javascript
// Generate src/data/tmSpecs.json — 파이썬 네이티브 TM(runtime/tm.py) 의 tm 고정 블록 스펙.
// dobotkit(gen-robot-blocks.cjs)과 동일 패턴: 손으로 큐레이션한 LibrarySpec 를 마운트 시 builtin 등록.
// Re-generate with: node scripts/gen-tm-blocks.cjs
const fs = require('fs');
const path = require('path');

const P = (...n) => n.map((x) => ({ name: x, kind: 'positional', hasDefault: false }));
const cmd = (name, ...a) => ({ kind: 'method', owner: 'Model', name, params: P(...a), returns: false });
const val = (name, ...a) => ({ kind: 'method', owner: 'Model', name, params: P(...a), returns: true });

const spec = {
  module: 'tm',
  entries: [
    { kind: 'class', name: 'Model', qualName: 'tm.Model', params: P('labels'), returns: true }, // model = tm.Model([...])
    cmd('add_example', 'frame', 'label'),
    cmd('train'),
    val('predict', 'frame'),
    val('predict_proba', 'frame'),
    cmd('save', 'path'),
    { kind: 'property', owner: 'Model', name: 'labels', qualName: 'tm.Model.labels' },
    { kind: 'function', name: 'load_model', qualName: 'tm.load_model', params: P('path'), returns: true },
  ],
};

const dest = path.join(__dirname, '..', 'src', 'data', 'tmSpecs.json');
fs.mkdirSync(path.dirname(dest), { recursive: true });
fs.writeFileSync(dest, JSON.stringify([spec], null, 1));
console.log(`[tm] wrote tm spec (${spec.entries.length} entries) -> ${path.relative(path.join(__dirname, '..'), dest)}`);
```

- [ ] **Step 2: 생성 실행**

Run: `node scripts/gen-tm-blocks.cjs`
Expected: `[tm] wrote tm spec (8 entries) -> src/data/tmSpecs.json`

- [ ] **Step 3: 실패 테스트 작성** — `tests/tm_blocks.spec.js`에 추가(node lower + browser)

```javascript
// ── node lower ──
require('../src/utils/libRegistry.js');
require('../src/utils/libImport.js');
require('../src/utils/irToBlockly.js');
require('../src/utils/blocklyToIr.js');
const REG = global.BlockPyLibRegistry;
const IMP = global.BlockPyLibImport;
const IR = global.BlockPyIR;
let tmSpecs; try { tmSpecs = require('../src/data/tmSpecs.json'); } catch (_) { tmSpecs = null; }

test.describe('tm blocks lowering (node)', () => {
  test.beforeAll(() => {
    REG.clearAll();
    const tm = tmSpecs.find((m) => m.module === 'tm');
    const mapped = IMP.librarySpecToRegistrySpecs(tm, { both: false });
    for (const s of mapped.specs) REG.registerLibBlock({ ...s, builtin: true });
    for (const p of mapped.props) REG.registerProp({ ...p });
  });
  test.afterAll(() => REG.clearAll());

  test('tm.Model(labels) 값', () => {
    const ir = IR.blocklyToIr({ blocks: { blocks: [{ type: 'lib_tm_Model', inputs: {
      ARG0: { shadow: { type: 'ir_name', fields: { ID: 'labels' } } } } }] } });
    expect(ir.body[0].value).toMatchObject({ type: 'Call', func: { type: 'Attribute', attr: 'Model', value: { type: 'Name', id: 'tm' } } });
  });
  test('model.add_example(frame, label) 명령', () => {
    const ir = IR.blocklyToIr({ blocks: { blocks: [{ type: 'lib_model_add_example_stmt', inputs: {
      ARG0: { shadow: { type: 'ir_name', fields: { ID: 'model' } } },
      ARG1: { shadow: { type: 'ir_name', fields: { ID: 'frame' } } },
      ARG2: { shadow: { type: 'ir_name', fields: { ID: 'label' } } } } }] } });
    expect(ir.body[0]).toMatchObject({ type: 'Expr', value: { type: 'Call',
      func: { type: 'Attribute', attr: 'add_example', value: { type: 'Name', id: 'model' } },
      args: [{ type: 'Name', id: 'frame' }, { type: 'Name', id: 'label' }] } });
  });
  test('model.predict(frame) 값', () => {
    const ir = IR.blocklyToIr({ blocks: { blocks: [{ type: 'lib_model_predict', inputs: {
      ARG0: { shadow: { type: 'ir_name', fields: { ID: 'model' } } },
      ARG1: { shadow: { type: 'ir_name', fields: { ID: 'frame' } } } } }] } });
    expect(ir.body[0].value).toMatchObject({ type: 'Call', func: { type: 'Attribute', attr: 'predict', value: { type: 'Name', id: 'model' } } });
  });
  test('tm.load_model(path) 값', () => {
    const ir = IR.blocklyToIr({ blocks: { blocks: [{ type: 'lib_tm_load_model', inputs: {
      ARG0: { shadow: { type: 'ir_const', fields: { VALUE: '"m.npz"' } } } } }] } });
    expect(ir.body[0].value).toMatchObject({ type: 'Call', func: { type: 'Attribute', attr: 'load_model', value: { type: 'Name', id: 'tm' } }, args: [{ type: 'Constant', value: 'm.npz' }] });
  });
});

// ── browser: 마운트 카테고리 + 무손실 라운드트립 ──
test.describe('tm built-in blocks (browser)', () => {
  test('마운트 후 tm 카테고리와 대표 블록 존재(builtin)', async ({ page }) => {
    test.setTimeout(300000);
    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => window.__blocklyWorkspace && window.BlockPyLibRegistry && window.BlockPyBuildIrToolbox, null, { timeout: 180000 });
    const out = await page.evaluate(() => {
      const reg = window.BlockPyLibRegistry;
      const cat = window.BlockPyBuildIrToolbox().contents.find((c) => c.name === 'tm');
      const flat = cat ? JSON.stringify(cat.contents) : '';
      return {
        hasCat: !!cat,
        modelBuiltin: !!(reg.getLibSpec('lib_tm_Model') || {}).builtin,
        trainBuiltin: !!(reg.getLibSpec('lib_model_train_stmt') || {}).builtin,
        hasPredict: flat.includes('"method":"predict"'),
        hasModelFunc: flat.includes('tm.Model'),
        hasLoad: flat.includes('tm.load_model'),
      };
    });
    expect(out.hasCat).toBe(true);
    expect(out.modelBuiltin).toBe(true);
    expect(out.trainBuiltin).toBe(true);
    expect(out.hasPredict).toBe(true);
    expect(out.hasModelFunc).toBe(true);
    expect(out.hasLoad).toBe(true);
  });

  test('tm 프로그램이 무손실 라운드트립 (텍스트 동일)', async ({ page }) => {
    test.setTimeout(300000);
    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => window.BlockPyIR && window.BlockPyAstBridge, null, { timeout: 180000 });
    const out = await page.evaluate(async () => {
      const src = [
        'import tm',
        "model = tm.Model(['가위', '바위', '보'])",
        'model.add_example(frame, \'가위\')',
        'model.train()',
        'label, conf = model.predict(frame)',
        'print(model.labels)',
        "model.save('rps.npz')",
      ].join('\n');
      const py = await window.BlockPyAstBridge.getPyodide();
      const ir = await window.BlockPyAstBridge.pythonToIR(py, src);
      const back = (await window.BlockPyAstBridge.irToPython(py, ir)).trim();
      return { src: src.trim(), back };
    });
    expect(out.back).toBe(out.src);
  });
});
```

- [ ] **Step 4: 실행 → 브라우저 카테고리 테스트 실패 확인**

Run: `npx playwright test tests/tm_blocks.spec.js -g "tm blocks lowering|tm built-in" --project=chromium`
Expected: node lowering PASS(스펙 등록됨), browser 카테고리 FAIL(App 미배선), round-trip은 PASS 가능.

- [ ] **Step 5: App.jsx 배선** — import + bundledSpecs

`import robotSpecs ...`(15행) 다음에:
```javascript
import tmSpecs from './data/tmSpecs.json';
```
`bundledSpecs` 배열에 추가:
```javascript
      const bundledSpecs = [
        ...(Array.isArray(stdlibSpecs) ? stdlibSpecs : []),
        ...(Array.isArray(robotSpecs) ? robotSpecs : []),
        ...(Array.isArray(tmSpecs) ? tmSpecs : []),
      ];
```

- [ ] **Step 6: 실행 → 통과**

Run: `npx playwright test tests/tm_blocks.spec.js --project=chromium`
Expected: 전부 PASS.

- [ ] **Step 7: 회귀 + 커밋**

Run: `npx playwright test tests/ir_lib_blocks.spec.js tests/ir_toolbox.spec.js tests/robot_blocks.spec.js tests/tm_blocks.spec.js --project=chromium`
Expected: 모두 PASS(additive). 라이브러리 목록 하드코딩 테스트가 깨지면 tm 포함으로 갱신.
```bash
git add scripts/gen-tm-blocks.cjs src/data/tmSpecs.json src/App.jsx tests/tm_blocks.spec.js
git commit -m "feat(tm): tm 고정 블록(tmSpecs.json) + App 마운트 등록 + 검증"
```

---

## 최종 검증

- [ ] `python runtime/tm_test.py` (파이썬 런타임) + `npx playwright test tests/tm_blocks.spec.js` 통과.
- [ ] `npm run test:ir` 게이트: dobotkit 때와 동일하게 `ir_blockify_app`(백엔드 필요)만 사전존재 실패, 나머지 통과.
- [ ] 코어 무변경: `git diff --name-only feat/dobotkit-blocks..HEAD`에 `irToBlockly.js`/`blocklyToIr.js`/`irBlocks.js`/`libRegistry.js`/`libImport.js`/`irToolbox.js`/`stdlibSpecs.json`/`robotSpecs.json` 없어야 함.
- [ ] MobileNet 가중치 오프라인 전달(사전 캐시/번들)은 셋업 항목으로 문서화(README/셋업 노트).

## 롤백

작업 `feat/tm-runtime-blocks`(dobotkit 위 스택). 원복: `git checkout feat/dobotkit-blocks`(B만) / `git reset --hard robot-wiring`(A+B). 병합 시 태그 `tm-runtime`.

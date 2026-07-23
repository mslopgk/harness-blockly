# AI 도우미 그라운딩(워크스페이스 자동 시딩) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 터미널의 AI 에이전트가 플랫폼 목적·`tm`/`dobotkit` API·규칙을 자동으로 알도록, 백엔드가 워크스페이스에 `AGENTS.md`+`CLAUDE.md`+예제를 멱등 시딩하고 터미널 파이썬에서 `import tm`이 되게 배선한다.

**Architecture:** 리포 `agent-context/AGENTS.md` 템플릿을 `server.js`의 새 `seedAgentContext()`가 워크스페이스로 복사(없을 때만) + `CLAUDE.md`(`@AGENTS.md`) 생성 + `examples/` 복사. 터미널 PTY env의 PYTHONPATH에 `RUNTIME_DIR` 추가.

**Tech Stack:** Node/Express `server.js`, node --test.

## Global Constraints

- 변환 코어/스펙 데이터는 **수정하지 않는다**: `src/utils/irToBlockly.js`, `blocklyToIr.js`, `irBlocks.js`, `irToolbox.js`, `libRegistry.js`, `libImport.js`, `src/data/*.json`, `runtime/tm.py`. (테스트에서 `robotSpecs.json`/`tm.py`를 **읽기만** 한다.)
- **시딩은 멱등**: 대상 파일/예제가 이미 있으면 **절대 덮지 않는다**(사용자 편집·산출물 보존).
- **격리**: `seedAgentContext()` 실패가 서버 기동을 막으면 안 된다(try/catch + 로그). 기존 `seedStarterFile`/`seedSampleImages`와 동일.
- 서버는 127.0.0.1 전용 바인딩 유지(이 기능은 네트워크 노출을 바꾸지 않음).
- `AGENTS.md`의 API 목록은 **실제 시그니처와 일치**해야 한다(`runtime/tm.py`, `src/data/robotSpecs.json` 기준). 정합 스모크 테스트로 강제.
- DRY, YAGNI(자동생성 UI 없음), TDD, 잦은 커밋.

---

## File Structure

- **`agent-context/AGENTS.md`** (신규) — 시딩할 에이전트 컨텍스트 템플릿(플랫폼 목적·API·규칙·예제 안내).
- **`server.js`** (수정) — `seedAgentContext()` 추가 + `start()`에서 호출; `attachTerminal` env에 `RUNTIME_DIR` PYTHONPATH 추가; `module.exports`에 `seedAgentContext` 노출.
- **`package.json`** (수정) — `build.files`에 `agent-context/**/*`·`runtime/**/*` 추가, `build.asarUnpack`에 `runtime/**/*` 추가(패키징 앱의 외부 python 프로세스가 `runtime/tm.py`를 읽어 `import tm` 되도록).
- **`tests/agent_grounding.test.mjs`** (신규) — 시딩 멱등/내용 + API 정합 스모크(node --test).
- **`tests/ai_terminal.test.mjs`** (수정) — 터미널 PTY env에 `RUNTIME_DIR`이 PYTHONPATH로 실리는지 확인.

---

### Task 1: 그라운딩 콘텐츠 + seedAgentContext 시딩 + 패키징

**Files:**
- Create: `agent-context/AGENTS.md`
- Modify: `server.js` (`seedAgentContext()` ~seedStarterFile 부근; `start()` 호출부 ~line 947; exports ~line 910)
- Modify: `package.json` (`build.files`, `build.asarUnpack`)
- Create: `tests/agent_grounding.test.mjs`

**Interfaces:**
- Consumes: 기존 `WORKSPACE_DIR`(server.js:45), `STATIC_DIR`(server.js:30), `path`/`fs`, 리포 `public/examples/*.py`, `src/data/robotSpecs.json`, `runtime/tm.py`.
- Produces: `seedAgentContext()` (export). 시작 시 `WORKSPACE_DIR`에 `AGENTS.md`·`CLAUDE.md`·`examples/{5개}.py`를 멱등 생성.

- [ ] **Step 1: 실패 테스트 작성** — `tests/agent_grounding.test.mjs`

```js
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
```

- [ ] **Step 2: 실패 확인**

Run: `node --test tests/agent_grounding.test.mjs`
Expected: FAIL — `seedAgentContext`가 export 안 됨 + `agent-context/AGENTS.md` 없음.

- [ ] **Step 3: `agent-context/AGENTS.md` 작성** (전체 내용, 그대로)

```markdown
# BlockPy 프로젝트 — AI 도우미 안내 (AGENTS.md)

이 파일은 이 폴더에서 실행되는 AI 코딩 에이전트를 위한 안내다. 아래 규칙과 API를 지켜 코드를 작성하라.

## 이 플랫폼이 무엇인가
- 국립부산과학관 AI·로보틱스 커리큘럼용 **블록코딩 학습 플랫폼(BlockPy)**이다. 사용자는 학생/교사다.
- 핵심: 여기서 작성한 **파이썬 코드는 Blockly 시각 블록과 1:1 무손실로 변환**된다. 그래서 코드는
  블록으로 깔끔히 변환되도록 평이하게 쓴다.
- 편집기의 Run 버튼(과 이 터미널의 `python`)은 **실제 로컬 파이썬을 이 폴더에서 실행**한다.
  파일·이미지 경로는 이 폴더 기준이다.

## 쓸 수 있는 라이브러리 (이것들 + 파이썬 표준 라이브러리 + cv2/numpy 만)
**없는 함수·인자를 지어내지 마라.** 확실치 않으면 `python -c "import tm; help(tm.Model)"` 로 실제
시그니처를 확인하라. 아래가 정확한 목록이다.

### tm — 티처블머신(카메라로 배우는 이미지 분류; `import tm`)
- `m = tm.Model(labels)` — labels 는 2개 이상 클래스 이름 리스트. 예: `tm.Model(['가위','바위','보'])`
- `m.add_example(frame, label)` — frame 은 카메라 프레임(BGR ndarray, 예: cv2 프레임), label 은 labels 중 하나
- `m.train(epochs=30)` — 수집한 예시로 학습
- `m.predict(frame)` → `(label, confidence)` 튜플
- `m.predict_proba(frame)` → `{label: 확률}` 딕셔너리
- `m.labels` — 클래스 이름 리스트(속성)
- `m.save(path)` / `tm.load_model(path)` → Model — 학습된 모델 저장/불러오기

### dobotkit — 로봇(`import dobotkit`)
로봇팔 MagicianLite:
- `arm = dobotkit.MagicianLite()`
- `arm.home()` / `arm.move_to(x, y, z)` / `arm.move_relative(dx, dy, dz)`
- `arm.suck(on)` — 흡착(on=True/False) / `arm.grip(on)` — 그리퍼
- `arm.set_speed(velocity, acceleration)` / `arm.get_pose()`

주행로봇 MagicianGO:
- `from dobotkit import MagicianGO` → `car = MagicianGO.open('COM5')`
- `car.forward(speed)` / `car.backward(speed)` / `car.spin(speed)` / `car.strafe(speed)`
- `car.move(x, y, r)` / `car.drive_for(x, y, r, seconds)` / `car.stop()`
- `car.buzzer()` / `car.battery()` / `car.ultrasonic()` / `car.imu_angle()`

## 규칙
- 위 라이브러리 + 표준 라이브러리 + cv2/numpy 만 사용. 새 라이브러리 pip 설치를 요구하지 마라.
- 코드는 블록으로 변환되므로 **평이한 파이썬**으로 쓴다. `examples/` 폴더의 스타일을 따르라.
- 로봇팔을 쓰기 전 **DobotLink 프로그램이 실행 중**이어야 한다. 컨트롤러에 알람이 뜨면 모션이 막히고,
  **전원 리셋으로만** 풀린다(코드로 못 푼다).
- 학생 대상 수업 자료다. 생성형 AI 이미지 결과물을 코드/자료에 넣지 마라.

## 예제
`examples/` 폴더에 검증된 정답 예제가 있다:
- 중등(블록): `m1_ai_sorting.py`(색 분류 로봇팔), `m2_gesture_rps.py`(가위바위보)
- 고등(파이썬): `h1_nl_control.py`(자연어 제어), `h2_teleop.py`(제스처 원격조종), `h3_vision_drive.py`(비전 자율주행)
```

- [ ] **Step 4: `server.js`에 `seedAgentContext()` 추가** (`function seedStarterFile()` 정의 근처, 같은 스타일)

```js
// AGENTS.md/CLAUDE.md + examples 를 워크스페이스에 멱등 시딩 — 터미널의 AI 에이전트가
// 플랫폼 목적·API·규칙을 자동으로 읽게 한다. 없을 때만 쓰고 사용자 파일은 절대 안 덮는다.
function seedAgentContext() {
  try {
    // 1) AGENTS.md (리포 agent-context/ 템플릿 복사)
    const agentsSrc = path.join(__dirname, 'agent-context', 'AGENTS.md');
    const agentsDst = path.join(WORKSPACE_DIR, 'AGENTS.md');
    if (fs.existsSync(agentsSrc) && !fs.existsSync(agentsDst)) {
      fs.copyFileSync(agentsSrc, agentsDst);
    }
    // 2) CLAUDE.md — Claude Code 가 AGENTS.md 를 읽도록 @import 한 줄
    const claudeDst = path.join(WORKSPACE_DIR, 'CLAUDE.md');
    if (!fs.existsSync(claudeDst)) {
      fs.writeFileSync(claudeDst,
        '# CLAUDE.md\n이 폴더의 AI 도우미 안내는 AGENTS.md 를 따른다.\n@AGENTS.md\n', 'utf8');
    }
    // 3) 커리큘럼 예제 복사 (dev: public/examples, 패키징: dist/examples = STATIC_DIR/examples)
    const exSrc = (STATIC_DIR && fs.existsSync(path.join(STATIC_DIR, 'examples')))
      ? path.join(STATIC_DIR, 'examples')
      : path.join(__dirname, 'public', 'examples');
    const NAMES = ['m1_ai_sorting.py', 'm2_gesture_rps.py', 'h1_nl_control.py', 'h2_teleop.py', 'h3_vision_drive.py'];
    if (fs.existsSync(exSrc)) {
      const exDst = path.join(WORKSPACE_DIR, 'examples');
      fs.mkdirSync(exDst, { recursive: true });
      for (const n of NAMES) {
        const s = path.join(exSrc, n), d = path.join(exDst, n);
        if (fs.existsSync(s) && !fs.existsSync(d)) fs.copyFileSync(s, d);
      }
    }
  } catch (e) { console.log('[grounding] seed skipped:', e.message); }
}
```

- [ ] **Step 5: `start()`에서 호출 + export**

`start()`의 listen 콜백에서 `seedSampleImages(); seedStarterFile();` 다음 줄에 추가:
```js
      seedAgentContext();
```
파일 끝 `module.exports = { app, start };` 를 다음으로 교체:
```js
module.exports = { app, start, seedAgentContext };
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `node --test tests/agent_grounding.test.mjs`
Expected: PASS (2/2) — 시딩·멱등·API 정합.

- [ ] **Step 7: 패키징 config** — `package.json`

`build.files` 배열에 두 항목 추가(기존 항목 유지):
```json
      "agent-context/**/*",
      "runtime/**/*",
```
`build.asarUnpack` 배열에 추가(기존 항목 유지):
```json
      "runtime/**/*"
```
(이유: 패키징 앱에서 `import tm`은 **외부 python 프로세스**가 `runtime/tm.py`를 실제 파일시스템에서 읽어야 하므로 asar 밖으로 풀어야 한다. `agent-context`는 Node `fs`가 asar에서 읽어 복사하므로 `files`만으로 충분.)

- [ ] **Step 8: 커밋**

```bash
git add agent-context/AGENTS.md server.js package.json tests/agent_grounding.test.mjs
git commit -m "feat(grounding): 워크스페이스에 AGENTS.md/CLAUDE.md/예제 멱등 시딩 + 패키징"
```

---

### Task 2: 터미널 파이썬 import 배선 (RUNTIME_DIR)

**Files:**
- Modify: `server.js` (`attachTerminal`의 PTY spawn env — 주 셸 + Windows cmd.exe 폴백)
- Modify: `tests/ai_terminal.test.mjs` (터미널 PYTHONPATH 확인 테스트 추가)

**Interfaces:**
- Consumes: 기존 `RUNTIME_DIR`(server.js:54), `attachTerminal`의 `nodePty.spawn(... env ...)`.
- Produces: 터미널 PTY의 env PYTHONPATH에 `RUNTIME_DIR`이 선두 포함 → 터미널에서 `import tm` 가능.

- [ ] **Step 1: 실패 테스트 작성** — `tests/ai_terminal.test.mjs` 끝에 추가

```js
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
    ws.on('message', (d) => { acc += d.toString(); if (acc.includes('PYPATH::')) { clearTimeout(timer); resolve(acc); } });
    ws.on('error', (e) => { clearTimeout(timer); reject(e); });
  });
  const line = buf.split(/\r?\n/).find((l) => l.includes('PYPATH::')) || '';
  assert.ok(/runtime/i.test(line), `terminal PYTHONPATH should contain runtime dir; got: ${line}`);
  ws.close();
});
```
(주: 파일 상단 import에 `fs`/`os`/`path`가 이미 있어야 한다 — 기존 첫 테스트가 `fs.mkdtempSync` 등을 쓰므로 이미 존재. 없으면 `import fs from 'node:fs'; import os from 'node:os'; import path from 'node:path';` 추가.)

- [ ] **Step 2: 실패 확인**

Run: `node --test tests/ai_terminal.test.mjs`
Expected: 새 테스트 FAIL — 현재 터미널 env에 PYTHONPATH(RUNTIME_DIR) 미설정이라 출력 라인에 `runtime` 없음.

- [ ] **Step 3: `attachTerminal` env에 RUNTIME_DIR 추가**

주 셸 spawn env(현재 `{ ...process.env, PYTHONIOENCODING: 'utf-8', BLOCKPY_TERMINAL: '1' }`)를 다음으로:
```js
        env: { ...process.env, PYTHONIOENCODING: 'utf-8',
          PYTHONPATH: [RUNTIME_DIR, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
          BLOCKPY_TERMINAL: '1' },
```
Windows cmd.exe 폴백 spawn env(현재 `{ ...process.env, BLOCKPY_TERMINAL: '1' }`)도 동일하게:
```js
          env: { ...process.env,
            PYTHONPATH: [RUNTIME_DIR, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
            BLOCKPY_TERMINAL: '1' },
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `node --test tests/ai_terminal.test.mjs`
Expected: PASS (기존 3 + 신규 1 = 4/4). 신규 테스트가 터미널 출력의 PYTHONPATH에 `runtime`을 확인.

- [ ] **Step 5: 회귀 게이트**

Run: `npm run test:ir`
Expected: 그대로 PASS(이 기능은 변환 파이프라인 미변경).

- [ ] **Step 6: 커밋**

```bash
git add server.js tests/ai_terminal.test.mjs
git commit -m "feat(terminal): PTY env PYTHONPATH 에 RUNTIME_DIR 배선 → 터미널에서 import tm"
```

---

## 수동 검증 (자동화 불가 — 실행자가 사람에게 안내)

1. **dev:** `npm start` → 워크스페이스 폴더(`~/BlockPyWorkspace`)에 `AGENTS.md`·`CLAUDE.md`·`examples/`가 생겼는지. 터미널에서 `claude` 실행 시 컨텍스트를 읽고 tm/dobotkit API로 올바른 코드를 쓰는지.
2. **패키징:** `npm run dist` 후 설치본에서 (a) 워크스페이스에 그라운딩 세트가 시딩되는지, (b) `resources/app.asar.unpacked/runtime/tm.py`가 존재하고 터미널/Run 의 `import tm`이 되는지, (c) python-embed 에 `dobotkit`·`cv2`·`numpy`가 있는지.

---

## Self-Review

- **스펙 커버리지:** AGENTS.md 콘텐츠(Task1 Step3) / CLAUDE.md @import(Task1 Step4) / examples 복사(Task1 Step4) / 멱등(Task1 Step4·테스트) / API 정합(Task1 테스트) / RUNTIME_DIR 배선(Task2) / 패키징(Task1 Step7) — 모두 매핑됨.
- **플레이스홀더:** 없음(AGENTS.md 전문·seed 코드·테스트 전부 기재).
- **타입/이름 일관성:** `seedAgentContext` 시그니처가 server.js·export·테스트에서 일치. 예제 파일명 5종이 seed 코드·AGENTS.md·테스트에서 일치. `RUNTIME_DIR`/`PYTHONPATH` 배선이 run-python(server.js:632)과 동일 관용구.

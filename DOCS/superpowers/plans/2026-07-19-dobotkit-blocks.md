# dobotkit 고정 블록 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** dobotkit(Dobot Magician Lite 팔 + Magician GO 차)의 커리큘럼 핵심 API를, 마운트 시 `builtin`으로 등록되는 항상-존재하는 "dobotkit" 토크박스 블록으로 제공한다. 블록은 일반 파이썬 호출로 무손실 변환되고 백엔드 실제 파이썬으로 실행된다.

**Architecture:** 기존 번들 LibrarySpec → `builtin` 등록 패턴(cv2/stdlib과 동일)을 재사용. dobotkit 큐레이션 스펙을 **별도 파일** `src/data/robotSpecs.json`(hand-authored, `scripts/gen-robot-blocks.cjs`로 생성)에 담고, `App.jsx` 마운트 등록 루프가 stdlibSpecs와 함께 등록한다. 변환 코어(irToBlockly/blocklyToIr/irBlocks)는 손대지 않는다 — 블록은 Call IR 위의 Tier-A 스킨이라 라운드트립이 자동으로 무손실.

**Tech Stack:** Node(gen script) · React/Vite(App.jsx) · Playwright(테스트) · 기존 `BlockPyLibRegistry`/`BlockPyLibImport`/`BlockPyBuildIrToolbox` · Pyodide(irToPython, 테스트에서만).

## Global Constraints

- **변환 코어 불변:** `src/utils/irToBlockly.js`, `src/utils/blocklyToIr.js`, `src/utils/irBlocks.js` 수정 금지.
- **stdlibSpecs.json 불변:** dobotkit은 `robotSpecs.json`(신규)에 담는다. `src/data/stdlibSpecs.json`을 재생성/수정하지 않는다(로컬 python 재introspection이 44줄 churn 유발함을 확인).
- **no hardcoded recognition tables:** Python→블록 인식에 dobotkit 전용 규칙 추가 금지(오소링 프리셋만).
- **무손실 라운드트립:** `ast.dump(parse(orig)) == ast.dump(parse(regenerated))`.
- **불필요 파일 손대지 않기.**
- 블록 lower 대상(검증필): 팔 연결 `dobotkit.MagicianLite()` · `arm.<m>(...)`(수신자 변수 arm) · 차 연결 `MagicianGO.open(port_name)`(from dobotkit import MagicianGO) · `car.<m>(...)`(수신자 변수 car).

## File Structure

- **Create** `scripts/gen-robot-blocks.cjs` — dobotkit 큐레이션 LibrarySpec를 정의하고 `src/data/robotSpecs.json`을 쓴다. `gen-stdlib-blocks.cjs`의 HAND 패턴을 그대로 따름.
- **Create** `src/data/robotSpecs.json` — 생성 산출물(모듈 스펙 배열 `[{module:'dobotkit', entries:[…]}]`). 커밋.
- **Modify** `src/App.jsx` — `robotSpecs` import + 마운트 builtin 등록 루프에 병합(약 2곳).
- **Create** `tests/robot_blocks.spec.js` — node-level 등록/lower + browser 토크박스/lower/라운드트립.

**절대 수정 금지:** `irToBlockly.js`, `blocklyToIr.js`, `irBlocks.js`, `libRegistry.js`, `libImport.js`, `irToolbox.js`, `stdlibSpecs.json`, `gen-stdlib-blocks.cjs`.

---

### Task 1: 큐레이션 dobotkit 스펙 번들 (gen script + robotSpecs.json)

**Files:**
- Create: `scripts/gen-robot-blocks.cjs`
- Create: `src/data/robotSpecs.json` (생성물)
- Test: `tests/robot_blocks.spec.js` (node-level describe 블록)

**Interfaces:**
- Produces: `src/data/robotSpecs.json` = `[{ module:'dobotkit', entries:[…] }]`. 각 entry는 blockpy-gen LibrarySpec entry 모양 `{kind, name, owner?, module?, qualName?, params:[{name,kind,hasDefault}], returns}`.
- Consumes: `window.BlockPyLibRegistry`, `window.BlockPyLibImport` (node에서 require; global에 부착).
- entry → 등록 스펙 매핑(검증필, `librarySpecToRegistrySpecs(spec,{both:false})`):
  - `{kind:'class', name:'MagicianLite'}` → `lib_dobotkit_MagicianLite` (값, `dobotkit.MagicianLite()`)
  - `{kind:'method', owner:'Arm', name:'move_to', params:[x,y,z], returns:false}` → `lib_arm_move_to_stmt` (명령, `arm.move_to(x,y,z)`)
  - `{kind:'method', owner:'Arm', name:'get_pose', returns:true}` → `lib_arm_get_pose` (값, `arm.get_pose()`)
  - `{kind:'function', name:'open', module:'dobotkit.MagicianGO', params:[port_name], returns:true}` → `lib_MagicianGO_open` (값, `MagicianGO.open(port_name)`)
  - `{kind:'method', owner:'Car', name:'battery', returns:true}` → `lib_car_battery` (값, `car.battery()`)

- [ ] **Step 1: 실패하는 node 테스트 작성** — `tests/robot_blocks.spec.js`에 아래 node describe를 만든다.

```javascript
const { test, expect } = require('@playwright/test');
const APP_URL = 'http://localhost:' + (process.env.PORT || '3000') + '/';

// ── Node-level: robotSpecs.json 이 등록 가능한 dobotkit 스펙을 담는지 ──
require('../src/utils/libRegistry.js');
require('../src/utils/libImport.js');
const REG = global.BlockPyLibRegistry;
const IMP = global.BlockPyLibImport;
let robotSpecs;
try { robotSpecs = require('../src/data/robotSpecs.json'); } catch (_) { robotSpecs = null; }

test.describe('robotSpecs bundle (node)', () => {
  test('robotSpecs.json 은 dobotkit 모듈 스펙 배열', () => {
    expect(Array.isArray(robotSpecs)).toBe(true);
    const dk = robotSpecs.find((m) => m.module === 'dobotkit');
    expect(dk).toBeTruthy();
    expect(dk.entries.length).toBeGreaterThanOrEqual(18);
  });

  test('모든 entry 가 등록되고 핵심 블록이 기대 형태/타입으로 매핑', () => {
    REG.clearAll();
    const dk = robotSpecs.find((m) => m.module === 'dobotkit');
    const { specs } = IMP.librarySpecToRegistrySpecs(dk, { both: false });
    const byType = {};
    for (const s of specs) {
      const res = REG.registerLibBlock({ ...s, builtin: true });
      expect(res.ok).toBe(true);              // 모든 스펙 등록 성공(충돌/무효 없음)
      byType[res.type] = s;
    }
    // 대표 타입 존재 + 값/명령 구분 + lib 태그
    expect(byType['lib_dobotkit_MagicianLite']).toMatchObject({ hasOutput: true, lib: 'dobotkit' });
    expect(byType['lib_arm_move_to_stmt']).toMatchObject({ hasOutput: false, module: 'arm', func: 'move_to' });
    expect(byType['lib_arm_get_pose']).toMatchObject({ hasOutput: true });
    expect(byType['lib_MagicianGO_open']).toMatchObject({ hasOutput: true, module: 'MagicianGO', func: 'open' });
    expect(byType['lib_car_battery']).toMatchObject({ hasOutput: true, module: 'car', func: 'battery' });
    REG.clearAll();
  });
});
```

- [ ] **Step 2: 테스트 실행 → 실패 확인**

Run: `npx playwright test tests/robot_blocks.spec.js -g "robotSpecs bundle" --project=chromium`
Expected: FAIL — `robotSpecs.json` 없음(`Array.isArray(robotSpecs)` false).

- [ ] **Step 3: gen script 작성** — `scripts/gen-robot-blocks.cjs`

```javascript
// Generate src/data/robotSpecs.json — a hand-curated LibrarySpec for dobotkit (Dobot Magician
// Lite arm + Magician GO car), registered as built-in "dobotkit" toolbox blocks at app startup
// (offline, no runtime introspection). dobotkit's API is class/method-heavy and raw introspection
// is noisy (enum/exception boilerplate: bit_length/with_traceback/...), so — like cv2 in
// gen-stdlib-blocks.cjs — only the curriculum-essential subset is hand-authored here.
// Signatures verified via `python -c "import inspect, dobotkit; ..."` on 2026-07-19 (dobotkit 0.1.x):
//   MagicianLite.move_to(x, y, z, r=0, *, ...); set_speed(velocity, acceleration); ...
//   MagicianGO.open(port_name='COM5'); forward(speed); move(x=0,y=0,r=0); drive_for(x,y,r,seconds); ...
// Re-generate with: node scripts/gen-robot-blocks.cjs
const fs = require('fs');
const path = require('path');

const P = (...names) => names.map((n) => ({ name: n, kind: 'positional', hasDefault: false }));
// method on the arm/car receiver: title "<recv>.<name>", lowers "<recv>.<name>(args)".
// returns:false → command (green statement) block; returns:true → value (reporter) block.
const armCmd = (name, ...args) => ({ kind: 'method', owner: 'Arm', name, params: P(...args), returns: false });
const armVal = (name, ...args) => ({ kind: 'method', owner: 'Arm', name, params: P(...args), returns: true });
const carCmd = (name, ...args) => ({ kind: 'method', owner: 'Car', name, params: P(...args), returns: false });
const carVal = (name, ...args) => ({ kind: 'method', owner: 'Car', name, params: P(...args), returns: true });

const spec = {
  module: 'dobotkit',
  entries: [
    // ── 팔 (MagicianLite) — 수신자 변수 arm ──
    { kind: 'class', name: 'MagicianLite', qualName: 'dobotkit.MagicianLite', params: [], returns: true }, // arm = dobotkit.MagicianLite()
    armCmd('home'),
    armCmd('move_to', 'x', 'y', 'z'),
    armCmd('move_relative', 'dx', 'dy', 'dz'),
    armCmd('suck', 'on'),
    armCmd('grip', 'on'),
    armCmd('set_speed', 'velocity', 'acceleration'),
    armVal('get_pose'),
    // ── 차 (MagicianGO) — 수신자 변수 car ──
    // 연결은 classmethod open: from dobotkit import MagicianGO → car = MagicianGO.open("COM5")
    { kind: 'function', name: 'open', module: 'dobotkit.MagicianGO', qualName: 'dobotkit.MagicianGO.open', params: P('port_name'), returns: true },
    carCmd('forward', 'speed'),
    carCmd('backward', 'speed'),
    carCmd('spin', 'speed'),
    carCmd('strafe', 'speed'),
    carCmd('move', 'x', 'y', 'r'),
    carCmd('drive_for', 'x', 'y', 'r', 'seconds'),
    carCmd('stop'),
    carCmd('buzzer'),
    carVal('battery'),
    carVal('ultrasonic'),
    carVal('imu_angle'),
  ],
};

const dest = path.join(__dirname, '..', 'src', 'data', 'robotSpecs.json');
fs.mkdirSync(path.dirname(dest), { recursive: true });
fs.writeFileSync(dest, JSON.stringify([spec], null, 1));
console.log(`[robot] wrote dobotkit spec (${spec.entries.length} entries) -> ${path.relative(path.join(__dirname, '..'), dest)}`);
```

- [ ] **Step 4: gen script 실행 → robotSpecs.json 생성**

Run: `node scripts/gen-robot-blocks.cjs`
Expected: `[robot] wrote dobotkit spec (20 entries) -> src/data/robotSpecs.json`

- [ ] **Step 5: node 테스트 실행 → 통과**

Run: `npx playwright test tests/robot_blocks.spec.js -g "robotSpecs bundle" --project=chromium`
Expected: PASS (2 tests).

- [ ] **Step 6: 커밋**

```bash
git add scripts/gen-robot-blocks.cjs src/data/robotSpecs.json tests/robot_blocks.spec.js
git commit -m "feat(robot): dobotkit 고정 블록 큐레이션 스펙 번들(robotSpecs.json)"
```

---

### Task 2: App 마운트 등록 + 브라우저 검증

**Files:**
- Modify: `src/App.jsx` (import + 마운트 builtin 등록 루프 병합)
- Test: `tests/robot_blocks.spec.js` (browser describe 블록 추가)

**Interfaces:**
- Consumes: Task 1의 `src/data/robotSpecs.json`.
- App.jsx 현재 등록 루프(약 500–511행)는 `stdlibSpecs`만 순회. 이를 `[...stdlibSpecs, ...robotSpecs]` 순회로 바꾼다. 나머지(`registerLibBlock({...s, builtin:true})`, installed dedupe)는 그대로.
- 결과: 마운트 후 `BlockPyBuildIrToolbox()`가 `name==='dobotkit'` 카테고리를 포함하고, 그 안에 unified ir_call 프리셋(module-func: `extraState.funcName`; method: `extraState.method` + `fields.RECV.name`)이 들어간다.

- [ ] **Step 1: 실패하는 브라우저 테스트 작성** — `tests/robot_blocks.spec.js`에 아래 browser describe를 추가한다.

```javascript
// ── Browser: 마운트 시 dobotkit 카테고리/블록 존재 + lower + 라운드트립 ──
test.describe('dobotkit built-in blocks (browser)', () => {
  test('마운트 후 dobotkit 카테고리와 대표 블록이 존재(builtin)', async ({ page }) => {
    test.setTimeout(300000);   // Pyodide cold-load
    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(
      () => window.__blocklyWorkspace && window.BlockPyLibRegistry && window.BlockPyBuildIrToolbox,
      null, { timeout: 180000 });
    const out = await page.evaluate(() => {
      const reg = window.BlockPyLibRegistry;
      const tb = window.BlockPyBuildIrToolbox();
      const cat = tb.contents.find((c) => c.name === 'dobotkit');
      const flat = cat ? JSON.stringify(cat.contents) : '';
      return {
        hasCat: !!cat,
        armLiteBuiltin: !!(reg.getLibSpec('lib_dobotkit_MagicianLite') || {}).builtin,
        moveToBuiltin: !!(reg.getLibSpec('lib_arm_move_to_stmt') || {}).builtin,
        goOpenBuiltin: !!(reg.getLibSpec('lib_MagicianGO_open') || {}).builtin,
        hasMoveTo: flat.includes('"method":"move_to"'),
        hasLiteFunc: flat.includes('dobotkit.MagicianLite'),
        hasGoOpen: flat.includes('MagicianGO.open'),
      };
    });
    expect(out.hasCat).toBe(true);
    expect(out.armLiteBuiltin).toBe(true);
    expect(out.moveToBuiltin).toBe(true);
    expect(out.goOpenBuiltin).toBe(true);
    expect(out.hasMoveTo).toBe(true);
    expect(out.hasLiteFunc).toBe(true);
    expect(out.hasGoOpen).toBe(true);
  });

  test('등록 블록이 정확한 파이썬으로 lower (REAL Blockly load→save→IR→Python)', async ({ page }) => {
    test.setTimeout(300000);
    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(
      () => window.__blocklyWorkspace && window.BlockPyIR && window.BlockPyAstBridge && window.Blockly && window.BlockPyLibRegistry,
      null, { timeout: 180000 });
    const out = await page.evaluate(async () => {
      const ws = window.__blocklyWorkspace;
      const py = await window.BlockPyAstBridge.getPyodide();
      const lower = async (blocks) => {
        ws.clear();
        window.Blockly.serialization.workspaces.load({ blocks: { blocks } }, ws);
        const ir = window.BlockPyIR.blocklyToIr(window.Blockly.serialization.workspaces.save(ws));
        return (await window.BlockPyAstBridge.irToPython(py, ir)).trim();
      };
      const arm = await lower([
        { type: 'lib_arm_move_to_stmt', inputs: {
          ARG0: { shadow: { type: 'ir_name', fields: { ID: 'arm' } } },
          ARG1: { shadow: { type: 'ir_const', fields: { VALUE: '200' } } },
          ARG2: { shadow: { type: 'ir_const', fields: { VALUE: '0' } } },
          ARG3: { shadow: { type: 'ir_const', fields: { VALUE: '40' } } } } },
      ]);
      const connect = await lower([
        { type: 'lib_dobotkit_MagicianLite' },
      ]);
      const go = await lower([
        { type: 'lib_MagicianGO_open', inputs: { ARG0: { shadow: { type: 'ir_const', fields: { VALUE: '"COM5"' } } } } },
      ]);
      const batt = await lower([
        { type: 'lib_car_battery', inputs: { ARG0: { shadow: { type: 'ir_name', fields: { ID: 'car' } } } } },
      ]);
      ws.clear();
      return { arm, connect, go, batt };
    });
    expect(out.connect).toBe('dobotkit.MagicianLite()');
    expect(out.arm).toBe('arm.move_to(200, 0, 40)');
    expect(out.go).toBe("MagicianGO.open('COM5')");
    expect(out.batt).toBe('car.battery()');
  });

  test('dobotkit 프로그램이 무손실 라운드트립 (ast 동치)', async ({ page }) => {
    test.setTimeout(300000);
    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(
      () => window.BlockPyIR && window.BlockPyAstBridge, null, { timeout: 180000 });
    const out = await page.evaluate(async () => {
      const src = [
        'import dobotkit',
        'from dobotkit import MagicianGO',
        'arm = dobotkit.MagicianLite()',
        'arm.home()',
        'arm.move_to(200, 0, 40)',
        'arm.suck(True)',
        'car = MagicianGO.open(\'COM5\')',
        'car.forward(50)',
        'print(car.battery())',
      ].join('\n');
      const py = await window.BlockPyAstBridge.getPyodide();
      const ir = await window.BlockPyAstBridge.pythonToIR(py, src);
      const back = (await window.BlockPyAstBridge.irToPython(py, ir)).trim();
      const eq = await window.BlockPyAstBridge.astEqual
        ? await window.BlockPyAstBridge.astEqual(py, src, back)
        : (src.trim() === back);
      return { src: src.trim(), back, eq };
    });
    expect(out.back).toBe(out.src);   // 텍스트 동일(포맷 안정) → ast 동치 보장
  });
});
```

- [ ] **Step 2: 브라우저 테스트 실행 → 실패 확인** (백엔드 불필요; Vite 자동)

Run: `npx playwright test tests/robot_blocks.spec.js -g "dobotkit built-in" --project=chromium`
Expected: FAIL — dobotkit 카테고리 없음(App이 robotSpecs를 아직 안 읽음). 단, 라운드트립 테스트는 이미 통과할 수 있음(제네릭 변환).

- [ ] **Step 3: App.jsx 에 robotSpecs import 추가**

`src/App.jsx` 상단(약 14행, `import stdlibSpecs ...` 다음 줄)에 추가:

```javascript
import robotSpecs from './data/robotSpecs.json';
```

- [ ] **Step 4: 마운트 등록 루프에 robotSpecs 병합**

`src/App.jsx` 마운트 useEffect 안, 현재:

```javascript
      const imp = window.BlockPyLibImport;
      if (imp && Array.isArray(stdlibSpecs)) {
        for (const spec of stdlibSpecs) {
```

를 아래로 교체:

```javascript
      const imp = window.BlockPyLibImport;
      // 번들 built-in 스펙: 파이썬 stdlib/cv2(stdlibSpecs) + dobotkit 로봇 블록(robotSpecs).
      // 둘 다 builtin 등록 → 항상 존재, 사용자 삭제 불가, localStorage 미저장.
      const bundledSpecs = [
        ...(Array.isArray(stdlibSpecs) ? stdlibSpecs : []),
        ...(Array.isArray(robotSpecs) ? robotSpecs : []),
      ];
      if (imp) {
        for (const spec of bundledSpecs) {
```

(루프 본문·닫는 괄호는 그대로 둔다.)

- [ ] **Step 5: 브라우저 테스트 실행 → 통과**

Run: `npx playwright test tests/robot_blocks.spec.js -g "dobotkit built-in" --project=chromium`
Expected: PASS (3 tests).

- [ ] **Step 6: 회귀 확인 — 관련 스펙 재실행**

Run: `npx playwright test tests/ir_lib_blocks.spec.js tests/robot_blocks.spec.js --project=chromium`
Expected: 모두 PASS. (dobotkit 추가는 additive — cv2/stdlib 탭 테스트에 영향 없어야 함. 라이브러리 카테고리 목록을 하드코딩 검증하는 테스트가 깨지면, dobotkit 포함으로 기대값을 갱신한다.)

- [ ] **Step 7: 커밋**

```bash
git add src/App.jsx tests/robot_blocks.spec.js
git commit -m "feat(robot): dobotkit 고정 블록 App 마운트 등록 + 브라우저 검증"
```

---

## 최종 검증 (Task 완료 후)

- [ ] 전체 스위트 게이트: `npm run test:ir` (IR 라운드트립 게이트) + `npx playwright test tests/robot_blocks.spec.js` 통과 확인. 실패 시 dobotkit-additive가 원인인지 판별(무관 실패는 별도 보고).
- [ ] 코어 파일 무변경 확인: `git diff --name-only robot-wiring..HEAD` 에 `irToBlockly.js`/`blocklyToIr.js`/`irBlocks.js`/`libRegistry.js`/`libImport.js`/`irToolbox.js`/`stdlibSpecs.json` 없어야 함.

## 롤백

- 작업 브랜치 `feat/dobotkit-blocks`. master는 `robot-wiring`(95a6cbc) = 롤백 지점.
- 원복: `git checkout master` 또는 `git reset --hard robot-wiring`.
- 완료·검증·사용자 승인 후 병합 시 태그 `robot-blocks` 부여.

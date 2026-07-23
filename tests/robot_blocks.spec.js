const { test, expect } = require('@playwright/test');
const APP_URL = 'http://localhost:' + (process.env.PORT || '3000') + '/';

// dobotkit 고정 블록: 마운트 시 builtin 으로 등록되는 "dobotkit" 토크박스 블록(팔 MagicianLite +
// 차 MagicianGO). 블록은 일반 Call IR 위 Tier-A 스킨이라 파이썬으로 무손실 변환되고, dobotkit이
// 백엔드에 설치돼 있으면 Run 시 실제 로봇이 움직인다. 스펙은 src/data/robotSpecs.json(hand-curated).

// ── Node-level (no browser) ─────────────────────────────────────────────────
require('../src/utils/libRegistry.js');
require('../src/utils/libImport.js');
require('../src/utils/irToBlockly.js');   // BlockPyIR.renderComments (used by blocklyToIr)
require('../src/utils/blocklyToIr.js');
const REG = global.BlockPyLibRegistry;
const IMP = global.BlockPyLibImport;
const IR = global.BlockPyIR;
let robotSpecs;
try { robotSpecs = require('../src/data/robotSpecs.json'); } catch (_) { robotSpecs = null; }

function registerDobotkit() {
  REG.clearAll();
  const dk = robotSpecs.find((m) => m.module === 'dobotkit');
  for (const s of IMP.librarySpecToRegistrySpecs(dk, { both: false }).specs) REG.registerLibBlock({ ...s, builtin: true });
}

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

test.describe('dobotkit lib lowering (node)', () => {
  test.beforeAll(registerDobotkit);
  test.afterAll(() => REG.clearAll());

  test('팔 연결: dobotkit.MagicianLite() (값)', () => {
    const ir = IR.blocklyToIr({ blocks: { blocks: [{ type: 'lib_dobotkit_MagicianLite' }] } });
    expect(ir.body[0].value).toMatchObject({
      type: 'Call', func: { type: 'Attribute', attr: 'MagicianLite', value: { type: 'Name', id: 'dobotkit' } }, args: [],
    });
  });

  test('팔 이동: arm.move_to(x, y, z) — 명령, 수신자=ARG0', () => {
    const ws = { blocks: { blocks: [{ type: 'lib_arm_move_to_stmt', inputs: {
      ARG0: { shadow: { type: 'ir_name', fields: { ID: 'arm' } } },
      ARG1: { shadow: { type: 'ir_name', fields: { ID: 'x' } } },
      ARG2: { shadow: { type: 'ir_name', fields: { ID: 'y' } } },
      ARG3: { shadow: { type: 'ir_name', fields: { ID: 'z' } } } } }] } };
    const ir = IR.blocklyToIr(ws);
    expect(ir.body[0]).toMatchObject({ type: 'Expr', value: {
      type: 'Call',
      func: { type: 'Attribute', attr: 'move_to', value: { type: 'Name', id: 'arm' } },
      args: [{ type: 'Name', id: 'x' }, { type: 'Name', id: 'y' }, { type: 'Name', id: 'z' }],
      keywords: [] } });
  });

  test('차 연결: MagicianGO.open(port) (값)', () => {
    const ws = { blocks: { blocks: [{ type: 'lib_MagicianGO_open', inputs: {
      ARG0: { shadow: { type: 'ir_const', fields: { VALUE: '"COM5"' } } } } }] } };
    const ir = IR.blocklyToIr(ws);
    expect(ir.body[0].value).toMatchObject({
      type: 'Call', func: { type: 'Attribute', attr: 'open', value: { type: 'Name', id: 'MagicianGO' } },
      args: [{ type: 'Constant', value: 'COM5' }] });
  });

  test('차 값: car.battery() — 값, 수신자=ARG0', () => {
    const ws = { blocks: { blocks: [{ type: 'lib_car_battery', inputs: {
      ARG0: { shadow: { type: 'ir_name', fields: { ID: 'car' } } } } }] } };
    const ir = IR.blocklyToIr(ws);
    expect(ir.body[0].value).toMatchObject({
      type: 'Call', func: { type: 'Attribute', attr: 'battery', value: { type: 'Name', id: 'car' } }, args: [] });
  });
});

// ── Browser: 마운트 시 dobotkit 카테고리/블록 존재 + 무손실 라운드트립 ──
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

  test('dobotkit 프로그램이 무손실 라운드트립 (텍스트 동일)', async ({ page }) => {
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
        "car = MagicianGO.open('COM5')",
        'car.forward(50)',
        'print(car.battery())',
      ].join('\n');
      const py = await window.BlockPyAstBridge.getPyodide();
      const ir = await window.BlockPyAstBridge.pythonToIR(py, src);
      const back = (await window.BlockPyAstBridge.irToPython(py, ir)).trim();
      return { src: src.trim(), back };
    });
    expect(out.back).toBe(out.src);   // 포맷 안정 → ast 동치 보장
  });
});

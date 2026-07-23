const { test, expect } = require('@playwright/test');
const APP_URL = 'http://localhost:' + (process.env.PORT || '3000') + '/';
const path = require('path');
const { spawnSync } = require('child_process');

// 파이썬 네이티브 TM: runtime/tm.py 를 PYTHONPATH 로 실어 `import tm` (server.js run-python 과 동일
// 메커니즘) + 마운트 시 builtin 으로 등록되는 "tm" 토크박스 블록. 학습·추론 전부 파이썬(자기일관).

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
        hasLabelsProp: flat.includes('"attr":"labels"'),
      };
    });
    expect(out.hasCat).toBe(true);
    expect(out.modelBuiltin).toBe(true);
    expect(out.trainBuiltin).toBe(true);
    expect(out.hasPredict).toBe(true);
    expect(out.hasModelFunc).toBe(true);
    expect(out.hasLoad).toBe(true);
    expect(out.hasLabelsProp).toBe(true);   // model.labels 속성 블록도 tm 탭에 노출
  });

  test('tm 프로그램이 무손실 라운드트립 (텍스트 동일)', async ({ page }) => {
    test.setTimeout(300000);
    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => window.BlockPyIR && window.BlockPyAstBridge, null, { timeout: 180000 });
    const out = await page.evaluate(async () => {
      const src = [
        'import tm',
        "model = tm.Model(['가위', '바위', '보'])",
        "model.add_example(frame, '가위')",
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

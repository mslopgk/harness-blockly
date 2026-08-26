// Phase B slice 3 (UI wiring): the LibraryManager "Blockify" flow. Typing a module name and
// clicking Blockify hits POST /api/blockify (real-python introspection), maps the LibrarySpec
// via window.BlockPyLibImport, and registers the blocks into the libRegistry — so they appear in
// the Library palette and round-trip losslessly, exactly like AI-abstracted blocks.
//
// Needs BOTH servers: the Vite dev server (Playwright auto-starts it on :3000) AND the Express
// backend for /api/blockify (`npm run server`, :3001) — same as the AI tests. Set APP_URL to
// target a non-default port. Uses stdlib `html.parser` so no pip/micropip/Pillow is required.
const { test, expect } = require('@playwright/test');
const APP = process.env.APP_URL || 'http://localhost:3000';

test('Blockify UI: introspect html.parser → Library blocks, method round-trips to receiver.method', async ({ page }) => {
  test.setTimeout(120000);
  await page.goto(APP, { waitUntil: 'networkidle', timeout: 60000 });
  await page.waitForFunction(
    () => !!(window.__blocklyWorkspace && window.BlockPyLibRegistry && window.BlockPyLibImport && window.BlockPyBuildIrToolbox),
    null, { timeout: 60000 },
  );

  const count = () => page.evaluate(() => window.BlockPyLibRegistry.listLibBlocks().reduce((n, g) => n + g.blocks.length, 0));
  const before = await count();

  // LibraryManager 는 rail 의 'AI 라이브러리' 팝업(#tab-btn-ai)에 있다. 예전 스펙이 쓰던
  // `#tab-btn-library` 컨트롤은 이 레이아웃에 존재하지 않는다(디자인 v2 이전부터 부재).
  await page.locator('#tab-btn-ai').click();
  await page.locator('#blockify-mod-input').fill('html.parser');
  // 라벨은 한국어로 바뀔 수 있으므로(현재 '블록 만들기') 문구 대신 id 로 잡는다.
  await page.locator('#btn-blockify').click();

  // The registry grows only if /api/blockify answered — a clear message when the backend is down.
  const grew = await page
    .waitForFunction((b) => window.BlockPyLibRegistry.listLibBlocks().reduce((n, g) => n + g.blocks.length, 0) > b,
      before, { timeout: 60000 })
    .then(() => true).catch(() => false);
  expect(grew, 'registry did not grow — is the Express backend (npm run server) running for /api/blockify?').toBe(true);

  await page.waitForTimeout(600); // toolbox-refresh effect

  // the library's import block is auto-added (real block, so it round-trips) -> dragged blocks run
  const hasImport = await page.evaluate(() => window.__blocklyWorkspace.getAllBlocks(false)
    .some((b) => b.type === 'ir_importfrom' && b.getFieldValue('MODULE') === 'html'));
  expect(hasImport, 'an import block (from html import parser) should be auto-added').toBe(true);

  const proof = await page.evaluate(() => {
    const reg = window.BlockPyLibRegistry;
    // toolbox carries a populated PER-LIBRARY category (one tab per library — there is no single
    // lumped "Library" category anymore), with group/Constants/Properties sub-categories inside.
    const tb = window.BlockPyBuildIrToolbox();
    const countBlocks = (c) => (c.contents || []).reduce(
      (n, x) => n + (x.kind === 'block' ? 1 : (x.kind === 'category' ? countBlocks(x) : 0)), 0);
    const lib = tb.contents.find((c) => c.kind === 'category' && c.name === 'html.parser');
    const libCount = lib ? countBlocks(lib) : 0;

    // pick any registered instance-method block and lower it: receiver = ARG0's value
    let lowered = null;
    for (const g of reg.listLibBlocks()) {
      for (const b of g.blocks) {
        const spec = reg.getLibSpec(b.type);
        if (!spec || !spec.method) continue;
        const inputs = {};
        spec.argNames.forEach((_, i) => { inputs['ARG' + i] = { block: { type: 'ir_name', fields: { ID: i === 0 ? 'recv' : 'x' + i } } }; });
        const ir = window.BlockPyIR.blocklyToIr({ blocks: { languageVersion: 0, blocks: [{ type: b.type, inputs }] } });
        const call = ir.body[0].value;
        lowered = { attr: call.func.attr, recvId: call.func.value && call.func.value.id, recvType: call.func.value && call.func.value.type, func: spec.func };
        break;
      }
      if (lowered) break;
    }
    return { libCount, lowered };
  });

  // the blockified library's own tab exists in the toolbox and actually offers blocks
  expect(proof.libCount).toBeGreaterThan(0);
  // a method lowers to `recv.<method>(...)` — receiver is ARG0's value (a Name), not a duplicated literal
  expect(proof.lowered).not.toBeNull();
  expect(proof.lowered.recvType).toBe('Name');
  expect(proof.lowered.recvId).toBe('recv');
  expect(proof.lowered.attr).toBe(proof.lowered.func);
});

// Phase 4 slice 3 — App wiring for the "Auto Desugar" toggle. Drives the REAL UI: type Python,
// Convert, and confirm the live workspace holds SUGAR blocks when the toggle is OFF (default) and
// desugared loop blocks when ON, with the block->Python regen producing the loop form. Toggling
// must re-Convert (invalidating the stale snapshot). Pyodide value-equivalence is proven separately
// in ir_desugar_semantics.spec.js; this test is about the wiring.
const { test, expect } = require('@playwright/test');

// 코드정리/구문트리 탭은 고급(교사) 모드 전용이므로 ?advanced=1 로 진입한다(검증 내용은 동일).
const APP_URL = 'http://localhost:' + (process.env.PORT || '3000') + '/?advanced=1';
const wsJson = (page) => page.evaluate(() =>
  JSON.stringify(window.Blockly.serialization.workspaces.save(window.__blocklyWorkspace)));

test.describe('Phase 4 slice 3: Auto Desugar toggle wiring', () => {
  test('default OFF preserves sugar; ON desugars; OFF restores — with loop-form regen when ON', async ({ page }) => {
    test.setTimeout(200000);
    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(
      () => window.__pyodide && window.__blocklyWorkspace && window.BlockPyIR
        && window.BlockPyAstBridge && window.BlockPyIrDesugar,
      null, { timeout: 180000 });

    // Convert a list comprehension with the toggle at its default (OFF).
    const code = 'squares = [i*i for i in range(5)]';
    await page.locator('#tab-btn-python').click();
    await page.locator('#python-code').fill(code);
    await page.locator('#btn-sync-to-blocks').click();

    // Default OFF -> SUGAR preserved: the workspace has an ir_listcomp block.
    await page.waitForFunction(() => {
      const s = JSON.stringify(window.Blockly.serialization.workspaces.save(window.__blocklyWorkspace));
      return s.includes('ir_listcomp');
    }, null, { timeout: 60000 });

    // Turn Auto Desugar ON (the checkbox lives in the AST tab).
    await page.locator('#tab-btn-ast').click();
    await page.locator('#toggle-desugar').check();

    // ON -> the comprehension is unrolled: ir_for + ir_call(append) appear, ir_listcomp is gone.
    await page.waitForFunction(() => {
      const s = JSON.stringify(window.Blockly.serialization.workspaces.save(window.__blocklyWorkspace));
      return s.includes('ir_for') && s.includes('ir_call') && !s.includes('ir_listcomp');
    }, null, { timeout: 60000 });

    // block -> Python regenerates the LOOP form (one-directional: no re-sugar).
    const regen = await page.evaluate(async () => {
      const snap = window.Blockly.serialization.workspaces.save(window.__blocklyWorkspace);
      const ir = window.BlockPyIR.blocklyToIr(snap);
      const py = await window.BlockPyAstBridge.getPyodide();
      return (await window.BlockPyAstBridge.irToPython(py, ir)).replace(/\n$/, '');
    });
    expect(regen).toContain('for i in range(5)');
    expect(regen).toContain('.append(');
    expect(regen).not.toContain('for i in range(5)]');   // not a comprehension

    // Turn it back OFF -> sugar is restored (ir_listcomp returns).
    await page.locator('#toggle-desugar').uncheck();
    await page.waitForFunction(() => {
      const s = JSON.stringify(window.Blockly.serialization.workspaces.save(window.__blocklyWorkspace));
      return s.includes('ir_listcomp');
    }, null, { timeout: 60000 });

    // sanity: the final workspace is all ir_* blocks (no stray legacy/raw blocks).
    const finalJson = await wsJson(page);
    const tops = JSON.parse(finalJson).blocks.blocks || [];
    expect(tops.length).toBeGreaterThan(0);
    expect(tops.every((b) => b.type.startsWith('ir_'))).toBe(true);
  });

  test('Desugared preview pane shows the IR desugar (loop form), matching the real pass', async ({ page }) => {
    test.setTimeout(200000);
    await page.goto(APP_URL, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(
      () => window.__pyodide && window.BlockPyAstBridge && window.BlockPyIrDesugar,
      null, { timeout: 180000 });

    const code = 'result = [n*2 for n in range(3)]';
    await page.locator('#tab-btn-python').click();
    await page.locator('#python-code').fill(code);

    // Open the Desugared pane: the effect computes pythonToIR -> desugarIr -> irToPython.
    await page.locator('#tab-btn-desugar').click();
    await page.waitForFunction(() => {
      const t = document.getElementById('desugared-target-code');
      return t && t.textContent.includes('.append(') && t.textContent.includes('for n in range(3)');
    }, null, { timeout: 60000 });

    const preview = await page.locator('#desugared-target-code').textContent();
    expect(preview).toContain('for n in range(3)');
    expect(preview).toContain('.append(');
    expect(preview).not.toContain('for n in range(3)]');   // unrolled, not a comprehension
    // original pane still shows the source
    expect(await page.locator('#sugar-original-code').textContent()).toContain('[n*2 for n in range(3)]');
  });
});

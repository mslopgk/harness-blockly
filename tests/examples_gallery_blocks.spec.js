// VERIFICATION METHODOLOGY (requested): every gallery example, selected from the in-app
// "예제" dropdown and Converted, must actually PRODUCE VISIBLE BLOCKS — not just parse.
//
// The earlier gallery test only ran the code and checked stdout, so it silently passed
// even if Convert produced no blocks. This test drives the exact user path:
//   pick example -> Convert -> switch to Blockly tab -> assert real, on-screen blocks
// and asserts the workspace regenerates non-empty Python (so the blocks are wired, not
// empty shells).
const { test, expect } = require('@playwright/test');
const { DEMO_SNIPPETS } = require('../src/examples/snippets.js');

test.describe('every example converts to visible blocks', () => {
  for (const sn of DEMO_SNIPPETS) {
    test(`${sn.category}/${sn.id}`, async ({ page }) => {
      test.setTimeout(45000);
      await page.goto('http://localhost:3000', { waitUntil: 'networkidle', timeout: 30000 });

      // 1. Pick the example from the dropdown (real user path).
      await page.locator('#tab-btn-python').click();
      await page.locator('#example-picker').selectOption(sn.id);
      await page.waitForTimeout(150);

      // 2. The editor must hold this example's code.
      expect(await page.locator('#python-code').inputValue()).toBe(sn.code);

      // 3. Convert — 문법 상태가 정상이어야 한다(오류 아님).
      //    문구("문법 오류"/"Parser Error")로 검사하면 라벨을 번역·수정하는 순간 조용히
      //    무조건 통과하는 헛단정이 된다 → 상태를 나타내는 클래스로 검사한다.
      await page.locator('#btn-sync-to-blocks').click();
      await page.waitForTimeout(700);
      const cls = (await page.locator('#syntax-status-text').getAttribute('class')) || '';
      expect(cls, `문법 상태: ${(await page.locator('#syntax-status-text').textContent()) || ''}`).toContain('valid');
      expect(cls).not.toContain('invalid');

      // 4. Switch to the Blockly tab and assert real, on-screen blocks.
      await page.locator('#tab-btn-blockly').click();
      await page.waitForTimeout(500);
      const info = await page.evaluate(async () => {
        const ws = window.Blockly.getMainWorkspace();
        if (!ws) return { all: 0, topVisible: 0, code: '', err: 'no workspace' };
        const top = ws.getTopBlocks(false);
        let topVisible = 0;
        for (const b of top) {
          const r = b.getSvgRoot().getBoundingClientRect();
          if (r.width > 0 && r.height > 0) topVisible++;
        }
        // 블록 -> 파이썬 재생성은 **IR 경로**로 확인한다(blocklyToIr -> irToPython).
        // 예전에는 레거시 `Blockly.Python.workspaceToCode` 를 썼는데, 그 생성기는 은퇴했고
        // ir_* 블록을 모른다("Python generator does not know how to generate code for block
        // type ir_assign" 로 throw) → catch 가 빈 문자열을 만들어 모든 예제가 실패했다.
        // 제품은 정상이었고 단정만 낡았던 것(실측 확인). CLAUDE.md 의 Legacy 항목 참조.
        let code = '', err = '';
        try {
          const snap = window.Blockly.serialization.workspaces.save(ws);
          const ir = window.BlockPyIR.blocklyToIr(snap);
          const py = await window.BlockPyAstBridge.getPyodide();
          code = (await window.BlockPyAstBridge.irToPython(py, ir)) || '';
        } catch (e) { err = (e && e.message) || String(e); }
        return { all: ws.getAllBlocks().length, topVisible, code: code.trim(), err };
      });

      // Blocks exist, are rendered on-screen, and regenerate non-empty Python.
      expect(info.all).toBeGreaterThan(0);
      expect(info.topVisible).toBeGreaterThan(0);
      expect(info.err, `블록 → 파이썬 재생성 실패: ${info.err}`).toBe('');
      expect(info.code.length).toBeGreaterThan(0);
    });
  }
});

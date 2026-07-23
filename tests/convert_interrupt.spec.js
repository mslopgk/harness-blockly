const { test, expect } = require('@playwright/test');

// Regression: a leftover Pyodide SIGINT (from a prior Stop) must NOT poison conversion.
//
// Pyodide's interrupt buffer is SHARED between the Run/Stop path and the Python<->blocks
// conversion path (one Pyodide instance). handleStopExecution -> interruptPyodide() sets the
// buffer to 2 (SIGINT) and never clears it; only runCode clears it (and the app's Run goes to
// the backend, so runCode rarely runs). So after a single Stop the buffer stays at 2, and every
// subsequent conversion's ast.parse inside Pyodide raises KeyboardInterrupt on its first op
// (dedent) -> surfaced as "[Parser Error] ... KeyboardInterrupt". With editor auto-reload this
// fires on every ~1.5s reload, poisoning conversion continuously.
//
// Fix: the conversion path clears the interrupt buffer to 0 before parsing (like runCode does),
// so a stale run-interrupt can never kill a convert.
test.describe('conversion is not poisoned by a leftover Stop (SIGINT)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    // getPyodide() resolves only after FULL init (incl. setInterruptBuffer at pyodideRunner.js:188).
    // window.__pyodide is set mid-init (line 174), before the buffer is attached, so waiting on it
    // alone can race the buffer setup.
    await page.waitForFunction(async () => {
      if (!window.BlockPyAstBridge) return false;
      const py = await window.BlockPyAstBridge.getPyodide().catch(() => null);
      return !!(py && (py._interruptBuffer || typeof SharedArrayBuffer === 'undefined'));
    }, null, { timeout: 180000 });
  });

  test('pythonToIR succeeds even with a pending interrupt buffer', async ({ page }) => {
    const result = await page.evaluate(async () => {
      const B = window.BlockPyAstBridge;
      const py = await B.getPyodide();
      if (!py._interruptBuffer) return { skipped: true }; // no SharedArrayBuffer -> nothing to poison
      py._interruptBuffer[0] = 2; // simulate a leftover SIGINT from a prior Stop
      try {
        const ir = await B.pythonToIR(py, 'x = 1\n');
        return { ok: true, type: ir.type, buf: py._interruptBuffer[0] };
      } catch (e) {
        return { ok: false, err: String(e && e.message || e) };
      }
    });
    if (result.skipped) test.skip(true, 'SharedArrayBuffer/interrupt buffer unavailable');
    expect(result.ok, `conversion threw: ${result.err || ''}`).toBeTruthy();
    expect(result.type).toBe('Module');
    expect(result.buf).toBe(0); // buffer left cleared for the next parse
  });

  test('irToPython succeeds even with a pending interrupt buffer', async ({ page }) => {
    const result = await page.evaluate(async () => {
      const B = window.BlockPyAstBridge;
      const py = await B.getPyodide();
      if (!py._interruptBuffer) return { skipped: true };
      const ir = await B.pythonToIR(py, 'y = 2\n'); // parse while buffer is clean
      py._interruptBuffer[0] = 2; // now poison it before unparse
      try {
        const code = await B.irToPython(py, ir);
        return { ok: true, code: code.trim() };
      } catch (e) {
        return { ok: false, err: String(e && e.message || e) };
      }
    });
    if (result.skipped) test.skip(true, 'SharedArrayBuffer/interrupt buffer unavailable');
    expect(result.ok, `unparse threw: ${result.err || ''}`).toBeTruthy();
    expect(result.code).toBe('y = 2');
  });
});

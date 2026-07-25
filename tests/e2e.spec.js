const { test, expect } = require('@playwright/test');

async function setSpeedToMax(_page) {
  // No-op: the speed slider / JS step interpreter was removed (Run uses Pyodide only).
  // Kept as a no-op so existing call sites across the suite need no changes.
}

test.describe('BlockPy E2E Harness Tests', () => {
  test.beforeEach(async ({ page }) => {
    page.on('console', msg => {
      console.log(`[Browser Console - ${msg.type()}] ${msg.text()}`);
    });
  });

  test('should verify print("hello world") parses, syncs, and prints in console', async ({ page }) => {
    // 1. Navigate to the local server
    await page.goto('http://localhost:3000');

    // 2. Select the Python Tab and the Logs Tab to make them visible
    const pythonTabButton = page.locator('#tab-btn-python');
    await expect(pythonTabButton).toBeVisible();
    await pythonTabButton.click();

    const logsTabButton = page.locator('#tab-btn-logs');
    await expect(logsTabButton).toBeVisible();
    await logsTabButton.click();

    // 3. Locate the Python code textarea which is now visible
    const pythonCodeField = page.locator('#python-code');
    await expect(pythonCodeField).toBeVisible();

    // 4. Clear existing text and fill with print("hello world")
    await pythonCodeField.fill('');
    await pythonCodeField.fill('print("hello world")');

    // 5. Click the compile/sync button to compile to Blockly
    const syncButton = page.locator('#btn-sync-to-blocks');
    await expect(syncButton).toBeEnabled();
    await syncButton.click();

    // Set speed to max
    await setSpeedToMax(page);

    // 6. Click the Run button
    const runButton = page.locator('#btn-run');
    await expect(runButton).toBeEnabled();
    await runButton.click();

    // 7. Wait for execution and assert that the logs container contains the output "hello world"
    const consoleLogs = page.locator('#console-logs');
    await expect(consoleLogs).toContainText('hello world');

    // 8. Verify there are no parser or runtime errors in console-logs
    const errorLogs = page.locator('#console-logs .error');
    const count = await errorLogs.count();
    if (count > 0) {
      const texts = await errorLogs.allInnerTexts();
      throw new Error(`Found unexpected errors in console: ${texts.join(', ')}`);
    }
  });

  test('should verify list.append(val) parses and updates variable monitor without errors', async ({ page }) => {
    // 변수 탭은 고급(교사) 모드 전용 → ?advanced=1 로 진입
    await page.goto('http://localhost:3000/?advanced=1');

    // Switch to Python tab
    const pythonTabButton = page.locator('#tab-btn-python');
    await expect(pythonTabButton).toBeVisible();
    await pythonTabButton.click();

    // Switch to Variables tab
    const variablesTabButton = page.locator('#tab-btn-variables');
    await expect(variablesTabButton).toBeVisible();
    await variablesTabButton.click();

    const pythonCodeField = page.locator('#python-code');
    await expect(pythonCodeField).toBeVisible();

    // Reset and input list creation and append
    await pythonCodeField.fill('arr = [1, 2]\narr.append(3)');

    // Sync to Blockly
    const syncButton = page.locator('#btn-sync-to-blocks');
    await syncButton.click();

    // Set speed to max
    await setSpeedToMax(page);

    // Run code
    const runButton = page.locator('#btn-run');
    await runButton.click();

    // Assert that standard console error element contains no error
    const errorLogs = page.locator('#console-logs .error');
    await expect(errorLogs).toHaveCount(0);
  });

  test('should verify sprite motion and pen custom blocks and generators without any Blockly generator errors', async ({ page }) => {
    await page.goto('http://localhost:3000');

    // Switch to Python tab
    const pythonTabButton = page.locator('#tab-btn-python');
    await expect(pythonTabButton).toBeVisible();
    await pythonTabButton.click();

    // Switch to Logs tab so the console logs container is mounted
    const logsTabButton = page.locator('#tab-btn-logs');
    await expect(logsTabButton).toBeVisible();
    await logsTabButton.click();

    const pythonCodeField = page.locator('#python-code');
    await expect(pythonCodeField).toBeVisible();

    // Input sprite commands
    const testCode = 'sprite.pen_down()\nsprite.move(100)\nsprite.turn_right(90)\nsprite.pen_up()';
    await pythonCodeField.fill('');
    await pythonCodeField.fill(testCode);

    // Sync to Blockly (this triggers Blockly parser/generators)
    const syncButton = page.locator('#btn-sync-to-blocks');
    await expect(syncButton).toBeEnabled();
    await syncButton.click();

    // Set speed to max
    await setSpeedToMax(page);

    // Verify there are no errors in console or browser-console
    const errorLogs = page.locator('#console-logs .error');
    await expect(errorLogs).toHaveCount(0);

    // Also click the run button to make sure it executes inside our custom sprite Stage without error
    const runButton = page.locator('#btn-run');
    await expect(runButton).toBeEnabled();
    await runButton.click();

    // The logs shouldn't have [Parser Error] or [Runtime Error]
    const logsText = await page.locator('#console-logs').innerText();
    expect(logsText).not.toContain('[Parser Error]');
    expect(logsText).not.toContain('[Runtime Error]');
  });

  test('should verify List Comprehension desugars, syncs to blocks, and executes correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');

    // Switch to Python tab
    const pythonTabButton = page.locator('#tab-btn-python');
    await expect(pythonTabButton).toBeVisible();
    await pythonTabButton.click();

    // Switch to Logs tab
    const logsTabButton = page.locator('#tab-btn-logs');
    await expect(logsTabButton).toBeVisible();
    await logsTabButton.click();

    const pythonCodeField = page.locator('#python-code');
    await expect(pythonCodeField).toBeVisible();

    // Input list comprehension preset
    const testCode = 'numbers = [1, 2, 3, 4, 5]\ny = [x * 10 for x in numbers]\nprint(y)';
    await pythonCodeField.fill('');
    await pythonCodeField.fill(testCode);

    // Sync to Blockly
    const syncButton = page.locator('#btn-sync-to-blocks');
    await expect(syncButton).toBeEnabled();
    await syncButton.click();

    // Set speed to max
    await setSpeedToMax(page);

    // Run execution
    const runButton = page.locator('#btn-run');
    await expect(runButton).toBeEnabled();
    await runButton.click();

    // Wait and check console output
    const consoleLogs = page.locator('#console-logs');
    await expect(consoleLogs).toContainText('[10, 20, 30, 40, 50]', { timeout: 10000 });

    // Ensure no parser or runtime errors occurred
    const logsText = await consoleLogs.innerText();
    expect(logsText).not.toContain('[Parser Error]');
    expect(logsText).not.toContain('[Runtime Error]');
  });

  test('should verify Ternary Operator desugars, syncs to blocks, and executes correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const pythonTabButton = page.locator('#tab-btn-python');
    await pythonTabButton.click();

    const logsTabButton = page.locator('#tab-btn-logs');
    await logsTabButton.click();

    const pythonCodeField = page.locator('#python-code');
    await pythonCodeField.fill('');
    await pythonCodeField.fill('speed = 120\nstatus = "Danger" if speed > 100 else "Safe"\nprint(status)');

    const syncButton = page.locator('#btn-sync-to-blocks');
    await syncButton.click();

    // Set speed to max
    await setSpeedToMax(page);

    const runButton = page.locator('#btn-run');
    await runButton.click();

    const consoleLogs = page.locator('#console-logs');
    await expect(consoleLogs).toContainText('Danger', { timeout: 10000 });
  });

  test('should verify Chained Comparison desugars, syncs to blocks, and executes correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const pythonTabButton = page.locator('#tab-btn-python');
    await pythonTabButton.click();

    const logsTabButton = page.locator('#tab-btn-logs');
    await logsTabButton.click();

    const pythonCodeField = page.locator('#python-code');
    await pythonCodeField.fill('');
    await pythonCodeField.fill('speed = 85\nif 60 < speed < 120:\n    print("Cruising")');

    const syncButton = page.locator('#btn-sync-to-blocks');
    await syncButton.click();

    // Set speed to max
    await setSpeedToMax(page);

    const runButton = page.locator('#btn-run');
    await runButton.click();

    const consoleLogs = page.locator('#console-logs');
    await expect(consoleLogs).toContainText('Cruising', { timeout: 10000 });
  });

  test('should verify Augmented Assignment desugars, syncs to blocks, and executes correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const pythonTabButton = page.locator('#tab-btn-python');
    await pythonTabButton.click();

    const logsTabButton = page.locator('#tab-btn-logs');
    await logsTabButton.click();

    const pythonCodeField = page.locator('#python-code');
    await pythonCodeField.fill('');
    await pythonCodeField.fill('count = 0\nfor i in range(4):\n    count += 2\nprint(count)');

    const syncButton = page.locator('#btn-sync-to-blocks');
    await syncButton.click();

    // Set speed to max
    await setSpeedToMax(page);

    const runButton = page.locator('#btn-run');
    await runButton.click();

    const consoleLogs = page.locator('#console-logs');
    await expect(consoleLogs).toContainText('8', { timeout: 10000 });
  });

  test('should verify List Comprehension with if condition desugars, syncs to blocks, and executes correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const pythonTabButton = page.locator('#tab-btn-python');
    await pythonTabButton.click();

    const logsTabButton = page.locator('#tab-btn-logs');
    await logsTabButton.click();

    const pythonCodeField = page.locator('#python-code');
    await pythonCodeField.fill('');
    await pythonCodeField.fill('numbers = [1, 2, 3, 4, 5]\ny = [x * 10 for x in numbers if x > 2]\nprint(y)');

    const syncButton = page.locator('#btn-sync-to-blocks');
    await syncButton.click();

    // Set speed to max
    await setSpeedToMax(page);

    const runButton = page.locator('#btn-run');
    await runButton.click();

    const consoleLogs = page.locator('#console-logs');
    await expect(consoleLogs).toContainText('[30, 40, 50]', { timeout: 10000 });
  });

  test('should verify Nested List Comprehension desugars, syncs to blocks, and executes correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const pythonTabButton = page.locator('#tab-btn-python');
    await pythonTabButton.click();

    const logsTabButton = page.locator('#tab-btn-logs');
    await logsTabButton.click();

    const pythonCodeField = page.locator('#python-code');
    await pythonCodeField.fill('');
    await pythonCodeField.fill('numbers = [1, 2]\ny = [[x * y for x in numbers] for y in [10, 20]]\nprint(y)');

    const syncButton = page.locator('#btn-sync-to-blocks');
    await syncButton.click();

    // Set speed to max
    await setSpeedToMax(page);

    const runButton = page.locator('#btn-run');
    await runButton.click();

    const consoleLogs = page.locator('#console-logs');
    await expect(consoleLogs).toContainText('[[10, 20], [20, 40]]', { timeout: 10000 });
  });

  test('should verify Double Chained Comparison desugars, syncs to blocks, and executes correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const pythonTabButton = page.locator('#tab-btn-python');
    await pythonTabButton.click();

    const logsTabButton = page.locator('#tab-btn-logs');
    await logsTabButton.click();

    const pythonCodeField = page.locator('#python-code');
    await pythonCodeField.fill('');
    await pythonCodeField.fill('x = 15\nif 10 < x < 20 < 30:\n    print("DoubleCruising")');

    const syncButton = page.locator('#btn-sync-to-blocks');
    await syncButton.click();

    // Set speed to max
    await setSpeedToMax(page);

    const runButton = page.locator('#btn-run');
    await runButton.click();

    const consoleLogs = page.locator('#console-logs');
    await expect(consoleLogs).toContainText('DoubleCruising', { timeout: 10000 });
  });

  test('should verify Nested Ternary Operator desugars, syncs to blocks, and executes correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const pythonTabButton = page.locator('#tab-btn-python');
    await pythonTabButton.click();

    const logsTabButton = page.locator('#tab-btn-logs');
    await logsTabButton.click();

    const pythonCodeField = page.locator('#python-code');
    await pythonCodeField.fill('');
    await pythonCodeField.fill('val = 50\nx = "high" if val > 80 else "mid" if val > 40 else "low"\nprint(x)');

    const syncButton = page.locator('#btn-sync-to-blocks');
    await syncButton.click();

    // Set speed to max
    await setSpeedToMax(page);

    const runButton = page.locator('#btn-run');
    await runButton.click();

    const consoleLogs = page.locator('#console-logs');
    await expect(consoleLogs).toContainText('mid', { timeout: 10000 });
  });

  test('should verify parenthesized complex nested ternary operator desugars and executes correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const pythonTabButton = page.locator('#tab-btn-python');
    await pythonTabButton.click();

    const logsTabButton = page.locator('#tab-btn-logs');
    await logsTabButton.click();

    const pythonCodeField = page.locator('#python-code');
    await pythonCodeField.fill('');
    await pythonCodeField.fill('score = 85\nstatus = ("Pass_With_Honor" if score > 90 else "Pass") if score >= 60 else "Fail"\nprint(status)');

    const syncButton = page.locator('#btn-sync-to-blocks');
    await syncButton.click();

    // Set speed to max
    await setSpeedToMax(page);

    const runButton = page.locator('#btn-run');
    await runButton.click();

    const consoleLogs = page.locator('#console-logs');
    await expect(consoleLogs).toContainText('Pass', { timeout: 10000 });
  });

  test('should verify complex chained and logical comparison compiles and executes correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const pythonTabButton = page.locator('#tab-btn-python');
    await pythonTabButton.click();

    const logsTabButton = page.locator('#tab-btn-logs');
    await logsTabButton.click();

    const pythonCodeField = page.locator('#python-code');
    await pythonCodeField.fill('');
    await pythonCodeField.fill('score = 95\ngrade = "A"\nif 0 <= score <= 100 and grade == "A":\n    print("Excellent")');

    const syncButton = page.locator('#btn-sync-to-blocks');
    await syncButton.click();

    // Set speed to max
    await setSpeedToMax(page);

    const runButton = page.locator('#btn-run');
    await runButton.click();

    const consoleLogs = page.locator('#console-logs');
    await expect(consoleLogs).toContainText('Excellent', { timeout: 10000 });
  });

  test('should verify nested list comprehension with filters compiles, syncs and executes correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const pythonTabButton = page.locator('#tab-btn-python');
    await pythonTabButton.click();

    const logsTabButton = page.locator('#tab-btn-logs');
    await logsTabButton.click();

    const pythonCodeField = page.locator('#python-code');
    await pythonCodeField.fill('');
    await pythonCodeField.fill('y = [[x * y for x in [1, 2, 3] if x > 1] for y in [10, 20] if y > 15]\nprint(y)');

    const syncButton = page.locator('#btn-sync-to-blocks');
    await syncButton.click();

    // Set speed to max
    await setSpeedToMax(page);

    const runButton = page.locator('#btn-run');
    await runButton.click();

    const consoleLogs = page.locator('#console-logs');
    await expect(consoleLogs).toContainText('[[40, 60]]', { timeout: 10000 });
  });

  test('should verify logical operator precedence with not, comparisons and or compiles, syncs and executes correctly', async ({ page }) => {
    await page.goto('http://localhost:3000');

    const pythonTabButton = page.locator('#tab-btn-python');
    await pythonTabButton.click();

    const logsTabButton = page.locator('#tab-btn-logs');
    await logsTabButton.click();

    const pythonCodeField = page.locator('#python-code');
    await pythonCodeField.fill('');
    await pythonCodeField.fill('score = 75\ngrade = "B"\nresult = "Pass" if score >= 80 or not grade == "C" else "Fail"\nprint(result)');

    const syncButton = page.locator('#btn-sync-to-blocks');
    await syncButton.click();

    // Set speed to max
    await setSpeedToMax(page);

    const runButton = page.locator('#btn-run');
    await runButton.click();

    const consoleLogs = page.locator('#console-logs');
    await expect(consoleLogs).toContainText('Pass', { timeout: 10000 });
  });
});

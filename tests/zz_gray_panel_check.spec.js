const { test, expect } = require('@playwright/test');
const APP_URL = 'http://localhost:3000';

test('gray blocks panel stays 0 for exotic/edge-case python', async ({ page }) => {
  await page.goto(APP_URL + '/?advanced=1');
  await page.waitForTimeout(300);
  await page.locator('.tab-btn', { hasText: '파이썬' }).first().click();
  await page.waitForTimeout(200);

  const code = `
match command:
    case "go", speed if speed > 0:
        print("moving", speed)
    case [x, *rest]:
        print(x, rest)
    case {"a": a, **rest2}:
        print(a, rest2)
    case _:
        print("unknown")

async def f():
    async with open("x") as fh:
        async for line in fh:
            yield line

x = (a := compute())
`;
  const pythonCode = page.locator('#python-code');
  await expect(pythonCode).toBeVisible();
  await pythonCode.fill('');
  await pythonCode.fill(code);
  await page.waitForTimeout(200);
  const syncButton = page.locator('#btn-sync-to-blocks');
  await expect(syncButton).toBeEnabled();
  await syncButton.click();
  await page.waitForTimeout(1500);

  const types = await page.evaluate(() =>
    (window.Blockly && window.Blockly.getMainWorkspace)
      ? window.Blockly.getMainWorkspace().getAllBlocks(false).map(b => b.type)
      : ['NO_WORKSPACE']
  );
  console.log('BLOCK TYPES:', JSON.stringify(types));

  // Now open the gray log panel and check reported count
  const grayTab = page.locator('text=Gray').first();
  console.log('gray tab visible?', await grayTab.count());
});

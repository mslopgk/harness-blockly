import { test, expect } from '@playwright/test';

// 백엔드(:3001)는 Playwright 가 띄우지 않는다 — 이 테스트는 UI 마운트/토글/지연연결만 본다.
// WS 연결 자체는 실패해도 무방(연결 성공을 단언하지 않음).
test('터미널 패널은 접힘이 기본이고, 열기 전에는 xterm 이 마운트되지 않는다', async ({ page }) => {
  await page.addInitScript(() => localStorage.removeItem('blockpy.terminal.open'));
  await page.goto('/');
  // 열기 전: xterm 미마운트
  await expect(page.locator('.ai-terminal-screen .xterm')).toHaveCount(0);
  // 토글 버튼으로 펼치기
  await page.getByRole('button', { name: /터미널/ }).first().click();
  // 펼친 후: xterm 마운트됨
  await expect(page.locator('.ai-terminal-screen .xterm')).toHaveCount(1, { timeout: 15000 });
});

// 회귀: 터미널을 열면 3열 그리드가 뷰포트를 넘어 터미널 패널이 화면 밖으로 잘리던 버그.
// 편집기 열이 `1fr`(=minmax(auto,1fr))이라 Blockly 의 min-content 아래로 줄지 못해, 세 번째
// (터미널) 열을 더하면 그리드가 가로로 넘쳤다. `minmax(0,1fr)` 로 편집기가 축소되도록 고쳤다.
test('터미널을 열어도 가로 오버플로우가 없고 패널이 뷰포트 안에 들어온다', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.addInitScript(() => localStorage.setItem('blockpy.terminal.open', '1'));
  await page.goto('/');
  await expect(page.locator('.ai-terminal-screen .xterm')).toHaveCount(1, { timeout: 15000 });
  // 문서에 가로 오버플로우가 없어야 한다(반올림 1px 허용).
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(overflow).toBeLessThanOrEqual(1);
  // 터미널 패널의 오른쪽 끝이 뷰포트 안에 있어야 한다.
  const { panelRight, winW } = await page.evaluate(() => ({
    panelRight: Math.round(document.querySelector('.terminal-panel').getBoundingClientRect().right),
    winW: window.innerWidth,
  }));
  expect(panelRight).toBeLessThanOrEqual(winW + 1);
});

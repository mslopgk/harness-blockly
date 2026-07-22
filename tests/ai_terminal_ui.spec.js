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

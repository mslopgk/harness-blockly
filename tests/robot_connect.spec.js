const { test, expect } = require('@playwright/test');

// 로봇 연결 UI 흐름. 실제 하드웨어/DobotLink 없이 /api/robot/* 를 라우트 목으로 처리한다
// (모션 없음, 결정적). 검증: 포트 조회 → 드롭다운 → 연결(상태 표시) → 해제, 그리고 에러 표시.
test.describe('Robot connect UI', () => {
  test('포트 조회 → 연결 → 상태 → 해제', async ({ page }) => {
    await page.route('**/api/robot/ports', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, ports: ['COM8', 'COM5'], device: 'lite' }) }));
    await page.route('**/api/robot/connect', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, device: 'lite', port: 'COM8', status: { pose: { x: 180, y: 60, z: 60 } } }) }));
    await page.route('**/api/robot/disconnect', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, device: 'lite' }) }));

    await page.goto('/');
    await page.locator('#tab-btn-robot').click();

    // 포트가 조회돼 드롭다운에 노출
    await expect(page.locator('#robot-port-select')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('#robot-port-select option')).toContainText(['포트 선택…', 'COM8', 'COM5']);

    // COM8 선택 → 연결
    await page.locator('#robot-port-select').selectOption('COM8');
    await page.locator('#robot-connect-btn').click();

    // 상태: 연결됨 + 포트 + pose 요약
    await expect(page.locator('#robot-status')).toContainText('연결됨', { timeout: 15000 });
    await expect(page.locator('#robot-status')).toContainText('COM8');
    await expect(page.locator('#robot-status')).toContainText('x180');

    // 해제 → 연결 안 됨
    await page.locator('#robot-disconnect-btn').click();
    await expect(page.locator('#robot-status')).toContainText('연결 안 됨', { timeout: 15000 });
  });

  test('연결 실패 시 에러+힌트 표시', async ({ page }) => {
    await page.route('**/api/robot/ports', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, ports: ['COM8'], device: 'lite' }) }));
    await page.route('**/api/robot/connect', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: false, error: 'cannot connect to DobotLink', hint: 'DobotLink.exe를 실행한 뒤 다시 시도하세요.' }) }));

    await page.goto('/');
    await page.locator('#tab-btn-robot').click();
    await expect(page.locator('#robot-port-select')).toBeVisible({ timeout: 15000 });
    await page.locator('#robot-port-select').selectOption('COM8');
    await page.locator('#robot-connect-btn').click();

    await expect(page.locator('#robot-error')).toContainText('cannot connect to DobotLink', { timeout: 15000 });
    await expect(page.locator('#robot-error')).toContainText('DobotLink.exe');
    await expect(page.locator('#robot-status')).toContainText('연결 안 됨');
  });
});

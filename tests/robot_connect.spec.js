const { test, expect } = require('@playwright/test');

// 로봇 연결 UI 흐름. 실제 하드웨어/DobotLink 없이 /api/robot/* 를 라우트 목으로 처리한다
// (모션 없음, 결정적). 검증: 포트 조회 → 드롭다운 → 연결(상태 표시) → 해제, 에러 표시,
// 그리고 팔 연결 시 캘리브레이션이 실제 이동 훅(move-preset)을 부르는 배선.
test.use({
  launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] },
});

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

  test('팔 연결 시 캘리브레이션 재보정이 실제 이동 훅을 호출', async ({ page }) => {
    let movePresetBody = null;
    await page.route('**/api/robot/ports', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, ports: ['COM8'], device: 'lite' }) }));
    await page.route('**/api/robot/connect', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, device: 'lite', port: 'COM8', status: { pose: { x: 200, y: 0, z: 40 } } }) }));
    await page.route('**/api/robot/move-preset', (route) => {
      movePresetBody = JSON.parse(route.request().postData() || '{}');
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, moved: true, target: [200, -80, 40] }) });
    });

    await page.goto('/');
    await page.locator('#tab-btn-robot').click();

    // 팔(lite) 연결 → armWired 활성 → 캘리브레이션이 실제 훅을 받음
    await expect(page.locator('#robot-port-select')).toBeVisible({ timeout: 15000 });
    await page.locator('#robot-port-select').selectOption('COM8');
    await page.locator('#robot-connect-btn').click();
    await expect(page.locator('#robot-status')).toContainText('연결됨', { timeout: 15000 });

    // 재보정 시작 → 첫 프리셋으로 이동 호출(home=true) → 뱃지 '팔이 가리킴'
    await page.locator('#calib-start').click();
    await expect(page.locator('#calib-robot-badge')).toContainText('팔이 가리킴', { timeout: 15000 });
    await expect.poll(() => movePresetBody && movePresetBody.home, { timeout: 15000 }).toBe(true);
    expect(movePresetBody.port).toBe('COM8');
    expect(movePresetBody.x).toBe(200);
  });
});

const { test, expect } = require('@playwright/test');

// 카메라↔로봇 캘리브레이션 UI 흐름 테스트. 백엔드/하드웨어 불필요:
//  - 로봇 이동은 스텁(dobotkit 대기)
//  - 카메라는 Chromium 가짜 미디어스트림(--use-fake-device-for-media-stream)
// 검증: 미측정 상태 표시 → 재보정 시작 → 프리셋 4점 클릭(비일직선) → 아핀 풀이 → 저장 → 사용중.
test.use({
  launchOptions: {
    args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
  },
});

test.describe('Robot calibration panel', () => {
  test('recalibrate flow: 미측정 → 4점 클릭 → 풀이 → 저장', async ({ page }) => {
    await page.addInitScript(() => {
      try { window.localStorage.removeItem('blockpy.robotCalib.v1'); } catch (_) {}
    });
    await page.goto('/');

    await page.locator('#tab-btn-robot').click();

    // seed 가 미측정(M=null)이라 재보정 필요 안내가 떠야 한다.
    await expect(page.locator('#calib-status')).toContainText('미측정');

    await page.locator('#calib-start').click();
    await expect(page.locator('#calib-step')).toContainText('점 1/4');

    const wrap = page.locator('#calib-video-wrap');
    await expect(wrap).toBeVisible();

    // 4개의 비일직선 지점을 클릭(코너 배치) → 각 클릭이 프리셋 1점과 대응.
    const spots = [{ x: 40, y: 40 }, { x: 300, y: 40 }, { x: 300, y: 220 }, { x: 40, y: 220 }];
    await wrap.click({ position: spots[0] });
    await expect(page.locator('#calib-step')).toContainText('점 2/4');
    await wrap.click({ position: spots[1] });
    await expect(page.locator('#calib-step')).toContainText('점 3/4');
    await wrap.click({ position: spots[2] });
    await expect(page.locator('#calib-step')).toContainText('점 4/4');
    await wrap.click({ position: spots[3] });

    // 풀이 완료 화면 + 저장 → 사용 중 상태로 전환.
    await expect(page.locator('#calib-solved')).toBeVisible();
    await page.locator('#calib-save').click();
    await expect(page.locator('#calib-status')).toContainText('고정 캘리브레이션 사용 중');
  });
});

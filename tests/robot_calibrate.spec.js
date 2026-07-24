const { test, expect } = require('@playwright/test');

// 카메라↔로봇 캘리브레이션 UI 흐름 테스트 (eye-in-hand 2단계). 백엔드/하드웨어 불필요:
//  - 로봇 이동은 스텁(팔 미연결 → onMoveToPreset undefined)
//  - 카메라는 Chromium 가짜 미디어스트림(--use-fake-device-for-media-stream)
// 검증: 미측정 → 재보정 시작 → 표시 4점(다음 지점) → 관측 자세 → 4점 클릭(비일직선) → 풀이 → 저장.
test.use({
  launchOptions: {
    args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
  },
});

test.describe('Robot calibration panel (eye-in-hand 2단계)', () => {
  test('recalibrate flow: 미측정 → 표시 → 관측 → 4점 클릭 → 풀이 → 저장', async ({ page }) => {
    await page.addInitScript(() => {
      try { window.localStorage.removeItem('blockpy.robotCalib.v1'); } catch (_) {}
    });
    await page.goto('/');

    // 사이드 rail 의 'Robot' 아이콘 → 도구 팝업 열림.
    await page.locator('button[aria-label="Robot"]').click();

    // seed 가 미측정(M=null)이라 재보정 필요 안내가 떠야 한다.
    await expect(page.locator('#calib-status')).toContainText('미측정');

    // ── 1단계: 표시(팔이 4곳 가리킴 → 스티커). 스텁이라 실이동 없이 진행. ──
    await page.locator('#calib-start').click();
    await expect(page.locator('#calib-mark-step')).toContainText('표시 1/4');
    await page.locator('#calib-next-mark').click();
    await expect(page.locator('#calib-mark-step')).toContainText('표시 2/4');
    await page.locator('#calib-next-mark').click();
    await expect(page.locator('#calib-mark-step')).toContainText('표시 3/4');
    await page.locator('#calib-next-mark').click();
    await expect(page.locator('#calib-mark-step')).toContainText('표시 4/4');
    // 마지막 표시 후 버튼 = '관측 자세로 →' → 2단계로.
    await page.locator('#calib-next-mark').click();

    // ── 2단계: 관측 자세(고정) + 화면에서 스티커 4개 클릭(비일직선 코너 배치). ──
    const wrap = page.locator('#calib-video-wrap');
    await expect(wrap).toBeVisible();
    await expect(page.locator('#calib-click-step')).toContainText('클릭 1/4');

    const spots = [{ x: 40, y: 40 }, { x: 340, y: 40 }, { x: 340, y: 240 }, { x: 40, y: 240 }];
    await wrap.click({ position: spots[0] });
    await expect(page.locator('#calib-click-step')).toContainText('클릭 2/4');
    await wrap.click({ position: spots[1] });
    await expect(page.locator('#calib-click-step')).toContainText('클릭 3/4');
    await wrap.click({ position: spots[2] });
    await expect(page.locator('#calib-click-step')).toContainText('클릭 4/4');
    await wrap.click({ position: spots[3] });

    // 풀이 완료 화면 + 저장 → 사용 중 상태로 전환.
    await expect(page.locator('#calib-solved')).toBeVisible();
    await page.locator('#calib-save').click();
    await expect(page.locator('#calib-status')).toContainText('고정 캘리브레이션 사용 중');
  });
});

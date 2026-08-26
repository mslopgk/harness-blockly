const { test, expect } = require('@playwright/test');

// TM 전체 UI 흐름. 실제 MobileNet/카메라 없이:
//  - featurize 는 가짜(window.__TM_TEST_FEATURIZER) → 고정 4차원 벡터
//  - 카메라는 Chromium 가짜 미디어스트림
//  - 저장 /api/tm/train 은 라우트 목으로 200 처리(백엔드·파이썬 학습 불필요)
//    저장은 브라우저 head 를 내보내는 게 아니라 원본 프레임을 백엔드로 보내 파이썬이 다시
//    학습해 <이름>.npz 를 만드는 경로다(TF.js 임베딩 ≠ Keras 임베딩이라 재사용 불가).
// 검증: TM 탭 → 클래스 2개 → 각 샘플 수집 → 학습 → 미리보기 라벨 → 파일명 저장 성공.
test.use({
  launchOptions: {
    args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
  },
});

test.describe('Teachable Machine UI', () => {
  test('탭 → 샘플 수집 → 학습 → 미리보기 → 저장', async ({ page }) => {
    await page.addInitScript(() => {
      // MobileNet 대체: 어떤 입력이든 고정 4차원 벡터 반환(흐름 검증용).
      window.__TM_TEST_FEATURIZER = () => [0.11, 0.22, 0.33, 0.44];
    });
    // 저장 백엔드 목 — 파이썬 재학습은 수십 초 걸리므로 목으로 즉시 응답한다.
    await page.route('**/api/tm/train', (route) => {
      if (route.request().method() === 'POST') {
        return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ ok: true, path: 'my-model.npz' }) });
      }
      return route.continue();
    });

    await page.goto('/');
    await page.locator('#tab-btn-tm').click();

    await expect(page.locator('#tm-class-0')).toBeVisible();
    await expect(page.locator('#tm-class-1')).toBeVisible();

    // 각 클래스 샘플 수집: capture 버튼 누른 채로 잠깐 대기 → 놓기
    for (const idx of [0, 1]) {
      const btn = page.locator(`#tm-capture-${idx}`);
      await btn.hover();
      await page.mouse.down();
      await page.waitForTimeout(450); // CAPTURE_MS=100 → 최소 4프레임
      await page.mouse.up();
      await expect.poll(async () => {
        const txt = await page.locator(`#tm-count-${idx}`).textContent();
        return Number((txt || '').replace(/[^0-9]/g, '')) || 0;
      }, { timeout: 10000 }).toBeGreaterThanOrEqual(1);
    }

    // 학습
    await page.locator('#tm-train').click();
    await expect(page.locator('#tm-trained')).toBeVisible({ timeout: 30000 });

    // 라이브 미리보기 라벨(두 클래스 중 하나)
    await expect(page.locator('#tm-preview-label')).toHaveText(/클래스 1|클래스 2/, { timeout: 15000 });

    // 저장
    await page.locator('#tm-filename').fill('my-model');
    await page.locator('#tm-save').click();
    await expect(page.locator('#tm-save-status')).toContainText('my-model.npz', { timeout: 15000 });
  });
});

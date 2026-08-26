const { test, expect } = require('@playwright/test');

// 강의자료 수업 예제(파일 서빙 + 지연 로드) 흐름:
//  좌측 '예제' 탭 → '수업 (고등)' 필터 → 수업 카드 클릭 → public/examples/*.py 를 fetch 해
//  파이썬 편집기에 로드(대용량이라 자동 블록 변환은 하지 않음; 백엔드 불필요, Vite가 파일 서빙).
test.describe('Example Gallery Tab — 수업(강의자료) 예제', () => {
  test('탭 → 수업 카드 → 파일 지연 로드 → 파이썬 편집기 반영', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(
      () => !!(window.BlockPyLessonExamples && window.BlockPyExamples && window.__blocklyWorkspace),
      null, { timeout: 60000 },
    );

    // 수업 예제 15개 등록 확인 (2026-08-11: 차시별 3단계로 쪼갬 — 중등 6 + 고등 9)
    expect(await page.evaluate(() => window.BlockPyLessonExamples.length)).toBe(15);

    // 좌측 '예제' 탭 열기 → '수업 (고등)' 필터(H1/H2/H3 × 3단계 → 9개)
    await page.locator('#tab-btn-examples').click();
    await expect(page.locator('#example-card-grid')).toBeVisible();
    await page.locator('.example-cat-chip', { hasText: '수업 (고등)' }).click();
    await expect.poll(async () => page.locator('#example-card-grid .example-card').count()).toBe(9);

    // 수업 카드(h3) 클릭 → 파일 지연 로드
    await page.locator('[data-example-id="lesson-h3-drive"]').click();

    // 파이썬 편집기에 파일 내용 로드([H3] 태그·본문 키워드 포함)
    await expect(page.locator('#python-code')).toHaveValue(/\[H3\]/, { timeout: 20000 });
    await expect(page.locator('#python-code')).toHaveValue(/자율주행/, { timeout: 5000 });
  });
});

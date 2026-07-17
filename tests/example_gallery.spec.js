const { test, expect } = require('@playwright/test');

// 예제 좌측 보조 탭 흐름:
//  탭 열기 → 카드 목록(인라인 스니펫 + 수업 예제 합계) → 카테고리 필터 →
//  인라인 예제 불러오기(코드 반영 + 자동 블록 변환) → 상단 '예제' 버튼도 같은 탭을 연다.
test.describe('Example Gallery Tab', () => {
  test('탭 → 목록 → 필터 → 인라인 예제 불러오기 → 자동 변환', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(
      () => !!(window.__blocklyWorkspace && window.BlockPyExamples && window.BlockPyAstBridge),
      null, { timeout: 60000 },
    );
    // 갤러리는 인라인 스니펫 + 파일 서빙 수업 예제를 합쳐 보여준다.
    const total = await page.evaluate(
      () => window.BlockPyExamples.length + (window.BlockPyLessonExamples ? window.BlockPyLessonExamples.length : 0),
    );
    expect(total).toBeGreaterThan(0);

    // 좌측 '예제' 탭 열기
    await page.locator('#tab-btn-examples').click();
    await expect(page.locator('#example-card-grid')).toBeVisible();

    // 카드 수 = 두 소스 합계
    await expect.poll(async () => page.locator('#example-card-grid .example-card').count()).toBe(total);

    // 카테고리 필터: 'Basics' → Basics 카드만
    const basicsCount = await page.evaluate(
      () => window.BlockPyExamples.filter((s) => s.category === 'Basics').length,
    );
    await page.locator('.example-cat-chip', { hasText: 'Basics' }).click();
    await expect.poll(async () => page.locator('#example-card-grid .example-card').count()).toBe(basicsCount);

    // 인라인 예제 불러오기 → 파이썬 코드 반영 + 자동 변환(Code Valid + 블록 생성)
    await page.locator('[data-example-id="basics-arith"]').click();
    const expected = await page.evaluate(() => window.BlockPyExamples.find((s) => s.id === 'basics-arith').code);
    await expect(page.locator('#python-code')).toHaveValue(expected, { timeout: 15000 });
    await expect(page.locator('#syntax-status-text.valid')).toBeVisible({ timeout: 30000 });
    await expect.poll(async () => page.evaluate(
      () => (window.__blocklyWorkspace ? window.__blocklyWorkspace.getAllBlocks(false).length : 0),
    ), { timeout: 30000 }).toBeGreaterThan(0);

    // 상단 액션 바 '예제' 버튼도 좌측 탭을 연다
    await page.locator('#tab-btn-files').click();
    await expect(page.locator('#example-card-grid')).toHaveCount(0);
    await page.locator('#btn-examples').click();
    await expect(page.locator('#example-card-grid')).toBeVisible();
  });
});

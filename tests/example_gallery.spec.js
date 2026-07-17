const { test, expect } = require('@playwright/test');

// 예제 갤러리 전체 흐름: 버튼 → 모달 → 카테고리 필터 → 카드 불러오기(코드 반영 + 자동 블록 변환) → 닫기.
// 백엔드 불필요: 변환은 페이지 내 Pyodide로, 로드 대상 basics-arith 는 import가 없어 오프라인에서 완전 변환된다.
test.describe('Example Gallery', () => {
  test('버튼 → 모달 → 필터 → 불러오기 → 자동 변환 → 닫기', async ({ page }) => {
    await page.goto('/');

    // 앱/변환 파이프라인 준비 대기(스타트업 데모가 이미 변환되어 워크스페이스가 뜬 상태).
    await page.waitForFunction(
      () => !!(window.__blocklyWorkspace && window.BlockPyExamples && window.BlockPyAstBridge),
      null, { timeout: 60000 },
    );
    // 갤러리는 인라인 스니펫 + 파일 서빙 수업 예제를 합쳐 보여준다 → 전체 카드 수는 두 소스 합계.
    const total = await page.evaluate(
      () => window.BlockPyExamples.length + (window.BlockPyLessonExamples ? window.BlockPyLessonExamples.length : 0),
    );
    expect(total).toBeGreaterThan(0);

    // 1) 버튼으로 모달 열기
    await page.locator('#btn-examples').click();
    await expect(page.locator('.example-gallery-box')).toBeVisible();

    // 2) 카드 수 = 전체 예제 수
    await expect.poll(async () => page.locator('#example-card-grid .example-card').count())
      .toBe(total);

    // 3) 카테고리 필터: 'Basics' 칩 클릭 → Basics 예제만
    const basicsCount = await page.evaluate(
      () => window.BlockPyExamples.filter((s) => s.category === 'Basics').length,
    );
    await page.locator('.example-cat-chip', { hasText: 'Basics' }).click();
    await expect.poll(async () => page.locator('#example-card-grid .example-card').count())
      .toBe(basicsCount);

    // 4) basics-arith 카드 불러오기
    await page.locator('[data-example-id="basics-arith"]').click();
    // 모달 닫힘 + 코드 반영(파이썬 탭)
    await expect(page.locator('.example-gallery-box')).toHaveCount(0);
    const expected = await page.evaluate(
      () => window.BlockPyExamples.find((s) => s.id === 'basics-arith').code,
    );
    await expect(page.locator('#python-code')).toHaveValue(expected, { timeout: 15000 });
    // 자동 블록 변환: 새 코드가 오류 없이 변환됨(Code Valid) + 워크스페이스에 블록 존재.
    await expect(page.locator('#syntax-status-text.valid')).toBeVisible({ timeout: 30000 });
    await expect.poll(async () => page.evaluate(
      () => (window.__blocklyWorkspace ? window.__blocklyWorkspace.getAllBlocks(false).length : 0),
    ), { timeout: 30000 }).toBeGreaterThan(0);

    // 5) 다시 열고 Esc로 닫기
    await page.locator('#btn-examples').click();
    await expect(page.locator('.example-gallery-box')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('.example-gallery-box')).toHaveCount(0);

    // 6) 백드롭 클릭 닫기
    await page.locator('#btn-examples').click();
    await expect(page.locator('.example-gallery-box')).toBeVisible();
    await page.locator('.example-gallery-overlay').click({ position: { x: 5, y: 5 } });
    await expect(page.locator('.example-gallery-box')).toHaveCount(0);
  });
});

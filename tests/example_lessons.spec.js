const { test, expect } = require('@playwright/test');

// 강의자료 수업 예제(파일 서빙 + 지연 로드) 흐름:
//  갤러리 → 수업 카드 클릭 → public/examples/*.py 를 fetch 해 파이썬 편집기에 로드.
//  대용량이라 로드 시 자동 블록 변환은 하지 않는다(코드만 로드; 백엔드 불필요, Vite가 파일 서빙).
test.describe('Example Gallery — 수업(강의자료) 예제', () => {
  test('수업 카드 → 파일 지연 로드 → 파이썬 편집기 반영', async ({ page }) => {
    await page.goto('/');
    await page.waitForFunction(
      () => !!(window.BlockPyLessonExamples && window.BlockPyExamples && window.__blocklyWorkspace),
      null, { timeout: 60000 },
    );

    // 수업 예제 5개 등록 확인
    const lessonCount = await page.evaluate(() => window.BlockPyLessonExamples.length);
    expect(lessonCount).toBe(5);

    // 갤러리 열기 → 수업 카드가 그리드에 노출
    await page.locator('#btn-examples').click();
    await expect(page.locator('.example-gallery-box')).toBeVisible();
    const card = page.locator('[data-example-id="lesson-h3-drive"]');
    await expect(card).toBeVisible();

    // '수업 (고등)' 카테고리 칩으로 필터되는지(고등 = H1/H2/H3 → 3개)
    await page.locator('.example-cat-chip', { hasText: '수업 (고등)' }).click();
    await expect.poll(async () => page.locator('#example-card-grid .example-card').count()).toBe(3);

    // 카드 클릭 → 파일 지연 로드
    await page.locator('[data-example-id="lesson-h3-drive"]').click();

    // 모달 닫힘 + 파이썬 편집기에 파일 내용 로드([H3] 태그·본문 키워드 포함)
    await expect(page.locator('.example-gallery-box')).toHaveCount(0);
    await expect(page.locator('#python-code')).toHaveValue(/\[H3\]/, { timeout: 20000 });
    await expect(page.locator('#python-code')).toHaveValue(/자율주행/, { timeout: 5000 });
  });
});

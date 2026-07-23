import { test, expect } from '@playwright/test';

// 백엔드(:3001)가 있어야 하는 통합 테스트 — 없으면 skip(실패 아님).
// 워크스페이스의 main.py 를 외부에서(터미널의 AI 에이전트처럼) 바꾸면 편집기가 자동 리로드하는지 확인.
// 원본 main.py 내용은 테스트 후 복구한다(사용자 워크스페이스 오염 방지).
test('활성 main.py 가 디스크에서 바뀌면 편집기가 자동 리로드한다', async ({ page }) => {
  const health = await page.request.get('http://localhost:3000/api/health').catch(() => null);
  test.skip(!health || !health.ok(), '백엔드(:3001)가 실행 중이어야 함');

  const orig = await page.request.get('http://localhost:3000/api/fs/file?path=main.py');
  const origContent = orig.ok() ? ((await orig.json()).content || '') : '';

  try {
    await page.goto('/');
    await expect(page.locator('.active-file-chip')).toContainText('main.py', { timeout: 20000 });
    const ta = page.locator('.code-editor-wrapper textarea');
    await expect(ta).not.toHaveValue('', { timeout: 20000 }); // 초기 로드 완료 대기

    const marker = 'AUTORELOAD_' + Date.now();
    const resp = await page.request.post('http://localhost:3000/api/fs/file', {
      data: { path: 'main.py', content: `# ${marker}\nprint("${marker}")\n` },
      headers: { 'Content-Type': 'application/json' },
    });
    expect(resp.ok()).toBeTruthy();

    // 폴링(~1.5s)이 디스크 변경을 잡아 편집기를 리로드할 때까지 대기.
    await expect(ta).toHaveValue(new RegExp(marker), { timeout: 10000 });
  } finally {
    await page.request.post('http://localhost:3000/api/fs/file', {
      data: { path: 'main.py', content: origContent },
      headers: { 'Content-Type': 'application/json' },
    }).catch(() => {});
  }
});

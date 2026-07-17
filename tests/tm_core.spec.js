const { test, expect } = require('@playwright/test');

// teachable.js + tmPack.js 통합. UI 없이 window.BlockPyTM 을 직접 구동한다.
// 실제 MobileNet 은 로드하지 않고(직접 임베딩 텐서 주입) tf.js 로만 head 학습/직렬화/역직렬화 왕복을 검증.
test.describe('Teachable Machine core (teachable+tmPack)', () => {
  test('build → train → serialize(blockpy-tm-v1) → deserialize 왕복', async ({ page }) => {
    await page.goto('/');
    await expect.poll(async () => page.evaluate(() => !!window.BlockPyTM), { timeout: 30000 }).toBe(true);

    const result = await page.evaluate(async () => {
      const TM = window.BlockPyTM;
      const tf = await TM.ensureTf();
      const mk = (cls, a, b) => ({ classIndex: cls, embedding: tf.tensor2d([[a, b, a * 0.5, 1 - b]], [1, 4]) });
      const samples = [mk(0, 0.9, 0.1), mk(0, 0.8, 0.2), mk(1, 0.1, 0.9), mk(1, 0.2, 0.8)];
      const head = await TM.buildHead(4, 2);
      await TM.trainHead(head, samples, 2, { epochs: 5 });
      const json = await TM.serializeModel({ head, labels: ['A', 'B'] });
      const parsed = JSON.parse(json);
      const back = await TM.deserializeModel(json);
      const pred = await TM.predictTop(back.head, tf.tensor2d([[0.9, 0.1, 0.45, 0.9]], [1, 4]), back.labels);
      return {
        format: parsed.format,
        labels: parsed.labels,
        base: parsed.base,
        imageSize: parsed.imageSize,
        weightsIsString: typeof parsed.head.weightData === 'string' && parsed.head.weightData.length > 0,
        backLabels: back.labels,
        predLabel: pred.label,
        predConfIsNum: typeof pred.confidence === 'number',
      };
    });

    expect(result.format).toBe('blockpy-tm-v1');
    expect(result.labels).toEqual(['A', 'B']);
    expect(result.base).toBe('mobilenet-v2');
    expect(result.imageSize).toBe(224);
    expect(result.weightsIsString).toBe(true);
    expect(result.backLabels).toEqual(['A', 'B']);
    expect(['A', 'B']).toContain(result.predLabel);
    expect(result.predConfIsNum).toBe(true);
  });

  test('featurize() test-hook 경로 — window.__TM_TEST_FEATURIZER 로 MobileNet 미로드 임베딩 생성', async ({ page }) => {
    // 앱 로드 전에 테스트 featurizer 를 주입해야 teachable.js 의 testFeaturizer() 가 이를 감지한다.
    await page.addInitScript(() => {
      window.__TM_TEST_FEATURIZER = () => [0.1, 0.2, 0.3, 0.4];
    });
    await page.goto('/');
    await expect.poll(async () => page.evaluate(() => !!window.BlockPyTM), { timeout: 30000 }).toBe(true);

    const shape = await page.evaluate(async () => {
      const TM = window.BlockPyTM;
      const emb = await TM.featurize(document.createElement('canvas'));
      const shape = emb.shape;
      emb.dispose();
      return shape;
    });

    expect(shape).toEqual([1, 4]);
  });

  test('오프라인 자산 누락 시 featurize 가 친절한 에러로 실패한다(fail-loud)', async ({ page }) => {
    // 벤더된 MobileNet model.json 요청을 404 로 막아 "자산 없음" 상황을 결정적으로 재현.
    await page.route('**/vendor/mobilenet/model.json', (route) => route.fulfill({ status: 404, body: 'not found' }));
    await page.goto('/');
    await expect.poll(async () => page.evaluate(() => !!window.BlockPyTM), { timeout: 30000 }).toBe(true);
    const err = await page.evaluate(async () => {
      try {
        await window.BlockPyTM.featurize(document.createElement('canvas'));
        return null;
      } catch (e) {
        return String((e && e.message) || e);
      }
    });
    expect(err).toBeTruthy();
    expect(err).toMatch(/vendor|MobileNet/i);
  });
});

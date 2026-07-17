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
});

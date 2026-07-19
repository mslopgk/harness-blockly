const { test, expect } = require('@playwright/test');
const APP_URL = 'http://localhost:' + (process.env.PORT || '3000') + '/';
const path = require('path');
const { spawnSync } = require('child_process');

// 파이썬 네이티브 TM: runtime/tm.py 를 PYTHONPATH 로 실어 `import tm` (server.js run-python 과 동일
// 메커니즘) + 마운트 시 builtin 으로 등록되는 "tm" 토크박스 블록. 학습·추론 전부 파이썬(자기일관).

// tm 런타임이 PYTHONPATH(runtime/)로 import 되는지 — server.js 가 쓰는 것과 동일 메커니즘.
test.describe('tm runtime import via PYTHONPATH (node)', () => {
  test('import tm 성공(runtime/ 를 PYTHONPATH 에 실으면)', () => {
    const repo = path.join(__dirname, '..');
    const runtime = path.join(repo, 'runtime');
    const PY = process.env.PYTHON_CMD || 'python';
    const r = spawnSync(PY, ['-c', 'import tm; print("TMOK", hasattr(tm, "Model"), hasattr(tm, "load_model"))'], {
      env: { ...process.env, PYTHONPATH: [runtime, process.env.PYTHONPATH].filter(Boolean).join(path.delimiter), PYTHONIOENCODING: 'utf-8' },
      encoding: 'utf-8',
    });
    expect(r.stdout || '').toContain('TMOK True True');
  });
});

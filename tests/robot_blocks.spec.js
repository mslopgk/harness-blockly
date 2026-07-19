const { test, expect } = require('@playwright/test');
const APP_URL = 'http://localhost:' + (process.env.PORT || '3000') + '/';

// dobotkit 고정 블록: 마운트 시 builtin 으로 등록되는 "dobotkit" 토크박스 블록(팔 MagicianLite +
// 차 MagicianGO). 블록은 일반 Call IR 위 Tier-A 스킨이라 파이썬으로 무손실 변환되고, dobotkit이
// 백엔드에 설치돼 있으면 Run 시 실제 로봇이 움직인다. 스펙은 src/data/robotSpecs.json(hand-curated).

// ── Node-level: robotSpecs.json 이 등록 가능한 dobotkit 스펙을 담는지 ──
require('../src/utils/libRegistry.js');
require('../src/utils/libImport.js');
const REG = global.BlockPyLibRegistry;
const IMP = global.BlockPyLibImport;
let robotSpecs;
try { robotSpecs = require('../src/data/robotSpecs.json'); } catch (_) { robotSpecs = null; }

test.describe('robotSpecs bundle (node)', () => {
  test('robotSpecs.json 은 dobotkit 모듈 스펙 배열', () => {
    expect(Array.isArray(robotSpecs)).toBe(true);
    const dk = robotSpecs.find((m) => m.module === 'dobotkit');
    expect(dk).toBeTruthy();
    expect(dk.entries.length).toBeGreaterThanOrEqual(18);
  });

  test('모든 entry 가 등록되고 핵심 블록이 기대 형태/타입으로 매핑', () => {
    REG.clearAll();
    const dk = robotSpecs.find((m) => m.module === 'dobotkit');
    const { specs } = IMP.librarySpecToRegistrySpecs(dk, { both: false });
    const byType = {};
    for (const s of specs) {
      const res = REG.registerLibBlock({ ...s, builtin: true });
      expect(res.ok).toBe(true);              // 모든 스펙 등록 성공(충돌/무효 없음)
      byType[res.type] = s;
    }
    // 대표 타입 존재 + 값/명령 구분 + lib 태그
    expect(byType['lib_dobotkit_MagicianLite']).toMatchObject({ hasOutput: true, lib: 'dobotkit' });
    expect(byType['lib_arm_move_to_stmt']).toMatchObject({ hasOutput: false, module: 'arm', func: 'move_to' });
    expect(byType['lib_arm_get_pose']).toMatchObject({ hasOutput: true });
    expect(byType['lib_MagicianGO_open']).toMatchObject({ hasOutput: true, module: 'MagicianGO', func: 'open' });
    expect(byType['lib_car_battery']).toMatchObject({ hasOutput: true, module: 'car', func: 'battery' });
    REG.clearAll();
  });
});

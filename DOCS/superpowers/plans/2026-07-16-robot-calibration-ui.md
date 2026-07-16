# 카메라↔로봇 캘리브레이션 UI — 구현 계획

> 설계: `../specs/2026-07-16-robot-calibration-ui-design.md`. 프론트 전용. 블록 코어 무수정.

**목표**: Robot 탭에 캘리브레이션 UI 추가 — 기본은 저장/동봉 캘리값 자동 로드, 없으면
"최초 1회 재보정" 유도, 재보정은 접근 1(로봇 프리셋 자동이동[스텁]→화면 클릭→아핀 풀이→저장).

**기술**: React 19, getUserMedia(웹캠), 순수 JS 아핀 최소제곱, localStorage, Playwright.

## 전역 제약
- `src/utils/irBlocks.js`/`irToBlockly.js`/`blocklyToIr.js`/`irToolbox.js` **수정 금지**.
- 로봇 실이동·캘리값 소비는 dobotkit 확정 후 배선 — 지금은 `onMoveToPreset` 스텁 1곳만.
- 실측 안 된 캘리 행렬을 지어내 기본값으로 박지 않는다(seed = 미측정).

## Task 1 — `src/utils/affineCalib.js` (순수 아핀 수학)
**Files:** Create `src/utils/affineCalib.js`
**Interfaces (Produces):**
- `estimateAffine(pairs) → M`  pairs=`[[[u,v],[x,y]], …]`(≥3), M=`[[a,b,c],[d,e,f]]`. 최소제곱(정규방정식). n<3 또는 퇴화 → `throw Error`.
- `applyAffine(M,[u,v]) → [x,y]`  = `[a*u+b*v+c, d*u+e*v+f]`.
- `isDegenerate(pairs) → bool`  픽셀점 거의 일직선(정규행렬 det≈0).
- `reprojectionError(M,pairs) → {mean,max}` (mm).

- [ ] 1. 구현 (아래 코드).
- [ ] 2. 검증(scratch): 알려진 아핀 x=0.5u+100, y=−0.4v+180 로 합성 4점 → `estimateAffine` 복원 → `applyAffine(320,240)≈(260,84)`, `reprojectionError.mean≈0`; 일직선 4점 → `isDegenerate=true`. (Task 4 Playwright가 UI-in-situ 재검증.)

```js
// 정규방정식 A^T A p = A^T b (A행 = [u,v,1]) — 3x3 가우스 소거로 품.
function solve3(M, b) { /* [M|b] 부분피벗 가우스 소거 → [p0,p1,p2] 또는 null(특이) */ }
function normalEqn(pairs, axis) { /* Σ 로 3x3 ATA 와 3-vec ATb 구성(axis 0=x,1=y) */ }
export function isDegenerate(pairs) { /* ATA(x) det≈0 (scale 상대) → true */ }
export function estimateAffine(pairs) {
  if (pairs.length < 3) throw new Error('아핀 추정에는 대응점 3개 이상이 필요합니다');
  if (isDegenerate(pairs)) throw new Error('대응점이 거의 한 직선 위입니다 — 넓게 다시 찍으세요');
  const [ax] = normalEqn(pairs,0), [ay] = normalEqn(pairs,1);
  const px = solve3(...ax), py = solve3(...ay);
  if (!px || !py) throw new Error('아핀을 풀 수 없습니다(퇴화)');
  return [px, py];
}
export function applyAffine(M,[u,v]){ return [M[0][0]*u+M[0][1]*v+M[0][2], M[1][0]*u+M[1][1]*v+M[1][2]]; }
export function reprojectionError(M,pairs){ /* hypot 평균/최대 */ }
```

## Task 2 — `src/data/robotCalib.default.json` (seed, 미측정)
**Files:** Create `src/data/robotCalib.default.json`
- [ ] 1. `{ "version": 1, "measured": false, "M": null, "presets": [[200,-80],[200,80],[300,80],[300,-80]], "note": "실측 후 M 채우기(dobotkit/하드웨어 확정 후)" }`

## Task 3 — `src/components/RobotCalibrate.jsx`
**Files:** Create `src/components/RobotCalibrate.jsx`
**Consumes:** `affineCalib.js`, `robotCalib.default.json`.
**Interfaces (Produces):** default export `<RobotCalibrate onMoveToPreset? />`.
- prop `onMoveToPreset(preset:[x,y]) → Promise` (기본 = 스텁: `console.warn` + 즉시 resolve, "미연결" 배지).
- 상태: `calib`(로드된 M/measured), `mode`('idle'|'capturing'|'solved'), `stepIndex`, `pairs`, 웹캠 refs, `error`.
- 로드: mount 시 localStorage `blockpy.robotCalib.v1` > seed default > 미측정.
- 웹캠: getUserMedia({video}) → `<video>` + 클릭 오버레이(클릭→비디오 좌표→프레임 픽셀 스케일 보정).
- 재보정: 시작→각 preset: `await onMoveToPreset(preset)`(배지 갱신)→클릭 기록→다음; 마지막 후 `estimateAffine`→`reprojectionError`→"저장"(localStorage).
- 에러: 웹캠 거부/없음, `estimateAffine` throw(<3/일직선), 저장 실패.
- [ ] 1. 컴포넌트 구현(설계 §배치 ASCII 레이아웃, 기존 btn 클래스 재사용, 인라인 style 최소).

## Task 4 — `src/App.jsx` 배선 + Playwright
**Files:** Modify `src/App.jsx`; Create `tests/robot_calibrate.spec.js`
- [ ] 1. `import RobotCalibrate from './components/RobotCalibrate';`
- [ ] 2. Robot 탭 패널에서 `<RobotConnect/>` 아래에 `<RobotCalibrate/>` 추가.
- [ ] 3. `npx vite build` 컴파일 통과 확인.
- [ ] 4. Playwright `tests/robot_calibrate.spec.js`: 패널 렌더 + "미측정 → 재보정 필요" 표시 + 재보정 스텝 진행(스텁 이동) + 가짜 미디어(`--use-fake-device-for-media-stream` via launch args in config? → use context permissions + fake stream) 클릭 4회 → 풀기 → 상태 "사용 중 · 오차" 전환. 카메라 없으면 렌더/안내만 검증(그레이스풀).
```

## 검증
- vite build 통과, affineCalib scratch 검증 통과, Playwright 통과(가능 범위), 변경 범위 최소.

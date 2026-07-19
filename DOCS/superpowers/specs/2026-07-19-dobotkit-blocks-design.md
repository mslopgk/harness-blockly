# dobotkit 고정 블록 (Fixed Robot Blocks) — 설계

**작성일:** 2026-07-19
**롤백 앵커:** `master` @ `robot-wiring` (95a6cbc). 작업 브랜치 `feat/dobotkit-blocks`.

## 목표 (Goal)

부산과학관 AI·로보틱스 커리큘럼용으로, dobotkit(Dobot Magician Lite 팔 + Magician GO 차)의
핵심 API를 **항상 팔레트에 존재하는 고정 블록**으로 제공한다. 학생이 `pip install` + 동적
introspection 없이도 로봇 블록을 바로 꺼내 쓸 수 있어야 하고, 만든 블록은 **실제 파이썬으로
변환·실행되어 실제 로봇을 움직여야 한다.**

## 비목표 (Non-goals)

- Python→블록 인식(recognition) 규칙 추가 — 안 함(코어 불변, "no hardcoded tables" 준수).
- dobotkit 전체 API 노출 — 안 함(커리큘럼용 큐레이션 집합만).
- Teachable Machine — 별도 후속 프로젝트(B).

## 아키텍처 (Architecture)

기존 **번들 LibrarySpec → 마운트 시 `builtin:true` 등록** 패턴(cv2/stdlib과 동일)을 그대로 쓴다.
새 개념·새 코어 코드 없음.

- dobotkit 큐레이션 스펙을 `scripts/gen-stdlib-blocks.cjs`에 손으로 추가 → 재생성으로
  `src/data/stdlibSpecs.json`에 dobotkit 모듈 스펙을 포함시킨다.
- `src/App.jsx`의 기존 마운트 등록 루프(`librarySpecToRegistrySpecs(spec, {both:false})` →
  `registerLibBlock({...s, builtin:true})`)가 dobotkit 스펙도 **자동으로** 등록한다 —
  루프 수정 불필요(스펙만 추가되면 됨).
- 등록된 블록은 **Tier-A 스킨**: `blocklyToIr`에서 일반 Call IR로 lower되어 파이썬과 무손실
  라운드트립. `irToBlockly`/`blocklyToIr`/`irBlocks`(변환 코어)는 **손대지 않는다.**
- dobotkit은 백엔드 파이썬에 이미 설치돼 있으므로 Run 시 실제 실행된다.

### 명령(command) vs 값(reporter) 구분

기존 `both:false` 등록 경로의 의미 규칙을 그대로 활용한다:
- `kind:'class'` 또는 `returns:true` → **값 블록**(reporter, 출력 플러그) — 연결/게터에 사용.
- `returns:false` → **명령 블록**(초록 statement, 스택) — 모션/부수효과에 사용.

손으로 각 엔트리에 올바른 `returns` 플래그를 부여해 의미에 맞는 형태를 만든다(추가 코드 없음).

### 친근한 라벨 / 수신자 변수

메서드 엔트리는 `entryToSpec`에서 `recv = owner.toLowerCase()`가 되어 제목이 `recv.method`,
argNames[0]=recv(수신자)로 lower된다. 따라서 팔 메서드는 `owner:'Arm'`(→`arm`), 차 메서드는
`owner:'Car'`(→`car`)로 손수 작성해 블록 라벨을 `arm.move_to`, `car.forward`로, 수신자 변수
기본값을 `arm`/`car`로 맞춘다(커리큘럼 관례와 일치). 실제 lower 시 수신자 슬롯에 꽂힌
변수(학생이 만든 변수)가 그대로 리시버가 된다.

## 블록 집합 (큐레이션) 과 lower 대상 파이썬

토크박스 카테고리: **"🤖 로봇 (dobotkit)"** (라이브러리 탭, `lib='dobotkit'`).

### 팔 — MagicianLite (수신자 `arm`)

| 블록 | 형태 | lower 파이썬 |
|---|---|---|
| 팔 연결 | 값 | `dobotkit.MagicianLite()` |
| `arm.home()` | 명령 | `arm.home()` |
| `arm.move_to(x, y, z)` | 명령 | `arm.move_to(x, y, z)` |
| `arm.move_relative(dx, dy, dz)` | 명령 | `arm.move_relative(dx, dy, dz)` |
| `arm.suck(on)` | 명령 | `arm.suck(on)` |
| `arm.grip(on)` | 명령 | `arm.grip(on)` |
| `arm.set_speed(velocity, acceleration)` | 명령 | `arm.set_speed(velocity, acceleration)` |
| `arm.get_pose()` | 값 | `arm.get_pose()` |

### 차 — MagicianGO (수신자 `car`)

| 블록 | 형태 | lower 파이썬 |
|---|---|---|
| 차 연결 | 값 | `dobotkit.MagicianGO.open(port_name)` |
| `car.forward(speed)` | 명령 | `car.forward(speed)` |
| `car.backward(speed)` | 명령 | `car.backward(speed)` |
| `car.spin(speed)` | 명령 | `car.spin(speed)` |
| `car.strafe(speed)` | 명령 | `car.strafe(speed)` |
| `car.move(x, y, r)` | 명령 | `car.move(x, y, r)` |
| `car.drive_for(x, y, r, seconds)` | 명령 | `car.drive_for(x, y, r, seconds)` |
| `car.stop()` | 명령 | `car.stop()` |
| `car.buzzer()` | 명령 | `car.buzzer()` |
| `car.battery()` | 값 | `car.battery()` |
| `car.ultrasonic()` | 값 | `car.ultrasonic()` |
| `car.imu_angle()` | 값 | `car.imu_angle()` |

시그니처는 실기 introspection으로 검증한 실제 값(예: `move_to(x,y,z,r=0,*,...)` → 필수 x,y,z만
노출; `set_speed(velocity, acceleration)`; `drive_for(x,y,r,seconds)` — 커리큘럼 편의로 필수 노출).

### 연결 블록 표현 (구현 세부 — 플랜에서 확정)

- 팔 연결은 `kind:'class'` 엔트리(`dobotkit.MagicianLite`)로 `dobotkit.MagicianLite()` 값 블록.
- 차 연결 `dobotkit.MagicianGO.open(...)`는 점(dot) 두 번 체인이라, 등록 시 dotted-module
  스펙(`module:'dobotkit.MagicianGO'`, `func:'open'`)으로 처리되어 토크박스에 **통합 ir_call**
  형태로 제공될 수 있다(전용 색상 lib 블록 대신). 어느 쪽이든 **동일한 파이썬으로 lower·무손실
  라운드트립**되면 계약 충족. 플랜에서 실제 등록 방식을 정한다.

## 임포트 (Import)

블록이 실행되려면 `import dobotkit`가 코드에 있어야 한다. 커리큘럼 예제/스캐폴드가 이미
`import dobotkit`를 포함하며, 동적 라이브러리 경로와 달리 고정 블록은 자동 임포트 주입을 하지
않는다. 로봇 카테고리에 **`import dobotkit` 임포트 블록**을 함께 제공해 학생이 한 번에 넣게 한다
(ir_import 블록, 무손실).

## 변경 파일 (File changes)

- `scripts/gen-stdlib-blocks.cjs` — HAND 목록에 dobotkit 큐레이션 엔트리 추가(팔/차, `returns`
  플래그로 명령/값 구분, `owner` 로 수신자 라벨).
- `src/data/stdlibSpecs.json` — 재생성 산출물(dobotkit 모듈 스펙 포함). 커밋.
- `src/App.jsx` — 마운트 등록 루프는 **수정 없음**(스펙만 추가되면 자동). 단, 로봇 카테고리
  아이콘/라벨이 필요하면 토크박스 표시 계층에서 소폭 조정 가능(플랜에서 확인).
- `tests/robot_blocks.spec.js` — 신규 Playwright 스펙.

**절대 수정 금지:** `src/utils/irToBlockly.js`, `blocklyToIr.js`, `irBlocks.js`(변환 코어 =
Python-first 철학). dobotkit 인식용 하드코딩 규칙 추가 금지.

## 테스트 (Testing)

Playwright(오프라인, 백엔드 불필요 — Pyodide 변환만):
1. **존재:** 마운트 후 `window.BlockPyLibRegistry`에 dobotkit 블록들이 `builtin`으로 등록,
   토크박스에 "로봇 (dobotkit)" 카테고리가 뜬다.
2. **lower 정확성 + 명령/값:** 각 대표 블록을 워크스페이스에 놓고 → 위 표의 파이썬으로 lower.
   모션 블록은 statement(명령), 게터/연결은 reporter(값).
3. **라운드트립 무손실:** 대표 프로그램(팔 연결→home→move_to; 차 연결→forward→battery)을
   파이썬으로 놓고 `ast.dump(parse(orig)) == ast.dump(parse(regenerated))` 통과.
4. **재시작 지속:** builtin이라 새로고침 후에도 카테고리·블록 유지(localStorage 없이).

## 전역 제약 (Global Constraints)

- **변환 코어 불변** — 블록 사이드 핵심(irToBlockly/blocklyToIr/irBlocks) 수정 금지.
- **무손실 라운드트립** — `ast.dump` 동치. 필드/extraState 키 일치.
- **고정 블록 UX** — 함수/메서드/속성명은 비편집 라벨; 변수는 네이티브 변수 드롭다운; 자유
  텍스트는 리터럴/kwarg 이름에만.
- **no hardcoded recognition tables** — Python→블록 인식에 dobotkit 전용 규칙 추가 금지
  (오소링 전용 프리셋만).
- **불필요 파일 손대지 않기.**

## 롤백 (Rollback)

- 작업은 `feat/dobotkit-blocks` 브랜치에서만. master는 `robot-wiring`(95a6cbc) 유지 = 롤백 지점.
- 완료·검증 후 사용자 선택으로 병합. 병합 시 완료 태그 `robot-blocks` 부여.
- 어느 시점이든 `git checkout master` 또는 `git reset --hard robot-wiring`로 원복.

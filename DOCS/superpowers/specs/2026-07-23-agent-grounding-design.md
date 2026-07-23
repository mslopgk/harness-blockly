# AI 도우미 그라운딩(워크스페이스 자동 시딩) — 설계 문서

**작성일:** 2026-07-23
**대상:** BlockPy (Express `server.js` 백엔드 + 워크스페이스 폴더 + AI 도우미 터미널)

## 배경 / 문제

AI 도우미 터미널에서 도는 코딩 에이전트(claude/opencode 등)는 이 플랫폼의 목적도, `tm`·`dobotkit`
API도, 로봇/캘리 흐름도 모르는 "백지" 상태다. 그대로 바이브코딩하면 없는 API를 지어내거나 블록으로
변환되지 않는 코드를 만들어 오류 범벅이 된다. 에이전트를 **작업 폴더의 컨텍스트 파일로 자동
grounding** 해서, 학생이 `claude`만 쳐도 플랫폼의 규칙·API·예제를 알고 시작하게 한다.

## 목표

터미널의 작업 폴더(워크스페이스)에 "그라운딩 세트"를 백엔드가 시작 시 자동 시딩한다:
- 에이전트가 실행 시 자동으로 읽는 컨텍스트 파일(`AGENTS.md` + `CLAUDE.md`).
- 베낄 수 있는 **검증된 정답 예제**(커리큘럼 예제 5종).
- 터미널 파이썬에서 `import tm`이 실제로 되도록 배선.

## 비목표 (YAGNI)

- 등록 라이브러리에서 컨텍스트를 자동 생성하는 앱 UI 버튼 — 고정 builtin 라이브러리라 불필요.
- 에이전트 자동 실행/프리셋 프롬프트 — 터미널은 빈 셸 유지(기존 설계).
- 사용자 워크스페이스의 기존 파일 덮어쓰기 — 절대 안 함(멱등 시딩).
- `dobotkit` 라이브러리 번들/설치 — 이미 파이썬 환경에 설치돼 있음(실측). 이 기능 범위 밖.

## 접근 방식

**백엔드가 워크스페이스에 "그라운딩 세트"를 멱등 시딩** (새 `seedAgentContext()`, 시작 시
`seedStarterFile()`·`seedSampleImages()`와 함께 호출). 각 파일은 **없을 때만 생성**하고,
사용자가 만든/수정한 파일은 절대 덮지 않는다.

에이전트 컨텍스트 파일은 작업 폴더에서 자동 로드되는 게 업계 관례다: Claude Code는 `CLAUDE.md`,
opencode/Codex/Cursor 등은 `AGENTS.md`. 따라서 두 파일을 모두 두되 **단일 출처**로 관리한다.

## 아키텍처

### 시드 위치 / 대상

터미널·run-python·파일탐색기의 공통 작업 폴더 `WORKSPACE_DIR`(server.js:45)에 시딩한다.

시드 대상:
1. `WORKSPACE_DIR/AGENTS.md` — 표준·에이전트 공통 컨텍스트(단일 출처, 내용은 아래 "AGENTS.md 내용").
2. `WORKSPACE_DIR/CLAUDE.md` — Claude Code 네이티브. 내용은 `@AGENTS.md` 임포트 한 줄 + 한 줄 설명
   (Claude Code의 `@경로` 임포트 문법으로 AGENTS.md를 그대로 끌어옴 → 중복 없음).
3. `WORKSPACE_DIR/examples/` — 리포 `public/examples/`의 커리큘럼 예제 5종 복사:
   `m1_ai_sorting.py`, `m2_gesture_rps.py`, `h1_nl_control.py`, `h2_teleop.py`, `h3_vision_drive.py`.
   (에이전트가 실제로 도는 정답 코드를 읽고 모방하도록.)

### import 배선 (터미널 파이썬)

- `import dobotkit`: 로컬/번들 파이썬에 이미 설치됨(실측 OK). 조치 불필요.
- `import tm`: `tm.py`는 리포 `runtime/`에 있다. run-python은 이미 `RUNTIME_DIR`을 PYTHONPATH에
  싣는다(server.js:632). **터미널 PTY의 env에도 동일하게 `RUNTIME_DIR`을 PYTHONPATH 선두에 추가**
  해 `import tm`이 되게 한다(`attachTerminal`의 spawn env). run-python과 정합.

### 멱등 / 보존 규칙

- 각 대상 파일/예제는 **대상 경로가 이미 있으면 건너뛴다**(사용자 편집·산출물 보존).
- `AGENTS.md`/`CLAUDE.md`는 개별적으로 판단(하나만 지워도 그것만 재생성).
- `examples/` 는 각 예제 파일 단위로 판단(개별 없을 때만 복사); 리포에 원본이 없으면 조용히 건너뜀.
- 시딩 실패(권한 등)는 서버 기동을 막지 않는다(try/catch, 로그만) — 기존 seed 함수들과 동일.

### AGENTS.md 내용 (구현 시 이 스펙을 근거로 작성)

실제 시그니처는 아래와 일치해야 한다(리포 `runtime/tm.py`, `src/data/robotSpecs.json` 기준).

1) **플랫폼 정체성·목적**
   - 국립부산과학관 AI·로보틱스 커리큘럼용 블록코딩 플랫폼(BlockPy).
   - Python ↔ Blockly 블록 **무손실 양방향 변환**이 핵심. 학생 대상.

2) **사용 가능한 라이브러리와 정확한 API** (이것들과 파이썬 표준 라이브러리 + `cv2`/`numpy`만 사용)

   `import tm`  — 티처블머신(파이썬 자체 학습):
   - `m = tm.Model(labels)` — `labels`: 2개 이상 클래스 이름 리스트. 예 `tm.Model(['가위','바위','보'])`.
   - `m.add_example(frame, label)` — `frame`은 카메라 프레임(BGR ndarray, 예: `cv2` 프레임), `label`은 `labels` 중 하나.
   - `m.train(epochs=30)`
   - `m.predict(frame) -> (label, confidence)`
   - `m.predict_proba(frame) -> {label: prob}`
   - `m.labels` (속성) -> 클래스 이름 리스트
   - `m.save(path)` / `tm.load_model(path) -> Model`

   `import dobotkit` — 로봇:
   - 팔: `arm = dobotkit.MagicianLite()` → `arm.home()`, `arm.move_to(x, y, z)`,
     `arm.move_relative(dx, dy, dz)`, `arm.suck(on)`, `arm.grip(on)`,
     `arm.set_speed(velocity, acceleration)`, `arm.get_pose()`
   - 차: `from dobotkit import MagicianGO` → `car = MagicianGO.open('COM5')` →
     `car.forward(speed)`, `car.backward(speed)`, `car.spin(speed)`, `car.strafe(speed)`,
     `car.move(x, y, r)`, `car.drive_for(x, y, r, seconds)`, `car.stop()`, `car.buzzer()`,
     `car.battery()`, `car.ultrasonic()`, `car.imu_angle()`

3) **하드 규칙**
   - 위 라이브러리 + 파이썬 표준 라이브러리 + `cv2`/`numpy`만 사용. **없는 함수·인자를 지어내지 말 것.**
     확실치 않으면 `python -c "import tm; help(tm.Model)"` 처럼 실제 시그니처를 확인.
   - 코드는 BlockPy 블록으로 깔끔히 변환되도록 작성(평이한 문법 위주). `examples/`의 스타일을 따를 것.
   - Run 버튼/터미널의 `python`은 **실제 로컬 파이썬을 이 폴더(cwd)에서 실행**한다. 파일·이미지 경로는 이 폴더 기준.
   - 팔 동작 전 **DobotLink 실행 필수**. 컨트롤러 알람이 뜨면 모션이 막히며 **전원 리셋으로만** 해소된다.
   - 학생 대상 커리큘럼: 생성형 AI 이미지 산출물 사용 금지 등 커리큘럼 규칙 준수.

4) **실행·참고**
   - 실행: `python <파일>.py`.
   - 정답 예제: `examples/` 폴더(중등 m1·m2, 고등 h1·h2·h3).

## 오류 처리

- 시딩 실패는 서버 기동을 막지 않음(try/catch + 로그).
- 리포 `public/examples/` 원본이 없으면 해당 예제는 건너뜀(빈 `examples/`라도 무방).
- 사용자가 이미 만든 `AGENTS.md`/`CLAUDE.md`/예제는 절대 덮지 않음.

## 테스트 전략

- **백엔드(node, 통합):** 임시 `BLOCKPY_WORKSPACE`에 대해 `seedAgentContext()`를 호출하면
  `AGENTS.md`·`CLAUDE.md`·`examples/`가 생기고, 핵심 API 토큰(예: `tm.Model`, `MagicianLite`,
  `move_to`, `predict`)이 `AGENTS.md`에 포함되는지 확인. 이미 존재하는 파일은 덮지 않음(내용 보존)을 확인.
- **터미널 env:** `attachTerminal`이 만드는 PTY env의 PYTHONPATH에 `RUNTIME_DIR`이 포함되는지 확인
  (기존 `tests/ai_terminal.test.mjs` 확장 또는 신규 assert). 가능하면 터미널에서 `python -c "import tm"`이
  성공하는지도 확인.
- **AGENTS.md ↔ 실제 API 정합(선택 스모크):** AGENTS.md에 적힌 메서드 이름들이 `robotSpecs.json`/`tm.py`에
  실제로 존재하는지 교차 확인하는 가벼운 테스트.
- **기존 게이트 불변:** 변환 파이프라인/블록 코어 미변경 → `test:ir`·`test:gen` 그대로 통과.

## 전제 / 리스크

- **패키징 앱**: `npm run dist` 로 만든 데스크톱 앱의 `python-embed` 에도 `dobotkit`·`tm`(및 `cv2`/`numpy`)이
  있어야 예제·`import`가 실제 동작한다. 이는 기존 tm/dobotkit 기능의 패키징 전제와 동일하며, 이 기능이
  새로 만드는 문제는 아니다(수동 검증 항목).
- AGENTS.md 내용은 **손수 큐레이션**이라 API가 바뀌면 갱신이 필요하다. 고정 builtin 라이브러리라 변동은
  드물고, 테스트의 정합 스모크가 드리프트를 잡는다.

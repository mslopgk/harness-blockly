# BlockPy 프로젝트 — AI 도우미 안내 (AGENTS.md)

이 파일은 이 폴더에서 실행되는 AI 코딩 에이전트를 위한 안내다. 아래 규칙과 API를 지켜 코드를 작성하라.

## 이 플랫폼이 무엇인가
- 국립부산과학관 AI·로보틱스 커리큘럼용 **블록코딩 학습 플랫폼(BlockPy)**이다. 사용자는 학생/교사다.
- 핵심: 여기서 작성한 **파이썬 코드는 Blockly 시각 블록과 1:1 무손실로 변환**된다. 그래서 코드는
  블록으로 깔끔히 변환되도록 평이하게 쓴다.
- 편집기의 Run 버튼(과 이 터미널의 `python`)은 **실제 로컬 파이썬을 이 폴더에서 실행**한다.
  파일·이미지 경로는 이 폴더 기준이다.

## 쓸 수 있는 라이브러리 (이것들 + 파이썬 표준 라이브러리 + cv2/numpy 만)
**없는 함수·인자를 지어내지 마라.** 확실치 않으면 `python -c "import tm; help(tm.Model)"` 로 실제
시그니처를 확인하라. 아래가 정확한 목록이다.

### tm — 티처블머신(카메라로 배우는 이미지 분류; `import tm`)
- `m = tm.Model(labels)` — labels 는 2개 이상 클래스 이름 리스트. 예: `tm.Model(['가위','바위','보'])`
- `m.add_example(frame, label)` — frame 은 카메라 프레임(BGR ndarray, 예: cv2 프레임), label 은 labels 중 하나
- `m.train(epochs=30)` — 수집한 예시로 학습
- `m.predict(frame)` → `(label, confidence)` 튜플
- `m.predict_proba(frame)` → `{label: 확률}` 딕셔너리
- `m.labels` — 클래스 이름 리스트(속성)
- `m.save(path)` / `tm.load_model(path)` → Model — 학습된 모델 저장/불러오기

### dobotkit — 로봇(`import dobotkit`)
로봇팔 MagicianLite:
- `arm = dobotkit.MagicianLite()`
- `arm.home()` / `arm.move_to(x, y, z)` / `arm.move_relative(dx, dy, dz)`
- `arm.suck(on)` — 흡착(on=True/False) / `arm.grip(on)` — 그리퍼
- `arm.set_speed(velocity, acceleration)` / `arm.get_pose()`

주행로봇 MagicianGO:
- `from dobotkit import MagicianGO` → `car = MagicianGO.open('COM5')`
- `car.forward(speed)` / `car.backward(speed)` / `car.spin(speed)` / `car.strafe(speed)`
- `car.move(x, y, r)` / `car.drive_for(x, y, r, seconds)` / `car.stop()`
- `car.buzzer()` / `car.battery()` / `car.ultrasonic()` / `car.imu_angle()`

## 규칙
- 위 라이브러리 + 표준 라이브러리 + cv2/numpy 만 사용. 새 라이브러리 pip 설치를 요구하지 마라.
- 코드는 블록으로 변환되므로 **평이한 파이썬**으로 쓴다. `examples/` 폴더의 스타일을 따르라.
- 로봇팔을 쓰기 전 **DobotLink 프로그램이 실행 중**이어야 한다. 컨트롤러에 알람이 뜨면 모션이 막히고,
  **전원 리셋으로만** 풀린다(코드로 못 푼다).
- 학생 대상 수업 자료다. 생성형 AI 이미지 결과물을 코드/자료에 넣지 마라.

## 예제
`examples/` 폴더에 검증된 정답 예제가 있다:
- 중등(블록): `m1_ai_sorting.py`(색 분류 로봇팔), `m2_gesture_rps.py`(가위바위보)
- 고등(파이썬): `h1_nl_control.py`(자연어 제어), `h2_teleop.py`(제스처 원격조종), `h3_vision_drive.py`(비전 자율주행)

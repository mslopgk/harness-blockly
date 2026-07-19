# Teachable Machine 파이썬 런타임 + 고정 블록 — 설계

**작성일:** 2026-07-19
**롤백 앵커:** `feat/dobotkit-blocks`(B만 제거) / `robot-wiring`(A+B 제거). 작업 브랜치 `feat/tm-runtime-blocks`(dobotkit 위에 스택).

## 목표 (Goal)

부산과학관 AI·로보틱스 커리큘럼에서, **브라우저 TM 패널로 학습·저장한 이미지 분류 모델**
(`blockpy-tm-v1`)을 **파이썬에서 로드해 실제 추론**한다. 블록으로 짜서 Run하면 백엔드 실제
파이썬이 예측하고, 그 결과로 dobotkit 로봇을 제어할 수 있다. "블록 A = 실제 실행되는 파이썬"
원칙을 TM에도 성립시킨다.

## 비목표 (Non-goals)

- 파이썬에서의 **학습** — 안 함(학습은 브라우저 TM 패널이 담당; 파이썬은 추론 전용).
- 카메라 헬퍼 — 안 함(프레임은 기존 cv2 블록으로 캡처; `frame`은 numpy 이미지).
- 변환 코어(irToBlockly/blocklyToIr/irBlocks) 수정 — 안 함.
- TM 패널 UI 변경 — 안 함(저장은 이미 `/api/fs/file`로 워크스페이스에 씀).

## 배경: 모델 봉투(`blockpy-tm-v1`)

브라우저(`src/utils/teachable.js` + `tmPack.js`)가 저장하는 JSON:
```
{ format:'blockpy-tm-v1', labels:[…], imageSize:224, base:'mobilenet-v2',
  head:{ modelTopology, weightSpecs, weightData(base64) } }
```
- **base:** MobileNet v2(alpha 1.0)를 **특징추출기**로만 사용(브라우저는 `@tensorflow-models/mobilenet`
  `infer(img, embedding=true)` → 1280차원 임베딩). 저장 안 됨(런타임 재사용).
- **head:** 고정 2층 분류기 `dense(100, relu) → dense(N, softmax)`(입력 1280). tfjs LayersModel로
  직렬화되어 있으나 **아키텍처가 고정**이라 파이썬에서 numpy로 그대로 재현 가능.
- 저장 경로: TM 패널 "저장" → `POST /api/fs/file` → 워크스페이스 루트 `<이름>.json`. 워크스페이스는
  Run 경로의 cwd이므로 파이썬이 상대경로로 바로 읽는다.

## 아키텍처 (두 부분)

### ① 파이썬 `tm` 런타임 모듈 (신규, 핵심)

플랫폼이 제공하는 `tm` 모듈(레포 `runtime/tm.py`). 공개 API:

- `tm.load_model(path) -> Model`
  - 워크스페이스의 봉투 JSON 로드, `format` 검증(아니면 친절한 오류).
  - head 가중치를 weightSpecs/weightData(base64)에서 순서대로 4개 numpy 배열로 추출
    (`W1[1280,100], b1[100], W2[100,N], b2[N]`), labels 보관.
  - MobileNet base(특징추출기)를 준비(아래 featurizer). 프로세스 1회 로드 후 캐시.
- `Model.predict(frame) -> (label:str, confidence:float)`
  - `frame`(numpy uint8 HxWx3) → featurize → 1280 임베딩 → head(numpy: `relu(e@W1+b1)` →
    `softmax(·@W2+b2)`) → argmax → (label, prob). 커리큘럼 h3의 `predict(frame)->(label,conf)`와 동일.
- `Model.predict_proba(frame) -> dict[str,float]` — 클래스별 확률.
- `Model.labels -> list[str]` — 클래스 이름 목록(속성).

`frame` 계약: numpy uint8 배열(H,W,3, RGB 또는 BGR — featurizer가 일관 처리). cv2로 캡처한
프레임을 그대로 넘긴다.

### ② tm 고정 블록 (dobotkit과 동일 패턴)

- `src/data/tmSpecs.json`(+`scripts/gen-tm-blocks.cjs`) = `{module:'tm', entries:[…]}`:
  - `{kind:'function', name:'load_model', params:[path], returns:true}` → `tm.load_model(path)` 값
  - `{kind:'method', owner:'Model', name:'predict', params:[frame], returns:true}` → `model.predict(frame)` 값
  - `{kind:'method', owner:'Model', name:'predict_proba', params:[frame], returns:true}` → 값
  - `{kind:'property', owner:'Model', name:'labels'}` → `model.labels` 값 속성
- `src/App.jsx` 마운트의 기존 `bundledSpecs` 배열(A에서 도입)에 `tmSpecs` 추가 → **"tm" 토크박스
  카테고리** 자동 생성. Tier-A 스킨이라 무손실 라운드트립. 코어 불변.
- 학생은 `import tm` + cv2로 프레임 캡처. 수신자 변수 기본 `model`.

## Featurizer 와 패리티 게이트 (⚠️ 린치핀)

브라우저 head는 **브라우저 MobileNet 임베딩** 위에서 학습됐다. 파이썬 예측이 맞으려면 파이썬
featurizer가 **같은 이미지에 대해 같은 임베딩**을 내야 한다.

- **1차 접근:** `tf.keras.applications.MobileNetV2(input_shape=(224,224,3), alpha=1.0,
  include_top=False, weights='imagenet', pooling='avg')` → 1280차원. 전처리
  `mobilenet_v2.preprocess_input`(= x/127.5 − 1)은 브라우저 `@tensorflow-models/mobilenet`
  v2 전처리와 동일. 프레임은 224로 리사이즈.
- **패리티 게이트(플랜 1번 태스크, 반드시 선통과):**
  1. 결정적 테스트 이미지 N장에 대해 **브라우저 임베딩**(`window.BlockPyTM.featurize`)과 **파이썬
     임베딩**을 비교 → 코사인 유사도 > 0.999(또는 정해진 허용오차).
  2. **엔드투엔드:** 브라우저서 2클래스 미니 모델 학습·저장 → 파이썬 `load_model`+`predict`로
     같은 이미지 예측 → 라벨 일치.
- **폴백(게이트 실패 시):** 벤더된 그 tfjs GraphModel(`public/vendor/mobilenet/`)을 빌드 시 TF로
  변환(예: `tfjs-graph-converter`)해 정확 일치하는 임베딩을 사용. 작업량 증가. 게이트 결과에 따라
  플랜에서 분기.

## 헬퍼 배치 (PYTHONPATH)

- `tm.py`는 워크스페이스가 아니라 레포 `runtime/`에 둔다(워크스페이스 초기화·오염과 무관, 플랫폼과
  함께 버전관리).
- `server.js`의 run-python 서브프로세스 spawn env에 `PYTHONPATH`로 `runtime/`를 추가 → 어떤
  워크스페이스에서든 `import tm` 가능. 데스크톱(python-embed)에서도 동일하게 실린다.
- 의존성: `tensorflow`(확인 2.21.0), `numpy`(2.4.4) — 셋업 시 사전 설치. `tm.py`는 tensorflow
  미설치 시 명확한 안내 메시지로 degrade(설치법 안내).

## 데이터 흐름 (Data flow)

브라우저 학습 → 저장(`/api/fs/file` → 워크스페이스 `모델.json`) → 파이썬:
`import tm` → `model = tm.load_model("모델.json")` → (cv2로 frame 캡처) →
`label, conf = model.predict(frame)` → `if label == "왼쪽": car.spin(...)`(dobotkit).

## 변경/생성 파일

- **Create** `runtime/tm.py` — tm 런타임 모듈(load_model/Model.predict/predict_proba/labels + featurizer + head).
- **Create** `scripts/gen-tm-blocks.cjs`, `src/data/tmSpecs.json` — tm 고정 블록 스펙(생성물).
- **Create** 테스트: 패리티/엔드투엔드(브라우저 vs 파이썬), tm 블록 lower/round-trip, run-python `import tm`.
- **Modify** `server.js` — run-python spawn env에 `PYTHONPATH += runtime`.
- **Modify** `src/App.jsx` — `bundledSpecs`에 `tmSpecs` 추가(한 줄 + import).

**절대 수정 금지:** `irToBlockly.js`, `blocklyToIr.js`, `irBlocks.js`, `libRegistry.js`,
`libImport.js`, `irToolbox.js`, `stdlibSpecs.json`, TM 패널 UI(`TeachableMachine.jsx`),
`teachable.js`/`tmPack.js`(브라우저 학습·저장은 이미 완성 — 읽기만).

## 테스트 (Testing)

1. **패리티 게이트(우선):** 브라우저 임베딩 vs 파이썬 임베딩 코사인>0.999. (Playwright + python)
2. **엔드투엔드:** 브라우저 미니학습→저장→파이썬 예측 라벨 일치.
3. **tm 런타임 단위:** 봉투 로드, head numpy 순전파(고정 가중치 입력 → 기대 확률), 잘못된 형식
   friendly 오류, tensorflow 미설치 시 degrade 메시지.
4. **tm 블록:** node lower(`tm.load_model(p)`, `model.predict(frame)`, `model.predict_proba(frame)`,
   `model.labels`) + 브라우저 "tm" 카테고리 존재 + dobotkit 프로그램과 함께 무손실 라운드트립.
5. **run-python 통합:** `PYTHONPATH`로 `import tm` 성공(server.js 경유).

## 전역 제약 (Global Constraints)

- **변환 코어 불변** · **무손실 라운드트립**(ast.dump 동치) · **no hardcoded recognition tables**
  (오소링 프리셋만) · **불필요 파일 손대지 않기.**
- tm 런타임은 **추론 전용**(학습은 브라우저). 브라우저와 **임베딩 일치**가 정확성의 전제 — 패리티
  게이트 선통과.
- `frame` 계약: numpy uint8 HxWx3.

## 롤백 (Rollback)

- `feat/tm-runtime-blocks`(dobotkit 위 스택)에서만 작업. 원복: `git checkout feat/dobotkit-blocks`
  (B만 제거) 또는 `git reset --hard robot-wiring`(A+B 제거).
- 완료·검증·승인 후 병합 시 태그 `tm-runtime`.

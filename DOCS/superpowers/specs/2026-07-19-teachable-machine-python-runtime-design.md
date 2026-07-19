# Teachable Machine 파이썬 런타임 + 고정 블록 — 설계 (옵션 B: 파이썬 네이티브)

**작성일:** 2026-07-19 (개정: 패리티 게이트 실패로 "브라우저 모델 재사용"→"파이썬 자체 학습"으로 전환)
**롤백 앵커:** `feat/dobotkit-blocks`(B만 제거) / `robot-wiring`(A+B 제거). 작업 브랜치 `feat/tm-runtime-blocks`.

## 결정 배경 (왜 옵션 B)

당초 "브라우저 TM 패널에서 학습한 모델을 파이썬에서 재사용"을 목표했으나, **패리티 게이트에서
탈락**: 브라우저는 TF-Slim MobilenetV2(임베딩=`MobilenetV2/Logits/AvgPool`)를 쓰는데
`keras.applications.MobileNetV2`와 **다른 체크포인트**라 같은 이미지 임베딩 코사인 유사도가 **0.79**
(목표 >0.999). 정확 재사용은 벤더 tfjs 모델 변환이 필요하나 변환 툴(`tensorflowjs`)이 numpy 2.x와
비호환 → 빌드 복잡성·툴체인 취약성 큼. **사용자 결정: 파이썬에서 자체 학습(옵션 B)로 전환.**

## 목표 (Goal)

`tm` 파이썬 모듈이 **파이썬 안에서** 이미지 분류기를 **수집·학습·추론**한다(브라우저 TM 패널과 동일
개념: MobileNet 특징 + 소형 head, 단 전 과정 파이썬). 블록으로 짜서 Run하면 실제 파이썬이 학습·예측하고
그 결과로 dobotkit 로봇을 제어한다. 학습·추론이 **같은 파이썬 featurizer**를 쓰므로 자기일관적 —
크로스-환경 패리티·모델 변환 불필요.

## 비목표 (Non-goals)

- **브라우저 모델 재사용** — 안 함(패리티 실패로 폐기). 브라우저 TM 패널은 교육용 데모로 존치.
- 카메라 헬퍼 — 안 함(frame은 기존 cv2 블록으로 캡처).
- 변환 코어(irToBlockly/blocklyToIr/irBlocks)·TM 패널 UI·teachable.js/tmPack.js 수정 — 안 함.

## 아키텍처 (두 부분)

### ① 파이썬 `tm` 런타임 모듈 (신규, 핵심)

레포 `runtime/tm.py`. 커리큘럼 h3 `VisionPolicy`와 같은 API 형태:

- `tm.Model(labels: list[str]) -> Model` — 클래스 라벨로 빈 모델 생성.
- `Model.add_example(frame, label) -> None` — 라벨된 프레임을 수집(MobileNet 임베딩으로 저장).
- `Model.train() -> None` — 수집된 임베딩으로 소형 head 학습(dense(100,relu)→dense(N,softmax),
  adam, sparse categorical CE, ~30 epochs). 각 클래스 1장 이상 필요, 아니면 friendly 오류.
- `Model.predict(frame) -> (label:str, confidence:float)` — 커리큘럼 h3와 동일 시그니처.
- `Model.predict_proba(frame) -> dict[str,float]` — 클래스별 확률.
- `Model.labels -> list[str]` — 클래스 이름 목록(속성).
- `Model.save(path) -> None` — 라벨 + head 가중치 4개(W1,b1,W2,b2)를 **npz**로 저장(워크스페이스).
- `tm.load_model(path) -> Model` — npz 로드, head 재구성(학습 없이 바로 추론).

- **featurizer:** `keras.applications.MobileNetV2(input_shape=(224,224,3), alpha=1.0,
  include_top=False, weights=<resolved>, pooling='avg')` → 1280차원. 전처리 `preprocess_input`
  (=(x/127.5)−1), 프레임 224 리사이즈. base는 프로세스당 1회 로드·캐시. 학습·추론 동일 경로 → 일관.
- **frame 계약:** numpy uint8 (H,W,3). cv2로 캡처(BGR)한 프레임을 featurizer가 RGB로 일관 변환.
- **degrade:** tensorflow 미설치 시 명확한 안내(설치법) 오류.

### ② tm 고정 블록 (dobotkit과 동일 패턴)

- `src/data/tmSpecs.json`(+`scripts/gen-tm-blocks.cjs`) = `{module:'tm', entries:[…]}`:
  - `{kind:'class', name:'Model', params:[labels], returns:true}` → `tm.Model(labels)` 값
  - `{kind:'method', owner:'Model', name:'add_example', params:[frame,label], returns:false}` → 명령
  - `{kind:'method', owner:'Model', name:'train', returns:false}` → 명령
  - `{kind:'method', owner:'Model', name:'predict', params:[frame], returns:true}` → 값
  - `{kind:'method', owner:'Model', name:'predict_proba', params:[frame], returns:true}` → 값
  - `{kind:'method', owner:'Model', name:'save', params:[path], returns:false}` → 명령
  - `{kind:'property', owner:'Model', name:'labels'}` → `model.labels` 값 속성
  - `{kind:'function', name:'load_model', params:[path], returns:true}` → `tm.load_model(path)` 값
- 수신자 변수 기본 `model`. `src/App.jsx`의 기존 `bundledSpecs`(A 도입)에 `tmSpecs` 추가 → **"tm"
  토크박스 카테고리** 자동 생성. Tier-A 스킨 → 무손실 라운드트립. 코어 불변.

## 데이터 흐름 (Data flow)

```python
import tm, cv2
model = tm.Model(["가위", "바위", "보"])
model.add_example(frame, "가위")   # cv2로 프레임 캡처해 수집(여러 장)
model.train()
label, conf = model.predict(frame)
model.save("가위바위보.npz")        # 다음엔: model = tm.load_model("가위바위보.npz")
```
워크스페이스가 Run cwd이므로 상대경로 저장/로드가 바로 동작.

## 헬퍼 배치 & 의존성

- `runtime/tm.py`. `server.js`의 run-python spawn env에 `PYTHONPATH += runtime` → 어떤 워크스페이스
  에서든 `import tm`. 데스크톱(python-embed) 동일.
- 의존성: `tensorflow`(2.21.0 확인), `numpy`(2.4.4 확인) — 사전 설치.
- **MobileNet 가중치 전달:** keras `weights='imagenet'`는 `~/.keras`에 캐시(현재 캐시됨). 오프라인
  교실용으로 셋업 시 사전 캐시 또는 번들(gitignore된 `runtime/` 자산 + fetch 스크립트, `npm run
  vendor` 방식). tm.py는 번들 경로 우선, 없으면 `'imagenet'` 폴백, 완전 오프라인·미캐시 시 friendly 오류.

## 그라운딩 검증 (사전 확인 완료)

MobileNet 특징 + keras head 루프를 실제 실행: 2클래스 소량 학습 → held-out 예측 정확도 1.0 확인.
embed dim 1280, dense(100,relu)→dense(N,softmax), adam/sparse-CE/30ep.

## 변경/생성 파일

- **Create** `runtime/tm.py` — Model(add_example/train/predict/predict_proba/labels/save) + load_model + featurizer.
- **Create** `scripts/gen-tm-blocks.cjs`, `src/data/tmSpecs.json`(생성물).
- **Create** 테스트: tm 파이썬 단위(학습→예측·save/load·friendly 오류), tm 블록(node lower + 브라우저 카테고리 + round-trip), run-python `import tm`.
- **Modify** `server.js` — run-python spawn env에 `PYTHONPATH += runtime`.
- **Modify** `src/App.jsx` — `bundledSpecs`에 `tmSpecs` 추가(+import).

**절대 수정 금지:** `irToBlockly.js`, `blocklyToIr.js`, `irBlocks.js`, `libRegistry.js`,
`libImport.js`, `irToolbox.js`, `stdlibSpecs.json`, `robotSpecs.json`, TM 패널/`teachable.js`/`tmPack.js`.

## 테스트 (Testing)

1. **tm 파이썬 단위:** 결정적 2클래스 소량 → train → held-out predict 정답; save→load_model 후 예측 동일;
   빈 클래스/미학습 predict → friendly 오류; tensorflow 미설치 시뮬레이트 → 안내.
2. **tm 블록:** node lower(`tm.Model(labels)`, `model.add_example(frame,label)`, `model.train()`,
   `model.predict(frame)`, `model.predict_proba(frame)`, `model.save(path)`, `model.labels`,
   `tm.load_model(path)`) + 브라우저 "tm" 카테고리 존재 + dobotkit와 함께 무손실 라운드트립.
3. **run-python 통합:** `PYTHONPATH`로 `import tm` 성공(server.js 경유).

## 전역 제약 (Global Constraints)

- **변환 코어 불변** · **무손실 라운드트립**(ast.dump 동치) · **no hardcoded recognition tables**
  (오소링 프리셋만) · **불필요 파일 손대지 않기.**
- 학습·추론 **동일 파이썬 featurizer** → 자기일관(크로스-환경 패리티 없음).
- `frame`: numpy uint8 (H,W,3).

## 롤백 (Rollback)

- `feat/tm-runtime-blocks`(dobotkit 위 스택). 원복: `git checkout feat/dobotkit-blocks`(B만) /
  `git reset --hard robot-wiring`(A+B). 완료·검증·승인 후 병합 시 태그 `tm-runtime`.

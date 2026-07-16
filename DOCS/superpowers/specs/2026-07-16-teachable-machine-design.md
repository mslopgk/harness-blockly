# Teachable Machine 인앱 — 설계 (Design)

- 날짜: 2026-07-16
- 대상: BlockPy 플랫폼 (blockly프로젝트) 프론트엔드
- 관련: 중등 TM 단원(`강의자료개발/_공용/packs/tm.json`) — 현재는 구글 Teachable Machine 웹사이트 사용

## 목표 / 범위 (1단계)

플랫폼 안에서 웹캠으로 이미지 분류 모델을 학습하고, **특정 파일명으로 저장**하는 단계까지.
- 포함: 클래스 추가/이름 → 클래스별 웹캠 샘플 수집 → Train → **라이브 미리보기(예측)** → 파일명 입력 → 저장.
- **제외(후속)**: 블록/파이썬 연동, 저장 모델의 추론 소비, `.h5` 변환.

## 기술 스택 / 오프라인

- 브라우저 내 **TF.js**(`@tensorflow/tfjs`) + **MobileNet 전이학습**(구글 TM과 동일 방식).
- 오프라인 필수(CDN 금지) → MobileNet 가중치를 **로컬 vendored**(`public/vendor/mobilenet/`),
  `scripts/vendor-assets.cjs`에 복사 단계 추가. tfjs는 npm 의존 → Vite 번들(메인 번들 증가 감수).
- 학습·미리보기·저장 전부 프론트 완결. 저장만 기존 키리스 `/api/fs/file` 사용(로봇 백엔드 무관).

## 동작 흐름

1. MobileNet 로드(로컬, lazy). 클래스 추가/이름(기본 2개, ≥2).
2. 클래스별 **웹캠 샘플 수집**: 누르는 동안 프레임 캡처 → MobileNet 특징벡터(embedding)로 저장(이미지 원본 대신 벡터 → 메모리 절약).
3. **Train**: 작은 dense head(입력=특징차원, 출력=클래스수, softmax) 몇 epoch 학습, 진행률 표시.
4. **라이브 미리보기**: 웹캠 프레임 → 특징 → head 예측 → top 라벨 + 신뢰도%. throttled 루프.
5. **저장**: 파일명 입력 → 단일 JSON을 워크스페이스에 `<이름>.json`으로 저장(`/api/fs/file`).
   백엔드 미가동 시 브라우저 다운로드 폴백.

## 저장 형식 (단일 JSON, blockpy-tm-v1)

```jsonc
{ "format": "blockpy-tm-v1",
  "labels": ["캔", "페트", ...],     // 클래스 이름 = 라벨
  "imageSize": 224,
  "base": "mobilenet-v2",            // 소비자가 같은 base로 특징추출(식별자)
  "head": { /* tf.js head 모델 artifacts: modelTopology + weightSpecs + weightData(base64) */ } }
```
- **head(분류기)만 저장**: 파일이 작고 자기완결(라벨 포함). 추론 시 번들된 MobileNet 재사용.
- (전체 그래프 저장 시 파일마다 MobileNet 가중치가 들어가 수 MB → 비효율이라 배제. base는 식별자로만.)

## 컴포넌트 / 파일

- `src/components/TeachableMachine.jsx` (신규) — TM 패널 + 상태기계(idle→collecting→trained/preview→saved).
- `src/utils/teachable.js` (신규) — TF.js 래퍼: MobileNet 로드(로컬 경로), 특징추출, head 빌드/학습/예측, 단일 JSON 직렬화. 테스트 모드 훅(작은 결정적 featurizer 대체) 포함.
- `scripts/vendor-assets.cjs` (수정) — MobileNet 파일 vendor 복사.
- `package.json` (수정) — `@tensorflow/tfjs`.
- `src/App.jsx` (수정) — 좌패널 새 탭 **"TM"** + 마운트.
- 블록 코어 · 로봇 백엔드 · python 무수정.

## 에러 처리

- 웹캠 없음/거부 → 안내 + 수집/미리보기 비활성.
- MobileNet 로드 실패(vendor 누락) → 안내(학습 불가).
- 클래스 <2 또는 샘플 0인 클래스 → Train 거부 + 안내.
- 저장 실패(백엔드/localStorage) → 브라우저 다운로드 폴백.

## 테스트

- **단위**: 단일 JSON pack/unpack 순수 로직(라벨·base·head artifacts 왕복).
- **Playwright**: 테스트 모드(작은 결정적 featurizer로 MobileNet 대체)로 클래스 추가 · 샘플 수집(가짜 카메라) · Train · 저장 흐름 검증(실 MobileNet 헤드리스 학습은 느리고 불안정하므로 대체). 실 모델 정확도는 실앱 수동 확인.

## 범위 밖 (후속)

- 블록/파이썬 연동, 저장 모델 추론 소비, `.h5` 변환/내보내기, 데이터 편향 실습(차시3) 연계.

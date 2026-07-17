# 예제 갤러리 (Example Gallery) 설계

**작성일:** 2026-07-17
**상태:** 승인 대기

## 목표

상단 액션 바의 `예제` 버튼 하나로 카테고리별 예제 카드 갤러리(모달)를 열고, 카드를 고르면 해당 **파이썬 코드가 편집기에 로드**되어 기존 파이프라인으로 **블록으로 자동 변환**된다. 로드 직후에는 파이썬 편집기 화면을 보여준다.

## 배경 / 현재 상태

이미 예제 로더가 존재한다: 파이썬 편집기 헤더의 `Select example…` 드롭다운(`src/components/PythonEditor.jsx`)이 `window.BlockPyExamples`(= `src/examples/snippets.js`의 `DEMO_SNIPPETS`, 단일 소스)를 읽어 목록을 만들고, 선택 시 `App.jsx`의 `onLoadExample`이 코드를 채운다.

한계 두 가지:
1. **눈에 잘 안 띈다** — 편집기 헤더 안의 작은 `<select>`.
2. **로드가 불안정하다** — 현재 `onLoadExample={(sn) => { setCode(sn.code); setShouldDesugar(sn.desugar); }}`는 변환을 `shouldDesugar` 변경 effect에만 의존한다. desugar 값이 안 바뀌면(예: `desugar:true` 예제를 연속 로드) 변환이 트리거되지 않는 잠복 버그가 있다.

이 설계는 (1) 눈에 띄는 별도 갤러리 UI를 추가하고, (2) 로드 경로를 검증된 `loadDemoScript` 패턴으로 통합해 (2)의 버그까지 함께 해소한다.

## 비목표 (Non-goals)

- 새로운 예제 콘텐츠 추가 없음 — 기존 `snippets.js` 목록을 그대로 사용한다. (나중에 이 파일에 추가하면 갤러리에 자동 반영.)
- 블록 코어(`irBlocks.js`/`irToBlockly.js`/`blocklyToIr.js`/`irToolbox.js` 등) 변경 없음.
- 로봇(dobotkit)·Teachable Machine 관련 코드 변경 없음.
- 검색창·즐겨찾기·최근 사용 등 부가 기능 없음(YAGNI). 카테고리 필터까지만.

## UX 흐름

1. 상단 액션 바(`editor-tab-actions`, Run/Stop/Image 옆)의 `📚 예제` 버튼 클릭 → 갤러리 모달 오픈.
2. 모달 상단: 카테고리 필터 칩 행. `전체` + `snippets.js`에 실제 존재하는 카테고리들(예: 기초/Basics, 데이터/Data, 제어/Control, 함수/Functions, OpenCV, 타입힌트/Type Hints & Syntax, 라이브러리/Libraries). 카테고리 라벨은 코드의 `category` 값을 그대로 사용한다(하드코딩된 카테고리 표 없음).
3. 모달 본문: 예제 카드 그리드. 각 카드 = 제목(`title`) + 카테고리 배지(`category`) + 코드 앞 3줄 미리보기(모노스페이스, 넘치면 말줄임) + `불러오기` 버튼. 카드 전체 클릭도 `불러오기`와 동일 동작.
4. `전체`가 아닌 카테고리 칩 선택 시 해당 카테고리 카드만 표시.
5. `불러오기` 실행:
   - `shouldDesugar` = 스니펫의 `desugar`로 설정
   - 편집기 코드 = 스니펫의 `code`로 설정
   - `activeEditorTab` = `'python'`으로 전환
   - 모달 닫기
   - 지연 후(약 100ms) `syncCodeToBlocks(code)` 호출(세대 가드가 중복/경합을 안전 처리)
   - 로그 1줄: `[Examples] "<제목>" 예제를 불러왔습니다.`
6. 닫기: 백드롭 클릭 / ✕ 버튼 / `Esc` 키.

## 컴포넌트 구조

### 신규: `src/components/ExampleGallery.jsx`
순수 표시용(presentational) 모달 컴포넌트.

- **Props**
  - `open: boolean` — 열림 여부(false면 아무것도 렌더하지 않음)
  - `onClose: () => void`
  - `onLoad: (snippet) => void` — 카드/불러오기 클릭 시 선택된 스니펫 객체 전달
- **데이터 소스:** `window.BlockPyExamples`(없으면 `[]`)를 읽어 `category`로 그룹핑. (기존 `PythonEditor.jsx`와 동일 관례.)
- **내부 상태:** `activeCategory`(기본 `'전체'`에 해당하는 sentinel, 예: `'__ALL__'`).
- **닫기:** `open`일 때 `keydown`(Esc) 리스너 등록/해제; 백드롭 클릭 시 `onClose`, 박스 내부 클릭은 `stopPropagation`.
- **코드 미리보기:** `snippet.code.split('\n').slice(0, 3).join('\n')` + 3줄 초과 시 `…` 표시.

### 수정: `src/App.jsx` (통합 지점, 순수 추가/한 곳 교정)
1. 상태 추가: `const [showExamples, setShowExamples] = useState(false);`
2. 핸들러 추가: `loadExampleSnippet(sn)` — `loadDemoScript`와 동일한 안전 패턴:
   ```js
   const loadExampleSnippet = (sn) => {
     if (!sn || typeof sn.code !== 'string') return;
     setShouldDesugar(!!sn.desugar);
     latestCodeRef.current = sn.code;      // eager: 렌더 전에 지연 sync 가드용 ref 갱신
     setCode(sn.code);
     setHighlightedLine(null);
     setActiveEditorTab('python');
     setShowExamples(false);
     setLogs([`[Examples] "${sn.title}" 예제를 불러왔습니다.`]);
     setTimeout(() => {
       if (latestCodeRef.current === sn.code) syncCodeToBlocks(sn.code);
     }, 100);
   };
   ```
   (`shouldDesugar` effect가 값 변경 시 한 번 더 `syncCodeToBlocks`를 부를 수 있으나, `syncGenRef` 세대 가드로 최신 변환만 반영되어 안전. `latestCodeRef` 가드는 지연 창 안에 사용자가 코드를 바꾼 경우 덮어쓰지 않도록 함.)
3. 액션 바(`editor-tab-actions`)에 버튼 추가: `id="btn-examples"`, 클릭 시 `setShowExamples(true)`.
4. `imagePreview` 오버레이 근처에 모달 렌더:
   `{showExamples && <ExampleGallery open onClose={() => setShowExamples(false)} onLoad={loadExampleSnippet} />}`
   (또는 항상 마운트하고 `open={showExamples}` 전달 — 컴포넌트가 `open` false에서 null 렌더.)
5. **교정:** 기존 편집기 헤더 드롭다운의 `onLoadExample`을 `loadExampleSnippet`으로 통합 →
   `onLoadExample={loadExampleSnippet}`. 이로써 드롭다운·갤러리가 동일한 신뢰성 있는 로드 경로를 공유하고, 위의 잠복 버그(연속 로드 시 미변환)도 사라진다.

### 수정: `src/index.css`
- `.example-gallery-overlay` — 전체 화면 백드롭(기존 `.img-preview-overlay` 스타일 참고), `z-index`는 `.img-preview-overlay`와 동급.
- `.example-gallery-box` — 중앙 카드 컨테이너, `max-width`/`max-height`로 뷰포트 안에 들어오고 카드 그리드는 세로 스크롤.
- `.example-gallery-head`(제목+✕), `.example-cat-filter`(칩 행), `.example-cat-chip`/`.active`, `.example-card-grid`(반응형 그리드), `.example-card`, `.example-card-code`(모노스페이스 미리보기), `.example-card-badge`.
- 다크/라이트 테마 모두 대응: 기존 테마 변수(크림·코랄 등, `.example-picker`에서 쓰는 변수)와 동일 패턴 사용.

## 데이터 흐름

`snippets.js`(정적) → `window.BlockPyExamples` → `ExampleGallery`가 읽어 카테고리로 그룹핑/필터 → 카드 `불러오기` → `App.loadExampleSnippet(sn)` → `setCode`/`setShouldDesugar`/탭전환 → `syncCodeToBlocks`(Python→IR→blocks). 콘텐츠 추가는 `snippets.js`만 편집하면 자동 반영.

## 에러/엣지 처리

- `window.BlockPyExamples`가 없거나 빈 배열이면: `예제` 버튼을 **아예 렌더하지 않는다**(기존 드롭다운의 `examples.length > 0` 가드와 동일 규칙). 방어적으로 `ExampleGallery`도 예제 0개일 때 "예제가 없습니다" 빈 상태를 표시하지만, 정상 경로에서는 도달하지 않는다.
- 지연 sync 창 안에 사용자가 코드를 바꾸면 `latestCodeRef` 가드가 사용자 코드를 보존.
- 변환 실패(파서 에러 등)는 기존 `syncCodeToBlocks`의 처리(로그 + syntaxStatus)를 그대로 따른다 — 갤러리는 추가 처리를 하지 않는다.

## 테스트

### 신규: `tests/example_gallery.spec.js` (Playwright, `PORT=3100`, 백엔드 불필요)
1. `#btn-examples` 클릭 → 갤러리 모달 노출.
2. 모달의 예제 카드 수가 `window.BlockPyExamples.length`와 일치, 카테고리 칩이 실제 카테고리 집합을 반영.
3. 특정 카테고리 칩 클릭 → 그 카테고리 카드만 표시(수 검증).
4. 백엔드 불필요 스니펫(예: `basics-arith`) 카드 `불러오기` → 모달 닫힘, `#python-code` textarea에 해당 코드 반영, `activeEditorTab==='python'`, `[Examples]` 로그 노출, 그리고 `window.__blocklyWorkspace.getAllBlocks().length > 0`(자동 변환 확인).
5. Esc / 백드롭 / ✕ 각각으로 모달 닫힘.

### 회귀
- 기존 `tests/examples_roundtrip.spec.js`(스니펫 라운드트립)는 **수정하지 않음**. `snippets.js`를 건드리지 않으므로 영향 없음.
- IR 게이트(`npm run test:ir`)는 블록 코어 미변경이므로 영향 없음.

## 손대지 않는 것 (제약)

- 블록 코어: `irBlocks.js`, `irToBlockly.js`, `blocklyToIr.js`, `irToolbox.js`, `libRegistry.js`, `libImport.js`, `irDesugar.js`, `pyAstBridge.js`.
- `src/examples/snippets.js` — 읽기 전용(콘텐츠 변경 없음).
- 로봇/TM 관련 파일.
- `tests/examples_roundtrip.spec.js`.

## 열린 질문

없음(로드 후 화면=파이썬, 내용=기존 목록, 위치=상단 버튼+모달로 확정).

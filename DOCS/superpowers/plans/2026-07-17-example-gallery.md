# 예제 갤러리 (Example Gallery) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 상단 액션 바의 `예제` 버튼으로 카테고리별 예제 카드 갤러리(모달)를 열고, 카드를 고르면 해당 파이썬 코드가 편집기에 로드되어 기존 파이프라인으로 블록으로 자동 변환되게 한다(로드 후 파이썬 화면 표시).

**Architecture:** 순수 표시용 React 모달 컴포넌트(`ExampleGallery.jsx`)가 단일 소스 `window.BlockPyExamples`(= `src/examples/snippets.js`)를 읽어 카테고리로 그룹핑·필터한다. 로드/변환/탭 전환 로직은 `App.jsx`의 공유 핸들러(`loadExampleSnippet`)가 담당하며, 기존 편집기 헤더 드롭다운도 같은 핸들러로 통합한다(연속 로드 시 미변환 잠복 버그 동시 교정). 기존 `imagePreview` 오버레이와 동일한 모달 패턴·테마 변수를 재사용한다.

**Tech Stack:** React 19 + Vite, 기존 CSS 변수(테마 대응), Playwright(`PORT=3100`, 백엔드 불필요).

## Global Constraints

- **블록 코어 불변:** `irBlocks.js`, `irToBlockly.js`, `blocklyToIr.js`, `irToolbox.js`, `libRegistry.js`, `libImport.js`, `irDesugar.js`, `pyAstBridge.js` 를 수정하지 않는다.
- **콘텐츠 불변:** `src/examples/snippets.js` 는 **읽기 전용** — 예제 목록을 변경하지 않는다.
- **로봇/TM 불변:** 로봇(dobotkit)·Teachable Machine 관련 파일을 건드리지 않는다.
- **회귀 스펙 불변:** `tests/examples_roundtrip.spec.js` 를 수정하지 않는다.
- **수정 파일은 4개뿐:** `src/components/ExampleGallery.jsx`(신규), `src/App.jsx`(수정), `src/index.css`(수정), `tests/example_gallery.spec.js`(신규). 그 외 파일은 건드리지 않는다.
- **로드 후 화면 = 파이썬 편집기(`activeEditorTab='python'`).**
- 카테고리 라벨은 스니펫의 `category` 값을 그대로 사용한다(하드코딩된 카테고리 표 금지).
- 컴포넌트는 `open`이 false면 `null`을 렌더한다. `예제` 버튼은 `window.BlockPyExamples`가 비어 있으면 렌더하지 않는다.

---

## File Structure

- `src/components/ExampleGallery.jsx` — **신규**. 순수 표시용 모달. props `{ open, onClose, onLoad }`. `window.BlockPyExamples`를 읽어 카테고리 필터 + 카드 그리드 렌더. Esc/백드롭/✕ 닫기. 로드/변환 로직은 갖지 않고 `onLoad(snippet)`로 위임.
- `src/App.jsx` — **수정(순수 추가 + 한 곳 교정)**. `showExamples` 상태, `loadExampleSnippet` 핸들러, 액션 바 `예제` 버튼, `<ExampleGallery/>` 렌더, 기존 드롭다운 `onLoadExample` 통합.
- `src/index.css` — **수정(추가만)**. `.example-gallery-*`, `.example-cat-*`, `.example-card-*` 규칙(기존 CSS 변수로 테마 대응).
- `tests/example_gallery.spec.js` — **신규**. Playwright 흐름 테스트.

---

### Task 1: 예제 갤러리 (컴포넌트 + App 통합 + CSS + 테스트)

컴포넌트·통합·CSS·테스트가 하나의 테스트 가능한 산출물로 묶인다(컴포넌트 단독은 Playwright로 검증 불가). TDD: 실패 테스트 → 구현 → 통과.

**Files:**
- Create: `src/components/ExampleGallery.jsx`
- Modify: `src/App.jsx` (import 추가 / 상태 추가 / 핸들러 추가 / 액션 바 버튼 / 모달 렌더 / 드롭다운 통합)
- Modify: `src/index.css` (말미에 스타일 블록 추가)
- Test: `tests/example_gallery.spec.js`

**Interfaces:**
- Consumes:
  - `window.BlockPyExamples: Array<{ id, title, category, code, desugar, ... }>` — 단일 소스(`src/examples/snippets.js`).
  - `App.jsx`의 기존 심볼(수정 대상 파일 내부에서 사용): `setCode`, `setShouldDesugar`, `setHighlightedLine`, `setActiveEditorTab`, `setLogs`, `latestCodeRef`, `syncCodeToBlocks` — 이미 정의되어 있음.
- Produces:
  - React 컴포넌트 `ExampleGallery({ open, onClose, onLoad })` (default export).
  - App 핸들러 `loadExampleSnippet(snippet)`.
  - DOM 계약(테스트가 의존 — 이름 변경 금지): 버튼 `#btn-examples`, 모달 박스 `.example-gallery-box`, 백드롭 `.example-gallery-overlay`, 닫기 `#example-gallery-close`, 카테고리 필터 `#example-cat-filter`의 칩 `.example-cat-chip`, 카드 그리드 `#example-card-grid`의 카드 `.example-card[data-example-id="<id>"]`.

- [ ] **Step 1: 실패 테스트 작성** — `tests/example_gallery.spec.js` 를 아래 내용으로 생성한다.

```js
const { test, expect } = require('@playwright/test');

// 예제 갤러리 전체 흐름: 버튼 → 모달 → 카테고리 필터 → 카드 불러오기(코드 반영 + 자동 블록 변환) → 닫기.
// 백엔드 불필요: 변환은 페이지 내 Pyodide로, 로드 대상 basics-arith 는 import가 없어 오프라인에서 완전 변환된다.
test.describe('Example Gallery', () => {
  test('버튼 → 모달 → 필터 → 불러오기 → 자동 변환 → 닫기', async ({ page }) => {
    await page.goto('/');

    // 앱/변환 파이프라인 준비 대기(스타트업 데모가 이미 변환되어 워크스페이스가 뜬 상태).
    await page.waitForFunction(
      () => !!(window.__blocklyWorkspace && window.BlockPyExamples && window.BlockPyAstBridge),
      null, { timeout: 60000 },
    );
    const total = await page.evaluate(() => window.BlockPyExamples.length);
    expect(total).toBeGreaterThan(0);

    // 1) 버튼으로 모달 열기
    await page.locator('#btn-examples').click();
    await expect(page.locator('.example-gallery-box')).toBeVisible();

    // 2) 카드 수 = 전체 예제 수
    await expect.poll(async () => page.locator('#example-card-grid .example-card').count())
      .toBe(total);

    // 3) 카테고리 필터: 'Basics' 칩 클릭 → Basics 예제만
    const basicsCount = await page.evaluate(
      () => window.BlockPyExamples.filter((s) => s.category === 'Basics').length,
    );
    await page.locator('.example-cat-chip', { hasText: 'Basics' }).click();
    await expect.poll(async () => page.locator('#example-card-grid .example-card').count())
      .toBe(basicsCount);

    // 4) basics-arith 카드 불러오기
    await page.locator('[data-example-id="basics-arith"]').click();
    // 모달 닫힘 + 코드 반영(파이썬 탭)
    await expect(page.locator('.example-gallery-box')).toHaveCount(0);
    const expected = await page.evaluate(
      () => window.BlockPyExamples.find((s) => s.id === 'basics-arith').code,
    );
    await expect(page.locator('#python-code')).toHaveValue(expected, { timeout: 15000 });
    // 자동 블록 변환: 새 코드가 오류 없이 변환됨(Code Valid) + 워크스페이스에 블록 존재.
    await expect(page.locator('#syntax-status-text.valid')).toBeVisible({ timeout: 30000 });
    await expect.poll(async () => page.evaluate(
      () => (window.__blocklyWorkspace ? window.__blocklyWorkspace.getAllBlocks(false).length : 0),
    ), { timeout: 30000 }).toBeGreaterThan(0);

    // 5) 다시 열고 Esc로 닫기
    await page.locator('#btn-examples').click();
    await expect(page.locator('.example-gallery-box')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.locator('.example-gallery-box')).toHaveCount(0);

    // 6) 백드롭 클릭 닫기
    await page.locator('#btn-examples').click();
    await expect(page.locator('.example-gallery-box')).toBeVisible();
    await page.locator('.example-gallery-overlay').click({ position: { x: 5, y: 5 } });
    await expect(page.locator('.example-gallery-box')).toHaveCount(0);
  });
});
```

- [ ] **Step 2: 실패 확인**

Run (Git Bash): `PORT=3100 npx playwright test tests/example_gallery.spec.js`
(PowerShell: `$env:PORT=3100; npx playwright test tests/example_gallery.spec.js`)
Expected: FAIL — `#btn-examples` 를 찾지 못해 타임아웃(아직 구현 전).

- [ ] **Step 3: `ExampleGallery.jsx` 생성** — `src/components/ExampleGallery.jsx` 를 아래 내용으로 생성한다.

```jsx
import React, { useEffect, useState } from 'react';

// 예제 갤러리 모달 — 상단 '예제' 버튼으로 열린다. window.BlockPyExamples(= src/examples/snippets.js,
// 단일 소스)를 읽어 카테고리로 그룹핑하고, 카드를 고르면 onLoad(snippet)로 상위에 위임한다.
// 순수 표시용: 코드 로드/변환/탭 전환은 모두 App의 onLoad 핸들러가 담당한다.
const ALL = '__ALL__';

export default function ExampleGallery({ open, onClose, onLoad }) {
  const examples = (typeof window !== 'undefined' && window.BlockPyExamples) || [];
  const [activeCategory, setActiveCategory] = useState(ALL);

  // Esc로 닫기 — 열려 있을 때만 리스너 부착.
  useEffect(() => {
    if (!open) return undefined;
    const onKey = (e) => { if (e.key === 'Escape') onClose && onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  // 카테고리 목록: 코드에 실제 존재하는 category 값의 등장 순서를 보존(중복 제거).
  const categories = [];
  for (const s of examples) if (s && s.category && !categories.includes(s.category)) categories.push(s.category);

  const visible = activeCategory === ALL
    ? examples
    : examples.filter((s) => s.category === activeCategory);

  const preview = (code) => {
    const lines = String(code || '').split('\n');
    const head = lines.slice(0, 3).join('\n');
    return lines.length > 3 ? head + '\n…' : head;
  };

  return (
    <div className="example-gallery-overlay" onClick={() => onClose && onClose()}>
      <div className="example-gallery-box" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="예제 갤러리">
        <div className="example-gallery-head">
          <span><i className="fa-solid fa-book-open"></i> 예제 불러오기</span>
          <button className="btn btn-secondary btn-xs" id="example-gallery-close" onClick={() => onClose && onClose()}>✕</button>
        </div>

        {examples.length === 0 ? (
          <div className="example-empty">예제가 없습니다.</div>
        ) : (
          <>
            <div className="example-cat-filter" id="example-cat-filter">
              <button
                className={`example-cat-chip ${activeCategory === ALL ? 'active' : ''}`}
                onClick={() => setActiveCategory(ALL)}
              >전체</button>
              {categories.map((cat) => (
                <button
                  key={cat}
                  className={`example-cat-chip ${activeCategory === cat ? 'active' : ''}`}
                  onClick={() => setActiveCategory(cat)}
                >{cat}</button>
              ))}
            </div>

            <div className="example-card-grid" id="example-card-grid">
              {visible.map((s) => (
                <div
                  key={s.id}
                  className="example-card"
                  data-example-id={s.id}
                  role="button"
                  tabIndex={0}
                  title={`"${s.title}" 불러오기`}
                  onClick={() => onLoad && onLoad(s)}
                  onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onLoad && onLoad(s); } }}
                >
                  <div className="example-card-top">
                    <span className="example-card-title">{s.title}</span>
                    <span className="example-card-badge">{s.category}</span>
                  </div>
                  <pre className="example-card-code">{preview(s.code)}</pre>
                  <span className="example-card-load"><i className="fa-solid fa-download"></i> 불러오기</span>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: `App.jsx` 통합** — 아래 5개 편집을 적용한다.

**4a. import 추가** — 기존 `import TeachableMachine from './components/TeachableMachine';`(11행) 바로 다음 줄에 삽입:

```jsx
import ExampleGallery from './components/ExampleGallery';
```

**4b. 상태 추가** — `const [imagePreview, setImagePreview] = useState(null);` 근처(파일 상단 상태 그룹)에 한 줄 추가:

```jsx
const [showExamples, setShowExamples] = useState(false);
```

**4c. 핸들러 추가** — `loadDemoScript` 함수 정의가 끝나는 `};` 바로 다음(즉 `loadDemoScript` 아래)에 삽입:

```jsx
  // 예제 갤러리/드롭다운 공유 로드 경로. loadDemoScript와 동일한 안전 패턴:
  // 코드+desugar 세팅 → 파이썬 화면 전환 → 지연 변환(세대 가드가 중복/경합 안전 처리).
  // latestCodeRef 가드: 지연 창 안에 사용자가 코드를 바꾸면 덮어쓰지 않는다.
  const loadExampleSnippet = (sn) => {
    if (!sn || typeof sn.code !== 'string') return;
    setShouldDesugar(!!sn.desugar);
    latestCodeRef.current = sn.code;
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

**4d. 액션 바 버튼 추가** — `editor-tab-actions` 안, `Image` 업로드 `<label>` 앞(또는 `Run` 버튼 근처)에 삽입. `window.BlockPyExamples`가 비어 있으면 렌더하지 않는다:

```jsx
                {(typeof window !== 'undefined' && window.BlockPyExamples && window.BlockPyExamples.length > 0) && (
                  <button
                    className="btn btn-secondary btn-sm"
                    id="btn-examples"
                    onClick={() => setShowExamples(true)}
                    title="예제 코드 갤러리 열기"
                  >
                    <i className="fa-solid fa-book-open"></i> 예제
                  </button>
                )}
```

**4e. 모달 렌더 + 드롭다운 통합**

(i) 기존 `imagePreview` 오버레이 블록(`{imagePreview && ( ... )}`) 바로 다음에 삽입:

```jsx
      <ExampleGallery
        open={showExamples}
        onClose={() => setShowExamples(false)}
        onLoad={loadExampleSnippet}
      />
```

(ii) 기존 PythonEditor의 드롭다운 배선을 공유 핸들러로 교체 — 아래 한 줄을
`onLoadExample={(sn) => { setCode(sn.code); setShouldDesugar(sn.desugar); }}`
에서 다음으로 변경:

```jsx
                  onLoadExample={loadExampleSnippet}
```

- [ ] **Step 5: `index.css` 스타일 추가** — 파일 말미에 아래 블록을 추가한다(기존 CSS 변수로 라이트/다크 테마 자동 대응).

```css
/* ─── Example gallery modal (상단 '예제' 버튼) ───────────────────────────────── */
.example-gallery-overlay {
  position: fixed; inset: 0; z-index: 9999;
  background: rgba(20,20,19,0.55); backdrop-filter: blur(2px);
  display: flex; align-items: center; justify-content: center;
}
.example-gallery-box {
  background: var(--bg-card); border: 1px solid var(--hairline);
  border-radius: 12px; padding: 14px 16px; width: min(880px, 88vw); max-height: 82vh;
  box-shadow: 0 20px 60px rgba(0,0,0,0.35); display: flex; flex-direction: column;
}
.example-gallery-head {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  font-size: 0.95rem; font-weight: 600; color: var(--text-primary);
  margin-bottom: 10px; padding: 2px;
}
.example-gallery-head i { color: var(--coral); margin-right: 6px; }
.example-empty { color: var(--text-muted); font-size: 0.85rem; padding: 24px; text-align: center; }
.example-cat-filter { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px; }
.example-cat-chip {
  background: var(--canvas); color: var(--text-secondary);
  border: 1px solid var(--hairline); border-radius: 999px;
  padding: 4px 12px; font-size: 0.76rem; font-weight: 500; cursor: pointer;
  transition: all var(--transition-speed);
}
.example-cat-chip:hover { border-color: var(--coral); }
.example-cat-chip.active { background: var(--coral); color: #fff; border-color: var(--coral); }
.example-card-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px; overflow-y: auto; padding: 2px; align-content: start;
}
.example-card {
  display: flex; flex-direction: column; gap: 8px; text-align: left;
  background: var(--surface-soft); border: 1px solid var(--hairline-soft);
  border-radius: 10px; padding: 10px 12px; cursor: pointer;
  transition: border-color var(--transition-speed), transform var(--transition-speed);
}
.example-card:hover { border-color: var(--coral); transform: translateY(-1px); }
.example-card:focus-visible { outline: 2px solid var(--coral); outline-offset: 1px; }
.example-card-top { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.example-card-title {
  font-size: 0.86rem; font-weight: 600; color: var(--text-primary);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.example-card-badge {
  flex-shrink: 0; font-size: 0.66rem; font-weight: 600; color: var(--coral);
  background: var(--active-highlight); border-radius: 6px; padding: 2px 7px;
}
.example-card-code {
  margin: 0; font-family: var(--font-mono); font-size: 0.72rem; line-height: 1.4;
  color: var(--text-secondary); background: var(--canvas);
  border: 1px solid var(--hairline-soft); border-radius: 7px; padding: 7px 9px;
  white-space: pre; overflow: hidden; max-height: 4.6em;
}
.example-card-load { font-size: 0.74rem; font-weight: 600; color: var(--coral); }
.example-card-load i { margin-right: 5px; }
```

- [ ] **Step 6: 통과 확인**

Run (Git Bash): `PORT=3100 npx playwright test tests/example_gallery.spec.js`
Expected: PASS (1 passed).

- [ ] **Step 7: 회귀 확인** — 기존 예제 라운드트립 스펙이 여전히 통과하는지 본다(콘텐츠·블록 코어 미변경이므로 통과해야 함).

Run (Git Bash): `PORT=3100 npx playwright test tests/examples_roundtrip.spec.js`
Expected: PASS (기존과 동일).

- [ ] **Step 8: 커밋**

```bash
git add src/components/ExampleGallery.jsx src/App.jsx src/index.css tests/example_gallery.spec.js
git commit -m "feat(examples): 상단 '예제' 버튼 + 카드 갤러리 모달으로 예제 코드 로드

카테고리 필터 + 카드 그리드. 카드 선택 시 파이썬 코드 로드 → 파이썬 화면 전환 →
자동 블록 변환. 기존 헤더 드롭다운도 공유 loadExampleSnippet 경로로 통합(연속 로드
미변환 잠복 버그 교정). 내용은 기존 snippets.js 재사용."
```

---

## Self-Review

**1. Spec coverage:**
- 상단 버튼 + 모달 → Step 4d(버튼), Step 3/4e(모달). ✅
- 카테고리 필터 → Step 3(칩) + 테스트 Step 1(필터 검증). ✅
- 카드(제목/배지/코드 미리보기/불러오기) → Step 3. ✅
- 로드 = 코드 세팅 + 파이썬 화면 + 자동 변환 + 로그 → Step 4c. ✅
- Esc/백드롭/✕ 닫기 → Step 3(Esc, 백드롭, ✕) + 테스트(Esc, 백드롭). ✅
- 내용 = 기존 snippets 재사용 → 컴포넌트가 `window.BlockPyExamples`만 읽음, snippets.js 미수정. ✅
- 드롭다운 통합(잠복 버그 교정) → Step 4e(ii). ✅
- 예제 0개 시 버튼 미노출 → Step 4d 가드 + 컴포넌트 빈 상태. ✅

**2. Placeholder scan:** TBD/TODO/"적절히 처리" 없음. 모든 코드 스텝에 전체 코드 포함. ✅

**3. Type/이름 일관성:** 컴포넌트 default export `ExampleGallery`(Step 3) = App import(4a) = 렌더(4e). props `{open,onClose,onLoad}` 3곳 일치. DOM id/클래스(`#btn-examples`, `.example-gallery-box`, `.example-gallery-overlay`, `#example-cat-filter`, `.example-cat-chip`, `#example-card-grid`, `.example-card`, `data-example-id`)가 컴포넌트·CSS·테스트에서 동일. `loadExampleSnippet`가 사용하는 심볼(`setShouldDesugar`, `latestCodeRef`, `setCode`, `setHighlightedLine`, `setActiveEditorTab`, `setLogs`, `syncCodeToBlocks`)은 모두 App.jsx에 기존 정의됨. ✅

**4. 제약 준수:** 수정 파일 4개(신규 2 + 수정 2)뿐. 블록 코어·snippets.js·로봇/TM·examples_roundtrip 스펙 미수정. ✅

import React, { useState } from 'react';

// 예제 목록 본문(카테고리 필터 + 카드 그리드) — 좌측 '예제' 보조 탭에서 렌더된다.
// 순수 표시용: 카드 선택 시 onLoad(snippet)로 상위(App.loadExampleSnippet)에 위임한다.
// 두 소스를 합쳐 읽는다: 인라인 스니펫(BlockPyExamples) + 파일 서빙 수업 예제(BlockPyLessonExamples).
const ALL = '__ALL__';

export default function ExampleGalleryContent({ onLoad }) {
  const inlineExamples = (typeof window !== 'undefined' && window.BlockPyExamples) || [];
  const lessonExamples = (typeof window !== 'undefined' && window.BlockPyLessonExamples) || [];
  const examples = [...inlineExamples, ...lessonExamples];
  const [activeCategory, setActiveCategory] = useState(ALL);

  if (examples.length === 0) {
    return <div className="example-empty">예제가 없습니다.</div>;
  }

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
            <pre className="example-card-code">{s.preview || preview(s.code)}</pre>
            <span className="example-card-load"><i className="fa-solid fa-download"></i> 불러오기</span>
          </div>
        ))}
      </div>
    </>
  );
}

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

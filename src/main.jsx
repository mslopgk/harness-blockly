import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';

// 디자인 v2 는 한국 블록코딩 사이트(엔트리) 톤을 따라 시스템 폰트 스택만 쓴다
// (index.css: --font-sans = Pretendard/Noto Sans KR/맑은 고딕…, --font-mono = D2Coding/Consolas…).
// v1 의 @fontsource Inter/Cormorant Garamond/JetBrains Mono import 는 어떤 CSS 도
// 참조하지 않으면서 woff/woff2 20여 개를 dist 에 밀어넣고 있어 제거했다.
// (오프라인 규칙은 그대로 — CDN/@import 없음, FontAwesome 은 public/vendor 에서 서빙.)

import './index.css';

// Import compiler utilities so they are bundled by Vite and register globally
import './utils/libRegistry.js';   // Phase 5: window.BlockPyLibRegistry (load before irToolbox.js)
import './utils/libImport.js';     // Phase B: window.BlockPyLibImport (blockpy-gen LibrarySpec -> libRegistry)
import './utils/curateHeuristic.js'; // deterministic no-AI curation (offline fallback for /api/abstract-library)
import './utils/pyAstBridge.js';
import './utils/irToBlockly.js';
import './utils/blocklyToIr.js';
import './utils/irDesugar.js';   // Phase 4: window.BlockPyIrDesugar (optional IR->IR desugar pass)
import './utils/irBlocks.js';
import './utils/irToolbox.js';   // builds window.BlockPyIrToolbox (load-order only matters for the live coverage test, which compares against the irBlocks.js registry)
import './utils/teachable.js'; // window.BlockPyTM (Teachable Machine) 노출
import './examples/snippets.js';
import './examples/lessons.js';  // window.BlockPyLessonExamples (강의자료 수업 예제 — 파일 서빙)

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

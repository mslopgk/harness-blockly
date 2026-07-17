import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App.jsx';

// Self-hosted fonts (offline). @fontsource ships the woff2 + @font-face CSS; Vite bundles them
// into dist/assets, so the app needs no Google Fonts CDN. Weights match index.css usage.
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import '@fontsource/cormorant-garamond/500.css';
import '@fontsource/cormorant-garamond/600.css';
import '@fontsource/cormorant-garamond/700.css';
import '@fontsource/jetbrains-mono/400.css';
import '@fontsource/jetbrains-mono/500.css';

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

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);

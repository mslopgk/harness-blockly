#!/usr/bin/env node
// Copies offline runtime assets from node_modules into public/vendor so the desktop
// (Electron) build runs with NO CDN. Run automatically by `prebuild` before every
// `vite build`, and manually via `npm run vendor`. public/vendor is gitignored — these
// are reproducible copies of pinned npm deps (blockly, @fortawesome/fontawesome-free,
// pyodide), not source to commit.
const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const NM = path.join(ROOT, 'node_modules');
const OUT = path.join(ROOT, 'public', 'vendor');

function copy(src, dst) {
  fs.mkdirSync(path.dirname(dst), { recursive: true });
  fs.copyFileSync(src, dst);
}

function copyDir(src, dst) {
  fs.mkdirSync(dst, { recursive: true });
  for (const name of fs.readdirSync(src)) {
    const s = path.join(src, name);
    const d = path.join(dst, name);
    if (fs.statSync(s).isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}

// Whole-directory copies (recursive).
const DIRS = [
  // Blockly media: trashcan / zoom / dropdown icons + click/delete sounds. Without this,
  // Blockly fetches them from static.blockly.com (broken offline). Set media:'/vendor/blockly/media/'.
  ['blockly/media', 'blockly/media'],
];

// One [from node_modules] -> [to public/vendor] mapping per file.
const FILES = [
  // Blockly core + Python generator + English messages (loaded as <script> in index.html)
  ['blockly/blockly_compressed.js', 'blockly/blockly_compressed.js'],
  ['blockly/blocks_compressed.js', 'blockly/blocks_compressed.js'],
  ['blockly/python_compressed.js', 'blockly/python_compressed.js'],
  ['blockly/msg/en.js', 'blockly/msg/en.js'],

  // FontAwesome CSS + webfonts (the CSS references ../webfonts/* relatively)
  ['@fortawesome/fontawesome-free/css/all.min.css', 'fontawesome/css/all.min.css'],
  ['@fortawesome/fontawesome-free/webfonts/fa-solid-900.woff2', 'fontawesome/webfonts/fa-solid-900.woff2'],
  ['@fortawesome/fontawesome-free/webfonts/fa-regular-400.woff2', 'fontawesome/webfonts/fa-regular-400.woff2'],
  ['@fortawesome/fontawesome-free/webfonts/fa-brands-400.woff2', 'fontawesome/webfonts/fa-brands-400.woff2'],
  ['@fortawesome/fontawesome-free/webfonts/fa-v4compatibility.woff2', 'fontawesome/webfonts/fa-v4compatibility.woff2'],

  // Pyodide CORE (CPython + stdlib). Enough for the Python<->block IR bridge (uses `ast`),
  // sprite/turtle, and pure-Python Run — all OFFLINE. Scientific wheels (numpy, opencv…) are
  // NOT bundled; run those through the real local-Python backend (/api/run-python).
  ['pyodide/pyodide.js', 'pyodide/pyodide.js'],
  ['pyodide/pyodide.mjs', 'pyodide/pyodide.mjs'],
  ['pyodide/pyodide.asm.js', 'pyodide/pyodide.asm.js'],
  ['pyodide/pyodide.asm.wasm', 'pyodide/pyodide.asm.wasm'],
  ['pyodide/python_stdlib.zip', 'pyodide/python_stdlib.zip'],
  ['pyodide/pyodide-lock.json', 'pyodide/pyodide-lock.json'],
];

let copied = 0;
let missing = 0;
for (const [from, to] of FILES) {
  const src = path.join(NM, from);
  const dst = path.join(OUT, to);
  if (!fs.existsSync(src)) {
    console.warn(`[vendor] MISSING (skipped): ${from} — run npm install`);
    missing++;
    continue;
  }
  copy(src, dst);
  copied++;
}

for (const [from, to] of DIRS) {
  const src = path.join(NM, from);
  const dst = path.join(OUT, to);
  if (!fs.existsSync(src)) {
    console.warn(`[vendor] MISSING dir (skipped): ${from} — run npm install`);
    missing++;
    continue;
  }
  copyDir(src, dst);
  copied++;
}

// ─── MobileNet v2 (Teachable Machine 임베딩 추출기) 오프라인 vendoring ──────────
// @tensorflow-models/mobilenet 은 기본적으로 storage.googleapis.com 에서 가중치를
// 내려받는다(온라인 전용). 오프라인 구동을 위해 model.json + weight shard 들을
// public/vendor/mobilenet 으로 한 번 복사해 둔다. 존재하면 skip, 오프라인이면 경고만.
async function vendorMobileNet() {
  const base = 'https://storage.googleapis.com/tfjs-models/tfjs/mobilenet_v2_1.0_224/';
  const outDir = path.join(OUT, 'mobilenet');
  const modelJson = path.join(outDir, 'model.json');
  if (fs.existsSync(modelJson)) {
    console.log('[vendor] mobilenet: already present, skipped');
    return;
  }
  if (typeof fetch !== 'function') {
    console.warn('[vendor] mobilenet: global fetch 없음(Node<18) — 건너뜀. 온라인 Node18+ 에서 `npm run vendor` 재실행 필요');
    return;
  }
  try {
    fs.mkdirSync(outDir, { recursive: true });
    const mjRes = await fetch(base + 'model.json');
    if (!mjRes.ok) throw new Error('model.json HTTP ' + mjRes.status);
    const mjText = await mjRes.text();
    fs.writeFileSync(modelJson, mjText, 'utf8');
    const manifest = JSON.parse(mjText).weightsManifest || [];
    const shards = manifest.flatMap((g) => g.paths || []);
    for (const shard of shards) {
      const r = await fetch(base + shard);
      if (!r.ok) throw new Error(shard + ' HTTP ' + r.status);
      const buf = Buffer.from(await r.arrayBuffer());
      fs.writeFileSync(path.join(outDir, shard), buf);
    }
    console.log(`[vendor] mobilenet: downloaded model.json + ${shards.length} shard(s)`);
  } catch (e) {
    console.warn('[vendor] mobilenet: 다운로드 실패(오프라인?) — TM 학습은 온라인에서 `npm run vendor` 후 가능:', e.message);
  }
}

(async () => {
  await vendorMobileNet();
  console.log(`[vendor] copied ${copied} item(s) into public/vendor${missing ? `, ${missing} missing` : ''}`);
  if (missing) process.exitCode = 0; // non-fatal: build can still proceed (CDN fallback at runtime)
})();

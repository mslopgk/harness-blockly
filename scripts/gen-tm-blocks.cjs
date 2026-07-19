// Generate src/data/tmSpecs.json — 파이썬 네이티브 TM(runtime/tm.py) 의 tm 고정 블록 스펙.
// dobotkit(gen-robot-blocks.cjs)과 동일 패턴: 손으로 큐레이션한 LibrarySpec 를 마운트 시 builtin 등록.
// Re-generate with: node scripts/gen-tm-blocks.cjs
const fs = require('fs');
const path = require('path');

const P = (...n) => n.map((x) => ({ name: x, kind: 'positional', hasDefault: false }));
const cmd = (name, ...a) => ({ kind: 'method', owner: 'Model', name, params: P(...a), returns: false });
const val = (name, ...a) => ({ kind: 'method', owner: 'Model', name, params: P(...a), returns: true });

const spec = {
  module: 'tm',
  entries: [
    { kind: 'class', name: 'Model', qualName: 'tm.Model', params: P('labels'), returns: true }, // model = tm.Model([...])
    cmd('add_example', 'frame', 'label'),
    cmd('train'),
    val('predict', 'frame'),
    val('predict_proba', 'frame'),
    cmd('save', 'path'),
    { kind: 'property', owner: 'Model', name: 'labels', qualName: 'tm.Model.labels' },
    { kind: 'function', name: 'load_model', qualName: 'tm.load_model', params: P('path'), returns: true },
  ],
};

const dest = path.join(__dirname, '..', 'src', 'data', 'tmSpecs.json');
fs.mkdirSync(path.dirname(dest), { recursive: true });
fs.writeFileSync(dest, JSON.stringify([spec], null, 1));
console.log(`[tm] wrote tm spec (${spec.entries.length} entries) -> ${path.relative(path.join(__dirname, '..'), dest)}`);

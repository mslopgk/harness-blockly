/* irToolbox.js — the drag-to-edit toolbox, built from ir_* blocks (side-effect load).
 *
 * After the IR engine swap (commit 651e2be) the legacy XML toolbox was retired because
 * blocklyToIr only understands ir_* types. This restores the palette: every standalone ir_*
 * block, grouped by worklist family, exposed so a user can drag a fresh block onto the canvas
 * (not only reach blocks via Python -> Convert).
 *
 * Single source of truth: IR_TOOLBOX_TABLE below. buildIrToolbox() compiles it to a Blockly
 * `categoryToolbox` JSON object. We use JSON (not hand-written XML) because most ir_* blocks
 * are mutator-driven (variable arity); a valid default `extraState` + shadow children are far
 * cleaner as JSON than as XML <mutation> nodes.
 *
 * Default inputs: a freshly-dragged block must convert to valid Python immediately, so each
 * REQUIRED value/expr input carries a shadow default child. Statement *bodies* are left empty
 * (blocklyToIr's stmtListOrPass synthesizes `pass`); only value/expr inputs get shadows.
 * blocklyToIr collapses a shadow-only input into its block on read, so the defaults round-trip.
 *
 * HELPER-only blocks valid solely inside a parent (ir_formattedvalue, inside ir_joinedstr) are
 * intentionally NOT exposed; the browser coverage test asserts this is the only omission.
 */

// ── 엔트리 공식 블록 팔레트 (디자인 v2) ───────────────────────────────────────────────────
// 소스오브트루스: DOCS/superpowers/specs/2026-07-25-blockpy-korean-blockcoding-design-v2.md §B
// (entrylabs/entryjs `src/theme/standard.js` 실측). 카테고리마다 3단:
//   default = 블록 본체 / lighten = 내부 필드·하이라이트 / darken = 외곽선.
// 엔트리 룩의 입체감은 "단색 1톤"이 아니라 이 3단에서 나온다 — v1 이 저에너지로 읽힌 원인이
// 카테고리 색을 단색으로 눌러버린 것이었다. BlocklyEditor 가 이 표를 그대로 Blockly 테마
// blockStyles(colourPrimary/Secondary/Tertiary) 로 등록하므로, 여기가 색의 유일한 출처다.
// 값은 실측치 그대로 사용한다. 스펙 표에서 lighten 이 '—' 인 JUDGE/EXPANSION 두 칸만
// default 를 흰색과 블렌드해(≈25%) 산출했고, 그 외 어떤 색도 새로 발명하지 않았다.
const ENTRY_PALETTE = {
  START:     { default: '#10D35E', lighten: '#53E68E', darken: '#13BF68' },  // 시작
  FLOW:      { default: '#31C1EC', lighten: '#4ADAFB', darken: '#08ACDD' },  // 흐름
  MOVING:    { default: '#BF63FF', lighten: '#CA7DFF', darken: '#B13EFE' },  // 움직임
  LOOKS:     { default: '#FF5174', lighten: '#FF7792', darken: '#EE3157' },  // 생김새
  BRUSH:     { default: '#FC7E01', lighten: '#FF9831', darken: '#FC5E01' },  // 붓
  SOUND:     { default: '#82D214', lighten: '#9FEC35', darken: '#6EBC02' },  // 소리
  HARDWARE:  { default: '#00CFCA', lighten: '#65E3E0', darken: '#04B5B0' },  // 하드웨어
  CALC:      { default: '#FEB71A', lighten: '#FFDE82', darken: '#FF9C00' },  // 계산
  VARIABLE:  { default: '#F57DF1', lighten: '#FAA0F7', darken: '#EC52E7' },  // 자료
  FUNC:      { default: '#DE6E22', lighten: '#F3853B', darken: '#C85404' },  // 함수
  JUDGE:     { default: '#7E8EFE', lighten: '#9EAAFE', darken: '#1B3AD8' },  // 판단 (lighten 산출)
  TEXT:      { default: '#FC5D01', lighten: '#FF9354', darken: '#E43500' },  // 글상자
  EXPANSION: { default: '#FF8888', lighten: '#FFA6A6', darken: '#EF6D6D' },  // 확장 (lighten 산출)
};
// 톤 키 -> 본체색. 카테고리 탭 색과 블록 본체 색이 같은 표에서 나오므로 절대 어긋나지 않는다.
const tone = (key) => (ENTRY_PALETTE[key] || ENTRY_PALETTE.FLOW).default;

// --- shadow-child helpers (the JSON Blockly expects for a default input) ---
const name = (id) => ({ shadow: { type: 'ir_name', fields: { ID: id } } });
// value is JSON-encoded to match ir_const's field contract (blockToExpr does JSON.parse).
const konst = (jsonValue) => ({ shadow: { type: 'ir_const', fields: { VALUE: JSON.stringify(jsonValue) } } });
// A rounded string shadow (ir_str holds raw text, no JSON quoting).
const text = (s) => ({ shadow: { type: 'ir_str', fields: { TEXT: s } } });
// A fixed built-in function block: ir_call with a non-editable funcName label + arg shadows.
// stmt=true makes it a command (stack) block (print); otherwise a reporter (len, range, …).
const builtin = (funcName, args, stmt) => {
  const inputs = {};
  (args || []).forEach((a, i) => { inputs['ARG' + i] = a; });
  const extraState = { nargs: (args || []).length, kw: [], funcName };
  if (stmt) extraState.stmt = true;
  const entry = { type: 'ir_call', extraState };
  if (args && args.length) entry.inputs = inputs;
  return entry;
};

// A comprehension generator/element default: [elt] for x in items
const COMP_GENS = { gens: [{ ifs: 0, async: false }] };

// The closed family table. Order = worklist order (common -> rare). Each block entry is
// { type, extraState?, fields?, inputs? }; extraState/inputs describe the default drag-out form.
// `tone` = the ENTRY_PALETTE key for the category (디자인 v2 매핑표). The tab colour AND every
// block body in that category resolve from it, so the palette can never drift from the tabs.
const IR_TOOLBOX_TABLE = [
  { name: 'Values', tone: 'FLOW', blocks: [
    { type: 'ir_name' },
    { type: 'ir_str' },                                   // rounded text string (type content directly)
    { type: 'ir_const' },
  ] },
  { name: 'Collections', tone: 'MOVING', blocks: [
    { type: 'ir_list', extraState: { n: 0 } },
    { type: 'ir_tuple', extraState: { n: 0 } },
    { type: 'ir_set', extraState: { n: 1 }, inputs: { ELT0: konst(0) } },
    { type: 'ir_dict', extraState: { n: 0 } },
  ] },
  { name: 'Operators', tone: 'SOUND', blocks: [
    { type: 'ir_binop', inputs: { LEFT: konst(0), RIGHT: konst(0) } },
    { type: 'ir_unaryop', inputs: { OPERAND: konst(0) } },
    { type: 'ir_boolop', extraState: { n: 2 }, inputs: { VAL0: konst(true), VAL1: konst(false) } },
    { type: 'ir_compare', extraState: { n: 1 }, inputs: { LEFT: konst(0), CMP0: konst(0) } },
  ] },
  { name: 'Access', tone: 'HARDWARE', blocks: [
    { type: 'ir_attribute', inputs: { VALUE: name('obj') } },
    { type: 'ir_subscript', inputs: { VALUE: name('obj'), SLICE: konst(0) } },
    { type: 'ir_slice' },                                  // bounds optional (a[:])
    { type: 'ir_starred', inputs: { VALUE: name('args') } },
  ] },
  { name: 'Variables', tone: 'VARIABLE', button: { text: 'Create variable…', callbackkey: 'IR_CREATE_VARIABLE' }, blocks: [
    { type: 'ir_assign', extraState: { n: 1 }, inputs: { TARGET0: name('x'), VALUE: konst(0) } },
    { type: 'ir_augassign', inputs: { TARGET: name('x'), VALUE: konst(1) } },
    { type: 'ir_annassign', inputs: { TARGET: name('x'), ANNOTATION: name('int') } },
    { type: 'ir_namedexpr', inputs: { TARGET: name('x'), VALUE: konst(0) } },
    { type: 'ir_delete', extraState: { n: 1 }, inputs: { TARGET0: name('x') } },
    { type: 'ir_global' },
    { type: 'ir_nonlocal' },
  ] },
  { name: 'Control flow', tone: 'CALC', blocks: [
    { type: 'ir_if', inputs: { TEST: konst(true) } },
    { type: 'ir_if', extraState: { hasElse: true }, inputs: { TEST: konst(true) } },   // if / else
    { type: 'ir_while', inputs: { TEST: konst(true) } },
    { type: 'ir_for', inputs: { TARGET: name('i'), ITER: name('items') } },
    { type: 'ir_for', extraState: { hasElse: true }, inputs: { TARGET: name('i'), ITER: name('items') } },  // for / else
    { type: 'ir_break' },
    { type: 'ir_continue' },
    { type: 'ir_pass' },
  ] },
  { name: 'Functions', tone: 'FUNC', blocks: [
    { type: 'ir_funcdef' },                                // def f(): pass
    { type: 'ir_lambda', inputs: { BODY: konst(0) } },
    { type: 'ir_return' },                                 // bare `return`
    { type: 'ir_call', extraState: { nargs: 0, kw: [] }, inputs: { FUNC: name('func') } },                       // call as a value (reporter)
    { type: 'ir_call', extraState: { nargs: 1, kw: [], stmt: true }, inputs: { FUNC: name('func'), ARG0: name('x') } },  // call as a command (stack)
    { type: 'ir_exprstmt', inputs: { VALUE: name('value') } },
  ] },
  { name: 'Built-ins', tone: 'JUDGE', blocks: [
    builtin('print', [text('Hello')], true),               // print(...) — a command (stack) block
    builtin('input', [text('? ')]),
    builtin('len', [name('items')]),
    builtin('range', [konst(10)]),
    builtin('int', [name('x')]),
    builtin('str', [name('x')]),
    builtin('float', [name('x')]),
    builtin('bool', [name('x')]),
    builtin('abs', [name('x')]),
    builtin('round', [name('x')]),
    builtin('min', [name('items')]),
    builtin('max', [name('items')]),
    builtin('sum', [name('items')]),
    builtin('sorted', [name('items')]),
    builtin('list', [name('x')]),
    builtin('dict', []),
    builtin('set', [name('x')]),
    builtin('tuple', [name('x')]),
    builtin('type', [name('x')]),
    builtin('enumerate', [name('items')]),
    builtin('zip', [name('a'), name('b')]),
    // ── coverage fill (audit): common builtins that were missing ──
    builtin('any', [name('items')]),
    builtin('all', [name('items')]),
    builtin('map', [name('func'), name('items')]),
    builtin('filter', [name('func'), name('items')]),
    builtin('reversed', [name('items')]),
    builtin('isinstance', [name('x'), name('int')]),
    builtin('issubclass', [name('cls'), name('int')]),
    builtin('open', [text('file.txt'), text('r')]),
    builtin('pow', [name('x'), name('y')]),
    builtin('divmod', [name('a'), name('b')]),
    builtin('ord', [text('A')]),
    builtin('chr', [konst(65)]),
    builtin('repr', [name('x')]),
    builtin('format', [name('x'), text('.2f')]),
    builtin('hex', [name('x')]),
    builtin('oct', [name('x')]),
    builtin('bin', [name('x')]),
    builtin('bytes', [name('x')]),
    builtin('bytearray', [name('x')]),
    builtin('frozenset', [name('items')]),
    builtin('complex', [name('re'), name('im')]),
    builtin('iter', [name('items')]),
    builtin('next', [name('it')]),
    builtin('getattr', [name('obj'), text('attr')]),
    builtin('setattr', [name('obj'), text('attr'), name('value')], true),
    builtin('hasattr', [name('obj'), text('attr')]),
    builtin('delattr', [name('obj'), text('attr')], true),
    builtin('callable', [name('x')]),
    builtin('id', [name('x')]),
    builtin('hash', [name('x')]),
    builtin('slice', [konst(0), konst(10)]),
    builtin('super', []),
  ] },
  { name: 'Classes', tone: 'MOVING', blocks: [
    { type: 'ir_classdef' },                               // class C: pass
  ] },
  { name: 'Exceptions', tone: 'LOOKS', blocks: [
    { type: 'ir_try' },                                    // try: pass / except: pass
    { type: 'ir_trystar', extraState: { handlers: [{ type: true, name: null }] },
      inputs: { TYPE0: name('Exception') } },
    { type: 'ir_raise' },                                  // bare re-raise
    { type: 'ir_assert', inputs: { TEST: konst(true) } },
    { type: 'ir_with', extraState: { items: [{ as: false }] }, inputs: { CTX0: name('ctx') } },
  ] },
  { name: 'Imports', tone: 'FLOW', blocks: [
    { type: 'ir_import' },                                 // import os
    { type: 'ir_importfrom' },                             // from os import path
  ] },
  { name: 'Sugar', tone: 'VARIABLE', blocks: [
    { type: 'ir_listcomp', extraState: COMP_GENS, inputs: { ELT: name('x'), TARGET0: name('x'), ITER0: name('items') } },
    { type: 'ir_setcomp', extraState: COMP_GENS, inputs: { ELT: name('x'), TARGET0: name('x'), ITER0: name('items') } },
    { type: 'ir_genexp', extraState: COMP_GENS, inputs: { ELT: name('x'), TARGET0: name('x'), ITER0: name('items') } },
    { type: 'ir_dictcomp', extraState: COMP_GENS, inputs: { KEY: name('k'), VAL: name('v'), TARGET0: name('k'), ITER0: name('items') } },
    { type: 'ir_ifexp', inputs: { BODY: konst(0), TEST: konst(true), ORELSE: konst(0) } },
  ] },
  { name: 'Async', tone: 'HARDWARE', blocks: [
    { type: 'ir_asyncfuncdef' },                           // async def f(): pass
    { type: 'ir_asyncfor', inputs: { TARGET: name('i'), ITER: name('items') } },
    { type: 'ir_asyncwith', extraState: { items: [{ as: false }] }, inputs: { CTX0: name('ctx') } },
    { type: 'ir_await', inputs: { VALUE: name('x') } },
    { type: 'ir_yield' },                                  // bare `yield`
    { type: 'ir_yieldfrom', inputs: { VALUE: name('x') } },
  ] },
  { name: 'Text', tone: 'TEXT', blocks: [
    { type: 'ir_joinedstr', extraState: { n: 0 } },        // f''
  ] },
  { name: 'Match', tone: 'CALC', blocks: [
    // match x: / case _: pass   (MatchAs wildcard — no embedded exprs, no guard)
    { type: 'ir_match', extraState: { cases: [{ pattern: { p: 'As' }, nexpr: 0, guard: false }] },
      inputs: { SUBJECT: name('x') } },
  ] },
  { name: 'Types', tone: 'SOUND', blocks: [
    { type: 'ir_typealias', inputs: { VALUE: name('int') } },  // type X = int
  ] },
];

// A library call rendered as the UNIFIED ir_call block (not a separate lib_* block) so the toolbox
// block is IDENTICAL to what Python→blocks produces. Two shapes, from the registry spec: an imported
// module function as one dotted funcName label (math.sqrt, cv2.imread); an instance method on a
// variable receiver (image.resize → [image ▾].resize). ir_call.updateShape_ then renders it emerald
// with per-param labels. Each positional param carries an ir_name shadow so a freshly-dragged block
// is valid Python immediately. null when the type isn't registered.
function libCallEntry(reg, type) {
  const s = reg.getLibSpec ? reg.getLibSpec(type) : null;
  if (!s) return null;
  const isMethod = !!s.method;
  const params = isMethod ? (s.argNames || []).slice(1) : (s.argNames || []);
  const extraState = { nargs: params.length, kw: [], funcName: null, method: null };
  if (isMethod) extraState.method = s.func;
  else extraState.funcName = `${s.module ? s.module + '.' : ''}${s.func}`;
  if (!s.hasOutput) extraState.stmt = true;
  const entry = { kind: 'block', type: 'ir_call', extraState };
  if (isMethod) entry.fields = { RECV: { name: (s.argNames && s.argNames[0]) || 'obj' } };
  if (params.length) {
    const inputs = {};
    params.forEach((p, i) => { inputs['ARG' + i] = name(p); });
    entry.inputs = inputs;
  }
  return entry;
}

// Sub-category colours — DISTINCT per semantic KIND so, inside a library, "Constants" / "Properties"
// / "Macros" / a curation group are visually separable at a glance (they used to all be one teal).
// Display-only (a category colour never affects a block's lowering).
// v2: 값은 전부 엔트리 팔레트/크롬(스펙 §A·§B)에서 가져와 상위 라이브러리 탭(LIB_PALETTE)·
// ★ 큐레이션 탭과 겹치지 않는 6개 색으로 정리했다 — 임의의 머티리얼 색을 쓰지 않는다.
const SUBCAT = {
  group:     ENTRY_PALETTE.FLOW.darken,        // #08ACDD 의미 그룹 — 진한 블루
  other:     '#606c73',                        // 그룹 없는 호출 — 엔트리 보조 텍스트 슬레이트(중립)
  constants: ENTRY_PALETTE.JUDGE.default,      // #7E8EFE 모듈 상수 — 페리윙클
  property:  ENTRY_PALETTE.FUNC.default,       // #DE6E22 클래스 속성 — 오렌지
  macros:    ENTRY_PALETTE.VARIABLE.darken,    // #EC52E7 조합 워크플로 — 마젠타
  more:      '#979797',                        // "더 보기" 보조 선반 — 엔트리 뮤트 그레이
};

// Top-level library category colour, keyed by the TOP package so a whole-package Blockify keeps its
// submodules a visual family (all serial.* share one hue; cv2 / math / numpy each get their own),
// while the tab NAME still distinguishes members. Deterministic (no Math.random) → stable across
// rebuilds. Curated ★ tabs keep their own fixed accent below.
// v2: 후보 색을 전부 엔트리 팔레트 톤으로 교체하고, 사이 구분이 뚜렷한 9개만 남겼다. SUBCAT
// 6색(#08ACDD/#606c73/#7E8EFE/#DE6E22/#EC52E7/#979797) 과 ★ 큐레이션 틸(HARDWARE) 은 제외 —
// 라이브러리 탭이 자기 하위 Constants/Properties/Macros 나 ★ 탭과 절대 섞이지 않는다.
const LIB_PALETTE = [
  ENTRY_PALETTE.FLOW.default,      // #31C1EC
  ENTRY_PALETTE.MOVING.default,    // #BF63FF
  ENTRY_PALETTE.LOOKS.default,     // #FF5174
  ENTRY_PALETTE.SOUND.default,     // #82D214
  ENTRY_PALETTE.CALC.default,      // #FEB71A
  ENTRY_PALETTE.VARIABLE.default,  // #F57DF1
  ENTRY_PALETTE.TEXT.default,      // #FC5D01
  ENTRY_PALETTE.START.default,     // #10D35E
  ENTRY_PALETTE.JUDGE.darken,      // #1B3AD8
];
// 스펙 매핑표가 이름으로 지정한 라이브러리는 해시 대신 그 톤으로 고정한다(dobotkit→START,
// tm→MOVING). 커리큘럼의 주력 라이브러리라 탭 색이 빌드마다 흔들리면 안 된다.
const LIB_TONE_PIN = { dobotkit: 'START', tm: 'MOVING' };
function topPkg(libKey) { return String(libKey || '').replace(/^★\s*/, '').split('.')[0] || 'Library'; }
function libColour(libKey) {
  const top = topPkg(libKey);
  if (LIB_TONE_PIN[top]) return tone(LIB_TONE_PIN[top]);
  let h = 0;
  for (let i = 0; i < top.length; i++) h = (h * 31 + top.charCodeAt(i)) >>> 0;
  return LIB_PALETTE[h % LIB_PALETTE.length];
}
// ★ 큐레이션 탭 액센트: 엔트리 하드웨어 틸. 라이브러리 해시 팔레트에서 제외된 색이라
// "★ = 추천 뷰" 가 항상 한 눈에 구분된다(기존 #00796b 틸의 연속성도 유지).
const CURATED_COLOUR = ENTRY_PALETTE.HARDWARE.default;

// One toolbox category PER LIBRARY (named by the library, e.g. cv2 / pathlib / PIL.Image), instead
// of one lumped "Library". A library's blocks are bucketed by its source-library tag (lib, else the
// block's module for built-ins); a curated library nests one sub-category per semantic group
// (+ Other + Macros), an un-curated one is flat.
// A toolbox block entry from a registered type (curated tabs reference existing types; look up the
// spec for its argNames so the dragged-out block carries valid default shadows). null if unknown.
function typeBlockEntry(reg, type) {
  return libCallEntry(reg, type);
}

// A module constant renders as a pre-filled ir_attribute{dotted} reporter (lowers to the exact dotted
// name — lossless, no new block type). Build the library's "Constants" sub-category, grouping a shared
// UPPERCASE prefix family (IMREAD_*, COLOR_*) into its own nested sub-category so a flag-heavy library
// (cv2 has thousands) stays navigable; singletons (math.pi) and lone-prefix consts sit at the top.
function constEntry(c) { return { kind: 'block', type: 'ir_attribute', extraState: { dotted: c.dotted } }; }
function constSubcategory(consts) {
  if (!consts || !consts.length) return null;
  const byPrefix = new Map();
  const singles = [];
  for (const c of consts) {
    if (c.prefix) { if (!byPrefix.has(c.prefix)) byPrefix.set(c.prefix, []); byPrefix.get(c.prefix).push(c); }
    else singles.push(c);
  }
  const contents = [];
  for (const [p, list] of [...byPrefix].sort((a, b) => a[0].localeCompare(b[0]))) {
    if (list.length >= 2) contents.push({ kind: 'category', name: p, colour: SUBCAT.constants, contents: list.map(constEntry) });
    else singles.push(...list);                          // a lone prefixed const isn't worth its own sub-category
  }
  for (const c of singles.sort((a, b) => a.name.localeCompare(b.name))) contents.push(constEntry(c));
  return contents.length ? { kind: 'category', name: 'Constants', colour: SUBCAT.constants, contents } : null;
}

// A class property renders as an ir_attribute attr-form (`<recv>.device`) with an ir_name receiver
// shadow (so a dragged block is complete and round-trips to Attribute(recv, attr)). Grouped by owning
// class when a library has more than one, so the Properties sub-category stays organized.
function propEntry(p) { return { kind: 'block', type: 'ir_attribute', extraState: { attr: p.attr }, inputs: { VALUE: name(p.recv || 'obj') } }; }
function propSubcategory(props) {
  if (!props || !props.length) return null;
  const byOwner = new Map();
  for (const p of props) { const o = p.owner || ''; if (!byOwner.has(o)) byOwner.set(o, []); byOwner.get(o).push(p); }
  let contents;
  if (byOwner.size <= 1) {
    contents = props.slice().sort((a, b) => a.attr.localeCompare(b.attr)).map(propEntry);
  } else {
    contents = [];
    for (const [o, list] of [...byOwner].sort((a, b) => a[0].localeCompare(b[0]))) {
      contents.push({ kind: 'category', name: o || 'Other', colour: SUBCAT.property, contents: list.sort((a, b) => a.attr.localeCompare(b.attr)).map(propEntry) });
    }
  }
  return contents.length ? { kind: 'category', name: 'Properties', colour: SUBCAT.property, contents } : null;
}

function libraryCategories() {
  const reg = (typeof window !== 'undefined' ? window : global).BlockPyLibRegistry;
  if (!reg || typeof reg.listLibBlocks !== 'function') return [];
  const groups = reg.listLibBlocks();
  const macros = (typeof reg.listMacros === 'function' ? reg.listMacros() : []) || [];

  const byLib = new Map();            // libKey -> { groups: Map<groupName,[entries]>, anyGroup }
  (groups || []).forEach((mod) => {
    mod.blocks.forEach((b) => {
      const libKey = b.lib || mod.module || 'Library';
      if (!byLib.has(libKey)) byLib.set(libKey, { groups: new Map(), anyGroup: false });
      const L = byLib.get(libKey);
      const g = b.group || '';
      if (g) L.anyGroup = true;
      if (!L.groups.has(g)) L.groups.set(g, []);
      const e = libCallEntry(reg, b.type);
      if (e) L.groups.get(g).push(e);
    });
  });

  const macrosByLib = new Map();      // srcModule -> [macro block entries]
  macros.forEach((m) => {
    const k = m.srcModule || 'Library';
    if (!macrosByLib.has(k)) macrosByLib.set(k, []);
    macrosByLib.get(k).push({ kind: 'block', ...m.block });
  });

  const constsByLib = new Map();      // libKey -> [const records]
  ((typeof reg.listConsts === 'function' ? reg.listConsts() : []) || []).forEach((c) => {
    const k = c.lib || c.module || 'Library';
    if (!constsByLib.has(k)) constsByLib.set(k, []);
    constsByLib.get(k).push(c);
  });

  const propsByLib = new Map();       // libKey -> [prop records]
  ((typeof reg.listProps === 'function' ? reg.listProps() : []) || []).forEach((p) => {
    const k = p.lib || p.module || 'Library';
    if (!propsByLib.has(k)) propsByLib.set(k, []);
    propsByLib.get(k).push(p);
  });

  const cats = [];
  for (const [libKey, L] of byLib) {
    const macroEntries = macrosByLib.get(libKey) || [];
    const constCat = constSubcategory(constsByLib.get(libKey));
    const propCat = propSubcategory(propsByLib.get(libKey));
    let contents;
    if (!L.anyGroup && !macroEntries.length) {
      contents = [...L.groups.values()].flat();                         // flat library
    } else {
      contents = [];
      for (const [g, entries] of L.groups) if (g) contents.push({ kind: 'category', name: g, colour: SUBCAT.group, contents: entries });
      if (L.groups.has('') && L.groups.get('').length) contents.push({ kind: 'category', name: 'Other', colour: SUBCAT.other, contents: L.groups.get('') });
      if (macroEntries.length) contents.push({ kind: 'category', name: 'Macros', colour: SUBCAT.macros, contents: macroEntries });
    }
    if (propCat) contents = [...contents, propCat];                     // Properties + Constants sub-categories after the calls
    if (constCat) contents = [...contents, constCat];
    cats.push({ kind: 'category', name: libKey, colour: libColour(libKey), contents, _pkg: topPkg(libKey) });
  }
  // libraries whose curation produced only macros (no plain blocks)
  for (const [libKey, entries] of macrosByLib) {
    if (!byLib.has(libKey)) cats.push({ kind: 'category', name: libKey, colour: libColour(libKey), contents: [{ kind: 'category', name: 'Macros', colour: SUBCAT.macros, contents: entries }], _pkg: topPkg(libKey) });
  }
  // libraries that produced ONLY value blocks (constants and/or properties) still get a tab
  for (const libKey of new Set([...constsByLib.keys(), ...propsByLib.keys()])) {
    if (cats.some((c) => c.name === libKey)) continue;
    const extra = [propSubcategory(propsByLib.get(libKey)), constSubcategory(constsByLib.get(libKey))].filter(Boolean);
    if (extra.length) cats.push({ kind: 'category', name: libKey, colour: libColour(libKey), contents: extra, _pkg: topPkg(libKey) });
  }

  // Curated tabs (Phase C3): one extra category per curation, a purpose-driven subset that references
  // the full library's already-registered block types. Grouped into sub-categories when the curation
  // carries semantic groups; a ★ name marks it as the curated view, distinct from the full library.
  const curations = (typeof reg.listCurations === 'function' ? reg.listCurations() : []) || [];
  for (const cur of curations) {
    // Progressive disclosure: CORE items render up front; MORE items are folded into a single
    // collapsed "더 보기" shelf in the SAME tab — so the curated view stays small but nothing the
    // curation picked is lost to a hard cut (MakeCode advanced=true / Resnick wide-walls).
    const groupsOf = (items) => {
      const byGroup = new Map();
      (items || []).forEach((it) => {
        const entry = typeBlockEntry(reg, it.type);
        if (!entry) return;                                // type was removed -> skip stale ref
        const g = it.group || '';
        if (!byGroup.has(g)) byGroup.set(g, []);
        byGroup.get(g).push(entry);
      });
      return byGroup;
    };
    const items = cur.items || [];
    const coreG = groupsOf(items.filter((it) => (it.tier || 'core') !== 'more'));
    const moreG = groupsOf(items.filter((it) => it.tier === 'more'));
    const macroEntries = (cur.macros || []).map((m) => ({ kind: 'block', ...m.block }));

    const flatten = (byGroup) => {
      const anyGroup = [...byGroup.keys()].some((g) => g);
      if (!anyGroup) return [...byGroup.values()].flat();
      const out = [];
      for (const [g, entries] of byGroup) if (g) out.push({ kind: 'category', name: g, colour: SUBCAT.group, contents: entries });
      if (byGroup.has('') && byGroup.get('').length) out.push({ kind: 'category', name: 'Other', colour: SUBCAT.other, contents: byGroup.get('') });
      return out;
    };

    let contents = flatten(coreG);
    if (macroEntries.length) contents.push({ kind: 'category', name: 'Macros', colour: SUBCAT.macros, contents: macroEntries });
    const moreContents = flatten(moreG);
    if (moreContents.length) contents.push({ kind: 'category', name: '더 보기', colour: SUBCAT.more, contents: moreContents });
    if (contents.length) cats.push({ kind: 'category', name: `★ ${cur.label || cur.key}`, colour: CURATED_COLOUR, contents, _pkg: topPkg(cur.lib || cur.key) });
  }
  return nestByPackage(cats);
}

// Group top-level library categories by their TOP package so a whole-package Blockify
// (serial + serial.tools.list_ports + serial.threaded + …, plus any ★ curation of serial) is ONE
// "serial" tab with the members as sub-categories — not 19+ parallel top-level tabs. A package with
// a single category (cv2, math, html.parser) stays a flat top-level tab. Display-only nesting.
function nestByPackage(cats) {
  const byPkg = new Map();
  const order = [];
  for (const c of cats) {
    const pkg = c._pkg || topPkg(c.name);
    if (!byPkg.has(pkg)) { byPkg.set(pkg, []); order.push(pkg); }
    byPkg.get(pkg).push(c);
  }
  const strip = (c) => { const { _pkg, ...rest } = c; return rest; };
  const out = [];
  for (const pkg of order) {
    const group = byPkg.get(pkg);
    if (group.length === 1) { out.push(strip(group[0])); continue; }
    // Sort members: ★ curated views first (the "default face"), then the top module itself, then
    // submodules alphabetically. Rename members so the nested labels read cleanly.
    const rank = (c) => (c.name.startsWith('★') ? 0 : c.name === pkg ? 1 : 2);
    const members = group.slice().sort((a, b) => rank(a) - rank(b) || a.name.localeCompare(b.name)).map((c) => {
      const cc = strip(c);
      if (cc.name === pkg) cc.name = `${pkg} (기본)`;                        // top module vs the parent's own name
      else if (!cc.name.startsWith('★') && cc.name.startsWith(pkg + '.')) cc.name = cc.name.slice(pkg.length + 1);  // serial.tools.list_ports -> tools.list_ports
      return cc;
    });
    out.push({ kind: 'category', name: pkg, colour: libColour(pkg), contents: members });
  }
  return out;
}

// Compile the table to a Blockly categoryToolbox JSON object (+ a dynamic Library category).
function buildIrToolbox() {
  const contents = IR_TOOLBOX_TABLE.map((cat) => {
    const blocks = cat.blocks.map((b) => {
      const block = { kind: 'block', type: b.type };
      if (b.extraState) block.extraState = b.extraState;
      if (b.fields) block.fields = b.fields;
      if (b.inputs) block.inputs = b.inputs;
      return block;
    });
    // A category may prepend a flyout button (Variables' "Create variable…"); the button's
    // callbackkey is wired to Blockly.Variables.createVariableButtonHandler in BlocklyEditor.
    const items = cat.button
      ? [{ kind: 'button', text: cat.button.text, callbackkey: cat.button.callbackkey }, ...blocks]
      : blocks;
    return { kind: 'category', name: cat.name, colour: tone(cat.tone), contents: items };
  });
  for (const cat of libraryCategories()) contents.push(cat);   // one category per registered library
  return { kind: 'categoryToolbox', contents };
}

// ── 툴박스 카테고리 아이콘 슬러그 (MakeCode 규격: 이름 옆 컬러 아이콘) ──────────────────────
// MakeCode 는 카테고리마다 아이콘을 선언한다(자체 아이콘 폰트). 우리는 오프라인 Electron 앱이라
// 외부 폰트/CDN 을 못 쓰므로, 카테고리 행에 `bpy-cat-<slug>` 클래스를 붙이고 index.css 가
// 인라인 SVG(data URI) 를 mask-image 로 그린다. 색은 --cat-color(카테고리색) 를 쓰고 선택 시
// 툴박스 배경색으로 반전 — MakeCode 와 동일한 거동.
//
// ⚠ 클래스는 카테고리 정의의 cssconfig 로 주지 않는다: Blockly 의 cssConfig.row 는 기본 클래스를
//   **덮어써서** `.blocklyToolboxCategory` 가 사라지고 툴박스 스타일 전체가 무효화된다(실측 확인).
//   대신 BlocklyEditor.jsx 의 카테고리 페인트 루프가 렌더된 라벨 텍스트로 이 함수를 호출해
//   classList 에 추가한다(Blockly 내부 클래스명에 의존하지 않아 버전 안전, 툴박스 재생성 시 재적용).
// 매칭 안 되는 이름은 CSS 의 기본 아이콘(.bpy-cat 공통 규칙)으로 떨어진다.
function catIconSlug(rawName) {
  const n = String(rawName || '').replace(/^★\s*/, '').trim();
  const lower = n.toLowerCase();
  // 이름 → 아이콘 슬러그. 우리 코어 카테고리 + 자주 쓰는 stdlib + 서브카테고리.
  const MAP = {
    'values': 'values', 'collections': 'collections', 'operators': 'operators',
    'access': 'access', 'variables': 'variables', 'control flow': 'control',
    'functions': 'functions', 'built-ins': 'builtins', 'classes': 'classes',
    'exceptions': 'exceptions', 'imports': 'imports', 'sugar': 'sugar',
    'async': 'async', 'text': 'text', 'match': 'match', 'types': 'types',
    // 서브카테고리
    'constants': 'constants', 'properties': 'properties', 'macros': 'macros',
    'other': 'other', '더 보기': 'more',
    // 자주 쓰는 라이브러리(있으면 의미 아이콘, 없으면 기본)
    'random': 'random', 'time': 'time', 'datetime': 'time', 'math': 'math',
    'statistics': 'stats', 'json': 'json', 'functools': 'functions', 're': 'match',
    'cv2': 'vision', 'tm': 'vision', 'dobotkit': 'robot',
  };
  return MAP[lower] || 'lib';
}

// ── block type -> 엔트리 톤 키 (Blockly 테마용) ──────────────────────────────────────────
// IR_TOOLBOX_TABLE 에서 DERIVE 한다: 카테고리 탭 색과 그 카테고리 블록 본체 색이 같은 한 줄에서
//나오므로 팔레트가 탭과 어긋날 수 없다(중복 정의 없음). BlocklyEditor 가 이 표를 읽어 각
// ir_* 블록에 카테고리 톤을 찍는다 — 색은 display-only 라 lowering 에는 아무 영향이 없다.
const BLOCK_TONE_OVERRIDE = {
  // ir_call 은 Functions(일반 호출) 와 Built-ins(print/len/…) 두 카테고리에 동시에 사는 유일한
  // 블록이다. 압도적 다수가 Built-ins 이므로 JUDGE 로 못박아 탭↔블록 색을 맞춘다.
  ir_call: 'JUDGE',
  // f-string 조각(HELPER, ir_joinedstr 안에서만 유효) — 툴박스에 없으므로 부모와 같은 TEXT.
  ir_formattedvalue: 'TEXT',
};
function blockTones() {
  const out = {};
  for (const cat of IR_TOOLBOX_TABLE) {
    for (const b of cat.blocks) if (b.type) out[b.type] = cat.tone;
  }
  return Object.assign(out, BLOCK_TONE_OVERRIDE);
}

const api = (typeof window !== 'undefined' ? window : global);
api.BlockPyIrToolbox = buildIrToolbox();        // initial (registry empty at module-load time)
api.BlockPyBuildIrToolbox = buildIrToolbox;     // Phase 5: re-callable to refresh the Library category
// 디자인 v2 팔레트 공개(테마 계층에서 소비). 하드코딩 hex 를 컴포넌트에 흩뿌리지 않기 위한 토큰.
api.BlockPyEntryPalette = ENTRY_PALETTE;        // 엔트리 4단 톤 표 (색의 유일한 출처)
api.BlockPyBlockTones = blockTones();           // ir_* 블록 타입 -> 톤 키
api.BlockPyCatIconSlug = catIconSlug;           // 카테고리명 -> 아이콘 슬러그(BlocklyEditor 가 classList 로 부착)
if (typeof module !== 'undefined') module.exports = { buildIrToolbox, IR_TOOLBOX_TABLE, ENTRY_PALETTE, blockTones, catIconSlug };

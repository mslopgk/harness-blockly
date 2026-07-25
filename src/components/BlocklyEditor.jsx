import React, { useEffect, useRef, useState } from 'react';

/* ── 디자인 v2: 엔트리(playentry.org) 룩의 Blockly 테마 ─────────────────────────────────────
 * 소스오브트루스: DOCS/superpowers/specs/2026-07-25-blockpy-korean-blockcoding-design-v2.md
 * 색 토큰의 유일한 출처는 irToolbox.js 의 ENTRY_PALETTE (window.BlockPyEntryPalette) 다.
 * 여기서는 그 4단 톤을 Blockly 가 이해하는 형태로 "등록"만 한다 — hex 를 새로 만들지 않는다.
 *
 * 크롬 토큰(스펙 §A). Blockly 내부는 CSS 변수를 읽지 못해(SVG 속성/JS 상수) 테마 값으로만
 * 전달할 수 있으므로, 이 상수들이 index.css 의 --bg/--panel/--line/--ink/--accent 와 같은 값을
 * 가리키도록 유지한다.
 */
const CHROME = {
  canvas: '#f9f9f9',   // --surface  워크스페이스 바닥(쿨 니어화이트)
  panel: '#ffffff',   // --panel    툴박스/플라이아웃
  line: '#e2e2e2',   // --line     헤어라인(그리드/스크롤바)
  ink: '#2c313d',   // --ink      본문 잉크
  muted: '#606c73',   // --muted    보조 텍스트
  faint: '#cbcbcb',   // 뮤트(스크롤바)
  accent: '#4f80ff',   // --accent   엔트리 프라이머리 블루(커서/삽입마커/선택)
};
const INK_RGB = [0x2c, 0x31, 0x3d];

// UI 폰트 스택(스펙 타이포). 오프라인 앱이라 시스템 폴백만 — @import/CDN 없음.
const UI_FONT = 'Pretendard, "Noto Sans KR", "Malgun Gothic", system-ui, sans-serif';

// irBlocks.js 가 setColour(hex) 로 직접 박아둔 레거시 색 -> 엔트리 톤 키.
// 왜 필요한가: ir_* 블록은 blockStyles 이름(style key)이 아니라 setColour 를 쓴다. Blockly 는
// 그런 블록에 'auto_<hex>' 라는 스타일을 즉석 생성하는데(renderers/common/constants:
// getBlockStyleForColour), 테마에 같은 키가 이미 있으면 그것을 쓴다. 그래서 이 표를
// 'auto_#hex' 블록스타일로 등록하면 블록 정의를 건드리지 않고 3단 톤이 적용된다.
// 특히 ir_call / ir_attribute 는 updateShape_ 에서 매번 스스로 setColour 하므로(라이브러리 인식
// 색) 이 경로가 유일한 후크다.
const LEGACY_TONE = {
  '#5b80a5': 'FLOW',      // ir_name (Values)
  '#a55b80': 'FLOW',      // ir_const (Values)
  '#5ba55b': 'FLOW',      // ir_str (Values)
  '#5b5ba5': 'VARIABLE',  // assign / augassign / annassign
  '#4a90a4': 'MOVING',    // ir_list
  '#4a7a90': 'MOVING',    // ir_tuple
  '#7a4a90': 'MOVING',    // ir_set
  '#90744a': 'MOVING',    // ir_dict
  '#5b67a5': 'SOUND',     // binop / unaryop / boolop / compare (Operators)
  '#a07a4a': 'HARDWARE',  // ir_attribute 기본값 + subscript/slice/starred (Access)
  '#6a8a5b': 'JUDGE',     // ir_call 기본값 (Built-ins) + ir_exprstmt
  '#a0734a': 'CALC',      // control flow / exceptions 공용 레거시 색
  '#888888': 'CALC',      // ir_pass / global / nonlocal / import
  '#9a6a8a': 'FUNC',      // funcdef / classdef / lambda / return / typealias
  // 라이브러리 인식 블록(libRegistry 기본 emerald). 스펙 매핑의 dobotkit→START 를 따라 초록:
  // 레지스트리는 모든 라이브러리 스펙에 같은 colour 를 주므로 블록 본체는 하나의 톤만 가진다
  // (라이브러리별 색 구분은 툴박스 탭에서 — irToolbox libColour).
  '#009688': 'START',
};

// 블록 본체 색을 그대로 라벨 텍스트에 쓰면(엔트리 채도 그대로) 흰 배경에서 대비가 2:1 수준으로
// 떨어진다. 색상(hue)은 유지하고 대비가 4.5:1 을 넘는 최초 지점까지 섞는다 —
// 왼쪽 컬러바는 원색 그대로라 에너지는 유지되고, 글자만 읽힌다.
// 섞는 방향은 실제 툴박스 배경에 따라 결정한다(라이트=잉크쪽 / 다크=흰색쪽): 배경을 흰색으로
// 가정하면 다크 테마(--panel #1f242e)에서 라벨이 3:1 로 떨어진다.
const WHITE_RGB = [255, 255, 255];
const relLuminance = ([r, g, b]) => {
  const f = (c) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4); };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
};
const contrastRatio = (a, b) => {
  const [hi, lo] = [relLuminance(a), relLuminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
};
const parseRgb = (css) => {
  const m = /rgba?\(([^)]+)\)/.exec(String(css || ''));
  if (m) { const p = m[1].split(',').map((v) => parseInt(v, 10)); return (p.length >= 3 && p.every((n) => !isNaN(n))) ? p.slice(0, 3) : null; }
  const h = /^#([0-9a-f]{6})$/i.exec(String(css || '').trim());
  if (!h) return null;
  const n = parseInt(h[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};
const readableOn = (css, bgCss) => {
  const rgb = parseRgb(css);
  if (!rgb) return null;
  const bg = parseRgb(bgCss) || WHITE_RGB;
  // 밝은 배경이면 잉크쪽으로, 어두운 배경이면 흰색쪽으로 섞는다.
  const target = relLuminance(bg) > 0.18 ? INK_RGB : WHITE_RGB;
  for (let t = 0; t <= 0.9; t += 0.05) {
    const mixed = rgb.map((c, i) => Math.round(c + (target[i] - c) * t));
    if (contrastRatio(mixed, bg) >= 4.5) return `rgb(${mixed[0]}, ${mixed[1]}, ${mixed[2]})`;
  }
  return `rgb(${target[0]}, ${target[1]}, ${target[2]})`;
};

export default function BlocklyEditor({
  onCodeChange,
  onSnapshotChange,
  initialSnapshot,
  isSyncingFromCode,
  workspaceRef,
}) {
  const containerRef = useRef(null);
  // Block→Python regeneration failure (e.g. a required input emptied by detaching its child) —
  // shown on the sync badge; the badge used to be hardcoded "Synchronized" even while sync stalled.
  const [syncError, setSyncError] = useState('');

  useEffect(() => {
    if (!containerRef.current) return;

    // 엔트리 톤 팔레트(irToolbox.js 가 소유). 없으면 테마 색만 기본으로 떨어지고 기능은 그대로.
    const palette = window.BlockPyEntryPalette || null;
    const blockTones = window.BlockPyBlockTones || null;

    // 한 톤 -> Blockly blockStyle 3단. default=본체, lighten=내부 필드, darken=외곽선.
    // Zelos 는 colourTertiary 를 블록 외곽선에, colourSecondary 를 필드/하이라이트에 쓴다.
    const styleOf = (t) => ({
      colourPrimary: t.default,
      colourSecondary: t.lighten,
      colourTertiary: t.darken,
    });

    // 엔트리 룩 테마(Zelos 렌더러 기반). v1 의 단색 코발트 대신 카테고리별 3단 톤.
    const getBlocklyTheme = () => {
      const base = window.Blockly.Themes.Zelos || window.Blockly.Themes.Classic;
      const blockStyles = {};
      if (palette) {
        // (1) 이름 있는 스타일: entry_flow / entry_moving / … (Blockly 표준 키도 같은 톤으로 매핑해
        //     네이티브 블록이 섞여도 팔레트가 유지된다).
        for (const key of Object.keys(palette)) blockStyles['entry_' + key.toLowerCase()] = styleOf(palette[key]);
        const std = {
          logic_blocks: 'JUDGE', loop_blocks: 'CALC', math_blocks: 'SOUND', text_blocks: 'TEXT',
          list_blocks: 'MOVING', variable_blocks: 'VARIABLE', variable_dynamic_blocks: 'VARIABLE',
          procedure_blocks: 'FUNC', colour_blocks: 'LOOKS', hat_blocks: 'START',
        };
        for (const k of Object.keys(std)) if (palette[std[k]]) blockStyles[k] = styleOf(palette[std[k]]);
        // (2) 'auto_<hex>' 오버라이드: setColour 로 색을 박는 블록(ir_*)이 3단 톤을 받는 후크.
        //     엔트리 본체색 자체와, irBlocks 의 레거시 hex 양쪽 모두 등록한다. 키는 소문자 hex —
        //     Blockly 가 parse 한 값('auto_' + colour.parse(hex))과 일치해야 한다.
        for (const key of Object.keys(palette)) blockStyles['auto_' + palette[key].default.toLowerCase()] = styleOf(palette[key]);
        for (const hex of Object.keys(LEGACY_TONE)) {
          const t = palette[LEGACY_TONE[hex]];
          if (t) blockStyles['auto_' + hex.toLowerCase()] = styleOf(t);
        }
      }
      return window.Blockly.Theme.defineTheme('blockpy_entry', {
        'base': base,
        // 크롬: 쿨 화이트 + 엔트리 블루 액센트(스펙 §A). 패널=흰색, 캔버스=#f9f9f9, 헤어라인 분리.
        'componentStyles': {
          'workspaceBackgroundColour': CHROME.canvas,
          'toolboxBackgroundColour': CHROME.panel,
          'toolboxForegroundColour': CHROME.ink,
          // index.css 의 `.blocklyFlyoutBackground { fill: var(--panel) }` 와 같은 값이어야 한다
          // (CSS 쪽이 다크 토글을 따라가므로 최종 승자는 CSS — 라이트 값만 여기서 일치시킨다).
          'flyoutBackgroundColour': CHROME.panel,
          'flyoutForegroundColour': CHROME.muted,
          'flyoutOpacity': 1,
          'scrollbarColour': CHROME.faint,
          'scrollbarOpacity': 0.6,
          'insertionMarkerColour': CHROME.accent,
          'insertionMarkerOpacity': 0.4,
          'markerColour': CHROME.accent,
          'cursorColour': CHROME.accent,
          'selectedGlowColour': CHROME.accent,
        },
        'fontStyle': { 'family': UI_FONT },
        'blockStyles': blockStyles,
      });
    };

    // 카테고리 톤을 각 ir_* 블록에 찍는다. 블록 정의(irBlocks.js)는 그대로 두고 init 뒤에
    // setColour(엔트리 본체색) 만 덧입히는 display-only 래퍼 — 로직/직렬화/변환에는 관여하지
    // 않는다(Blockly 는 블록 색을 저장하지 않는다). 톤은 툴박스 카테고리 표에서 파생되므로
    // 팔레트와 탭 색이 어긋날 수 없다.
    // 제외: ir_call / ir_attribute — 이 둘은 updateShape_ 에서 라이브러리 인식 여부에 따라 스스로
    // 색을 정한다(그 색 구분이 기능적 신호). 테마의 auto_<hex> 항목이 그 색들을 3단 톤으로 올린다.
    const DYNAMIC_COLOUR_BLOCKS = ['ir_call', 'ir_attribute'];
    const TONE_STAMP_FLAG = '__blockpyEntryToneStamped';
    const stampEntryTones = () => {
      const defs = window.Blockly && window.Blockly.Blocks;
      if (!defs || !palette || !blockTones) return;
      for (const type of Object.keys(blockTones)) {
        if (DYNAMIC_COLOUR_BLOCKS.indexOf(type) >= 0) continue;
        const def = defs[type];
        const t = palette[blockTones[type]];
        if (!def || !t || def[TONE_STAMP_FLAG] || typeof def.init !== 'function') continue;
        const origInit = def.init;
        def.init = function () {
          origInit.call(this);
          try { this.setColour(t.default); } catch (_) { /* display-only */ }
        };
        def[TONE_STAMP_FLAG] = true;
      }
    };
    stampEntryTones();

    // The ir_* toolbox is built in JS (irToolbox.js) from the ir_* block table, not the
    // retired XML stub — blocklyToIr only understands ir_* types, so the palette must too.
    const toolbox = window.BlockPyIrToolbox;

    // Inject Blockly
    const ws = window.Blockly.inject(containerRef.current, {
      toolbox: toolbox,
      theme: getBlocklyTheme(),
      // Self-hosted media (icons + sounds) so Blockly never reaches static.blockly.com — works
      // offline. Vendored from the blockly npm package into public/vendor/blockly/media.
      media: '/vendor/blockly/media/',
      renderer: 'zelos',
      grid: {
        spacing: 20,
        length: 3,
        colour: CHROME.line,          // 헤어라인 그리드(쿨 그레이) — 웜 블랙 도트 제거
        snap: true
      },
      zoom: {
        controls: true,
        wheel: true,
        startScale: 0.85,
        maxScale: 3,
        minScale: 0.3,
        scaleSpeed: 1.2
      },
      trashcan: true
    });

    workspaceRef.current = ws;
    window.__blocklyWorkspace = ws;

    // Wire the Variables category's "Create variable…" button to Blockly's native variable
    // creation dialog (the toolbox button declares callbackkey 'IR_CREATE_VARIABLE').
    try {
      ws.registerButtonCallback('IR_CREATE_VARIABLE', () => {
        window.Blockly.Variables.createVariableButtonHandler(ws);
      });
    } catch (_) { /* non-fatal */ }

    // 카테고리 라벨을 자기 카테고리 색으로 칠한다(엔트리/MakeCode 관습: 컬러바 + 컬러 라벨).
    // Blockly 는 카테고리 색을 행의 left border 로만 인라인 적용하므로 거기서 hue 를 읽어온다.
    // v2: 엔트리 채도를 그대로 텍스트에 쓰면 대비가 2:1 로 떨어지므로, hue 를 유지한 채
    // 4.5:1 을 넘는 지점까지 섞어 칠한다(라이트=잉크쪽 / 다크=흰색쪽 — readableOn 참조).
    // 컬러바는 원색 그대로 → 에너지 유지, 글자만 가독.
    const paintToolboxLabels = () => {
      const host = containerRef.current;
      if (!host) return;
      const tbEl = host.querySelector('.blocklyToolboxDiv, .blocklyToolbox');
      // 실측 배경(라이트 --panel #fff / 다크 --panel #1f242e)을 기준으로 대비를 맞춘다.
      const tbBg = tbEl ? getComputedStyle(tbEl).backgroundColor : null;
      const cats = host.querySelectorAll('.blocklyToolboxCategory');
      cats.forEach((cat) => {
        const hue = getComputedStyle(cat).borderLeftColor;
        const label = cat.querySelector('.blocklyToolboxCategoryLabel');
        if (!label || !hue) return;
        // MakeCode 규격: 선택 시 행 전체가 카테고리색으로 채워진다. Blockly 는 그 색을
        // border-left-color 인라인으로만 주므로, CSS 가 배경에도 쓸 수 있게 --cat-color 로 심는다.
        // (index.css 의 [aria-selected="true"] 규칙이 이 변수를 읽는다.)
        cat.style.setProperty('--cat-color', hue);
        const readable = readableOn(hue, tbBg);
        if (readable) label.style.color = readable;
      });
    };
    // 라벨 색은 인라인 style 이라 툴박스가 다시 그려지면 사라진다. 실제로 App.jsx 가 라이브러리를
    // 등록하며 updateToolbox() 를 호출해 카테고리 DOM 을 통째로 재생성하므로(마운트 후 수 초 뒤,
    // 카테고리 36→38), 타이머 한 번만으로는 칠이 전부 날아가 라벨이 전부 잉크색으로 남는다.
    // → 툴박스 DOM 을 관찰해 재생성될 때마다 다시 칠한다. 관찰 대상은 툴박스 엘리먼트로 한정하고
    //   (워크스페이스 SVG 전체를 관찰하면 블록 렌더마다 콜백이 돈다), 칠할 때마다 재부착해
    //   툴박스 엘리먼트 자체가 교체되는 경우에도 따라간다. style 속성 변경은 관찰하지 않으므로
    //   (childList 전용) 칠하는 행위가 다시 콜백을 부르는 루프는 생기지 않는다.
    let repaintTimer = null;
    const paintHost = containerRef.current;
    const schedulePaint = () => { clearTimeout(repaintTimer); repaintTimer = setTimeout(paintAndReattach, 0); };
    const observer = new MutationObserver(schedulePaint);
    let observed = null;
    const reattachObserver = () => {
      const host = paintHost.querySelector('.blocklyToolboxDiv, .blocklyToolbox');
      if (!host || host === observed) return;
      observer.disconnect();
      observer.observe(host, { childList: true, subtree: true });
      observed = host;
    };
    function paintAndReattach() { paintToolboxLabels(); reattachObserver(); }
    const paintTimer = setTimeout(paintAndReattach, 250);
    reattachObserver();
    // 다크 토글(body.theme-dark)은 툴박스 배경을 바꾸므로 라벨 대비를 다시 계산해야 한다.
    const themeObserver = new MutationObserver(schedulePaint);
    themeObserver.observe(document.body, { attributes: true, attributeFilter: ['class'] });
    // 백스톱: 라이브러리 하위 카테고리는 부모를 펼치는 순간 DOM 에 생긴다.
    paintHost.addEventListener('click', schedulePaint);

    // Load initial snapshot if provided
    if (initialSnapshot) {
      try {
        window.Blockly.serialization.workspaces.load(initialSnapshot, ws);
      } catch (err) {
        console.error('Failed to load initial snapshot:', err);
      }
    }

    // Block -> Python via the CPython-3.12 ast single-IR pipeline (Pyodide):
    //   workspace JSON -> blocklyToIr -> irToPython. Async (Pyodide) + debounced so rapid edits
    // coalesce into one regeneration. The legacy Blockly.Python generator path is retired.
    let codeGenTimer = null;
    const regenerate = async () => {
      if (isSyncingFromCode.current) return;
      try {
        const snapshot = window.Blockly.serialization.workspaces.save(ws);
        const pyodide = await window.BlockPyAstBridge.getPyodide();
        const ir = window.BlockPyIR.blocklyToIr(snapshot);
        const code = await window.BlockPyAstBridge.irToPython(pyodide, ir);
        if (isSyncingFromCode.current) return; // a code->block sync may have started during await
        onCodeChange(code);
        onSnapshotChange(snapshot);
        setSyncError('');
      } catch (err) {
        // A block outside the IR vocabulary, or an invalid block state (detached required child,
        // bad identifier field), makes blocklyToIr throw. Surface it on the badge instead of
        // silently stalling sync while the badge claims "Synchronized".
        console.error('Error generating code on workspace change (IR path):', err);
        setSyncError(err && err.message ? err.message : String(err));
      }
    };

    const changeListener = (event) => {
      if (isSyncingFromCode.current) return;

      if (
        event.type === window.Blockly.Events.BLOCK_CREATE ||
        event.type === window.Blockly.Events.BLOCK_DELETE ||
        event.type === window.Blockly.Events.BLOCK_CHANGE ||
        event.type === window.Blockly.Events.BLOCK_MOVE
      ) {
        clearTimeout(codeGenTimer);
        codeGenTimer = setTimeout(regenerate, 200);
      }
    };

    ws.addChangeListener(changeListener);

    // Cleanup
    return () => {
      clearTimeout(paintTimer);
      clearTimeout(repaintTimer);
      observer.disconnect();
      themeObserver.disconnect();
      if (paintHost) paintHost.removeEventListener('click', schedulePaint);
      clearTimeout(codeGenTimer);
      ws.removeChangeListener(changeListener);
      ws.dispose();
      workspaceRef.current = null;
      if (window.__blocklyWorkspace === ws) {
        window.__blocklyWorkspace = null;
      }
    };
  }, []);

  return (
    <div className="blockly-card">
      {/* 뷰 탭이 이미 "블록 작업실"이라 제목은 중복이었다(v1 잔재 영문 제목) → 동기화 배지만 남긴다. */}
      <div className="panel-header panel-header-badge-only">
        <div
          id="sync-indicator"
          className={`badge ${syncError ? 'badge-error' : 'badge-success'}`}
          title={syncError ? `블록 → 파이썬 변환 실패: ${syncError}` : '블록 ↔ 파이썬 동기화됨'}
        >
          <i className={`fa-solid ${syncError ? 'fa-triangle-exclamation' : 'fa-rotate'}`}></i>
          {' '}{syncError ? '동기화 오류 — 표시된 블록을 고쳐주세요' : '동기화됨'}
        </div>
      </div>
      {/* 제목 줄을 없애면서 헤더 높이가 고정 48px 이 아니게 됐다 → calc(100% - 48px) 대신
          부모(.blockly-card)의 컬럼 플렉스를 그대로 채운다(minHeight 로 inject 시 0높이 방지). */}
      <div
        ref={containerRef}
        id="blockly-div"
        style={{ width: '100%', flex: 1, minHeight: '380px' }}
      ></div>
    </div>
  );
}

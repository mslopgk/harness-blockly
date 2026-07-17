import React, { useState, useEffect, useRef } from 'react';
import BlocklyEditor from './components/BlocklyEditor';
import PythonEditor from './components/PythonEditor';
import FileExplorer from './components/FileExplorer';
import ConsoleLogs from './components/ConsoleLogs';
import VariableWatch from './components/VariableWatch';
import ASTTreeView from './components/ASTTreeView';
import LibraryManager from './components/LibraryManager';
import RobotConnect from './components/RobotConnect';
import RobotCalibrate from './components/RobotCalibrate';
import TeachableMachine from './components/TeachableMachine';
import { interruptPyodide, prewarmEnvironment, writeImageToFS } from './utils/pyodideRunner';
import stdlibSpecs from './data/stdlibSpecs.json';

// A pip PACKAGE name is not always the IMPORT name (opencv-python→cv2, pillow→PIL, …). Map the
// common mismatches; default = the package lowercased with '-' → '_' (pydobot→pydobot, scikit→…).
// Strip version/extra specifiers → the bare package name as typed. The backend (/api/blockify →
// _inspect.py) resolves the real import name from installed metadata (pyserial→serial, pillow→PIL,
// opencv-python→cv2), so there is NO hardcoded pip→import table here.
function pkgBaseName(pkg) {
  return String(pkg).split(/[=<>!~ [@]/)[0].trim();
}

export default function App() {
  const [code, setCode] = useState('');
  const [logs, setLogs] = useState([]);
  const [variables, setVariables] = useState({});
  const [isRunning, setIsRunning] = useState(false);
  const [highlightedLine, setHighlightedLine] = useState(null);

  // Workspace file explorer: which file is open in the editor, an image-preview overlay,
  // and a token bumped to make the tree re-read after writes/uploads/runs.
  const [activeFile, setActiveFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(null); // { name, url } | null
  const [fsReload, setFsReload] = useState(0);

  // OpenCV image output (from real cv2.imshow) + uploaded image name
  const [cv2Images, setCv2Images] = useState([]);
  const [uploadedImageName, setUploadedImageName] = useState(null);
  const [uploadedMedia, setUploadedMedia] = useState([]); // thumbnails of uploaded media

  // Gray (raw_statement/raw_expression) blocks — parts that didn't map to a dedicated block.
  const [grayBlocks, setGrayBlocks] = useState([]);

  // Custom Abstract blocks and thoughts
  const [installedBlocks, setInstalledBlocks] = useState([]);
  const [aiThoughts, setAiThoughts] = useState([]);
  const [isAbstracting, setIsAbstracting] = useState(false);

  // Pyodide state
  const [pyodideReady, setPyodideReady] = useState(false);
  const [pyodideLoading, setPyodideLoading] = useState(false);

  // Synced status state
  const [syntaxStatus, setSyntaxStatus] = useState({ valid: true, error: '' });
  const [isConverting, setIsConverting] = useState(false);   // spinner while Convert introspects + builds blocks
  const [curationProposal, setCurationProposal] = useState(null);   // Curate preview (null = no pending proposal)
  const [isCurating, setIsCurating] = useState(false);              // Curate busy flag — separate from isAbstracting (Blockify/pip) so Cancel can't clear Blockify's spinner
  const curateReqRef = useRef(0);                                    // newest propose wins; stale awaits are dropped
  // Phase 4: desugar-as-feature is OPT-IN. Default OFF -> Convert preserves SUGAR blocks (the
  // "intended coexistence" IR behavior); ON rewrites sugar to elementary loop/conditional blocks.
  const [shouldDesugar, setShouldDesugar] = useState(false);
  // Phase 4 slice 4: the Desugared preview pane shows the REAL IR desugar (computed async).
  const [desugaredPreview, setDesugaredPreview] = useState('');

  // Tabs layout variables
  const [activeEditorTab, setActiveEditorTab] = useState('blockly');
  const [activeAuxTab, setActiveAuxTab] = useState('files');
  const [isDarkTheme, setIsDarkTheme] = useState(false); // default = Claude cream (light)

  // Synchronization refs
  const workspaceRef = useRef(null);
  // Counter (not boolean): a code->block sync increments on entry / decrements on exit, so the
  // block->code listener stays suppressed until ALL concurrent syncs finish (BlocklyEditor reads it
  // for truthiness: 0 = idle, >0 = syncing). Guards rapid Auto-Desugar toggles racing each other.
  const isSyncingFromCodeRef = useRef(0);
  const syncGenRef = useRef(0);   // monotonic id; only the LATEST sync's workspace load is applied
  const blocklySnapshotRef = useRef(null);
  const introspectedSpecsRef = useRef(new Map());  // dotted module -> cached LibrarySpec (or null) this session
  const registeredSymRef = useRef(new Set());       // module::kind::owner.name already materialized (convert-time)
  const classNamesRef = useRef(new Set());          // library class names seen (Tier-1 receiver-type inference)
  const convertBindingsRef = useRef(new Map());     // dotted module -> the LOCAL name this program binds it to (np)
  const latestCodeRef = useRef('');                 // mirrors `code` for async callbacks (startup-load clobber guard)
  const associatedPythonRef = useRef('');
  const shellAbortRef = useRef(null);
  const desugarToggleMountRef = useRef(true);   // skip the toggle re-Convert on initial mount

  // Which library SYMBOLS a program actually references, so Convert can materialize exactly those
  // (used-symbols-only) into the toolbox in their proper category. Resolves imported module aliases:
  //   import numpy as np        → np.mean            => module 'numpy',                 attr 'mean'
  //   import a.b.c              → a.b.c.func         => module 'a.b.c',                 attr 'func'
  //   from serial.tools import list_ports → list_ports.comports() => module 'serial.tools.list_ports', attr 'comports'
  //   np.linalg.inv            → module 'numpy.linalg', attr 'inv'  (submodule chains resolve too)
  // A method/property on a non-module receiver (ser.baudrate) is collected as a bare attr name, later
  // matched against the referenced libraries' introspected method/property entries. A bare from-imported
  // symbol (`from math import sqrt; sqrt(x)`) stays a generic block (no module prefix) — a known limit.
  const referencedSymbols = (ir) => {
    const IDT = /^[A-Za-z_][A-Za-z0-9_]*$/;
    const alias = new Map();     // local binding -> dotted module (or dotted symbol for from-imports)
    const collect = (node) => {
      if (!node || typeof node !== 'object') return;
      if (Array.isArray(node)) { node.forEach(collect); return; }
      if (node.type === 'Import') {
        for (const a of node.names || []) {
          if (!a || !a.name) continue;
          if (a.asname) alias.set(a.asname, a.name);                 // import a.b.c as w -> w -> a.b.c
          else { const top = a.name.split('.')[0]; alias.set(top, top); }  // import a.b.c binds 'a'; chain resolved below
        }
      } else if (node.type === 'ImportFrom') {
        const mod = node.module || '';
        for (const a of node.names || []) {
          if (!a || !a.name || a.name === '*') continue;
          alias.set(a.asname || a.name, mod ? mod + '.' + a.name : a.name);   // from a.b import c -> c -> a.b.c
        }
      }
      for (const k in node) if (k !== 'type') collect(node[k]);
    };
    collect(ir && ir.body);

    const moduleAttrs = new Map();   // dotted module -> Set(attr)   (lib.func / lib.CONST)
    const bareAttrs = new Set();     // method/property names on local receivers
    const bareFuncs = new Map();     // dotted module -> Set(symbol)  (from lib import f; f(...))
    const flatten = (n) => { const path = []; let cur = n; while (cur && cur.type === 'Attribute') { path.unshift(cur.attr); cur = cur.value; } return { base: (cur && cur.type === 'Name') ? cur.id : null, path }; };
    const visit = (node) => {
      if (!node || typeof node !== 'object') return;
      if (Array.isArray(node)) { node.forEach(visit); return; }
      if (node.type === 'Attribute') {
        const { base, path } = flatten(node);
        const attr = path[path.length - 1];
        if (attr && IDT.test(attr)) {
          if (base && alias.has(base)) {
            const module = [alias.get(base), ...path.slice(0, -1)].join('.');   // np.linalg.inv -> numpy.linalg / inv
            if (!moduleAttrs.has(module)) moduleAttrs.set(module, new Set());
            moduleAttrs.get(module).add(attr);
          } else {
            bareAttrs.add(attr);                                                // method/property on a local receiver
          }
        }
      } else if (node.type === 'Call' && node.func && node.func.type === 'Name' && alias.has(node.func.id)) {
        // `from math import sqrt; sqrt(x)` — a bare call of a from-imported symbol. alias resolves the
        // binding (sqrt -> math.sqrt); split into module + symbol so autoBlockifyRefs can recognize it.
        const dotted = alias.get(node.func.id); const d = dotted.lastIndexOf('.');
        // key = the LOCAL binding (honors `from math import sqrt as s` — the program only binds `s`),
        // value = the source symbol name to look up in the introspected spec.
        if (d > 0) { const m = dotted.slice(0, d), s = dotted.slice(d + 1); if (!bareFuncs.has(m)) bareFuncs.set(m, new Map()); bareFuncs.get(m).set(node.func.id, s); }
      }
      for (const k in node) if (k !== 'type') visit(node[k]);
    };
    visit(ir && ir.body);
    // Invert the alias map: dotted module -> the name THIS program binds it to. Materialized blocks
    // must lower to that binding (np.mean under `import numpy as np`), or dragging them NameErrors.
    const bindings = new Map();
    for (const [bind, dotted] of alias) if (!bindings.has(dotted)) bindings.set(dotted, bind);
    return { moduleAttrs, bareAttrs, bareFuncs, bindings };
  };

  // Register only SPECIFIC symbols of a library (additive, idempotent — NO removeModules), so a
  // library's toolbox tab GROWS to match what the code actually uses instead of dumping the whole API.
  const registerUsedLibrary = (librarySpec, opts = {}) => {
    const reg = window.BlockPyLibRegistry;
    const imp = window.BlockPyLibImport;
    if (!reg || !imp) return { registered: [] };
    const mapped = imp.librarySpecToRegistrySpecs(librarySpec, { bindings: opts.bindings });
    const registered = [];
    for (const spec of mapped.specs) {
      // A builtin stdlib tab (math, random, …) already covers this call in its curated single form.
      // Re-registering the convert-time twin (the _stmt/value double) would double the palette and
      // flip the protected tab user-deletable — skip when EITHER form is already builtin.
      if (typeof reg.blockType === 'function') {
        const cur = reg.getLibSpec(reg.blockType(spec));
        const alt = reg.getLibSpec(reg.blockType({ ...spec, hasOutput: !spec.hasOutput }));
        if ((cur && cur.builtin) || (alt && alt.builtin)) continue;
      }
      const res = reg.registerLibBlock(spec);
      if (!res.ok) continue;
      const stored = reg.getLibSpec(res.type) || spec;
      registered.push({ type: res.type, title: stored.title, hasOutput: stored.hasOutput, func: stored.func, args: stored.argNames, colour: stored.colour });
    }
    let constCount = 0, propCount = 0;
    if (reg.registerConst) for (const c of (mapped.consts || [])) { const had = reg.findConst && reg.findConst(c.dotted); if ((!had || !had.builtin) && reg.registerConst(c).ok) constCount++; }
    if (reg.registerProp) for (const p of (mapped.props || [])) { if (reg.registerProp(p).ok) propCount++; }
    reg.persist();
    setInstalledBlocks((prev) => { const have = new Set(prev.map((p) => p.type)); return [...prev, ...registered.filter((r) => !have.has(r.type))]; });
    return { registered, constCount, propCount };
  };

  // Convert-time exception rule: every library symbol the code references becomes a recognized block in
  // its proper toolbox place, on first paint. Introspects each referenced module that is ALREADY
  // installed (cached), then materializes ONLY the used entries (functions/classes/constants by name;
  // methods/properties by name for local receivers). No auto-install: a not-installed library stays a
  // generic block — install it once via the Library pip field using its PACKAGE name (the single
  // install path; note the package name may differ from the import, e.g. opencv-python -> cv2).
  // Introspect a module once per session (cached). Records its class names for Tier-1 inference; logs a
  // hint if not installed. Returns the LibrarySpec or null.
  const getSpec = async (module) => {
    let spec = introspectedSpecsRef.current.get(module);
    if (spec === undefined) {
      const data = await introspectModule(module, { quiet: true, maxEntries: 3000 });
      spec = (data && data.spec) ? data.spec : null;
      // Cache only DEFINITIVE answers: a real spec, or the backend's explicit 404 "no such module".
      // A transient failure (backend down/wedged/5xx/timeout) must NOT poison the whole session —
      // the next Convert retries. (pip install clears this cache so fresh modules re-probe.)
      if (spec || (data && data.notFound)) introspectedSpecsRef.current.set(module, spec);
      if (spec) { for (const e of (spec.entries || [])) if (e.kind === 'class') classNamesRef.current.add(e.name); }
      else if (data && data.notFound) {
        // Name the ROOT package to pip-install (the import name often differs, e.g. serial→pyserial,
        // cv2→opencv-python, PIL→pillow). We can't know the exact distribution, but the top-level
        // import name is the right starting point and far more actionable than the dotted submodule.
        const root = String(module).split('.')[0];
        setLogs((prev) => [...prev, `[Convert] "${module}" isn't installed — its blocks stay generic. Install it in the Library "pip install" field (try "${root}"; the package name can differ from the import, e.g. serial→pyserial, cv2→opencv-python).`]);
      }
    }
    return spec;
  };

  // Tier-2 oracle: ask the backend (Jedi) for each attribute receiver's inferred class. Display-only —
  // a wrong/absent answer never affects lowering. Builtin containers are dropped (their methods aren't
  // library blocks). Returns { name: {type, module} }.
  const inferTypes = async (code) => {
    try {
      const r = await fetch('/api/infer-types', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ code }), signal: AbortSignal.timeout(12000) });
      if (!r.ok) return {};
      const d = await r.json();
      const out = {};
      for (const [name, v] of Object.entries((d && d.vars) || {})) {
        // drop builtins (list/dict/… — not library blocks) and __main__ (user-defined classes in the
        // script itself — let the __user__ heuristic suppress them, don't introspect the wrong __main__).
        if (v && v.type && v.module && v.module !== 'builtins' && v.module !== '__main__') out[name] = v;
      }
      return out;
    } catch (_) { return {}; }
  };

  // Register the classes Jedi resolved (e.g. ListPortInfo from serial.tools.list_ports_common) — just
  // that class + its methods/properties — so `p.device` colours precisely. This is what makes a
  // return-typed receiver work where static heuristics can't. Additive; returns true if the toolbox grew.
  const registerInferredClasses = async (jediVars) => {
    const reg = window.BlockPyLibRegistry;
    if (!reg) return false;
    const byModule = new Map();
    for (const v of Object.values(jediVars || {})) { if (!byModule.has(v.module)) byModule.set(v.module, new Set()); byModule.get(v.module).add(v.type); }
    let changed = false;
    for (const [module, types] of byModule) {
      const spec = await getSpec(module);
      if (!spec) continue;
      for (const t of types) classNamesRef.current.add(t);
      const fresh = (spec.entries || []).filter((e) => {
        const want = (e.kind === 'class' && types.has(e.name)) || ((e.kind === 'method' || e.kind === 'property') && types.has(e.owner));
        if (!want) return false;
        const key = `${module}::${e.kind}::${e.owner || ''}.${e.name}`;
        if (registeredSymRef.current.has(key)) return false;
        registeredSymRef.current.add(key);
        return true;
      });
      if (fresh.length) { registerUsedLibrary({ ...spec, entries: fresh }, { bindings: convertBindingsRef.current }); changed = true; }
    }
    return changed;
  };

  const autoBlockifyRefs = async (ir) => {
    const reg = window.BlockPyLibRegistry;
    const imp = window.BlockPyLibImport;
    if (!reg || !imp) return false;
    const { moduleAttrs, bareAttrs, bareFuncs, bindings } = referencedSymbols(ir);
    convertBindingsRef.current = bindings;   // registerInferredClasses (Tier-2) reuses the same program bindings
    let changed = false;
    // A small/cohesive module (a submodule like serial.tools.list_ports) → materialize ALL its members
    // so the whole sub-library is available (the user expects "전부 다"). A large library (numpy) →
    // used-symbols-only so the toolbox doesn't flood. `whole` is the per-module policy switch.
    const WHOLE_CAP = 100;
    for (const [module, attrs] of moduleAttrs) {
      let spec = await getSpec(module);
      let classOnly = null;      // set when `module` was actually parent.ClassName (a from-imported class)
      if (!spec && module.indexOf('.') >= 0) {
        // `from datetime import datetime; datetime.now()` — `datetime` is a CLASS, not a submodule, so
        // `datetime.datetime` doesn't import. Retry the PARENT module and register just that class's
        // members, so datetime.now() resolves (methodHit) instead of staying a generic call.
        const dot = module.lastIndexOf('.');
        const parent = module.slice(0, dot), cls = module.slice(dot + 1);
        const pspec = await getSpec(parent);
        if (pspec && (pspec.entries || []).some((e) => e.kind === 'class' && e.name === cls)) { spec = pspec; classOnly = cls; }
      }
      if (!spec) continue;
      const all = spec.entries || [];
      const whole = !classOnly && all.length <= WHOLE_CAP;
      const reduced = all.filter((e) => {
        const used = classOnly
          ? ((e.kind === 'class' && e.name === classOnly) || ((e.kind === 'method' || e.kind === 'property') && e.owner === classOnly))
          : (whole || attrs.has(e.name) || ((e.kind === 'method' || e.kind === 'property') && bareAttrs.has(e.name)));
        if (!used) return false;
        const key = `${spec.module}::${e.kind}::${e.owner || ''}.${e.name}`;
        if (registeredSymRef.current.has(key)) return false;
        registeredSymRef.current.add(key);
        return true;
      });
      if (reduced.length) { registerUsedLibrary({ ...spec, entries: reduced }, { bindings }); changed = true; }
    }
    // Bare from-imports (`from math import sqrt; sqrt(x)`): register a BARE spec (module '') that lowers
    // to the LOCAL binding (`sqrt(...)`, or `s(...)` for `import sqrt as s`) and colours the bare call,
    // filed under the source library's tab. Text stays lossless.
    for (const [module, syms] of (bareFuncs || new Map())) {
      const spec = await getSpec(module);
      if (!spec) continue;
      for (const [binding, sym] of syms) {
        const key = `${module}::bare::${binding}`;
        if (registeredSymRef.current.has(key)) continue;
        const entry = (spec.entries || []).find((e) => e.name === sym && (e.kind === 'function' || e.kind === 'class'));
        if (!entry) continue;
        registeredSymRef.current.add(key);
        const res = reg.registerLibBlock({ module: '', func: binding, argNames: imp.requiredParamNames(entry), colour: '#009688', title: binding, lib: module, hasOutput: entry.returns !== false });
        if (res.ok) changed = true;
      }
    }
    // Bare specs above register directly (not via registerUsedLibrary), so persist here — otherwise
    // whether they survive a reload depends on some LATER unrelated action happening to call persist().
    if (changed && typeof reg.persist === 'function') reg.persist();
    return changed;
  };

  // Tier-1 receiver-type inference (deterministic): tag each `<var>.attr` node with the class `var` was
  // constructed from, so property colouring is PRECISE (ser.baudrate colours as serial.Serial; a user
  // object's dog.name does NOT colour). `var = Lib.Class(...)`/`Class(...)` -> that class; `var =
  // UserClass(...)` (a class defined in this code) -> '__user__' (suppress). Everything else stays
  // name-based. Mutates `_ownerType` onto Attribute nodes; irToBlockly carries it (display-only).
  const annotateOwnerTypes = (ir, jediVars) => {
    const userClasses = new Set();
    const walk = (node, fn) => {
      if (!node || typeof node !== 'object') return;
      if (Array.isArray(node)) { node.forEach((c) => walk(c, fn)); return; }
      fn(node);
      for (const k in node) if (k !== 'type') walk(node[k], fn);
    };
    walk(ir && ir.body, (n) => { if (n.type === 'ClassDef' && n.name) userClasses.add(n.name); });
    const libClasses = classNamesRef.current;
    const calleeName = (fn) => (!fn ? null : fn.type === 'Name' ? fn.id : fn.type === 'Attribute' ? fn.attr : null);
    const varType = new Map();
    // Tier-2 (Jedi) is authoritative — it resolves return types/subscripts the heuristic can't (p:ListPortInfo).
    for (const [name, v] of Object.entries(jediVars || {})) if (v && v.type) varType.set(name, v.type);
    // A method's receiver (`self`) is always an instance of a user-defined class in converted code, so
    // `self.attr` must NOT colour by name (it's the user's own attribute, not a library property).
    walk(ir && ir.body, (n) => {
      if (n.type === 'ClassDef' && Array.isArray(n.body)) {
        for (const m of n.body) {
          if ((m.type === 'FunctionDef' || m.type === 'AsyncFunctionDef') && m.args) {
            const pos = [...(m.args.posonlyargs || []), ...(m.args.args || [])];
            if (pos[0] && pos[0].arg) varType.set(pos[0].arg, '__user__');
          }
        }
      }
    });
    walk(ir && ir.body, (n) => {
      if (n.type === 'Assign' && Array.isArray(n.targets) && n.targets.length === 1
          && n.targets[0].type === 'Name' && n.value && n.value.type === 'Call' && !varType.has(n.targets[0].id)) {
        const cn = calleeName(n.value.func);   // fills only what Jedi didn't resolve
        if (cn) {
          if (userClasses.has(cn)) varType.set(n.targets[0].id, '__user__');
          else if (libClasses.has(cn)) varType.set(n.targets[0].id, cn);
        }
      }
    });
    if (!varType.size) return;
    walk(ir && ir.body, (n) => {
      if (n.type === 'Attribute' && n.value && n.value.type === 'Name' && varType.has(n.value.id)) n._ownerType = varType.get(n.value.id);
    });
  };

  // Compile Python to Blockly blocks via the CPython-3.12 ast single-IR pipeline (Pyodide):
  //   python -> pythonToIR -> irToBlockly -> Blockly workspace load.
  // Async because the parse runs in Pyodide. The legacy BlockPyParser/Desugarer path is retired
  // from conversion; IR keeps SUGAR blocks (no desugar — desugar-as-feature is a later phase).
  const syncCodeToBlocks = async (currentCode) => {
    if (!currentCode.trim() || currentCode.startsWith('# Start dragging')) return;
    if (!workspaceRef.current) return;

    isSyncingFromCodeRef.current += 1;
    const myGen = ++syncGenRef.current;
    setIsConverting(true);

    try {
      // Snapshot Recovery fast path: BYTE-IDENTICAL Python since the last block edit restores the
      // saved workspace JSON verbatim (no re-parse, no block drift).
      if (blocklySnapshotRef.current && currentCode === associatedPythonRef.current) {
        window.Blockly.serialization.workspaces.load(blocklySnapshotRef.current, workspaceRef.current);
        setLogs(prev => [...prev, '[Sync-Engine] Python matches active snapshot. Restored layout without block drift.']);
        setSyntaxStatus({ valid: true, error: '' });
        return;
      }

      const pyodide = await window.BlockPyAstBridge.getPyodide();
      let ir = await window.BlockPyAstBridge.pythonToIR(pyodide, currentCode);
      // Snapshot Recovery slow path: the text changed, but if it parses to the IDENTICAL IR
      // (including the _comments channel) the edit was formatting-only — keep the layout. This
      // replaces the old regex-normalized string compare, which collapsed ALL whitespace and
      // stripped comments, so a re-indented line (semantic in Python!), an edit inside a string
      // literal, or a comment change was silently REVERTED to the old blocks. AST identity can
      // never mistake a semantic or comment edit for "unchanged".
      if (blocklySnapshotRef.current && associatedPythonRef.current) {
        try {
          const prevIr = await window.BlockPyAstBridge.pythonToIR(pyodide, associatedPythonRef.current);
          if (JSON.stringify(prevIr) === JSON.stringify(ir)) {
            if (myGen !== syncGenRef.current) return;
            window.Blockly.serialization.workspaces.load(blocklySnapshotRef.current, workspaceRef.current);
            associatedPythonRef.current = currentCode;
            setLogs(prev => [...prev, '[Sync-Engine] Formatting-only change (same AST + comments). Restored layout without block drift.']);
            setSyntaxStatus({ valid: true, error: '' });
            return;
          }
        } catch (_) { /* previous text no longer parses — fall through to a full convert */ }
      }
      // Phase 4 (opt-in): rewrite sugar (comprehensions/ternary/chained compare) to elementary
      // loop/conditional/boolean IR in provably-safe positions; SUGAR is preserved elsewhere. The
      // pass emits only existing IR nodes, so irToBlockly consumes it unchanged.
      if (shouldDesugar && window.BlockPyIrDesugar) {
        ir = window.BlockPyIrDesugar.desugarIr(ir);
      }
      // Convert-time exception rule: materialize every referenced library symbol into the toolbox
      // BEFORE building blocks, so lib.func()/lib.CONST/obj.attr paint recognized (emerald) on first
      // render and every canvas block has a toolbox home — but on a TIME BUDGET. Recognition is
      // display-only (a wrong/absent oracle can only mis-colour, never change lowering), so a wedged
      // backend must degrade to generic styling instead of freezing Convert forever.
      const ORACLE_BUDGET_MS = 15000;
      const oracles = (async () => {
        const grew = await autoBlockifyRefs(ir);
        // Tier-2: Jedi resolves receiver types (incl. return types like p:ListPortInfo); register those
        // classes' members and use them for precise colouring. Degrades silently if the backend/Jedi is off.
        const jediVars = await inferTypes(currentCode);
        const grew2 = await registerInferredClasses(jediVars);
        return { grew: grew || grew2, jediVars };
      })();
      let oracle = await Promise.race([oracles, new Promise((res) => setTimeout(() => res(null), ORACLE_BUDGET_MS))]);
      if (!oracle) {
        setLogs((prev) => [...prev, '[Convert] Library recognition is slow — blocks render generic for now and will recolour automatically when it finishes (round-trip is unaffected).']);
        // Self-heal: when the oracle finally lands, grow the toolbox AND recolour the on-canvas calls
        // so a recognised library call turns emerald without the user re-converting.
        oracles.then((late) => {
          if (myGen !== syncGenRef.current) return;   // a newer convert now owns colouring
          if (late && late.grew) refreshToolboxNow();
          recolorLibBlocks(workspaceRef.current);
        }).catch(() => {});
        oracle = { grew: false, jediVars: {} };
      }
      if (oracle.grew) refreshToolboxNow();
      annotateOwnerTypes(ir, oracle.jediVars);   // tag attribute receivers with their inferred class for precise colouring
      if (myGen !== syncGenRef.current) return;   // a newer sync started while we awaited introspection/install
      const blocklyJson = window.BlockPyIR.irToBlockly(ir);
      // Library calls stay as the unified ir_call block; ir_call.updateShape_ styles a registered
      // call emerald with parameter-name labels (same look as the toolbox), so converting from Python
      // and dragging from the toolbox yield the IDENTICAL block — for ANY arg shape (incl. keyword
      // args, which a fixed-arity Tier-A block could not hold). No separate upgrade pass needed.
      // If a newer sync started while we awaited Pyodide/parse (e.g. a quick second Auto-Desugar
      // toggle), discard this stale result so the workspace always reflects the LATEST request.
      if (myGen !== syncGenRef.current) return;
      window.Blockly.serialization.workspaces.load(blocklyJson, workspaceRef.current);

      // Ensure the freshly-loaded blocks actually render and are in view. Loading into a
      // hidden/zero-size workspace (e.g. while the Python tab is active) leaves blocks
      // unrendered until a resize, and tall stacks can land off-screen — both look like
      // "convert produced no blocks". Resize + center fixes it.
      try {
        window.Blockly.svgResize(workspaceRef.current);
        if (typeof workspaceRef.current.scrollCenter === 'function') workspaceRef.current.scrollCenter();
      } catch (_) { /* non-fatal */ }

      blocklySnapshotRef.current = window.Blockly.serialization.workspaces.save(workspaceRef.current);
      associatedPythonRef.current = currentCode;
      refreshGrayBlocks(); // update the gray (unconverted) block inspector

      setLogs(prev => [...prev, '[Sync-Engine] Converted Python → blocks via CPython-3.12 ast IR.']);
      setSyntaxStatus({ valid: true, error: '' });
    } catch (err) {
      console.error(err);
      setLogs(prev => [...prev, `[Parser Error] ${err.message}`]);
      setSyntaxStatus({ valid: false, error: err.message });
    } finally {
      isSyncingFromCodeRef.current -= 1;
      if (myGen === syncGenRef.current) setIsConverting(false);   // only the latest sync clears the spinner
    }
  };

  // Register the built-in cv2 palette and restore any user-generated libraries — both through the
  // Phase 5 registry (BlockPyLibRegistry), the single source of truth, so they appear in the Library
  // toolbox category and lower correctly. The cv2 preload is in-memory only (re-registered each
  // mount); localStorage/hydrate is reserved for user-generated libraries. A single setInstalledBlocks
  // here (union, deduped by type) avoids the two-effects clobber.
  useEffect(() => {
    const reg = window.BlockPyLibRegistry;
    const installed = [];
    if (reg) {
      // Restore user-generated libraries from localStorage (re-registers their Blockly.Blocks defs).
      const restored = (typeof reg.hydrate === 'function') ? reg.hydrate() : [];
      if (Array.isArray(restored)) installed.push(...restored);
      // Built-in library tabs (math, random, datetime, json, statistics, re, functools, time, cv2).
      // Single-form (no command/value doubling) for a clean palette; registered builtin so they're
      // always present and not user-deletable. Bundled offline as stdlibSpecs.json (generated by
      // scripts/gen-stdlib-blocks.cjs — cv2's hand-authored signatures live there, replacing the old
      // AI_PRESETS table, since opencv's C functions expose no introspectable signature).
      const imp = window.BlockPyLibImport;
      if (imp && Array.isArray(stdlibSpecs)) {
        for (const spec of stdlibSpecs) {
          for (const s of imp.librarySpecToRegistrySpecs(spec, { both: false }).specs) {
            const res = reg.registerLibBlock({ ...s, builtin: true });
            if (res.ok && !installed.some((e) => e.type === res.type)) {
              const stored = reg.getLibSpec(res.type) || s;
              installed.push({ type: res.type, title: stored.title, hasOutput: stored.hasOutput, func: stored.func, args: stored.argNames, colour: stored.colour });
            }
          }
        }
      }
      setInstalledBlocks(installed);
    }

    // Open the workspace's main.py on startup if present; otherwise fall back to the demo.
    // Clobber guard: this fetch races the user (a slow backend can resolve AFTER they started
    // typing/converting) — never overwrite an editor that is no longer pristine, and only fire
    // the deferred sync if the editor still shows exactly what we loaded.
    (async () => {
      const pristine = () => !latestCodeRef.current || !latestCodeRef.current.trim();
      try {
        const r = await fetch('/api/fs/file?path=main.py');
        if (r.ok) {
          const j = await r.json();
          if (j.kind === 'text') {
            if (!pristine()) return;                       // user got there first — keep their code
            const content = j.content || '';
            // Atomic apply: the functional updater re-checks against the LATEST state, so an edit
            // that lands in the same React batch can never be overwritten.
            let applied = false;
            latestCodeRef.current = content;               // eager: don't depend on a render before the timer
            setCode((prev) => {
              if (prev && prev.trim()) { latestCodeRef.current = prev; return prev; }
              applied = true;
              return content;
            });
            setTimeout(() => {
              if (applied && latestCodeRef.current === content) {
                setActiveFile('main.py');
                syncCodeToBlocks(content);
              }
            }, 80);
            return;
          }
        }
      } catch (_) { /* backend not up — use the demo */ }
      if (pristine()) loadDemoScript('star');
    })();
  }, []);

  // Keep the ref in lockstep with the editor state (used by the startup-load guard above).
  useEffect(() => { latestCodeRef.current = code; }, [code]);

  // Pre-warm the Python environment (Pyodide + real opencv-python + sample images) in the
  // background as soon as the app loads, so the first Run is instant rather than waiting
  // for a one-time download/install. Within a session this is built once and reused.
  useEffect(() => {
    let cancelled = false;
    setPyodideLoading(true);
    prewarmEnvironment((msg) => { if (!cancelled) setLogs((prev) => [...prev, msg]); })
      .then(() => { if (!cancelled) { setPyodideLoading(false); setPyodideReady(true); } })
      .catch(() => { if (!cancelled) setPyodideLoading(false); });
    return () => { cancelled = true; };
  }, []);

  // When the Blockly tab becomes visible, force a resize + recenter. Blockly cannot lay
  // out blocks while its container is display:none, so blocks converted on the Python tab
  // would otherwise appear missing until the user nudges the canvas.
  useEffect(() => {
    if (activeEditorTab === 'blockly' && workspaceRef.current && window.Blockly) {
      requestAnimationFrame(() => {
        try {
          window.Blockly.svgResize(workspaceRef.current);
          if (typeof workspaceRef.current.scrollCenter === 'function') workspaceRef.current.scrollCenter();
        } catch (_) { /* non-fatal */ }
      });
    }
  }, [activeEditorTab]);

  // Dynamic-library palette (Phase 5): when the registry changes (hydrate on mount, or a new
  // AI/preset registration), rebuild the JSON toolbox so the "Library" category reflects the
  // live registry. Blockly diffs categoryToolbox JSON on updateToolbox(). Children-first effect
  // ordering means BlocklyEditor has already injected (workspaceRef set) before this runs.
  useEffect(() => {
    const ws = workspaceRef.current;
    if (!ws || typeof window.BlockPyBuildIrToolbox !== 'function') return;
    try {
      ws.updateToolbox(window.BlockPyBuildIrToolbox());
    } catch (e) {
      console.error('Failed to refresh library toolbox:', e);
    }
  }, [installedBlocks]);

  // Phase 4: toggling "Auto Desugar" must re-Convert the current code so the blocks immediately
  // reflect the new setting. The saved snapshot was captured under the OLD setting, so invalidate
  // it first — otherwise snapshot recovery (unchanged Python) would restore the old-setting blocks.
  useEffect(() => {
    if (desugarToggleMountRef.current) { desugarToggleMountRef.current = false; return; }
    blocklySnapshotRef.current = null;
    if (code && code.trim()) syncCodeToBlocks(code);
    // Intentionally keyed on shouldDesugar only; reads the current code/closure at toggle time.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shouldDesugar]);

  // Phase 4 slice 4: keep the Desugared preview pane in sync with the REAL IR desugar pass
  // (pythonToIR -> desugarIr -> irToPython), so the preview matches what "Auto Desugar" produces
  // in blocks. Computed only while the Desugared tab is active (Pyodide round-trip is async).
  useEffect(() => {
    if (activeEditorTab !== 'desugar') return;
    let cancelled = false;
    (async () => {
      if (!code || !code.trim()) { if (!cancelled) setDesugaredPreview(''); return; }
      try {
        const py = await window.BlockPyAstBridge.getPyodide();
        const ir = await window.BlockPyAstBridge.pythonToIR(py, code);
        const dir = window.BlockPyIrDesugar.desugarIr(ir);
        const out = await window.BlockPyAstBridge.irToPython(py, dir);
        if (!cancelled) setDesugaredPreview(out.replace(/\n$/, ''));
      } catch (e) {
        if (!cancelled) setDesugaredPreview('# (desugar preview unavailable: ' + (e.message || e) + ')');
      }
    })();
    return () => { cancelled = true; };
  }, [code, activeEditorTab]);

  const loadDemoScript = (type) => {
    let demoCode = '';
    switch (type) {
      case 'opencv':
        demoCode = `# OpenCV Webcam Stream — opens a real camera window
cap = cv2.VideoCapture(0)
print("Camera opened. Streaming...")
frame = cap.read()
cv2.imshow("Live Webcam", frame)
key = cv2.waitKey(1)
print("Press Stop to close the webcam window.")
cv2.destroyAllWindows()`;
        break;
      case 'star':
        demoCode = `# Drawing a Glowing Vector Star using Loops and Pen
sprite.pen_down()
sprite.color("#3b82f6")
for i in range(5):
    sprite.move(120)
    sprite.turn_right(144)
sprite.pen_up()
sprite.move(30)
sprite.say("Star drawing complete!")`;
        break;
      case 'listcomp':
        demoCode = `# Testing List Comprehension desugaring unrolls
numbers = [1, 2, 3, 4, 5]
y = [x * 10 for x in numbers]
print(y)`;
        break;
      case 'ternary':
        demoCode = `# Testing Ternary Operator desugaring unrolls
speed = 120
status = "Danger" if speed > 100 else "Safe"
print(status)`;
        break;
      case 'chained':
        demoCode = `# Testing Chained Comparisons unrolls
speed = 85
if 60 < speed < 120:
    print("Normal cruising speed activated")`;
        break;
      case 'augmented':
        demoCode = `# Testing Loop variables updates
count = 0
for i in range(4):
    count += 2
    print(count)`;
        break;
    }

    latestCodeRef.current = demoCode;   // eager: don't depend on a render before the deferred sync
    setCode(demoCode);
    setHighlightedLine(null);
    setLogs([`[System] Demo script "${type}" loaded into workspace.`]);

    setTimeout(() => {
      // Deferred sync fires only if the editor still shows this demo — a user who replaced the
      // content within the delay window must not have their code's blocks clobbered.
      if (latestCodeRef.current === demoCode) syncCodeToBlocks(demoCode);
    }, 100);
  };

  // ── Gray (raw) block inspector: collect the fallback blocks, jump to each ──────
  const refreshGrayBlocks = () => {
    const ws = window.__blocklyWorkspace ||
      (window.Blockly && window.Blockly.getMainWorkspace && window.Blockly.getMainWorkspace());
    if (!ws) { setGrayBlocks([]); return; }
    const list = ws.getAllBlocks()
      .filter((b) => b.type === 'raw_statement' || b.type === 'raw_expression')
      .map((b) => ({
        id: b.id,
        kind: b.type === 'raw_statement' ? 'statement' : 'expression',
        text: (b.getFieldValue('STMT') || b.getFieldValue('EXPR') || '').replace(/\s+/g, ' ').trim().slice(0, 140),
      }));
    setGrayBlocks(list);
  };

  const jumpToGray = (id) => {
    const ws = window.__blocklyWorkspace ||
      (window.Blockly && window.Blockly.getMainWorkspace && window.Blockly.getMainWorkspace());
    if (!ws) return;
    setActiveEditorTab('blockly');
    requestAnimationFrame(() => {
      try {
        const b = ws.getBlockById(id);
        if (!b) return;
        if (typeof ws.centerOnBlock === 'function') ws.centerOnBlock(id);
        if (typeof b.select === 'function') b.select();
      } catch (_) { /* ignore */ }
    });
  };

  // ── Image upload (App-Inventor-style): feed a real image to cv2.imread ─────────
  const handleImageUpload = async (file) => {
    if (!file) return;
    try {
      setPyodideLoading(!pyodideReady);
      const buf = new Uint8Array(await file.arrayBuffer());
      // (1) Pyodide FS — for the in-browser Run.
      await writeImageToFS(file.name, buf);
      setPyodideReady(true);
      setPyodideLoading(false);
      setUploadedImageName(file.name);
      const dataUrl = await new Promise((resolve) => {
        const r = new FileReader();
        r.onload = () => resolve(r.result);
        r.readAsDataURL(file);
      });
      // (2) Backend media dir — for the "Run (Shell)" real-python path.
      let shellNote = '';
      try {
        const resp = await fetch('/api/upload-image', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ filename: file.name, dataBase64: dataUrl }),
        });
        if (resp.ok) { const d = await resp.json(); shellNote = ` (also usable in Shell run via cv2.imread("${d.savedAs}"))`; }
      } catch (_) { /* backend may be off — browser Run still works */ }
      setCv2Images([{ title: `Uploaded: ${file.name}`, dataUrl }]);
      setUploadedMedia((prev) => [{ name: file.name, dataUrl }, ...prev.filter((m) => m.name !== file.name)].slice(0, 12));
      setFsReload((n) => n + 1); // the upload landed in the workspace → show it in the Files tree
      setLogs((prev) => [...prev, `[Image] "${file.name}" uploaded — use cv2.imread("${file.name}").${shellNote}`]);
    } catch (e) {
      setLogs((prev) => [...prev, `[Image upload error] ${e.message || e}`]);
    }
  };

  // ── Real pip install (backend) — installs into the local Python used by Shell runs ──
  const [pipPkg, setPipPkg] = useState('');
  const handlePipInstallShell = async () => {
    const pkg = pipPkg.trim();
    if (!pkg) return;
    setActiveAuxTab('logs');
    setLogs((prev) => [...prev, `[pip] Installing: pip install ${pkg} ...`]);
    try {
      const resp = await fetch('/api/pip-install', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ package: pkg }),
      });
      if (!resp.ok || !resp.body) {
        setLogs((prev) => [...prev, `[pip] Response error (${resp.status}). Check npm run server.`]); return;
      }
      const reader = resp.body.getReader();
      const dec = new TextDecoder();
      let out = '';
      for (;;) { const { done, value } = await reader.read(); if (done) break; const t = dec.decode(value, { stream: true }); if (t) { out += t; setLogs((prev) => [...prev, t.replace(/\n+$/, '')]); } }
      // Auto-blockify: the whole point of installing is to get the blocks — so generate them right
      // away into a toolbox tab (no separate Blockify step). Skip only if pip clearly failed.
      if (/\berror\b|could not find|no matching distribution/i.test(out) && !/successfully installed/i.test(out)) {
        setLogs((prev) => [...prev, `[pip] Install reported an error — skipping block generation. Fix the package name and retry.`]);
        return;
      }
      const pkgName = pkgBaseName(pkg);
      // New modules exist now — drop the convert-time session caches so modules previously cached
      // as "not installed" re-probe, and their symbols materialize freely on the next Convert.
      introspectedSpecsRef.current.clear();
      registeredSymRef.current.clear();
      setLogs((prev) => [...prev, `[pip] Installed. Generating blocks for "${pkgName}" → toolbox…`]);
      await handleBlockifyLibrary(pkgName);
      // Also blockify the installed dependencies pip just pulled in, so transitive libraries
      // (e.g. pydobot → pyserial) get their own toolbox tabs instead of bare green call blocks.
      await blockifyDependencies(pkgName);
    } catch (e) {
      setLogs((prev) => [...prev, `[pip] Error: ${e.message}. Make sure the backend is running.`]);
    }
  };

  // ── Run in a real local Python shell (backend) — real cv2, real webcam, real imshow ──
  // Streams stdout/stderr from the actual `python` process. Native OpenCV windows (imshow,
  // VideoCapture) open on the user's desktop. Requires the backend (npm run server).
  const handleRunShell = async () => {
    setCv2Images([]);
    // Persist the open file first so the run reads the latest from the workspace (and what
    // the explorer shows matches what executes).
    if (activeFile) { await saveActiveFile({ silent: true }); }
    setLogs([`[Shell] Running real Python (local python + real cv2)${activeFile ? ' on ' + activeFile : ''}. Files resolve against the workspace folder.`, `[Shell] Code:\n${code}`]);
    setActiveAuxTab('logs');
    setIsRunning(true);
    const controller = new AbortController();
    shellAbortRef.current = controller;
    try {
      const resp = await fetch('/api/run-python', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) {
        setLogs((prev) => [...prev, `[Shell] Backend response error (${resp.status}). Make sure npm run server is running.`]);
        return;
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        const text = decoder.decode(value, { stream: true });
        if (text) setLogs((prev) => [...prev, text.replace(/\n+$/, '')]);
      }
    } catch (e) {
      if (e.name === 'AbortError') setLogs((prev) => [...prev, '[Shell] Stopped.']);
      else setLogs((prev) => [...prev, `[Shell] Error: ${e.message}. Make sure the backend (npm run server) is running.`]);
    } finally {
      setIsRunning(false);
      shellAbortRef.current = null;
      // A run may have written output files (cv2.imwrite, open('w'), …) — refresh the tree.
      setFsReload((n) => n + 1);
    }
  };

  // ── Workspace file open / save ────────────────────────────────────────────────
  // Open a file from the explorer: text files load into the editor (and sync to blocks via
  // the Python editor's normal flow); image files pop a preview overlay.
  const openFile = async (relPath) => {
    try {
      const r = await fetch('/api/fs/file?path=' + encodeURIComponent(relPath));
      const j = await r.json();
      if (!r.ok) { setLogs((prev) => [...prev, `[Files] Open failed: ${j.error || r.status}`]); return; }
      if (j.kind === 'image') {
        setImagePreview({ name: relPath, url: j.url });
        return;
      }
      const content = j.content || '';
      setActiveFile(relPath);
      setCode(content);
      setActiveEditorTab('python');
      // For Python files, also rebuild the blocks from the opened file. Without this the
      // workspace still holds the previously loaded program, and its block->code listener
      // would clobber the freshly opened text. Non-.py files load as plain text only.
      if (relPath.endsWith('.py')) {
        setTimeout(() => { syncCodeToBlocks(content); }, 60);
      }
    } catch (e) {
      setLogs((prev) => [...prev, `[Files] Open error: ${e.message}`]);
    }
  };

  // Save the current editor content back to the open file. silent = no toast/log noise.
  const saveActiveFile = async (opts = {}) => {
    if (!activeFile) { if (!opts.silent) setLogs((prev) => [...prev, '[Files] No file open to save. Open a file from the Files tab first.']); return; }
    try {
      const r = await fetch('/api/fs/file', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: activeFile, content: code }),
      });
      if (!r.ok) { const j = await r.json().catch(() => ({})); setLogs((prev) => [...prev, `[Files] Save failed: ${j.error || r.status}`]); return; }
      if (!opts.silent) setLogs((prev) => [...prev, `[Files] Saved ${activeFile}.`]);
      setFsReload((n) => n + 1);
    } catch (e) {
      setLogs((prev) => [...prev, `[Files] Save error: ${e.message}`]);
    }
  };

  // Ctrl/Cmd+S saves the open file. Rebound on activeFile/code change so it always saves latest.
  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && (e.key === 's' || e.key === 'S')) {
        e.preventDefault();
        saveActiveFile();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [activeFile, code]);

  // ── Stop: interrupt any running program (shell run; also a no-op Pyodide interrupt) ──────────
  const handleStopExecution = () => {
    interruptPyodide();
    if (shellAbortRef.current) { try { shellAbortRef.current.abort(); } catch (_) {} }
    setHighlightedLine(null);
    setIsRunning(false);
    setLogs(prev => [...prev, '[Python] Stopped.']);
  };

  // ── Library / toolbox removal ─────────────────────────────────────────────────
  // Rebuild the Blockly toolbox immediately from the live registry (the [installedBlocks]
  // effect also does this, but calling it here guarantees the tab disappears at once).
  const refreshToolboxNow = () => {
    const ws = workspaceRef.current;
    if (ws && typeof window.BlockPyBuildIrToolbox === 'function') {
      try { ws.updateToolbox(window.BlockPyBuildIrToolbox()); } catch (_) { /* non-fatal */ }
    }
  };

  // Self-heal recognition on the canvas AFTER a late-completing oracle: re-run each library-callable
  // block's shape so a now-registered call turns emerald (with param labels) without a full re-convert.
  // Colour/labels are display-only, so this never changes the lowered Python — hence guarded by the
  // sync counter (no redundant block→code regen). ir_call keeps its children (reshapePreserving_);
  // only DOTTED ir_attribute (constants — no receiver child) is re-shaped, since re-running a
  // property's updateShape_ would drop its receiver input (that case recolours on the next convert).
  const recolorLibBlocks = (ws) => {
    if (!ws || typeof ws.getAllBlocks !== 'function') return;
    isSyncingFromCodeRef.current += 1;
    try {
      for (const b of ws.getAllBlocks(false)) {
        try {
          if (b.type === 'ir_call' && typeof b.reshapePreserving_ === 'function') b.reshapePreserving_();
          else if (b.type === 'ir_attribute' && b.dotted_ && typeof b.updateShape_ === 'function') {
            b.updateShape_();
            if (b.rendered && typeof b.render === 'function') b.render();
          }
        } catch (_) { /* one block failing must not stall the rest */ }
      }
    } finally {
      isSyncingFromCodeRef.current -= 1;
    }
  };

  // Delete one library tab: drops its user blocks + macros from the registry and the toolbox.
  const handleRemoveLibrary = (libKey) => {
    const reg = window.BlockPyLibRegistry;
    if (!reg || typeof reg.removeLibraryByTab !== 'function') return;
    const removed = reg.removeLibraryByTab(libKey);
    // The convert-time "already materialized" cache must follow the registry: stale keys would make
    // a re-Convert skip every symbol of the deleted tab, so it could never come back this session.
    registeredSymRef.current.clear();
    setInstalledBlocks((prev) => prev.filter((p) => !removed.includes(p.type)));
    refreshToolboxNow();
    setLogs((prev) => [...prev, `[Library] Removed "${libKey}" — ${removed.length} block(s) + its toolbox tab.`]);
  };

  // Wipe all user-added libraries (built-in presets stay).
  const handleClearLibraries = () => {
    const reg = window.BlockPyLibRegistry;
    if (!reg || typeof reg.removeAllUserLibraries !== 'function') return;
    if (!window.confirm('Remove ALL added libraries and their toolbox tabs?\n(Built-in preset blocks stay.)')) return;
    const removed = reg.removeAllUserLibraries();
    registeredSymRef.current.clear();   // same invalidation as single-tab removal
    setInstalledBlocks((prev) => prev.filter((p) => !removed.includes(p.type)));
    refreshToolboxNow();
    setLogs((prev) => [...prev, `[Library] Cleared all added libraries — ${removed.length} block(s).`]);
  };

  // Auto-add a library's import as a REAL ir_* block (round-trips losslessly) so dragged library
  // blocks run without the user hand-adding `from PIL import Image`. Added once per library, before
  // the user drags usage, so it serializes first → the import precedes use in generated Python.
  // BlocklyEditor stays mounted (display:none toggling), so window.__blocklyWorkspace is always live.
  const ensureLibraryImportBlock = (moduleDotted, alias) => {
    const ws = window.__blocklyWorkspace;
    const B = window.Blockly;
    if (!ws || !B || !B.serialization || !window.BlockPyLibImport) return false;
    const want = window.BlockPyLibImport.importBlockJson(moduleDotted, alias);
    const all = ws.getAllBlocks(false);
    const present = all.some((blk) => {
      if (blk.type !== want.type) return false;
      if (want.type === 'ir_import') return (blk.getFieldValue('NAMES') || '') === want.fields.NAMES;
      if ((blk.getFieldValue('MODULE') || '') !== want.fields.MODULE) return false;
      const names = (blk.getFieldValue('NAMES') || '').split(',').map((s) => s.trim().split(/\s+/)[0]);
      return names.includes(want.fields.NAMES);
    });
    if (present) return false;
    const importCount = all.filter((b) => b.type === 'ir_import' || b.type === 'ir_importfrom').length;
    try { B.serialization.blocks.append({ ...want, x: 24, y: 24 + importCount * 38 }, ws); return true; }
    catch (_) { return false; }
  };

  // Introspect a module (/api/blockify, real Python, no AI cost) → { spec, cached }. Logs + returns
  // null on failure. Shared by Blockify (full) and Curate.
  const introspectModule = async (mod, opts = {}) => {
    let response = null;
    try {
      response = await fetch('/api/blockify', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ module: mod, ...(opts.maxEntries ? { maxEntries: opts.maxEntries } : {}) }),
        signal: AbortSignal.timeout(90000),   // backstop; the backend kills a blocking import at ~60s
      });
    } catch (_) { response = null; }
    let data = null;
    if (response) { try { data = await response.json(); } catch (_) { data = null; } }
    if (!response || !response.ok || !data || !data.success || !data.spec) {
      // DEFINITIVE "no such module" (backend 404 / allowlist 403) vs TRANSIENT failure (backend
      // down/5xx/timeout): callers cache the former but must retry the latter (getSpec).
      const notFound = !!(response && (response.status === 404 || response.status === 403 || (data && data.notFound)));
      // Convert-time auto-blockify probes candidate submodules that may not be modules at all
      // (`from math import sqrt` → "math.sqrt"); a failed probe is expected, so stay silent.
      if (opts.quiet) return notFound ? { notFound: true } : null;
      const why = !response ? 'backend unreachable (is the Express server running?)'
        : (notFound ? `"${mod}" is not an importable module (not installed?)`
          : (!response.ok ? `backend ${response.status}${(data && data.error) ? ' — ' + data.error : ''}` : ((data && data.error) || 'introspection failed')));
      setLogs((prev) => [...prev, `[Blockify] ${why} for "${mod}".`]);
      return null;
    }
    return data;
  };

  // Register EVERY introspected entry of a library as Library-palette blocks. entryToSpec now emits
  // BOTH a command (green statement) and a value (reporter) form where the return type is unknown,
  // so a library's commands are finally draggable into the program flow. Idempotent re-run replaces
  // the library's prior blocks (latest labels/signatures win). Returns { mapped, registered, ... }.
  const registerFullLibrary = (librarySpec) => {
    const reg = window.BlockPyLibRegistry;
    const imp = window.BlockPyLibImport;
    const mapped = imp.librarySpecToRegistrySpecs(librarySpec);
    // Replace ONLY this library's prior blocks, scoped by its `lib` tag. (The old
    // removeModules(libraryModules) keyed on the receiver-alias module — a shared lowercased class
    // name — so Blockifying/Curating a library with a common class like `Timer`/`Client` WIPED other
    // libraries' same-named blocks. removeLibrarySpecs is scoped strictly to the source library.)
    const removedTypes = reg.removeLibrarySpecs
      ? reg.removeLibrarySpecs(librarySpec.module)
      : reg.removeModules(imp.libraryModules(librarySpec));
    const registered = [];
    let rejected = 0;
    for (const spec of mapped.specs) {
      const res = reg.registerLibBlock(spec);
      if (!res.ok) { rejected++; continue; }
      const stored = reg.getLibSpec(res.type) || spec;
      registered.push({ type: res.type, title: stored.title, hasOutput: stored.hasOutput, func: stored.func, args: stored.argNames, colour: stored.colour });
    }
    // Module constants (cv2.IMREAD_COLOR, math.pi) + class properties (obj.device) — value blocks,
    // registered alongside the calls (they lower to attribute references, not calls).
    let constCount = 0;
    if (reg.registerConst) for (const c of (mapped.consts || [])) { if (reg.registerConst(c).ok) constCount++; }
    let propCount = 0;
    if (reg.registerProp) for (const p of (mapped.props || [])) { if (reg.registerProp(p).ok) propCount++; }
    reg.persist();
    setInstalledBlocks((prev) => {
      const drop = new Set([...removedTypes, ...registered.map((r) => r.type)]);
      return [...prev.filter((p) => !drop.has(p.type)), ...registered];
    });
    return { mapped, registered, rejected, removedTypes, constCount, propCount };
  };

  // After installing a package, blockify the INSTALLED direct dependencies it pulled in (mapped
  // to their real import names by the backend, e.g. pydobot → pyserial → serial). Capped so a
  // dependency-heavy package can't flood the toolbox; best-effort (never blocks the main flow).
  const blockifyDependencies = async (pkgName) => {
    let deps = [];
    try {
      const r = await fetch('/api/deps', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ module: pkgName }),
      });
      if (r.ok) { const d = await r.json(); deps = (d && d.deps) || []; }
    } catch (_) { /* backend down — skip silently */ }
    if (!deps.length) return;
    const CAP = 20;
    const use = deps.slice(0, CAP);
    if (deps.length > CAP) setLogs((prev) => [...prev, `[pip] ${deps.length} dependencies found — blockifying the first ${CAP}.`]);
    setLogs((prev) => [...prev, `[pip] Dependencies of "${pkgName}": ${use.map((d) => d.import).join(', ')} — generating blocks…`]);
    for (const d of use) {
      await handleBlockifyLibrary(d.import);
    }
  };

  // Blockify (recursive/whole-package, OPT-IN): enumerate a package's importable submodules
  // (serial → serial.tools.list_ports, serial.threaded, …) and blockify EACH into its own tab, so
  // one action covers the whole library tree instead of just the module the code references. Bounded
  // by the backend's submodule cap; submodules that don't import here (platform-specific ones, e.g.
  // serialposix on Windows) are skipped silently and counted. Sequential — one spinner, one summary.
  const handleBlockifyPackage = async (rootModule) => {
    const root = (rootModule || '').trim();
    if (!root) return;
    setIsAbstracting(true);
    setAiThoughts([]);
    setLogs((prev) => [...prev, `[Blockify] Enumerating submodules of "${root}" (whole-package)…`]);
    try {
      let subs = [];
      let truncated = false, total = 0;
      try {
        const r = await fetch('/api/submodules', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ module: root }), signal: AbortSignal.timeout(35000),
        });
        if (r.ok) { const d = await r.json(); subs = (d && d.submodules) || []; truncated = !!(d && d.truncated); total = (d && d.total) || 0; }
        else { const d = await r.json().catch(() => null); setLogs((prev) => [...prev, `[Blockify] Couldn't list submodules of "${root}"${d && d.error ? ' — ' + d.error : ''}. Blockifying just the top module.`]); }
      } catch (_) { setLogs((prev) => [...prev, `[Blockify] Submodule listing unavailable — blockifying just the top module.`]); }
      if (!subs.length) subs = [root];
      setLogs((prev) => [...prev, `[Blockify] ${subs.length} submodule(s)${truncated ? ` of ${total} (capped)` : ''} — generating blocks (this can take a bit)…`]);
      let okCount = 0, skipped = 0, totalBlocks = 0, lastAlias = '';
      for (const sub of subs) {
        const data = await introspectModule(sub, { maxEntries: 3000, quiet: true });
        if (!data || !data.spec) { skipped++; continue; }
        // ADDITIVE (registerUsedLibrary, not registerFullLibrary): several submodules re-export the
        // same class (serial.rfc2217/threaded all expose `Serial`), whose method-receiver alias
        // collides — registerFullLibrary's removeModules would let a later submodule WIPE the earlier
        // top `serial` tab. Additive/first-wins keeps every submodule's unique API without clobbering.
        const { registered, constCount, propCount } = registerUsedLibrary(data.spec);
        if (registered.length || constCount || propCount) { okCount++; totalBlocks += registered.length + constCount + propCount; lastAlias = data.spec.module; }
        else skipped++;
      }
      refreshToolboxNow();
      setAiThoughts([
        `Whole-package Blockify of "${root}": ${okCount} module(s) → ${totalBlocks} block(s).`,
        skipped ? `${skipped} submodule(s) skipped (empty or not importable on this platform).` : `All submodules blockified.`,
        `Each submodule is its own toolbox tab (e.g. "${lastAlias || root}"). Add the matching import to run its blocks.`,
      ]);
      setLogs((prev) => [...prev, `[Blockify] ✅ Whole-package "${root}": ${okCount} tab(s), ${totalBlocks} block(s)${skipped ? `, ${skipped} skipped` : ''}.`]);
    } catch (err) {
      console.error(err);
      setLogs((prev) => [...prev, `[Blockify Error] ${err.message}`]);
    } finally {
      setIsAbstracting(false);
    }
  };

  // Blockify (full): introspect a module and put EVERY API call into its own Library palette tab.
  // No AI cost. Used by the Blockify field and automatically right after a `pip install`.
  // opts.recursive → blockify the whole package tree (delegates to handleBlockifyPackage).
  const handleBlockifyLibrary = async (moduleName, opts = {}) => {
    const mod = (moduleName || '').trim();
    if (!mod) return;
    if (opts.recursive) return handleBlockifyPackage(mod);
    setIsAbstracting(true);
    setAiThoughts([]);
    setLogs((prev) => [...prev, `[Blockify] Introspecting "${mod}" (real Python)...`]);
    try {
      // Same maxEntries as Convert's getSpec: a smaller default here would removeModules-delete
      // convert-registered symbols in the 1000..3000 range and never re-add them.
      const data = await introspectModule(mod, { maxEntries: 3000 });
      if (!data) return;
      const librarySpec = data.spec;
      const { mapped, registered, rejected, constCount, propCount } = registerFullLibrary(librarySpec);
      const extra = `${constCount ? ` + ${constCount} constant(s)` : ''}${propCount ? ` + ${propCount} property(ies)` : ''}`;
      setAiThoughts([
        `Introspected ${librarySpec.module} → ${librarySpec.entries.length} API entries${data.cached ? ' (cached)' : ''}.`,
        `Alias "${mapped.alias}" — add this import to run the blocks: ${mapped.importStmt}`,
        `Added ${registered.length} blocks (command + value forms)${extra} to the "${librarySpec.module}" palette tab.`,
      ]);
      const addedImport = (registered.length || constCount || propCount) ? ensureLibraryImportBlock(librarySpec.module, mapped.alias) : false;
      refreshToolboxNow();
      setLogs((prev) => [...prev, `[Blockify] ✅ ${registered.length} block(s)${extra} from "${mod}" added to the Library palette${rejected ? `, ${rejected} skipped` : ''}. ${addedImport ? 'Added import block' : 'Import'}: ${mapped.importStmt}`]);
      // Honest truncation notice: a huge library (numpy ≈ 3500 API entries) is capped, not silently
      // trimmed — tell the user how many were left out and how to get a focused subset.
      if (librarySpec.truncated && librarySpec.total) {
        setLogs((prev) => [...prev, `[Blockify] ⚠ "${mod}" has ${librarySpec.total} API entries — showing the first ${librarySpec.entries.length}. Use Curate to pick a focused subset.`]);
      }
    } catch (err) {
      console.error(err);
      setLogs((prev) => [...prev, `[Blockify Error] ${err.message}`]);
    } finally {
      setIsAbstracting(false);
    }
  };

  // Curate is a two-step, human-in-the-loop flow: (1) proposeCuration full-blockifies the library
  // (so every block stays available + the curated view's TYPES exist even on Cancel) and asks the AI
  // for a purpose-driven selection, then shows a PREVIEW — no ★ tab yet. (2) The user checks/unchecks
  // and edits the tab name / per-item groups, then Confirm builds the ★ tab (a lossless VIEW over the
  // already-registered types — check/uncheck only omits a type from the view, never changes lowering).
  // A monotonic token makes the newest propose win and prevents a stale in-flight result from
  // resurrecting a proposal after Confirm/Cancel/Regenerate.
  const proposeCuration = async (moduleName, purpose, level, opts = {}) => {
    const mod = (moduleName || '').trim();
    const want = (purpose || '').trim();
    const lvl = level || 'intermediate';
    if (!mod || !want) return;
    const reqId = ++curateReqRef.current;
    const reg = window.BlockPyLibRegistry;
    const imp = window.BlockPyLibImport;
    const heur = window.BlockPyCurateHeuristic;
    setIsCurating(true);
    setAiThoughts([]);
    setLogs((prev) => [...prev, opts.offline
      ? `[Curate] Introspecting "${mod}", then picking blocks for "${want}" without AI (heuristic)…`
      : `[Curate] Introspecting "${mod}", then asking the AI to pick blocks for: "${want}"…`]);
    try {
      const data = await introspectModule(mod, { maxEntries: 3000 });   // keep in step with Convert/Blockify
      if (!data || reqId !== curateReqRef.current) return;
      const librarySpec = data.spec;
      const { mapped } = registerFullLibrary(librarySpec);   // full tab + TYPES exist even if user Cancels
      refreshToolboxNow();                                    // show the full tab immediately, before the AI round-trip
      let cdata = null;
      // opts.offline forces the deterministic path (the "빠른 큐레이트" button). Otherwise try the AI;
      // if it's unavailable (no key / backend down / error / bad JSON), FALL BACK to the heuristic so
      // Curate still works offline instead of adding no tab at all.
      if (!opts.offline) {
        let cres = null;
        try {
          cres = await fetch('/api/abstract-library', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ spec: librarySpec, purpose: want, level: lvl }),
            signal: AbortSignal.timeout(90000),   // a wedged AI backend must not pin isCurating forever
          });
        } catch (_) { cres = null; }
        if (cres && cres.ok) { try { cdata = await cres.json(); } catch (_) { cdata = null; } }
        if (reqId !== curateReqRef.current) return;           // superseded while we awaited the AI
        if (!cdata || !cdata.success) {
          const why = !cres ? 'backend unreachable' : (!cres.ok ? `backend ${cres.status}` : 'AI unavailable');
          if (heur && typeof heur.curate === 'function') {
            setLogs((prev) => [...prev, `[Curate] ${why} — curating "${mod}" without AI (heuristic).`]);
            cdata = heur.curate(librarySpec, { purpose: want, level: lvl });
          }
        }
      } else if (heur && typeof heur.curate === 'function') {
        cdata = heur.curate(librarySpec, { purpose: want, level: lvl });
      }
      if (reqId !== curateReqRef.current) return;
      if (!cdata || !cdata.success) {
        setLogs((prev) => [...prev, `[Curate] Couldn't curate "${mod}" — the full tab is available; no curated tab added.`]);
        return;
      }
      // Resolve each AI ref to a REAL, registered block (one preview row per ref). realTitle is the
      // introspected title shown read-only (the block face); label editing is intentionally NOT offered
      // because the curated flyout renders the block from the spec, not from stored item labels.
      const selected = [];
      for (const sel of (cdata.selected || [])) {
        if (!sel || !sel.ref) continue;
        const probe = imp.curationToRegistrySpecs(librarySpec, [{ ref: sel.ref }]);
        const good = probe.specs.find((s) => reg.getLibSpec(reg.blockType(s)));
        if (!good) continue;
        selected.push({ ref: sel.ref, group: sel.group || '', tier: sel.tier === 'more' ? 'more' : 'core', realTitle: good.title, hasOutput: !!good.hasOutput, checked: true });
      }
      const macros = imp.macrosToRegistry(librarySpec, cdata.macros || []).map((m) => ({ ...m, checked: true }));
      setCurationProposal({ module: mod, purpose: want, level: cdata.level || lvl, librarySpec, alias: mapped.alias, importStmt: mapped.importStmt, selected, macros, thoughts: cdata.thoughts || [], dropped: cdata.dropped || {}, heuristic: !!cdata.heuristic });
      setAiThoughts([...(cdata.thoughts || []),
        `Proposed ${selected.length} block(s)${macros.length ? ` + ${macros.length} macro(s)` : ''} for "${want}" (${cdata.level || lvl}) — review below, then Confirm to create the ★ tab.`]);
    } catch (err) {
      console.error(err);
      setLogs((prev) => [...prev, `[Curate Error] ${err.message}`]);
    } finally {
      if (reqId === curateReqRef.current) setIsCurating(false);
    }
  };

  // Confirm: build the ★ tab from the user's EDITED proposal (checked entries + edited groups + tab
  // label). Re-filters to still-registered types (the library could have been removed mid-preview).
  const handleConfirmCuration = (edited) => {
    const p = curationProposal;
    if (!p) return;
    const reg = window.BlockPyLibRegistry;
    const imp = window.BlockPyLibImport;
    const chosen = (edited.entries || []).filter((e) => e.checked).map((e) => ({ ref: e.ref, group: (e.group || '').trim(), tier: e.tier === 'more' ? 'more' : 'core' }));
    const chosenMacros = (edited.macros || []).filter((m) => m.checked && m.block);
    curateReqRef.current++;                                   // any in-flight propose is now stale
    setCurationProposal(null);
    if (!chosen.length && !chosenMacros.length) { setLogs((prev) => [...prev, `[Curate] Nothing selected — the full "${p.module}" tab is available.`]); return; }
    const cur = imp.curationToRegistrySpecs(p.librarySpec, chosen);
    const items = [];
    for (const s of cur.specs) { const type = reg.blockType(s); if (reg.getLibSpec(type)) items.push({ type, label: s.title, group: s.group || '', tier: s.tier || 'core' }); }
    const lvlTag = { beginner: '초', intermediate: '중', advanced: '고' }[p.level] || '';
    const key = `${p.librarySpec.module} · ${p.purpose}${lvlTag ? ' · ' + lvlTag : ''}`.slice(0, 60);
    const defLabel = `${p.purpose}${lvlTag ? ` (${lvlTag})` : ''}`;
    const label = ((edited.tabLabel || '').trim() || defLabel).slice(0, 48);
    const res = reg.addCuration({ key, label, lib: p.librarySpec.module, items, macros: chosenMacros });
    if (!res.ok) { setLogs((prev) => [...prev, `[Curate] No usable blocks left — the full "${p.module}" tab is available.`]); refreshToolboxNow(); return; }
    ensureLibraryImportBlock(p.librarySpec.module, p.alias);
    refreshToolboxNow();
    setAiThoughts([`Created "★ ${label}" — ${items.length} block(s)${chosenMacros.length ? ` + ${chosenMacros.length} macro(s)` : ''}.`, `Add this import to run the blocks: ${p.importStmt}`]);
    setLogs((prev) => [...prev, `[Curate] ✅ New tab "★ ${label}" (${p.level}) — ${items.length} block(s)${chosenMacros.length ? ` + ${chosenMacros.length} macro(s)` : ''} for "${p.module}". The full library tab is still available.`]);
  };

  const handleCancelCuration = () => {
    curateReqRef.current++;                                   // invalidate any in-flight propose
    setCurationProposal(null);
    setIsCurating(false);                                     // clears ONLY the curate spinner (never Blockify's)
    setLogs((prev) => [...prev, `[Curate] Cancelled — the full library tab is still available.`]);
  };

  // Regenerate honors the LIVE 수준 selector (the radios stay clickable above the preview) —
  // regenerating with the OLD proposal's level silently discarded a changed selection.
  const handleRegenerateCuration = (level) => {
    const p = curationProposal;
    if (p) proposeCuration(p.module, p.purpose, level || p.level, { offline: p.heuristic });   // keep AI/heuristic mode
  };

  // User typing in the Python editor: update the mirror ref SYNCHRONOUSLY (React batches the state
  // update) so the startup-load clobber guard sees the edit the instant it happens.
  const handleUserCodeChange = (newCode) => {
    latestCodeRef.current = newCode;
    setCode(newCode);
  };

  const handleBlocklyCodeChange = (newCode) => {
    latestCodeRef.current = newCode;
    setCode(newCode);
    associatedPythonRef.current = newCode;
  };

  const handleBlocklySnapshotChange = (newSnapshot) => {
    blocklySnapshotRef.current = newSnapshot;
  };

  const handleSyncToBlocksClick = () => {
    syncCodeToBlocks(code);
  };

  const handleFormatCode = () => {
    const formatted = code.split('\n')
                          .map(line => line.trimEnd())
                          .join('\n')
                          .trim();
    setCode(formatted);
    setLogs(prev => [...prev, '[System] Cleaned trailing spaces and formatted editor lines.']);
  };

  // Theme Toggler — default is the Claude cream canvas; toggle flips to the in-brand dark navy.
  const toggleTheme = () => {
    setIsDarkTheme(!isDarkTheme);
    document.body.classList.toggle('theme-dark');
    
    // Refresh workspace layout safely
    if (workspaceRef.current) {
      const savedSnapshot = window.Blockly.serialization.workspaces.save(workspaceRef.current);
      workspaceRef.current.dispose();
      
      // Mount will naturally rerun inside BlocklyEditor once it is recreated/reloaded.
      setTimeout(() => {
        if (workspaceRef.current) {
          window.Blockly.serialization.workspaces.load(savedSnapshot, workspaceRef.current);
        }
      }, 50);
    }
  };

  // Phase 4 slice 4: the preview pane reflects the REAL IR desugar (desugaredPreview, computed by
  // the effect above) — the SAME pass "Auto Desugar" applies to blocks — not the legacy text
  // heuristic. (desugarer.js stays loaded for the server endpoints; just not used here.)
  const desugarChanged = !!desugaredPreview && desugaredPreview.trim() !== code.trim();
  const explanationHtml = desugarChanged
    ? 'Desugared (IR-level): comprehensions / ternaries / chained comparisons in provably-safe positions were rewritten to loops / conditionals / booleans; lazy or unsafe sugar is preserved.'
    : 'No desugarable sugar in safe positions — the desugared output matches the source.';

  return (
    <div className="harness-container">
      {/* Header bar removed — Auto Desugar + theme controls relocated into the
          AST Parser Tree tab to reclaim full-height vertical space. */}

      {/* Main Dashboard Layout grid */}
      <main className="dashboard-grid">
        {/* Left Side Panels: Stage, console, scopes, abstractions */}
        <section className="left-panel">
          {/* Unified left pane — Stage + watches + logs + gray blocks + AI/OpenCV, all as tabs */}
          <div className="tab-card">
            <div className="tab-header">
              <button
                id="tab-btn-files"
                className={`tab-btn ${activeAuxTab === 'files' ? 'active' : ''}`}
                onClick={() => setActiveAuxTab('files')}
              >
                Files
              </button>
              <button
                id="tab-btn-variables"
                className={`tab-btn ${activeAuxTab === 'variables' ? 'active' : ''}`}
                onClick={() => setActiveAuxTab('variables')}
              >
                Variable
              </button>
              <button
                id="tab-btn-logs"
                className={`tab-btn ${activeAuxTab === 'logs' ? 'active' : ''}`}
                onClick={() => setActiveAuxTab('logs')}
              >
                Terminal
              </button>
              <button
                id="tab-btn-gray"
                className={`tab-btn ${activeAuxTab === 'gray' ? 'active' : ''}`}
                onClick={() => { setActiveAuxTab('gray'); refreshGrayBlocks(); }}
                title="Parts left as gray (raw) blocks that could not convert to dedicated blocks"
              >
                Logs{grayBlocks.length ? ` (${grayBlocks.length})` : ''}
              </button>
              <button
                id="tab-btn-library"
                className={`tab-btn ${activeAuxTab === 'ai' ? 'active' : ''}`}
                onClick={() => setActiveAuxTab('ai')}
              >
                AI
              </button>
              <button
                id="tab-btn-robot"
                className={`tab-btn ${activeAuxTab === 'robot' ? 'active' : ''}`}
                onClick={() => setActiveAuxTab('robot')}
              >
                Robot
              </button>
              <button
                id="tab-btn-tm"
                className={`tab-btn ${activeAuxTab === 'tm' ? 'active' : ''}`}
                onClick={() => setActiveAuxTab('tm')}
              >
                TM
              </button>
            </div>
            <div className="tab-content-wrapper">
              {activeAuxTab === 'files' && (
                <FileExplorer
                  activeFile={activeFile}
                  onOpenFile={openFile}
                  onChanged={() => setFsReload((n) => n + 1)}
                  reloadToken={fsReload}
                />
              )}
              {activeAuxTab === 'variables' && (
                <VariableWatch variables={variables} />
              )}
              {activeAuxTab === 'logs' && (
                <ConsoleLogs
                  logs={logs}
                  onClearConsole={() => setLogs([])}
                />
              )}
              {activeAuxTab === 'ai' && (
                <div className="ai-tab-scroll">
                  <LibraryManager
                    onBlockify={handleBlockifyLibrary}
                    onCurate={proposeCuration}
                    curationProposal={curationProposal}
                    onConfirmCuration={handleConfirmCuration}
                    onCancelCuration={handleCancelCuration}
                    onRegenerateCuration={handleRegenerateCuration}
                    onRemoveLibrary={handleRemoveLibrary}
                    onClearLibraries={handleClearLibraries}
                    installedBlocks={installedBlocks}
                    aiThoughts={aiThoughts}
                    isAbstracting={isAbstracting}
                    isCurating={isCurating}
                    pipPkg={pipPkg}
                    onPipPkgChange={setPipPkg}
                    onPipInstallShell={handlePipInstallShell}
                  />
                </div>
              )}
              {activeAuxTab === 'robot' && (
                <div className="robot-tab-scroll" style={{ overflowY: 'auto', height: '100%' }}>
                  <RobotConnect />
                  <RobotCalibrate />
                </div>
              )}
              {activeAuxTab === 'tm' && (
                <div className="tm-tab-scroll" style={{ overflowY: 'auto', height: '100%' }}>
                  <TeachableMachine />
                </div>
              )}
              {activeAuxTab === 'gray' && (
                <div className="gray-blocks-panel">
                  <div className="gray-blocks-head">
                    <span>Gray (unconverted) blocks: <b>{grayBlocks.length}</b></span>
                    <button className="btn btn-secondary btn-sm" onClick={refreshGrayBlocks}>
                      <i className="fa-solid fa-rotate"></i> Refresh
                    </button>
                  </div>
                  {grayBlocks.length === 0 ? (
                    <div className="gray-blocks-empty">
                      No unconverted parts. Check here after Convert.
                    </div>
                  ) : (
                    <ul className="gray-blocks-list">
                      {grayBlocks.map((g) => (
                        <li key={g.id} className="gray-block-item" onClick={() => jumpToGray(g.id)} title="Click to jump to the block">
                          <span className="gray-block-kind">{g.kind}</span>
                          <code className="gray-block-text">{g.text}</code>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Right Side Panels: Interactive Editors, desugaring analysis */}
        <section className="right-panel">
          <div className="editor-tab-card" style={{ flex: 1, height: '100%' }}>
            <div className="editor-tab-header">
              <button 
                id="tab-btn-blockly"
                className={`tab-btn ${activeEditorTab === 'blockly' ? 'active' : ''}`}
                onClick={() => setActiveEditorTab('blockly')}
              >
                <i className="fa-solid fa-cubes"></i> Visual Blocks Workspace
              </button>
              <button 
                id="tab-btn-python"
                className={`tab-btn ${activeEditorTab === 'python' ? 'active' : ''}`}
                onClick={() => setActiveEditorTab('python')}
              >
                <i className="fa-brands fa-python"></i> Python Source Editor
              </button>
              <button 
                id="tab-btn-desugar"
                className={`tab-btn ${activeEditorTab === 'desugar' ? 'active' : ''}`}
                onClick={() => setActiveEditorTab('desugar')}
              >
                <i className="fa-solid fa-wand-magic-sparkles"></i> Desugared Code Normalizer
              </button>
              <button
                id="tab-btn-ast"
                className={`tab-btn ${activeEditorTab === 'ast' ? 'active' : ''}`}
                onClick={() => setActiveEditorTab('ast')}
              >
                <i className="fa-solid fa-diagram-project"></i> AST Parser Tree
              </button>
              {/* Active file + Save + Run (real shell) + image upload */}
              <div className="editor-tab-actions">
                <span className="active-file-chip" title={activeFile || 'No file open — open one from the Files tab'}>
                  <i className="fa-solid fa-file-code"></i>
                  {activeFile || 'untitled'}
                </span>
                <button
                  className="btn btn-secondary btn-sm"
                  id="btn-save-file"
                  onClick={() => saveActiveFile()}
                  disabled={!activeFile}
                  title="Save the open file (Ctrl+S)"
                >
                  <i className="fa-solid fa-floppy-disk"></i> Save
                </button>
                <button
                  className="btn btn-primary btn-sm"
                  id="btn-run-shell"
                  onClick={handleRunShell}
                  disabled={isRunning}
                  title="Run for real in local Python (shell). Files resolve against the workspace folder."
                >
                  <i className="fa-solid fa-play"></i> Run
                </button>
                <button
                  className="btn btn-action stop btn-sm"
                  id="btn-stop-shell"
                  onClick={handleStopExecution}
                  disabled={!isRunning}
                  title="Stop the running program"
                >
                  <i className="fa-solid fa-stop"></i>
                </button>
                <label className="btn btn-secondary btn-sm" htmlFor="cv-image-upload" style={{ cursor: 'pointer' }}>
                  <i className="fa-solid fa-upload"></i> Image
                  <input
                    id="cv-image-upload"
                    type="file"
                    accept="image/*"
                    style={{ display: 'none' }}
                    onChange={(e) => handleImageUpload(e.target.files && e.target.files[0])}
                  />
                </label>
              </div>
            </div>
            
            <div className="editor-content-wrapper" style={{ height: 'calc(100% - 48px)', position: 'relative' }}>
              {isConverting && (
                <div className="convert-overlay" role="status" aria-live="polite">
                  <div className="convert-spinner" />
                  <div className="convert-overlay-text">Converting…<span>introspecting libraries &amp; building blocks</span></div>
                </div>
              )}
              <div style={{ display: activeEditorTab === 'blockly' ? 'block' : 'none', height: '100%' }}>
                <BlocklyEditor
                  onCodeChange={handleBlocklyCodeChange}
                  onSnapshotChange={handleBlocklySnapshotChange}
                  initialSnapshot={blocklySnapshotRef.current}
                  isSyncingFromCode={isSyncingFromCodeRef}
                  workspaceRef={workspaceRef}
                />
              </div>
              <div style={{ display: activeEditorTab === 'python' ? 'block' : 'none', height: '100%' }}>
                <PythonEditor
                  code={code}
                  onCodeChange={handleUserCodeChange}
                  onSyncToBlocks={handleSyncToBlocksClick}
                  syntaxStatus={syntaxStatus}
                  highlightedLine={highlightedLine}
                  onLoadExample={(sn) => { setCode(sn.code); setShouldDesugar(sn.desugar); }}
                />
              </div>
              <div style={{ display: activeEditorTab === 'desugar' ? 'block' : 'none', height: '100%' }}>
                <div className="tools-content-wrapper" style={{ height: '100%', overflow: 'auto' }}>
                  <div className="desugar-preview-pane">
                    <div className="desugar-split">
                      <div className="code-block-box">
                        <div className="box-title">Original Advanced Syntax</div>
                        <pre id="sugar-original-code">{code}</pre>
                      </div>
                      <div className="code-block-box">
                        <div className="box-title">Desugared Normalized Code</div>
                        <pre id="desugared-target-code">
                          {desugaredPreview || '# No changes required.'}
                        </pre>
                      </div>
                    </div>
                    <div id="desugar-explanation-text" className="explanation-alert">
                      <i className="fa-solid fa-circle-info"></i> {explanationHtml}
                    </div>
                  </div>
                </div>
              </div>
              <div style={{ display: activeEditorTab === 'ast' ? 'block' : 'none', height: '100%' }}>
                <div className="tools-content-wrapper" style={{ height: '100%', overflow: 'auto' }}>
                  <div className="ast-controls-row">
                    <label className="toggle-group" htmlFor="toggle-desugar">
                      <input
                        type="checkbox"
                        id="toggle-desugar"
                        checked={shouldDesugar}
                        onChange={(e) => setShouldDesugar(e.target.checked)}
                      />
                      <span>Auto Desugar</span>
                    </label>
                    <button
                      id="theme-toggle"
                      className="btn btn-secondary btn-icon-only theme-btn"
                      onClick={toggleTheme}
                      title="Toggle theme styling"
                    >
                      <i className={isDarkTheme ? "fa-solid fa-moon" : "fa-solid fa-sun"}></i>
                    </button>
                  </div>
                  <ASTTreeView
                    code={code}
                    onHoverLine={(line) => setHighlightedLine(line)}
                    onLeaveLine={() => setHighlightedLine(null)}
                  />
                </div>
              </div>
            </div>
          </div>
        </section>
      </main>

      {imagePreview && (
        <div className="img-preview-overlay" onClick={() => setImagePreview(null)}>
          <div className="img-preview-box" onClick={(e) => e.stopPropagation()}>
            <div className="img-preview-head">
              <span><i className="fa-solid fa-image"></i> {imagePreview.name}</span>
              <button className="btn btn-secondary btn-xs" onClick={() => setImagePreview(null)}>✕</button>
            </div>
            <img src={imagePreview.url} alt={imagePreview.name} />
          </div>
        </div>
      )}
    </div>
  );
}

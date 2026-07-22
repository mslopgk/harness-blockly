require('dotenv').config();
const express = require('express');
const Anthropic = require('@anthropic-ai/sdk');
const { spawn } = require('child_process');
const os = require('os');
const fs = require('fs');
const path = require('path');
const { WebSocketServer } = require('ws');


const app = express();
// This server exposes LOCAL-ONLY, unauthenticated, powerful endpoints (run arbitrary Python, pip,
// read/write files). It must never be reachable cross-origin or off-box. Instead of wide-open CORS,
// require the Host header to be loopback — blocks DNS-rebinding (Host=attacker.com) and, together with
// the 127.0.0.1 bind below, direct LAN access (Host=<lan-ip>). The renderer is same-origin (packaged:
// 127.0.0.1:<port>; dev: Vite proxies with changeOrigin so Host=localhost), so no CORS header is needed.
const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]']);
function isLoopbackHost(req) {
  const host = String(req.headers.host || '').replace(/:\d+$/, '').toLowerCase();
  return LOOPBACK_HOSTS.has(host);
}
app.use((req, res, next) => {
  if (isLoopbackHost(req)) return next();
  return res.status(403).json({ error: 'forbidden: local-only server' });
});
app.use(express.json({ limit: '30mb' })); // allow base64 image uploads

// ─── Static frontend serving (Electron / packaged desktop build) ────────────────
// In dev the Vite server hosts the frontend and proxies /api here. In the packaged
// Electron app there is no Vite: this server hosts the built `dist/` itself so the
// renderer loads from http://127.0.0.1:<port> on the SAME origin as /api. The COOP/COEP
// headers mirror vite.config.js — they are REQUIRED for the SharedArrayBuffer that powers
// Pyodide's interrupt buffer (Stop button) and must be present on every document/asset.
const STATIC_DIR = process.env.BLOCKPY_STATIC_DIR;
if (STATIC_DIR && fs.existsSync(STATIC_DIR)) {
  app.use((req, res, next) => {
    res.setHeader('Cross-Origin-Opener-Policy', 'same-origin');
    res.setHeader('Cross-Origin-Embedder-Policy', 'credentialless');
    next();
  });
  app.use(express.static(STATIC_DIR));
  console.log(`🖥️  Serving built frontend from: ${STATIC_DIR}`);
}

// Workspace directory on real disk — the project root the user sees in the file explorer.
// It is the working directory for shell-run Python, so cv2.imread('name.jpg'), open('data.txt'),
// cv2.imwrite('out.png') etc. all resolve against (and appear in) this folder. Uploaded images
// land here too. Override with BLOCKPY_WORKSPACE; defaults to ~/BlockPyWorkspace.
const WORKSPACE_DIR = process.env.BLOCKPY_WORKSPACE || path.join(os.homedir(), 'BlockPyWorkspace');
try { fs.mkdirSync(WORKSPACE_DIR, { recursive: true }); } catch (_) {}
// MEDIA_DIR kept as an alias for existing call sites (uploads, seed images, run cwd).
const MEDIA_DIR = WORKSPACE_DIR;

// Resolve a client-supplied relative path INSIDE the workspace, rejecting traversal/absolute
// escapes. Returns the absolute path, or null if it would leave the workspace.
function safeResolve(relPath) {
  const rel = String(relPath == null ? '' : relPath).replace(/\\/g, '/').replace(/^\/+/, '');
  const abs = path.resolve(WORKSPACE_DIR, rel);
  const root = path.resolve(WORKSPACE_DIR);
  if (abs !== root && !abs.startsWith(root + path.sep)) return null;
  return abs;
}

const PYTHON_CMD = process.env.PYTHON_CMD || (process.platform === 'win32' ? 'python' : 'python3');

// Kill a spawned python AND anything it spawned. On win32 child.kill() only signals the direct
// process (grandchildren survive), so take down the whole tree with taskkill; elsewhere SIGKILL.
function killTree(child) {
  if (!child || child.killed || child.pid == null) return;
  try {
    if (process.platform === 'win32') {
      // no-op 'error' handler: an unhandled ChildProcess 'error' would itself crash the process
      spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], { stdio: 'ignore' })
        .on('error', () => { try { child.kill(); } catch (_) {} });
    } else {
      child.kill('SIGKILL');
    }
  } catch (_) {
    try { child.kill(); } catch (_) {}
  }
}

// ─── blockpy-gen introspection (ESM, lazy-imported into this CJS server) ───────
// /api/blockify turns an importable module into a LibrarySpec by importing it in a python
// subprocess (executes its top-level code) — the SAME trust level the app already grants
// /api/run-python and /api/pip-install. BLOCKIFY_ALLOW (comma-separated) optionally restricts
// which modules may be introspected; unset = allow any (local single-user posture).
const { pathToFileURL } = require('url');
// In the packaged Electron app __dirname lives inside app.asar, but blockpy-gen is asarUnpack'd
// (dynamic import()/spawn of files inside an asar fails). Redirect to the on-disk unpacked copy.
// In dev __dirname is the repo root, so this is a no-op.
function genBase() {
  let base = __dirname;
  if (base.includes('app.asar') && !base.includes('app.asar.unpacked')) {
    base = base.replace('app.asar', 'app.asar.unpacked');
  }
  return base;
}
let _introspectPromise = null;
function getIntrospect() {
  if (!_introspectPromise) {
    const url = pathToFileURL(path.join(genBase(), 'blockpy-gen', 'src', 'introspect', 'introspect.js')).href;
    // On rejection, clear the cache and rethrow — otherwise one transient EBUSY/EPERM (antivirus
    // scan, asar extraction race) would brick /api/blockify until the app restarts.
    _introspectPromise = import(url).then((m) => m.introspectModule).catch((e) => {
      _introspectPromise = null;
      throw e;
    });
  }
  return _introspectPromise;
}
const BLOCKIFY_ALLOW = (process.env.BLOCKIFY_ALLOW || '').split(',').map((s) => s.trim()).filter(Boolean);
const _blockifyCache = new Map();
// Accepts a dotted import path (numpy, PIL.Image) OR a pip distribution name with dashes
// (opencv-python, scikit-learn) — _inspect.py resolves a distribution name to its real import.
const MODULE_PATH_RE = /^[A-Za-z0-9_]+([.-][A-Za-z0-9_]+)*$/;
if (BLOCKIFY_ALLOW.length === 0) {
  console.warn('[blockify] No BLOCKIFY_ALLOW set — /api/blockify will import ANY requested module (executes top-level code). Local single-user use only; set BLOCKIFY_ALLOW=mod1,mod2 to restrict.');
}

// Seed a synthetic sample image into the demo filenames using the real local cv2, so
// OpenCV examples produce output in shell mode even before any upload (best-effort).
function seedSampleImages() {
  const py = [
    'import cv2, numpy as np, os',
    `d = r"${MEDIA_DIR.replace(/\\/g, '\\\\')}"`,
    'img = np.full((240,320,3), 30, np.uint8)',
    'cv2.rectangle(img,(40,50),(150,170),(0,0,255),-1)',
    'cv2.circle(img,(230,110),55,(0,200,0),-1)',
    'cv2.putText(img,"BlockPy",(30,215),cv2.FONT_HERSHEY_SIMPLEX,1.0,(255,255,255),2)',
    'for f in ["sample.jpg"]:',
    '    p=os.path.join(d,f)',
    '    if not os.path.exists(p): cv2.imwrite(p,img)',
  ].join('\n');
  const f = path.join(os.tmpdir(), `blockpy_seed_${Date.now()}.py`);
  try {
    fs.writeFileSync(f, py, 'utf8');
    const c = spawn(PYTHON_CMD, [f], { env: process.env });
    c.on('close', () => { try { fs.unlinkSync(f); } catch (_) {} });
    c.on('error', () => { try { fs.unlinkSync(f); } catch (_) {} });
  } catch (_) {}
}

// Seed a friendly starter file the first time the workspace is empty, so the explorer
// isn't blank on first run. Never overwrites existing user files.
function seedStarterFile() {
  try {
    const f = path.join(WORKSPACE_DIR, 'main.py');
    if (fs.existsSync(f)) return;
    const hasAny = fs.readdirSync(WORKSPACE_DIR).some((n) => n.endsWith('.py'));
    if (hasAny) return;
    fs.writeFileSync(f, [
      '# Welcome to BlockPy! This file lives in your workspace folder.',
      '# Files you read/write run from here, e.g. cv2.imread("sample.jpg").',
      '',
      'print("Hello from BlockPy")',
      '',
      'for i in range(3):',
      '    print("count", i)',
      '',
    ].join('\n'), 'utf8');
  } catch (_) {}
}

// ─── MiniMax API Key Pool (Round-Robin) ───────────────────────────────────────
// Keys come from (in order): the dev .env (MINIMAX1~4), a writable per-machine config the in-app
// Settings panel saves (BLOCKPY_CONFIG, set by Electron to userData), and an optional read-only
// config you can pre-seed next to the .exe (BLOCKPY_CONFIG_RO). NOTHING is baked into the build —
// a distributed .exe ships with zero keys, so a key is never extractable from the binary.
let MINIMAX_KEYS = [];

// The single writable config the Settings panel POSTs to. Electron points this at userData; dev
// falls back to a gitignored file in the cwd.
function primaryConfigPath() {
  return process.env.BLOCKPY_CONFIG || path.join(process.cwd(), 'blockpy-config.json');
}

// All config files we READ keys from (writable primary + optional alongside-exe read-only seed).
function configPaths() {
  const out = [primaryConfigPath()];
  if (process.env.BLOCKPY_CONFIG_RO) out.push(process.env.BLOCKPY_CONFIG_RO);
  return out;
}

// A config file is JSON: { "keys": ["sk-...", ...] } (also accepts MINIMAX1..4 keys). Missing/bad → [].
function keysFromFile(p) {
  try {
    if (!p || !fs.existsSync(p)) return [];
    const raw = JSON.parse(fs.readFileSync(p, 'utf8'));
    if (Array.isArray(raw.keys)) return raw.keys.filter(Boolean);
    return [raw.MINIMAX1, raw.MINIMAX2, raw.MINIMAX3, raw.MINIMAX4].filter(Boolean);
  } catch (_) { return []; }
}

let keyIndex = 0;
function loadKeys() {
  const envKeys = [process.env.MINIMAX1, process.env.MINIMAX2, process.env.MINIMAX3, process.env.MINIMAX4].filter(Boolean);
  const fileKeys = configPaths().flatMap(keysFromFile);
  MINIMAX_KEYS = [...new Set([...envKeys, ...fileKeys].map((k) => String(k).trim()).filter(Boolean))];
  keyIndex = 0;
  return MINIMAX_KEYS;
}
loadKeys();

if (MINIMAX_KEYS.length === 0) {
  console.error('[MiniMax] ⚠️  No API keys yet (env/.env or config). Set one in the app Settings — AI endpoints stay 503 until then.');
}

function getNextKey() {
  const key = MINIMAX_KEYS[keyIndex % MINIMAX_KEYS.length];
  keyIndex++;
  return key;
}

// Build an Anthropic client pointed at MiniMax's Anthropic-compatible endpoint
function createMiniMaxClient() {
  return new Anthropic({
    apiKey: getNextKey(),
    baseURL: 'https://api.minimax.io/anthropic',
  });
}

const MINIMAX_MODEL = 'MiniMax-M2.7';

// ─── Helper: stream thinking + text blocks from MiniMax response ─────────────
async function callMiniMax(systemPrompt, userContent, opts = {}) {
  const client = createMiniMaxClient();
  const message = await client.messages.create({
    model: MINIMAX_MODEL,
    max_tokens: opts.maxTokens || 2048,
    system: systemPrompt,
    messages: [
      {
        role: 'user',
        content: [{ type: 'text', text: userContent }]
      }
    ]
  });

  let thinkingText = '';
  let responseText = '';

  for (const block of message.content) {
    if (block.type === 'thinking') thinkingText += block.thinking;
    else if (block.type === 'text') responseText += block.text;
  }

  return { thinkingText, responseText };
}


// ─── AI key config (in-app Settings) ─────────────────────────────────────────
// Local-only (the server binds 127.0.0.1). GET returns STATUS ONLY — raw keys never leave the box,
// just a masked preview. POST saves keys to the per-machine config file and reloads the pool.
app.get('/api/ai-config', (req, res) => {
  res.json({
    configured: MINIMAX_KEYS.length > 0,
    count: MINIMAX_KEYS.length,
    masked: MINIMAX_KEYS.map((k) => (k.length > 8 ? `${k.slice(0, 4)}…${k.slice(-4)}` : '••••')),
    configPath: primaryConfigPath(),
    model: MINIMAX_MODEL,
  });
});

app.post('/api/ai-config', (req, res) => {
  const { keys, key } = req.body || {};
  let list = Array.isArray(keys) ? keys : (key != null ? [key] : null);
  if (!list) return res.status(400).json({ error: 'provide {keys:[...]} or {key:"..."}' });
  list = list.map((s) => String(s).trim()).filter(Boolean).slice(0, 8);   // cap the pool
  const p = primaryConfigPath();
  try {
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, JSON.stringify({ keys: list }, null, 2), 'utf8');
  } catch (e) {
    return res.status(500).json({ error: `could not write config: ${e.message}` });
  }
  loadKeys();
  res.json({ success: true, configured: MINIMAX_KEYS.length > 0, count: MINIMAX_KEYS.length, configPath: p });
});



// ─── 3.5 Blockify: introspection-based library blocks (no AI cost) ────────────
// Real-API ground truth: imports the module in a python subprocess and returns a LibrarySpec
// the frontend maps to libRegistry blocks (src/utils/libImport.js). No MiniMax involved.
app.post('/api/blockify', async (req, res) => {
  const moduleName = ((req.body && req.body.module) || '').trim();
  const includePrivate = !!(req.body && req.body.includePrivate);
  const maxEntries = Math.min(Number((req.body && req.body.maxEntries) || 1000) || 1000, 3000);
  if (!moduleName) return res.status(400).json({ error: 'module is required' });
  if (!MODULE_PATH_RE.test(moduleName)) return res.status(400).json({ error: 'invalid module name' });
  if (BLOCKIFY_ALLOW.length && !BLOCKIFY_ALLOW.includes(moduleName)) {
    return res.status(403).json({ error: `module '${moduleName}' not in BLOCKIFY_ALLOW` });
  }
  const key = `${moduleName}|${includePrivate ? 'p' : ''}|${maxEntries}`;
  if (!(req.body && req.body.refresh) && _blockifyCache.has(key)) {
    return res.json({ success: true, cached: true, spec: _blockifyCache.get(key) });
  }
  try {
    const introspect = await getIntrospect();
    const spec = await introspect(moduleName, { python: PYTHON_CMD, includePrivate, maxEntries });
    _blockifyCache.set(key, spec);
    res.json({ success: true, cached: false, spec });
  } catch (e) {
    console.error('[/api/blockify]', e.message);
    const msg = String(e.message || e);
    // _inspect.py exits 1 with a "ModuleNotFoundError: No module named '<x>'" traceback on stderr
    // for a missing module, and introspect.js folds that stderr into the rejection message. 404 lets
    // the frontend cache "definitively not installed"; anything else stays 500 (transient/broken).
    if (/ModuleNotFoundError|No module named/i.test(msg)) {
      return res.status(404).json({ success: false, notFound: true, error: msg });
    }
    res.status(500).json({ success: false, error: msg });
  }
});

// Installed DIRECT dependencies of a distribution, mapped to import names (pyserial->serial).
// Lets a `pip install <pkg>` also blockify what it pulled in. Metadata only — no import/AI.
app.post('/api/deps', (req, res) => {
  const moduleName = ((req.body && req.body.module) || '').trim();
  if (!moduleName) return res.status(400).json({ error: 'module is required' });
  if (!MODULE_PATH_RE.test(moduleName)) return res.status(400).json({ error: 'invalid module name' });
  const f = path.join(genBase(), 'blockpy-gen', 'src', 'introspect', '_deps.py');
  let child;
  // stdin 'ignore' (the script never reads it); UTF-8 env so metadata survives cp949 consoles.
  try {
    child = spawn(PYTHON_CMD, [f, moduleName], {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
    });
  }
  catch (e) { return res.status(500).json({ error: String(e.message || e) }); }
  // Settle-once guard: a failed spawn fires BOTH 'error' AND 'close', and the timeout races with
  // 'close' — replying twice throws ERR_HTTP_HEADERS_SENT and kills the whole (Electron) process.
  let responded = false;
  let timer = null;
  const reply = (status, body) => {
    if (responded) return;
    responded = true;
    clearTimeout(timer);
    res.status(status).json(body);
  };
  timer = setTimeout(() => { killTree(child); reply(500, { error: 'deps lookup timed out (30s)' }); }, 30000);
  let out = '', err = '';
  child.stdout.on('data', (d) => { out += d; });
  child.stderr.on('data', (d) => { err += d; });
  child.on('error', (e) => reply(500, { error: String(e.message || e) }));
  child.on('close', (code) => {
    if (code !== 0) return reply(500, { error: err.trim() || ('exit ' + code) });
    try { reply(200, { success: true, ...JSON.parse(out) }); }
    catch (e) { reply(500, { error: 'bad deps output: ' + e.message }); }
  });
});

// Importable SUBMODULES of a package (serial -> serial.tools.list_ports, serial.threaded, ...), so
// the app can OPT IN to blockifying a whole package tree. Enumeration only NAMES leaf modules; the
// frontend introspects each. Metadata + pkgutil only — no arbitrary import beyond sub-PACKAGE __init__.
app.post('/api/submodules', (req, res) => {
  const moduleName = ((req.body && req.body.module) || '').trim();
  const max = Math.min(Number((req.body && req.body.max) || 60) || 60, 300);
  if (!moduleName) return res.status(400).json({ error: 'module is required' });
  if (!MODULE_PATH_RE.test(moduleName)) return res.status(400).json({ error: 'invalid module name' });
  const f = path.join(genBase(), 'blockpy-gen', 'src', 'introspect', '_submodules.py');
  let child;
  try {
    child = spawn(PYTHON_CMD, [f, moduleName, `--max=${max}`], {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' },
    });
  }
  catch (e) { return res.status(500).json({ error: String(e.message || e) }); }
  let responded = false;
  let timer = null;
  const reply = (status, body) => {
    if (responded) return;
    responded = true;
    clearTimeout(timer);
    res.status(status).json(body);
  };
  timer = setTimeout(() => { killTree(child); reply(500, { error: 'submodule enumeration timed out (30s)' }); }, 30000);
  let out = '', err = '';
  child.stdout.on('data', (d) => { out += d; });
  child.stderr.on('data', (d) => { err += d; });
  child.on('error', (e) => reply(500, { error: String(e.message || e) }));
  child.on('close', (code) => {
    if (code !== 0) return reply(500, { error: err.trim() || ('exit ' + code) });
    try { reply(200, { success: true, ...JSON.parse(out) }); }
    catch (e) { reply(500, { error: 'bad submodules output: ' + e.message }); }
  });
});

// Tier-2 receiver-type oracle: Jedi infers the class of each attribute receiver in the code (static,
// no execution). Feeds the DISPLAY layer only (precise property colouring + registering the resolved
// class), so a wrong/absent inference is harmless. Degrades to {available:false} without Jedi.
app.post('/api/infer-types', (req, res) => {
  const code = (req.body && req.body.code) || '';
  if (typeof code !== 'string' || !code.trim()) return res.json({ available: true, vars: {} });
  const f = path.join(genBase(), 'blockpy-gen', 'src', 'introspect', '_infertypes.py');
  let child;
  // stdin stays a pipe — _infertypes.py reads the code from it (written + ended below). UTF-8 env
  // so Korean source doesn't mojibake through cp949 and silently empty the Jedi oracle.
  try { child = spawn(PYTHON_CMD, [f], { env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' } }); }
  catch (e) { return res.json({ available: false, vars: {} }); }
  // Settle-once guard (see /api/deps): 'error' + 'close' both fire on a failed spawn, and the
  // timeout races with 'close' — exactly one JSON reply ever goes out.
  let responded = false;
  let timer = null;
  const reply = (body) => {
    if (responded) return;
    responded = true;
    clearTimeout(timer);
    res.json(body);
  };
  timer = setTimeout(() => { killTree(child); reply({ available: false, vars: {} }); }, 15000);
  let out = '';
  child.stdout.on('data', (d) => { out += d; });
  child.stderr.on('data', () => {}); // drain — an undrained pipe deadlocks the child past ~64KB of warnings
  child.on('error', () => reply({ available: false, vars: {} }));
  child.on('close', () => { try { reply(JSON.parse(out)); } catch (_) { reply({ available: false, vars: {} }); } });
  try { child.stdin.write(code); child.stdin.end(); } catch (_) { /* child died — 'close' handles it */ }
});

// ─── 3.6 Abstract library by purpose (LLM curation + macros, grounded) ────────
// Given an introspected LibrarySpec (ground truth) + a purpose, MiniMax SELECTS a relevant
// subset, GROUPS + RELABELS it, and proposes composite MACROS — but only references real
// entries; the server drops any hallucinated ref so signatures always come from introspection.
function describeSpecEntry(spec, e) {
  const ps = (e.params || []).map((p) => {
    const star = p.kind === 'vararg' ? '*' : p.kind === 'kwarg' ? '**' : '';
    return star + p.name + (p.hasDefault ? '=…' : '');
  }).join(', ');
  const qn = e.qualName || (e.kind === 'method' ? `${spec.module}.${e.owner}.${e.name}` : `${spec.module}.${e.name}`);
  const kind = e.kind === 'method' ? 'method' : e.kind === 'class' ? 'class' : 'func';
  return `- [${kind}] ${qn}(${ps}) -> ${e.returns === false ? 'stmt' : 'value'}`;
}

// School-level abstraction knob: same library, different granularity (초=angle-only, 고=PWM/timing).
const CURATE_LEVELS = {
  beginner: { cap: 8, guide:
    'AUDIENCE: elementary students (초등). Pick the FEWEST, most INTUITIVE HIGH-LEVEL operations (e.g. "move to angle", not "set PWM pulse width"). HIDE low-level/timing/register/config/tuning operations. Prefer wrapping multi-step workflows into MACROS so one block does a whole task. Labels: plain everyday words, no jargon.' },
  intermediate: { cap: 16, guide:
    'AUDIENCE: middle-school students (중등). Pick common operations with a few key parameters exposed. A couple of macros for frequent workflows. Labels: clear, lightly technical.' },
  advanced: { cap: 34, guide:
    'AUDIENCE: high-school / advanced students (고등). Expose the FULLER API INCLUDING lower-level control (timing/PWM/config/tuning parameters). FEWER macros — prefer primitives so learners compose themselves. Labels: precise, technical.' },
};
function normLevel(x) {
  const s = String(x || '').toLowerCase();
  if (s === '초' || s.startsWith('beg') || s.startsWith('element')) return 'beginner';
  if (s === '고' || s.startsWith('adv') || s.startsWith('high')) return 'advanced';
  return 'intermediate';
}
// The representable arity of an entry (for deterministic macro checking). Methods carry the receiver
// as the macro step's first arg, so callable args = step.args minus the receiver.
function entryArity(e) {
  const ps = e.params || [];
  const pos = ps.filter((p) => p.kind === 'positional' || p.kind === 'keyword');
  return { isMethod: e.kind === 'method', required: pos.filter((p) => !p.hasDefault).length, total: pos.length, vararg: ps.some((p) => p.kind === 'vararg') };
}

app.post('/api/abstract-library', async (req, res) => {
  const { spec, purpose, max, level } = req.body || {};
  if (!spec || typeof spec.module !== 'string' || !Array.isArray(spec.entries)) {
    return res.status(400).json({ error: 'a LibrarySpec {module, entries[]} is required (call /api/blockify first)' });
  }
  if (!purpose || !String(purpose).trim()) return res.status(400).json({ error: 'purpose is required' });
  if (MINIMAX_KEYS.length === 0) return res.status(503).json({ error: 'No MiniMax API keys configured.' });

  const lvl = normLevel(level);
  const lvlCfg = CURATE_LEVELS[lvl];
  const limit = Math.min(Number(max) || lvlCfg.cap, 40);
  const entries = spec.entries;
  const refOf = (e) => e.qualName || (e.kind === 'method' ? `${spec.module}.${e.owner}.${e.name}` : `${spec.module}.${e.name}`);
  // Indexed menu (technique A: the model returns INTEGER indices, so it CANNOT reference a name that
  // isn't in the list). Each line carries the first docstring line (technique B: semantic grounding).
  const apiText = entries.map((e, i) => {
    const base = describeSpecEntry(spec, e).replace(/^- /, '');
    const doc = (e.doc || '').split('\n')[0].trim();
    return `[${i}] ${base}${doc ? '  // ' + doc.slice(0, 100) : ''}`;
  }).join('\n');

  const systemPrompt = `You curate a Python library's REAL API (ground truth) into a small, purpose-focused set of visual blocks for students.

${lvlCfg.guide}

Respond in STRICT JSON only — no markdown. Reference every API item by its integer INDEX "i" from the list (NEVER names/signatures). Schema:
{
  "thoughts": ["short reasoning"],
  "groups": [ { "name": "Category", "entries": [ { "i": <index>, "label": "friendly short label" } ] } ],
  "macros": [ { "name": "snake_id", "label": "friendly label", "group": "Category",
               "params": ["p1"], "steps": [ { "i": <index>, "assign": "var", "args": ["p1 | 'literal' | prior var"] } ], "result": "var" } ]
}

Rules:
- "i" MUST be an integer index shown in the list. Do not invent.
- Select operations relevant to the PURPOSE. Put the ${limit} MOST ESSENTIAL ones FIRST (they become the always-visible "core"); you MAY list up to ${limit * 2} more useful-but-secondary ones after those — they go under a collapsed "더 보기 / more" shelf, so nothing essential is lost to a hard cut. Order matters: most important first.
- Group into 2-5 intuitive categories. Write labels in the SAME LANGUAGE as the purpose, as SHORT task-oriented phrases (≤3 words, a verb + object like "포트 열기" / "open port" — never a full signature).
- Macros chain 2-4 real calls into one task; a step's args count must fit that call's parameters; later steps may use earlier "assign" vars.${lvl === 'beginner' ? '\n- BEGINNER: prefer MACROS — most of the core view should be whole-task macros (one block = one goal), with only a few primitives.' : ''}`;
  const userContent = `Library module: ${spec.module}\nPurpose: ${String(purpose).trim()}\nLevel: ${lvl}\n\nREAL API (reference by index "i"):\n${apiText}`;

  // technique D: retry once if the model returns unparseable JSON.
  async function askOnce(extra) {
    const { thinkingText, responseText } = await callMiniMax(systemPrompt + (extra || ''), userContent, { maxTokens: 2600 });
    const jsonStr = responseText.replace(/^```(?:json)?\n?/m, '').replace(/\n?```$/m, '').trim();
    return { parsed: JSON.parse(jsonStr), thinkingText };
  }

  try {
    let parsed, thinkingText;
    try { ({ parsed, thinkingText } = await askOnce('')); }
    catch { ({ parsed, thinkingText } = await askOnce('\n\nYour previous reply was not valid JSON. Return ONLY the JSON object, nothing else.')); }

    const idxOk = (i) => Number.isInteger(i) && i >= 0 && i < entries.length;
    // groups -> selected[] (map index -> real ref); drop out-of-range indices.
    const selected = [];
    let droppedSel = 0;
    for (const g of parsed.groups || []) {
      for (const en of (g && g.entries) || []) {
        const i = en && en.i;
        if (idxOk(i)) selected.push({ ref: refOf(entries[i]), label: (en.label || ''), group: (g.name || '') });
        else droppedSel++;
      }
    }
    // macros: every step index valid AND its arg count fits the real signature (technique C: deterministic
    // arity verification) — otherwise drop the whole macro so no wrong-arity workflow is emitted.
    const macros = [];
    let droppedMac = 0;
    for (const m of parsed.macros || []) {
      const steps = Array.isArray(m && m.steps) ? m.steps : [];
      const ok = m && m.name && steps.length && steps.every((s) => {
        if (!s || !idxOk(s.i)) return false;
        const a = entryArity(entries[s.i]);
        const callArgs = a.isMethod ? Math.max(0, (Array.isArray(s.args) ? s.args.length : 0) - 1) : (Array.isArray(s.args) ? s.args.length : 0);
        return callArgs >= a.required && (a.vararg || callArgs <= a.total);
      });
      if (!ok) { droppedMac++; continue; }
      macros.push({
        name: String(m.name), label: m.label || m.name, group: m.group || '',
        params: Array.isArray(m.params) ? m.params.map(String) : [],
        steps: steps.map((s) => ({ ref: refOf(entries[s.i]), assign: s.assign ? String(s.assign) : '', args: Array.isArray(s.args) ? s.args.map(String) : [] })),
        result: m.result ? String(m.result) : '',
      });
    }
    const thoughts = [
      ...(thinkingText ? thinkingText.split('\n').filter((l) => l.trim()).slice(0, 3) : []),
      ...(parsed.thoughts || []),
    ].slice(0, 8);

    // Two-tier progressive disclosure (technique: MakeCode advanced=true / Resnick wide-walls):
    // instead of SLICING the tail away, keep it and TAG it. The first `limit` (by the model's rank)
    // are "core" (always visible); the rest up to a ceiling are "more" (a collapsed "더 보기" shelf in
    // the same tab). Nothing essential is silently dropped — the beginner view stays small but the
    // needed-but-9th op is one click away, not gone.
    const MORE_CEIL = Math.min(limit * 3, 40);
    const kept = selected.slice(0, MORE_CEIL);
    const tiered = kept.map((s, idx) => ({ ...s, tier: idx < limit ? 'core' : 'more' }));
    // Macro budget by level: beginner FAVORS macros (one block = one whole task), advanced prefers
    // primitives so learners compose. Macros still count toward keeping the smallest view sane.
    const macroLimit = lvl === 'beginner' ? Math.max(4, limit)
      : lvl === 'advanced' ? Math.min(3, macros.length)
        : Math.max(2, Math.floor(limit / 2));
    const cappedMacros = macros.slice(0, macroLimit);

    res.json({ success: true, module: spec.module, level: lvl, selected: tiered, macros: cappedMacros, thoughts, dropped: { selected: droppedSel + (selected.length - kept.length), macros: droppedMac + (macros.length - cappedMacros.length) } });
  } catch (err) {
    console.error('[/api/abstract-library]', err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// ─── 4. AI Chat: general-purpose MiniMax chat for the AI Agent panel ──────────
app.post('/api/ai-chat', async (req, res) => {
  const { messages, systemPrompt } = req.body;
  if (!messages || !Array.isArray(messages)) {
    return res.status(400).json({ error: 'messages array is required' });
  }

  if (MINIMAX_KEYS.length === 0) {
    return res.status(503).json({ error: 'No MiniMax API keys configured.' });
  }

  try {
    const client = createMiniMaxClient();
    const response = await client.messages.create({
      model: MINIMAX_MODEL,
      max_tokens: 3000,
      system: systemPrompt || 'You are BlockPy AI – a helpful coding assistant for the BlockPy visual Python playground. When asked to write code, output only clean Python that can be visually represented as blocks.',
      messages
    });

    let thinking = '';
    let text = '';
    for (const block of response.content) {
      if (block.type === 'thinking') thinking += block.thinking;
      else if (block.type === 'text') text += block.text;
    }

    res.json({ success: true, thinking, text, model: MINIMAX_MODEL });
  } catch (err) {
    console.error('[/api/ai-chat] MiniMax error:', err.message);
    res.status(500).json({ success: false, error: err.message });
  }
});

// ─── Health check ─────────────────────────────────────────────────────────────
// ── Real Python execution in a local shell ──────────────────────────────────────
// Runs the user's code with the machine's actual Python (real cv2, real webcam, real
// imshow windows on the user's desktop). Streams stdout/stderr back live; aborting the
// request (Stop) kills the process. Intended for local single-user use.

app.post('/api/run-python', (req, res) => {
  const code = (req.body && req.body.code) || '';
  if (!code.trim()) { res.status(400).json({ error: 'No code provided' }); return; }

  const file = path.join(os.tmpdir(), `blockpy_${Date.now()}_${Math.random().toString(36).slice(2)}.py`);
  try { fs.writeFileSync(file, code, 'utf8'); }
  catch (e) { res.status(500).json({ error: 'Failed to write temp file: ' + e.message }); return; }

  res.setHeader('Content-Type', 'text/plain; charset=utf-8');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('X-Accel-Buffering', 'no'); // disable proxy buffering for live streaming

  let child;
  try {
    child = spawn(PYTHON_CMD, ['-u', file], {
      cwd: MEDIA_DIR, // so cv2.imread('name.jpg') finds uploaded/sample images
      env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUNBUFFERED: '1' },
    });
  } catch (e) {
    res.write(`[shell error] could not start "${PYTHON_CMD}": ${e.message}\n`);
    try { fs.unlinkSync(file); } catch (_) {}
    res.end();
    return;
  }

  let done = false;
  const cleanup = () => { try { fs.unlinkSync(file); } catch (_) {} };

  child.stdout.on('data', (d) => res.write(d));
  child.stderr.on('data', (d) => res.write(d));
  child.on('error', (e) => {
    res.write(`\n[shell error] ${e.message}\n`);
    if (e.code === 'ENOENT') {
      res.write(`[shell] Python not found. Install Python (and opencv-python) or set PYTHON_CMD.\n`);
    }
  });
  child.on('close', (codeNum) => {
    done = true;
    res.write(`\n[exit ${codeNum}]\n`);
    cleanup();
    res.end();
  });

  // Browser aborted (Stop) → kill the Python process. Only kill on a genuine client
  // disconnect: res 'close' BEFORE the response finished normally (res.end not called).
  // Guarding on res.writableEnded avoids killing on normal completion or proxy quirks.
  res.on('close', () => {
    cleanup();
    if (!done && !res.writableEnded && child && !child.killed) {
      try { child.kill(); } catch (_) {}
    }
  });
});

// Real `pip install <package>` on the local machine (python -m pip). Streams output;
// installed packages become available to subsequent shell runs. spawn (no shell) +
// charset validation prevents command injection.
app.post('/api/pip-install', (req, res) => {
  const pkg = ((req.body && req.body.package) || '').trim();
  if (!pkg) { res.status(400).json({ error: 'package required' }); return; }
  if (!/^[A-Za-z0-9._\-=<>!\[\],~+ ]+$/.test(pkg)) {
    res.status(400).json({ error: 'invalid package spec' }); return;
  }
  // Reject pip FLAGS (whitespace-split tokens starting with '-') — a bare charset check still lets
  // "pkg --target=… --pre" through, redirecting where/what pip installs. Only package specs allowed.
  if (pkg.split(/\s+/).some((t) => t.startsWith('-'))) {
    res.status(400).json({ error: 'flags are not allowed in the package spec' }); return;
  }
  res.setHeader('Content-Type', 'text/plain; charset=utf-8');
  res.setHeader('Cache-Control', 'no-cache');
  res.setHeader('X-Accel-Buffering', 'no');

  // Split on whitespace so "numpy pillow" or "pkg==1.2" both work; each token is a
  // separate arg (no shell interpolation).
  const args = ['-m', 'pip', 'install', ...pkg.split(/\s+/).filter(Boolean)];
  let child;
  try {
    child = spawn(PYTHON_CMD, args, { env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });
  } catch (e) {
    res.write(`[pip error] ${e.message}\n`); res.end(); return;
  }
  let done = false;
  child.stdout.on('data', (d) => res.write(d));
  child.stderr.on('data', (d) => res.write(d));
  child.on('error', (e) => res.write(`\n[pip error] ${e.message}\n`));
  child.on('close', (codeNum) => { done = true; res.write(`\n[pip exit ${codeNum}]\n`); res.end(); });
  res.on('close', () => { if (!done && !res.writableEnded && child && !child.killed) { try { child.kill(); } catch (_) {} } });
});

// ─── Robot (Dobot) bridge: DobotLink-mediated arm/car via dobotkit ─────────────
// Each call spawns scripts/robot_bridge.py with a JSON command on stdin; the script does ONE
// dobotkit action against DobotLink (ws://localhost:9090) and prints a JSON result. Stateless per
// call (DobotLink holds the hardware). Requires DobotLink.exe running + dobotkit installed in
// PYTHON_CMD; both failures surface as {ok:false,error,hint} (HTTP 200 so the UI can show them).
const ROBOT_BRIDGE = path.join(__dirname, 'scripts', 'robot_bridge.py');
function runRobotBridge(command, res, timeoutMs) {
  let child;
  try {
    child = spawn(PYTHON_CMD, [ROBOT_BRIDGE], { env: { ...process.env, PYTHONIOENCODING: 'utf-8', PYTHONUTF8: '1' } });
  } catch (e) {
    return res.json({ ok: false, error: `python 실행 실패: ${e.message}`, hint: 'PYTHON_CMD 확인' });
  }
  // Settle-once guard (as in /api/infer-types): 'error'/'close'/timeout race — exactly one reply.
  let responded = false;
  let timer = null;
  const reply = (body) => {
    if (responded) return;
    responded = true;
    clearTimeout(timer);
    res.json(body);
  };
  timer = setTimeout(() => {
    killTree(child);
    reply({ ok: false, error: `로봇 브리지 시간초과(${timeoutMs}ms)`, hint: 'DobotLink 응답 없음 — DobotLink.exe/로봇 상태를 확인하세요.' });
  }, timeoutMs);
  let out = '';
  child.stdout.on('data', (d) => { out += d; });
  child.stderr.on('data', () => {}); // drain — an undrained pipe can deadlock the child
  child.on('error', (e) => reply({ ok: false, error: `python 실행 오류: ${e.message}`, hint: 'PYTHON_CMD 확인' }));
  child.on('close', () => { try { reply(JSON.parse(out.trim().split('\n').pop() || '')); } catch (_) { reply({ ok: false, error: '로봇 브리지 응답 파싱 실패', hint: (out || '').slice(0, 400) }); } });
  try { child.stdin.write(JSON.stringify(command)); child.stdin.end(); } catch (_) { /* child died — 'close'/'error' handles it */ }
}

app.post('/api/robot/ports', (req, res) => {
  const device = (req.body && req.body.device) === 'go' ? 'go' : 'lite';
  runRobotBridge({ action: 'ports', device }, res, 15000);
});
app.post('/api/robot/connect', (req, res) => {
  const b = req.body || {};
  runRobotBridge({ action: 'connect', device: b.device === 'go' ? 'go' : 'lite', port: b.port || 'auto' }, res, 25000);
});
app.post('/api/robot/disconnect', (req, res) => {
  const b = req.body || {};
  runRobotBridge({ action: 'disconnect', device: b.device === 'go' ? 'go' : 'lite', port: b.port || 'auto' }, res, 15000);
});
app.post('/api/robot/move-preset', (req, res) => {
  const b = req.body || {};
  if (typeof b.x !== 'number' || typeof b.y !== 'number') return res.status(400).json({ ok: false, error: 'x, y (number) 필요' });
  // Motion (optional home + move, wait-for-finish) can take a while. This MUST exceed the bridge's
  // own sequential RPC deadlines (connect+queue+home+move+pose ≈ up to ~110s) so a slow-but-legit
  // home surfaces as a clean {ok:false} DobotTimeoutError from dobotkit instead of the server
  // killTree-ing python mid-motion (which would leave the queued move running while the UI shows a
  // false timeout). 120s > that sum.
  runRobotBridge({ action: 'move_preset', device: 'lite', port: b.port || 'auto', x: b.x, y: b.y, z: (typeof b.z === 'number' ? b.z : undefined), home: !!b.home }, res, 120000);
});

// Save an uploaded image to the media dir so shell-run Python can cv2.imread() it.
app.post('/api/upload-image', (req, res) => {
  const { filename, dataBase64 } = req.body || {};
  if (!filename || !dataBase64) { res.status(400).json({ error: 'filename and dataBase64 required' }); return; }
  // sanitize filename to a basename (no path traversal)
  const safe = path.basename(String(filename)).replace(/[^\w.\-]/g, '_') || 'upload.png';
  try {
    const bytes = Buffer.from(String(dataBase64).replace(/^data:[^,]+,/, ''), 'base64');
    fs.writeFileSync(path.join(MEDIA_DIR, safe), bytes);
    res.json({ ok: true, savedAs: safe, dir: MEDIA_DIR });
  } catch (e) {
    res.status(500).json({ error: 'Failed to save image: ' + e.message });
  }
});

// ─── Workspace file system API (the VS Code-style file explorer) ────────────────
// All paths are RELATIVE to WORKSPACE_DIR and validated by safeResolve (no traversal).
// Read-only static mount so the frontend can preview images: GET /workspace/<relpath>.
app.use('/workspace', express.static(WORKSPACE_DIR));

const TEXT_EXT = new Set(['.py','.txt','.md','.json','.csv','.html','.css','.js','.xml','.yml','.yaml','.ini','.cfg','.log','.tsv']);
const IMAGE_EXT = new Set(['.png','.jpg','.jpeg','.gif','.bmp','.webp','.svg']);

function buildTree(absDir, relDir, depth) {
  const out = [];
  let entries;
  try { entries = fs.readdirSync(absDir, { withFileTypes: true }); } catch (_) { return out; }
  // Folders first, then files; both alphabetical (case-insensitive).
  entries.sort((a, b) => {
    if (a.isDirectory() !== b.isDirectory()) return a.isDirectory() ? -1 : 1;
    return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
  });
  for (const e of entries) {
    if (e.name === '.git' || e.name === '__pycache__') continue;
    const rel = relDir ? `${relDir}/${e.name}` : e.name;
    const abs = path.join(absDir, e.name);
    if (e.isDirectory()) {
      out.push({ name: e.name, path: rel, type: 'dir', children: depth > 0 ? buildTree(abs, rel, depth - 1) : [] });
    } else {
      const ext = path.extname(e.name).toLowerCase();
      let size = 0; try { size = fs.statSync(abs).size; } catch (_) {}
      out.push({ name: e.name, path: rel, type: 'file', ext, size, kind: IMAGE_EXT.has(ext) ? 'image' : TEXT_EXT.has(ext) ? 'text' : 'binary' });
    }
  }
  return out;
}

app.get('/api/fs/root', (req, res) => {
  res.json({ root: WORKSPACE_DIR });
});

app.get('/api/fs/tree', (req, res) => {
  res.json({ root: WORKSPACE_DIR, tree: buildTree(WORKSPACE_DIR, '', 12) });
});

app.get('/api/fs/file', (req, res) => {
  const abs = safeResolve(req.query.path);
  if (!abs) return res.status(400).json({ error: 'invalid path' });
  if (!fs.existsSync(abs) || !fs.statSync(abs).isFile()) return res.status(404).json({ error: 'not found' });
  const ext = path.extname(abs).toLowerCase();
  if (IMAGE_EXT.has(ext)) {
    // Images are previewed via the /workspace static mount, not inlined here.
    return res.json({ path: req.query.path, kind: 'image', url: '/workspace/' + String(req.query.path).replace(/\\/g, '/') });
  }
  try {
    const content = fs.readFileSync(abs, 'utf8');
    res.json({ path: req.query.path, kind: 'text', content });
  } catch (e) {
    res.status(500).json({ error: 'read failed: ' + e.message });
  }
});

app.post('/api/fs/file', (req, res) => {
  const abs = safeResolve(req.body && req.body.path);
  if (!abs) return res.status(400).json({ error: 'invalid path' });
  try {
    fs.mkdirSync(path.dirname(abs), { recursive: true });
    fs.writeFileSync(abs, String((req.body && req.body.content) || ''), 'utf8');
    res.json({ ok: true, path: req.body.path });
  } catch (e) {
    res.status(500).json({ error: 'write failed: ' + e.message });
  }
});

app.post('/api/fs/mkdir', (req, res) => {
  const abs = safeResolve(req.body && req.body.path);
  if (!abs) return res.status(400).json({ error: 'invalid path' });
  try { fs.mkdirSync(abs, { recursive: true }); res.json({ ok: true, path: req.body.path }); }
  catch (e) { res.status(500).json({ error: 'mkdir failed: ' + e.message }); }
});

app.post('/api/fs/delete', (req, res) => {
  const abs = safeResolve(req.body && req.body.path);
  if (!abs) return res.status(400).json({ error: 'invalid path' });
  if (abs === path.resolve(WORKSPACE_DIR)) return res.status(400).json({ error: 'cannot delete the workspace root' });
  try { fs.rmSync(abs, { recursive: true, force: true }); res.json({ ok: true }); }
  catch (e) { res.status(500).json({ error: 'delete failed: ' + e.message }); }
});

app.post('/api/fs/rename', (req, res) => {
  const from = safeResolve(req.body && req.body.from);
  const to = safeResolve(req.body && req.body.to);
  if (!from || !to) return res.status(400).json({ error: 'invalid path' });
  try { fs.mkdirSync(path.dirname(to), { recursive: true }); fs.renameSync(from, to); res.json({ ok: true, path: req.body.to }); }
  catch (e) { res.status(500).json({ error: 'rename failed: ' + e.message }); }
});

app.get('/api/health', (req, res) => {
  res.json({
    status: 'ok',
    model: MINIMAX_MODEL,
    baseURL: 'https://api.minimax.io/anthropic',
    keysLoaded: MINIMAX_KEYS.length,
    keyPool: MINIMAX_KEYS.map((_, i) => `MINIMAX${i + 1}`)
  });
});

// ─── SPA fallback (only when serving a static frontend) ─────────────────────────
// Any non-/api GET that didn't match a static file returns index.html so client-side
// routing / direct loads work. Registered last so it never shadows the API routes.
// (Avoids Express 5 path-to-regexp wildcard syntax by using a path-less middleware.)
if (STATIC_DIR && fs.existsSync(STATIC_DIR)) {
  app.use((req, res, next) => {
    if (req.method !== 'GET' || req.path.startsWith('/api/')) return next();
    res.sendFile(path.join(STATIC_DIR, 'index.html'));
  });
}

// ─── AI 도우미 터미널 (WebSocket PTY) ───────────────────────────────────────────
// /api/terminal 로 붙는 WS 연결마다 실제 셸(PTY)을 띄워 바이트를 양방향 중계한다.
// cwd 는 워크스페이스(파일탐색기/Run 과 동일). run-python 과 같은 로컬 단일 사용자 신뢰 모델.
const wss = new WebSocketServer({ noServer: true });

function pickShell() {
  if (process.platform === 'win32') return 'powershell.exe';
  return process.env.SHELL || 'bash';
}

function attachTerminal(ws) {
  let pty;
  try {
    // 지연 require: 네이티브 빌드가 없더라도 서버의 나머지는 살아있게 한다.
    const nodePty = require('node-pty');
    let shell = pickShell();
    try {
      pty = nodePty.spawn(shell, [], {
        name: 'xterm-color', cols: 80, rows: 24, cwd: WORKSPACE_DIR,
        env: { ...process.env, PYTHONIOENCODING: 'utf-8', BLOCKPY_TERMINAL: '1' },
      });
    } catch (e1) {
      if (process.platform === 'win32') {
        shell = process.env.COMSPEC || 'cmd.exe'; // powershell 실패 시 폴백
        pty = nodePty.spawn(shell, [], { name: 'xterm-color', cols: 80, rows: 24, cwd: WORKSPACE_DIR,
          env: { ...process.env, BLOCKPY_TERMINAL: '1' } });
      } else { throw e1; }
    }
  } catch (e) {
    try { ws.send(`\r\n[터미널을 시작할 수 없습니다: ${e.message}]\r\n`); } catch (_) {}
    try { ws.close(); } catch (_) {}
    return;
  }

  pty.onData((d) => { try { ws.send(d); } catch (_) {} });
  pty.onExit(() => { try { ws.close(); } catch (_) {} });

  ws.on('message', (raw) => {
    let msg; try { msg = JSON.parse(raw.toString()); } catch (_) { return; }
    if (!msg || typeof msg !== 'object') return;
    if (msg.t === 'i' && typeof msg.d === 'string') { try { pty.write(msg.d); } catch (_) {} }
    else if (msg.t === 'r' && Number.isInteger(msg.cols) && Number.isInteger(msg.rows)) {
      try { pty.resize(Math.max(1, msg.cols), Math.max(1, msg.rows)); } catch (_) {}
    }
  });

  const kill = () => { try { pty.kill(); } catch (_) {} };
  ws.on('close', kill);
  ws.on('error', kill);
}

wss.on('connection', attachTerminal);

function start(port = process.env.PORT || 3001) {
  return new Promise((resolve) => {
    // Bind LOOPBACK ONLY (127.0.0.1) — never all interfaces. Prevents any other host on the LAN from
    // reaching the run-python/pip/blockify/fs endpoints (unauthenticated RCE + file access otherwise).
    const server = app.listen(port, '127.0.0.1', () => {
      const actual = server.address().port;
      console.log(`\n🚀 BlockPy Express Server  →  http://127.0.0.1:${actual}`);
      console.log(`🤖 AI Engine: MiniMax-M2.7  (via Anthropic SDK)`);
      console.log(`🔑 Key pool: ${MINIMAX_KEYS.length} key(s) loaded (round-robin)`);
      console.log(`📁 Workspace (file explorer + run cwd): ${WORKSPACE_DIR}\n`);
      seedSampleImages();
      seedStarterFile();
      resolve({ server, port: actual });
    });
    // WS 업그레이드: /api/terminal 만 처리하고, loopback Host 가 아니면 소켓을 파기한다
    // (Express 의 Host 미들웨어는 WS 업그레이드에 적용되지 않으므로 여기서 직접 검사).
    server.on('upgrade', (req, socket, head) => {
      if (!String(req.url || '').startsWith('/api/terminal')) { socket.destroy(); return; }
      if (!isLoopbackHost(req)) { socket.destroy(); return; }
      wss.handleUpgrade(req, socket, head, (ws) => wss.emit('connection', ws, req));
    });
  });
}

// Run standalone (`node server.js`) → listen immediately. When required by Electron's
// main process, export start() so it can pick a port and await readiness instead.
if (require.main === module) {
  start();
}

module.exports = { app, start };

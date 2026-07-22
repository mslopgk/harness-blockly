# AI 도우미 터미널 패널 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 편집기 오른쪽에 node-pty 기반 진짜 대화형 터미널 패널을 붙여, 그 안에서 `claude`/`opencode` 등 에이전트 CLI를 직접 실행하게 한다.

**Architecture:** 백엔드 `server.js`가 기존 http 서버에 `/api/terminal` WebSocket을 부착해 PTY 셸을 중계하고, 프론트 `AiTerminal.jsx`가 xterm.js로 렌더한다. dev(Vite ws 프록시)와 패키징 Electron(same-origin) 양쪽에서 동일 동작한다.

**Tech Stack:** node-pty, ws (백엔드) / @xterm/xterm, @xterm/addon-fit (프론트) / React 19 + Vite / Express 5.

## Global Constraints

- 변환 코어와 스펙 데이터는 **일절 건드리지 않는다**: `src/utils/irToBlockly.js`, `blocklyToIr.js`, `irBlocks.js`, `irToolbox.js`, `libRegistry.js`, `libImport.js`, `src/data/*.json`. 이 기능은 이들과 무관하다.
- 서버는 **127.0.0.1 전용 바인딩 + 비루프백 Host 거부**를 유지하며, **WS 업그레이드에도 동일한 loopback Host 검사를 적용**한다.
- `node-pty` 로드/스폰 실패가 **서버 전체를 죽여선 안 된다** — 지연 `require` + try/catch로 graceful 처리(run-python/fs 등 나머지 엔드포인트는 계속 동작).
- 상대경로 WS URL만 사용(`window.location` 기반) — 하드코딩 호스트/포트 금지.
- DRY, YAGNI(터미널 1개·자동실행 없음·미저장 버퍼 동기화 없음), TDD, 잦은 커밋.

---

## File Structure

- **`package.json`** (수정) — 의존성 4종 추가, `build.asarUnpack`에 node-pty 추가, `test:terminal` 스크립트 추가.
- **`server.js`** (수정) — 모듈 스코프에 `WebSocketServer` + `attachTerminal()`; `start()`에서 `server.on('upgrade')` 배선.
- **`vite.config.js`** (수정) — `/api` 프록시에 `ws: true`.
- **`src/components/terminalWs.mjs`** (신규) — 순수 함수 `terminalWsUrl(loc)` (node/Vite 공용, 유닛테스트 대상).
- **`src/components/AiTerminal.jsx`** (신규) — xterm 렌더 + WS 연결 컴포넌트.
- **`src/App.jsx`** (수정) — 3열 그리드, 터미널 패널 섹션, 접기/리사이즈 상태(localStorage), 지연 마운트.
- **`src/index.css`** (수정) — `.terminal-panel` / `.ai-terminal*` 스타일, 드래그 핸들.
- **`tests/ai_terminal.test.mjs`** (신규) — 백엔드 WS 통합 테스트(node --test).
- **`tests/xterm_url.test.mjs`** (신규) — `terminalWsUrl` 유닛 테스트.
- **`tests/ai_terminal_ui.spec.js`** (신규) — Playwright 레이아웃/지연마운트 테스트.

---

### Task 1: 백엔드 WS PTY 엔드포인트

**Files:**
- Modify: `package.json` (dependencies, build.asarUnpack, scripts)
- Modify: `server.js` (requires ~line 1-7; `attachTerminal`+`wss` at module scope ~before line 887; upgrade wiring inside `start()` ~line 891)
- Create: `tests/ai_terminal.test.mjs`

**Interfaces:**
- Consumes: 기존 `LOOPBACK_HOSTS`(server.js:16), `WORKSPACE_DIR`(server.js:45), `start(port)`(server.js:887, returns `{server, port}`). (주의: 이 브랜치는 master 분기라 `RUNTIME_DIR`가 없다 — 터미널 env에 넣지 않는다.)
- Produces: WS 엔드포인트 `GET (upgrade) /api/terminal`. 클라이언트→서버 프레임 `{"t":"i","d":string}`(입력) / `{"t":"r","cols":int,"rows":int}`(리사이즈). 서버→클라이언트: PTY 출력 문자열.

- [ ] **Step 1: 의존성 설치**

Run:
```bash
npm install node-pty@^1.0.0 ws@^8.18.0
```
Expected: 설치 성공. 이어서 네이티브 로드 확인:
```bash
node -e "require('node-pty'); require('ws'); console.log('OK')"
```
Expected 출력: `OK`
(실패 시 — Windows에 C++ 빌드툴 부재: Visual Studio Build Tools 또는 `npm i -g windows-build-tools` 필요. 이는 전제 리스크로 스펙에 명시됨.)

- [ ] **Step 2: 실패 테스트 작성** — `tests/ai_terminal.test.mjs`

```js
import { test } from 'node:test';
import assert from 'node:assert';
import { createRequire } from 'node:module';
import { WebSocket } from 'ws';
import os from 'node:os';
import path from 'node:path';
import fs from 'node:fs';

const require = createRequire(import.meta.url);

test('WS /api/terminal relays shell output', async (t) => {
  process.env.BLOCKPY_WORKSPACE = fs.mkdtempSync(path.join(os.tmpdir(), 'bpterm-'));
  const { start } = require('../server.js');
  const { server, port } = await start(0);
  t.after(() => new Promise((r) => server.close(r)));

  const marker = 'BLOCKPY_TERMINAL_OK_' + process.pid;
  const ws = new WebSocket(`ws://127.0.0.1:${port}/api/terminal`);
  const buf = await new Promise((resolve, reject) => {
    let acc = '';
    const timer = setTimeout(() => reject(new Error('timeout; got: ' + acc)), 25000);
    ws.on('open', () => {
      ws.send(JSON.stringify({ t: 'r', cols: 80, rows: 24 }));
      ws.send(JSON.stringify({ t: 'i', d: `echo ${marker}\r` }));
    });
    ws.on('message', (d) => { acc += d.toString(); if (acc.includes(marker)) { clearTimeout(timer); resolve(acc); } });
    ws.on('error', (e) => { clearTimeout(timer); reject(e); });
  });
  assert.ok(buf.includes(marker), 'shell output should echo the marker');
  ws.close();
});

test('WS upgrade rejects non-loopback Host', async (t) => {
  const { start } = require('../server.js');
  const { server, port } = await start(0);
  t.after(() => new Promise((r) => server.close(r)));

  const ws = new WebSocket(`ws://127.0.0.1:${port}/api/terminal`, { headers: { host: 'evil.example.com' } });
  const result = await new Promise((resolve) => {
    ws.on('open', () => resolve('opened'));
    ws.on('error', () => resolve('error'));
    ws.on('close', () => resolve('closed'));
  });
  assert.notStrictEqual(result, 'opened', 'non-loopback Host must not open a terminal');
});
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `node --test tests/ai_terminal.test.mjs`
Expected: FAIL — `/api/terminal` 업그레이드 핸들러가 없어 연결이 열리지 않음(첫 테스트 timeout/error).

- [ ] **Step 4: server.js에 require 추가** (파일 상단 require 블록, 8번째 줄 부근)

`server.js:7` (`const path = require('path');`) 바로 다음 줄에 추가:
```js
const { WebSocketServer } = require('ws');
```

- [ ] **Step 5: `attachTerminal` + `wss` 모듈 스코프 추가** (`function start(...)` 정의 바로 앞, 현재 line 887 부근)

`// ─── SPA fallback ...` 블록과 `function start(` 사이에 삽입:
```js
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
```

- [ ] **Step 6: `start()`에 upgrade 배선 추가**

`server.js` `start()` 안에서 `const server = app.listen(port, '127.0.0.1', () => { ... });` 문장 **바로 다음**(같은 Promise executor 내부)에 삽입:
```js
    // WS 업그레이드: /api/terminal 만 처리하고, loopback Host 가 아니면 소켓을 파기한다
    // (Express 의 Host 미들웨어는 WS 업그레이드에 적용되지 않으므로 여기서 직접 검사).
    server.on('upgrade', (req, socket, head) => {
      if (!String(req.url || '').startsWith('/api/terminal')) { socket.destroy(); return; }
      const host = String(req.headers.host || '').replace(/:\d+$/, '').toLowerCase();
      if (!LOOPBACK_HOSTS.has(host)) { socket.destroy(); return; }
      wss.handleUpgrade(req, socket, head, (ws) => wss.emit('connection', ws, req));
    });
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `node --test tests/ai_terminal.test.mjs`
Expected: PASS (2/2). 첫 테스트가 셸 출력에서 marker를 받고, 둘째가 비루프백 Host 거부를 확인.

- [ ] **Step 8: package.json 마무리 (asarUnpack + 스크립트)**

`build.asarUnpack` 배열을 다음으로 교체:
```json
    "asarUnpack": [
      "blockpy-gen/**/*",
      "node_modules/node-pty/**/*"
    ],
```
`scripts`에 추가:
```json
    "test:terminal": "node --test tests/ai_terminal.test.mjs tests/xterm_url.test.mjs",
```
(node-pty/ws가 dependencies에 `^1.0.0`/`^8.18.0`으로 추가돼 있는지 확인 — Step 1의 `npm install`이 기록함.)

- [ ] **Step 9: 커밋**

```bash
git add package.json package-lock.json server.js tests/ai_terminal.test.mjs
git commit -m "feat(terminal): /api/terminal WebSocket PTY 엔드포인트 + node 통합 테스트"
```

---

### Task 2: 프론트 터미널 컴포넌트

**Files:**
- Modify: `package.json` (dependencies: @xterm/xterm, @xterm/addon-fit)
- Create: `src/components/terminalWs.mjs`
- Create: `src/components/AiTerminal.jsx`
- Create: `tests/xterm_url.test.mjs`

**Interfaces:**
- Consumes: Task 1의 WS 프레임 규약(`{t:'i',d}` / `{t:'r',cols,rows}`), 서버 출력 문자열.
- Produces: `terminalWsUrl(loc) -> string` (from `terminalWs.mjs`); `<AiTerminal active={boolean} />` 기본 export.

- [ ] **Step 1: 의존성 설치**

Run:
```bash
npm install @xterm/xterm@^5.5.0 @xterm/addon-fit@^0.10.0
```
Expected: 설치 성공.

- [ ] **Step 2: URL 헬퍼 실패 테스트** — `tests/xterm_url.test.mjs`

```js
import { test } from 'node:test';
import assert from 'node:assert';
import { terminalWsUrl } from '../src/components/terminalWs.mjs';

test('http -> ws', () => {
  assert.strictEqual(terminalWsUrl({ protocol: 'http:', host: '127.0.0.1:3000' }), 'ws://127.0.0.1:3000/api/terminal');
});
test('https -> wss', () => {
  assert.strictEqual(terminalWsUrl({ protocol: 'https:', host: 'example:8443' }), 'wss://example:8443/api/terminal');
});
```

- [ ] **Step 3: 실패 확인**

Run: `node --test tests/xterm_url.test.mjs`
Expected: FAIL — `terminalWs.mjs` 없음(모듈 해석 실패).

- [ ] **Step 4: 헬퍼 작성** — `src/components/terminalWs.mjs`

```js
// /api/terminal 의 WebSocket URL 을 현재 문서 위치에서 만든다. dev(Vite ws 프록시)와
// 패키징(same-origin) 모두 상대적으로 올바른 호스트/포트를 쓰게 한다. 순수 함수 — 유닛테스트 대상.
export function terminalWsUrl(loc) {
  const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${loc.host}/api/terminal`;
}
```

- [ ] **Step 5: 헬퍼 테스트 통과 확인**

Run: `node --test tests/xterm_url.test.mjs`
Expected: PASS (2/2).

- [ ] **Step 6: 컴포넌트 작성** — `src/components/AiTerminal.jsx`

```jsx
import { useEffect, useRef, useState } from 'react';
import { Terminal } from '@xterm/xterm';
import { FitAddon } from '@xterm/addon-fit';
import '@xterm/xterm/css/xterm.css';
import { terminalWsUrl } from './terminalWs.mjs';

// 편집기 옆 진짜 터미널. active=true 로 처음 보일 때만 xterm 을 초기화하고 WS 를 연결한다
// (지연 마운트). 이후에는 유지 — 접혀도 스크롤백을 보존한다. WS 가 끊기면 '다시 연결' 버튼.
export default function AiTerminal({ active }) {
  const screenRef = useRef(null);
  const termRef = useRef(null);
  const fitRef = useRef(null);
  const wsRef = useRef(null);
  const [status, setStatus] = useState('connecting'); // connecting | open | closed

  function sendResize() {
    const ws = wsRef.current, term = termRef.current;
    if (ws && ws.readyState === WebSocket.OPEN && term) {
      ws.send(JSON.stringify({ t: 'r', cols: term.cols, rows: term.rows }));
    }
  }

  function connect() {
    const term = termRef.current;
    if (!term) return;
    setStatus('connecting');
    const ws = new WebSocket(terminalWsUrl(window.location));
    wsRef.current = ws;
    ws.onopen = () => { setStatus('open'); sendResize(); term.focus(); };
    ws.onmessage = (e) => term.write(typeof e.data === 'string' ? e.data : new Uint8Array(e.data));
    ws.onclose = () => setStatus('closed');
    ws.onerror = () => setStatus('closed');
  }

  useEffect(() => {
    if (!active || termRef.current) return; // 최초 표시 시 1회만 초기화
    const term = new Terminal({
      fontFamily: 'JetBrains Mono, ui-monospace, monospace', fontSize: 13,
      cursorBlink: true, convertEol: false,
      theme: { background: '#1a1815', foreground: '#e8e3da' },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(screenRef.current);
    fit.fit();
    termRef.current = term; fitRef.current = fit;

    // 입력은 한 번만 배선하고 현재 wsRef 를 참조한다(재연결 시 핸들러 중복 방지).
    term.onData((d) => {
      const ws = wsRef.current;
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ t: 'i', d }));
    });

    const ro = new ResizeObserver(() => { try { fit.fit(); sendResize(); } catch (_) {} });
    ro.observe(screenRef.current);
    connect();

    return () => { ro.disconnect(); };
  }, [active]);

  // 패널이 다시 보일 때 크기 재적합
  useEffect(() => { if (active && fitRef.current) { try { fitRef.current.fit(); sendResize(); } catch (_) {} } }, [active]);

  function reconnect() {
    if (termRef.current) termRef.current.reset();
    connect();
  }

  return (
    <div className="ai-terminal">
      <div className="ai-terminal-bar">
        <span className="ai-terminal-title"><i className="fa-solid fa-terminal"></i> AI 도우미 터미널</span>
        {status === 'closed' && (
          <button className="btn btn-secondary btn-sm" onClick={reconnect}>
            <i className="fa-solid fa-rotate-right"></i> 다시 연결
          </button>
        )}
      </div>
      <div ref={screenRef} className="ai-terminal-screen" />
    </div>
  );
}
```

- [ ] **Step 7: 빌드로 임포트 무결성 확인**

Run: `npm run build`
Expected: 성공(오타/임포트 오류 없이 `dist/` 생성). AiTerminal이 번들에 포함.

- [ ] **Step 8: 커밋**

```bash
git add package.json package-lock.json src/components/terminalWs.mjs src/components/AiTerminal.jsx tests/xterm_url.test.mjs
git commit -m "feat(terminal): AiTerminal xterm 컴포넌트 + terminalWsUrl 헬퍼/유닛테스트"
```

---

### Task 3: 레이아웃 통합 + Vite 프록시 + Playwright

**Files:**
- Modify: `vite.config.js` (`/api` proxy → `ws: true`)
- Modify: `src/App.jsx` (state, 3열 그리드 인라인 스타일, `<section className="terminal-panel">`, 지연 마운트)
- Modify: `src/index.css` (`.terminal-panel`, `.ai-terminal*`, 드래그 핸들, 접힘 스트립)
- Create: `tests/ai_terminal_ui.spec.js`

**Interfaces:**
- Consumes: `<AiTerminal active>` (Task 2), 기존 `dashboard-grid`/`left-panel`/`right-panel` 마크업(App.jsx:1411-1712, CSS:419-443).
- Produces: 없음(최종 UI). localStorage 키 `blockpy.terminal.open`(`'1'`/`'0'`), `blockpy.terminal.width`(px 숫자).

- [ ] **Step 1: Playwright 실패 테스트 작성** — `tests/ai_terminal_ui.spec.js`

```js
import { test, expect } from '@playwright/test';

// 백엔드(:3001)는 Playwright 가 띄우지 않는다 — 이 테스트는 UI 마운트/토글/지연연결만 본다.
// WS 연결 자체는 실패해도 무방(연결 성공을 단언하지 않음).
test('터미널 패널은 접힘이 기본이고, 열기 전에는 xterm 이 마운트되지 않는다', async ({ page }) => {
  await page.addInitScript(() => localStorage.removeItem('blockpy.terminal.open'));
  await page.goto('/');
  // 열기 전: xterm 미마운트
  await expect(page.locator('.ai-terminal-screen .xterm')).toHaveCount(0);
  // 토글 버튼으로 펼치기
  await page.getByRole('button', { name: /터미널/ }).first().click();
  // 펼친 후: xterm 마운트됨
  await expect(page.locator('.ai-terminal-screen .xterm')).toHaveCount(1, { timeout: 15000 });
});
```

- [ ] **Step 2: 실패 확인**

Run: `npx playwright test tests/ai_terminal_ui.spec.js`
Expected: FAIL — 터미널 토글/패널이 아직 없음.

- [ ] **Step 3: Vite 프록시에 ws 추가** — `vite.config.js`

`proxy['/api']` 객체에 `ws: true` 한 줄 추가:
```js
    proxy: {
      '/api': {
        target: 'http://localhost:3001',
        changeOrigin: true,
        secure: false,
        ws: true,
      },
    },
```

- [ ] **Step 4: App.jsx — import + 상태 추가**

파일 상단 import 구역에 추가(다른 컴포넌트 import 옆):
```js
import AiTerminal from './components/AiTerminal.jsx';
```
컴포넌트 함수 본문의 다른 `useState` 근처에 추가:
```js
  const [terminalOpen, setTerminalOpen] = useState(() => localStorage.getItem('blockpy.terminal.open') === '1');
  const [terminalWidth, setTerminalWidth] = useState(() => Number(localStorage.getItem('blockpy.terminal.width')) || 380);
  const [terminalEverOpened, setTerminalEverOpened] = useState(() => localStorage.getItem('blockpy.terminal.open') === '1');
  useEffect(() => { localStorage.setItem('blockpy.terminal.open', terminalOpen ? '1' : '0'); if (terminalOpen) setTerminalEverOpened(true); }, [terminalOpen]);
  useEffect(() => { localStorage.setItem('blockpy.terminal.width', String(terminalWidth)); }, [terminalWidth]);

  // 터미널 패널 너비 드래그 리사이즈(왼쪽 핸들). 포인터 이동을 추적해 240~800px 로 클램프.
  const startTerminalResize = (e) => {
    e.preventDefault();
    const startX = e.clientX, startW = terminalWidth;
    const onMove = (ev) => { const w = startW + (startX - ev.clientX); setTerminalWidth(Math.min(800, Math.max(240, w))); };
    const onUp = () => { window.removeEventListener('pointermove', onMove); window.removeEventListener('pointerup', onUp); };
    window.addEventListener('pointermove', onMove); window.addEventListener('pointerup', onUp);
  };
```

- [ ] **Step 5: App.jsx — 그리드 3열화**

`<main className="dashboard-grid">` (line 1411 부근)을 인라인 스타일 포함으로 교체:
```jsx
      <main className="dashboard-grid" style={{ gridTemplateColumns: `380px 1fr ${terminalOpen ? terminalWidth + 'px' : '2.25rem'}` }}>
```

- [ ] **Step 6: App.jsx — 터미널 섹션 삽입**

right-panel 닫는 `</section>` (line 1711)과 `</main>` (line 1712) **사이**에 삽입:
```jsx
        <section className="terminal-panel" data-open={terminalOpen ? '1' : '0'}>
          {terminalOpen && <div className="terminal-resize-handle" onPointerDown={startTerminalResize} title="너비 조절" />}
          <button
            className="terminal-toggle btn btn-secondary btn-sm"
            onClick={() => setTerminalOpen((v) => !v)}
            title={terminalOpen ? '터미널 접기' : 'AI 도우미 터미널 열기'}
            aria-label={terminalOpen ? '터미널 접기' : 'AI 도우미 터미널 열기'}
          >
            <i className={`fa-solid ${terminalOpen ? 'fa-angles-right' : 'fa-terminal'}`}></i>
          </button>
          {terminalEverOpened && (
            <div className="terminal-body" style={{ display: terminalOpen ? 'flex' : 'none' }}>
              <AiTerminal active={terminalOpen} />
            </div>
          )}
        </section>
```
(주의: Playwright 테스트가 `getByRole('button', { name: /터미널/ })`로 토글을 찾으므로, 접힘 상태 토글 버튼의 `title`에 "터미널"이 포함돼야 한다 — 위 `title`이 이를 만족.)

- [ ] **Step 7: CSS 추가** — `src/index.css` 끝부분에 추가

```css
/* ─── AI 도우미 터미널 패널 ─────────────────────────────────────────────── */
.terminal-panel { position: relative; display: flex; flex-direction: column; min-height: 0; height: 100%; }
.terminal-panel[data-open="0"] { align-items: center; }
.terminal-resize-handle { position: absolute; left: -6px; top: 0; width: 10px; height: 100%; cursor: col-resize; z-index: 5; }
.terminal-toggle { align-self: flex-start; margin-bottom: 0.5rem; }
.terminal-panel[data-open="0"] .terminal-toggle { writing-mode: vertical-rl; height: auto; padding: 0.5rem 0.25rem; }
.terminal-body { flex: 1; min-height: 0; }
.ai-terminal { display: flex; flex-direction: column; height: 100%; background: #1a1815; border-radius: 8px; overflow: hidden; }
.ai-terminal-bar { display: flex; align-items: center; justify-content: space-between; padding: 0.35rem 0.6rem; background: #242019; color: #e8e3da; font-size: 0.8rem; }
.ai-terminal-title i { margin-right: 0.4rem; }
.ai-terminal-screen { flex: 1; min-height: 0; padding: 0.4rem; }
.ai-terminal-screen .xterm, .ai-terminal-screen .xterm-viewport { height: 100% !important; }
```

- [ ] **Step 8: Playwright 테스트 통과 확인**

Run: `npx playwright test tests/ai_terminal_ui.spec.js`
Expected: PASS — 열기 전 xterm 0개, 토글 후 1개.

- [ ] **Step 9: 회귀 게이트 확인(변환 코어 불변)**

Run: `npm run test:ir`
Expected: 기존과 동일하게 전부 PASS(이 기능은 IR 파이프라인을 건드리지 않음).

- [ ] **Step 10: 커밋**

```bash
git add vite.config.js src/App.jsx src/index.css tests/ai_terminal_ui.spec.js
git commit -m "feat(terminal): 편집기 오른쪽 터미널 패널(3열 그리드·접기/리사이즈) + Vite ws 프록시 + Playwright"
```

---

## 수동 검증 (자동화 불가 — 실행자가 사람에게 안내)

이 항목들은 CI/유닛으로 덮이지 않으므로 최종 리뷰 시 사람 검증을 요청한다:

1. **dev 실사용:** `npm start` → 앱에서 터미널 펼치기 → `echo hi` 및 (설치돼 있으면) `claude` 실행이 대화형으로 동작하는지.
2. **패키징 로드:** `npm run dist` 후 설치본 실행 → 터미널이 뜨는지. electron-builder가 node-pty를 Electron ABI로 리빌드했는지(`resources/app.asar.unpacked/node_modules/node-pty` 존재) 확인.
3. **코드 연동:** 편집기에서 Save한 `.py`가 터미널 cwd(워크스페이스)에 보이는지(`ls`/`dir`), 에이전트가 수정 후 파일탐색기에서 다시 열 수 있는지.

---

## Self-Review 결과

- **스펙 커버리지:** WS PTY(Task1) / xterm 컴포넌트(Task2) / 오른쪽 3열 레이아웃·접기·리사이즈·빈 셸·지연연결(Task3) / loopback 이중화(Task1 Step6+테스트) / 패키징 asarUnpack(Task1 Step8) / dev ws 프록시(Task3 Step3) / 코드연동 cwd(Task1 Step5) — 모두 태스크로 매핑됨.
- **플레이스홀더:** 없음(모든 코드 완전 기재).
- **타입/이름 일관성:** WS 프레임 `{t:'i',d}`/`{t:'r',cols,rows}`가 server(Task1)·AiTerminal(Task2)에서 동일. `terminalWsUrl` 시그니처가 헬퍼·컴포넌트·테스트에서 일치. localStorage 키(`blockpy.terminal.open/width`) 일관.
- **전제:** node-pty 네이티브 빌드(dev/Electron)와 에이전트 CLI 사전설치는 리스크로 명시, 수동 검증에 반영.

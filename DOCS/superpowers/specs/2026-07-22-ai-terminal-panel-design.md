# AI 도우미 터미널 패널 — 설계 문서

**작성일:** 2026-07-22
**대상:** BlockPy (React 19 + Vite 프론트 / Express `server.js` 백엔드 / Electron 데스크톱 패키징)

## 목표

편집기 오른쪽에 **진짜 대화형 터미널**을 붙여, 학생·교사가 그 안에서 코딩 에이전트
CLI(`claude`, `opencode` 등)나 임의의 셸 명령을 직접 실행할 수 있게 한다. 터미널의
작업 폴더는 기존 워크스페이스(파일탐색기 루트 = Run cwd)와 동일해, 에이전트가 학생이
저장한 `.py`를 읽고 수정하면 학생은 그 파일을 편집기로 다시 열어 블록으로 변환할 수 있다.

## 비목표 (YAGNI)

- 터미널 여러 개(탭) — v1은 1개.
- 앱 재시작 간 셸 세션 보존 — 매번 새 셸.
- 에이전트 자동 실행 / 빠른 실행 버튼 — 빈 셸만 띄우고 사용자가 직접 입력.
- 편집기의 **미저장 버퍼** 실시간 동기화 — v1은 저장된 파일만 공유(파일탐색기 흐름 재사용).
- 에이전트 CLI(`claude`/`opencode`) 자체 설치·번들 — 각 PC의 사전 설치 전제.

## 접근 방식

**node-pty(백엔드 PTY) + xterm.js(프론트 렌더) + WebSocket(중계).**

대안 비교:

| 방식 | 판정 |
|---|---|
| **node-pty + xterm + WebSocket** | ✅ 채택 — 진짜 터미널, dev/패키징 동일 동작, 표준 스택 |
| ttyd/wetty iframe 임베드 | ❌ 외부 바이너리 번들·패키징 부담 |
| `claude -p` 헤드리스 채팅 UI | ❌ 진짜 터미널이 아님(요청과 불일치) |

## 아키텍처

### 실행 환경

현재 PC에 설치된 BlockPy는 **패키징 Electron 데스크톱 앱**
(`%LOCALAPPDATA%\Programs\BlockPy\BlockPy.exe`, NSIS 사용자 설치)이다. `electron/main.cjs`가
**동일한 `server.js`**를 free 포트로 부팅하고 `http://127.0.0.1:<port>`를 로드하며, 렌더러는
`contextIsolation:true, nodeIntegration:false`인 순수 웹페이지다. 따라서 `server.js`에
WebSocket PTY 엔드포인트를 추가하면 **dev(`npm start`)와 패키징 앱 양쪽에서 그대로 동작**한다.

### 백엔드 (`server.js` 확장 + `ws`, `node-pty` 신규 의존성)

- `start()`의 `app.listen`가 반환하는 **동일 http 서버 인스턴스**에 `ws` WebSocketServer를
  `noServer` 모드로 부착하고, http 서버의 `upgrade` 이벤트에서 경로가 `/api/terminal`일 때만
  처리한다.
- **보안 이중화:** Express의 loopback Host 미들웨어는 WS 업그레이드에 적용되지 않으므로,
  업그레이드 핸들러에서 `Host` 헤더가 loopback(`127.0.0.1`/`localhost`/`::1`)인지 동일하게
  검사해 아니면 소켓을 파기한다. (서버는 이미 `127.0.0.1` 전용 바인딩 — DNS 리바인딩 방어용.)
- 연결 수립 시 `node-pty.spawn`으로 셸 프로세스 생성:
  - **셸:** Windows → `powershell.exe`(에이전트 CLI 친화적; 실패 시 `process.env.COMSPEC || 'cmd.exe'`),
    POSIX → `process.env.SHELL || 'bash'`.
  - **cwd:** `WORKSPACE_DIR` (run-python·파일탐색기와 동일).
  - **env:** `process.env` 계승 + `PYTHONIOENCODING=utf-8` + `BLOCKPY_TERMINAL=1` 마커
    (이 브랜치는 master 분기라 run-python에 `RUNTIME_DIR`/`PYTHONPATH` 배선이 없다 — 터미널도
    동일하게 넣지 않는다. tm 브랜치 병합 시 run-python과 함께 일괄 배선).
  - 초기 cols/rows는 클라이언트 첫 리사이즈 프레임 도착 전 기본값(80x24).
- **중계 규약(클라이언트→서버 메시지):**
  - 일반 키 입력: `{"t":"i","d":"<문자열>"}` → `pty.write(d)`.
  - 리사이즈: `{"t":"r","cols":<n>,"rows":<n>}` → `pty.resize(cols, rows)`.
  - 그 외/파싱 실패 프레임은 무시(로그만).
- **중계(서버→클라이언트):** `pty.onData(chunk => ws.send(chunk))` (UTF-8 문자열).
- **수명주기:** ws `close`/`error` → `pty.kill()`. `pty.onExit` → `ws.close()`.
  한 ws 연결당 PTY 1개.

### 프론트엔드 (`src/components/AiTerminal.jsx` 신규 + `@xterm/xterm`, `@xterm/addon-fit`)

- `xterm.js` `Terminal` + `FitAddon`. 컨테이너 div에 `open()` 후 `fit()`.
- **WS 연결:** 상대 경로로 URL 구성 —
  `new URL('/api/terminal', window.location.href)`의 `protocol`을 `http→ws`, `https→wss`로
  바꿔 연결. dev는 Vite ws 프록시, 패키징은 same-origin으로 모두 자동 처리.
- **지연 연결:** 패널이 처음 보일 때(마운트 시) 연결. 앱 로드만으로 셸을 띄우지 않는다.
- **입출력:** `term.onData(d => ws.send(JSON.stringify({t:'i',d})))`;
  `ws.onmessage = e => term.write(e.data)`.
- **리사이즈:** `ResizeObserver` + `FitAddon.fit()` 후 `{t:'r',cols,rows}` 전송(디바운스).
- **재연결:** ws가 끊기면 터미널에 안내 문구 출력 + "다시 연결" 버튼(수동 재연결). 자동 재연결 X.
- CSS: `@xterm/xterm/css/xterm.css`를 컴포넌트에서 import(Vite 번들).

### 레이아웃 (`src/App.jsx`, CSS)

- `dashboard-grid`를 **`좌측 패널 | 편집기 | 터미널 패널`** 3열로 확장.
- 터미널 패널은 **접기/펼치기 토글** + **너비 드래그 리사이즈** 지원, 기본 너비 ~380px,
  접으면 얇은 토글 스트립만 남긴다. 접힘/너비 상태는 `localStorage`에 저장.
- 접혀 있을 때는 WS를 연결하지 않는다(펼칠 때 최초 연결, 이후 유지).

### 의존성 / 빌드

- 신규: `node-pty`(백엔드 네이티브), `ws`(백엔드), `@xterm/xterm` + `@xterm/addon-fit`(프론트).
- `@xterm/*`는 일반 ESM import → Vite가 `dist`로 번들(vendor 단계 불필요).
- **Vite 프록시:** `vite.config.js`의 `/api` 프록시에 `ws: true` 추가(dev에서 WS 프록시).
- **패키징:** `package.json` `build.asarUnpack`에 `node-pty`를 추가(네이티브 `.node`가 asar
  밖에서 로드되도록; 기존 `blockpy-gen`과 동일 패턴). `npm run dist` 시 electron-builder가
  Electron ABI로 `node-pty`를 자동 리빌드한다.

## 데이터 흐름 (코드 연동)

```
편집기 코드 --Save(/api/fs)--> 워크스페이스 폴더의 .py
                                     ^                |
터미널(cwd=워크스페이스): claude 실행 → 이 .py 읽기/수정
                                     |                v
학생: 파일탐색기에서 파일 다시 열기 → 편집기 로드 → 블록 변환
```

미저장 버퍼 실시간 전달은 v1 제외. 저장 파일 기반이라 기존 파일탐색기/Run cwd 모델과
그대로 맞물린다.

## 오류 처리

- **셸 spawn 실패**(경로/권한): 터미널에 `[셸을 시작할 수 없습니다: <메시지>]` 출력 후 ws close.
- **에이전트 CLI 미설치:** 셸이 정상 동작하되 `claude` 입력 시 OS의 "명령을 찾을 수 없음"이
  그대로 표시됨(정상 동작, 별도 처리 없음).
- **WS 조기 종료:** 프론트에서 안내 + 수동 "다시 연결" 버튼.
- **loopback 아닌 업그레이드 요청:** 소켓 즉시 파기(응답 없이).

## 보안

- 서버는 이미 `127.0.0.1` 전용 바인딩 + 비루프백 Host 거부(HTTP). WS 업그레이드에도 동일
  Host 검사를 명시적으로 적용.
- 셸은 임의 명령 실행이 가능하지만, 이는 기존 `run-python`/`pip`/`fs` 엔드포인트와 **동일한
  로컬 단일 사용자 신뢰 모델** 안이며 새로운 노출 등급을 만들지 않는다.
- 공용 서버 다중 접속 시나리오는 이 설계의 범위 밖(별도 격리 설계 필요).

## 테스트 전략

- **백엔드(Node, 통합):** 서버를 임의 포트로 띄우고 `ws`로 `/api/terminal`에 접속 → 첫
  리사이즈 프레임 전송 → 플랫폼 셸에 `echo`류 명령 입력 → 출력에 기대 문자열이 오는지 확인.
  ws close 후 자식 프로세스가 정리되는지 확인. 비루프백 Host 업그레이드가 거부되는지 확인.
- **프론트(Playwright):** 터미널 패널 토글 표시/숨김, 컨테이너에 xterm이 렌더되는지, 접힘
  상태에서 WS 미연결인지(네트워크 관찰) 확인. (실셸 상호작용은 백엔드 테스트가 담당.)
- **기존 게이트 불변:** IR 파이프라인/변환 코어(`irToBlockly.js`/`blocklyToIr.js`/`irBlocks.js`)는
  일절 건드리지 않으므로 `test:ir`·`test:gen`은 그대로 통과해야 한다.

## 전제 / 리스크

1. **에이전트 CLI는 각 PC에 사전 설치**(앱 번들 아님). 문서화만.
2. **node-pty 네이티브 빌드가 두 갈래** — dev(시스템 Node, `npm install` 시 빌드/프리빌드)와
   패키징(Electron ABI, electron-builder 리빌드). 계획에 각 환경 로딩 검증 단계를 포함한다.

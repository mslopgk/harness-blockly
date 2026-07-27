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
  const roRef = useRef(null);
  const wheelRef = useRef(null);   // alt-screen 휠→방향키 리스너 {el, fn} (언마운트 시 해제)
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
    // 초기화를 다음 매크로태스크로 미룬다(setTimeout 0) — dev 의 React.StrictMode 는 마운트
    // 이펙트를 mount→cleanup→mount 로 2번 실행해 부작용을 검사하는데, xterm Terminal.open()
    // 이 내부적으로 setTimeout(0) 로 뷰포트 동기화를 예약한다. 여기서 동기적으로 생성해버리면
    // StrictMode 의 "가짜" 첫 마운트가 만든 Terminal 이 같은 틱에서 dispose 된 뒤, 그 예약된
    // 콜백이 나중에 실행되며 이미 해제된 인스턴스를 건드려 크래시한다("Cannot read properties
    // of undefined (reading 'dimensions')"). 실제 초기화를 한 틱 미루고 cleanup 에서 취소하면
    // StrictMode 의 가짜 마운트는 아무것도 생성하지 않고 끝나고, 실제 마운트에서만 1회 생성된다.
    let cancelled = false;
    const timer = setTimeout(() => {
      if (cancelled) return;
      const term = new Terminal({
        // 디자인 v2: 코드 폰트 스택(index.css --font-mono)과 동일 — 오프라인 시스템 폰트만.
        fontFamily: 'D2Coding, Consolas, Menlo, ui-monospace, monospace', fontSize: 13,
        cursorBlink: true, convertEol: false,
        // 스크롤백: xterm 기본값은 1000줄이라 AI 에이전트 로그처럼 출력이 많으면 금방 잘려
        // "위로 스크롤이 안 된다"고 느끼게 된다. 10000줄로 늘린다(줄당 수백 바이트라 메모리 영향 미미).
        scrollback: 10000,
        // 쿨 슬레이트 다크. index.css 의 --term-bg / --term-ink 와 1:1 로 맞춘 값이다
        // (xterm 은 canvas 렌더러라 CSS 변수를 읽지 못해 여기서만 리터럴로 둔다).
        theme: { background: '#171b23', foreground: '#e8ebf1' },
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

      // ── alt screen(대체 화면 버퍼)에서 휠 스크롤 ────────────────────────────────
      // AI 에이전트(claude/opencode 등)나 vim 같은 TUI 는 alt screen 을 쓰는데, 이 모드에는
      // 터미널 스크롤백이 **존재하지 않는다**(실측: scrollHeight == clientHeight, 휠 무반응).
      // 표준 터미널들이 하는 대로, alt screen 에서는 휠을 방향키로 바꿔 앱에 전달해 앱 자체가
      // 스크롤하게 한다. 일반 화면에서는 xterm 기본 스크롤백 동작을 그대로 둔다.
      // (앱이 마우스 리포팅을 켠 경우 xterm 이 휠을 마우스 이벤트로 이미 보내므로 건드리지 않는다.)
      const onWheel = (ev) => {
        const t = termRef.current;
        if (!t || t.buffer.active.type !== 'alternate') return;   // 일반 화면 → 기본 동작
        if (t.modes && t.modes.mouseTrackingMode !== 'none') return; // 앱이 휠을 직접 받음
        ev.preventDefault();
        const lines = Math.max(1, Math.min(5, Math.round(Math.abs(ev.deltaY) / 40) || 1));
        const seq = ev.deltaY < 0 ? '\x1bOA' : '\x1bOB';           // 위/아래 방향키
        const ws = wsRef.current;
        if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ t: 'i', d: seq.repeat(lines) }));
      };
      screenRef.current.addEventListener('wheel', onWheel, { passive: false });
      wheelRef.current = { el: screenRef.current, fn: onWheel };

      // RO 는 최초 초기화 시 한 번만 만들고 ref 에 보관한다 — [active] 재실행(fold/unfold)마다
      // disconnect 하면 재생성 없이 영구히 죽어버린다(termRef.current 가드에 막혀 재생성 안 됨).
      const ro = new ResizeObserver(() => { try { fit.fit(); sendResize(); } catch (_) {} });
      ro.observe(screenRef.current);
      roRef.current = ro;
      connect();
    }, 0);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [active]);

  // 패널이 다시 보일 때 크기 재적합
  useEffect(() => { if (active && fitRef.current) { try { fitRef.current.fit(); sendResize(); } catch (_) {} } }, [active]);

  // 실제 언마운트 시에만 정리(RO/WS/Terminal 해제). [active] 효과와 분리 — fold/unfold 로는
  // 절대 실행되지 않는다. Task 3 는 <AiTerminal> 을 열린 뒤 계속 마운트해두고 active/CSS 만
  // 토글하므로, 이 정리는 앱 종료(언마운트) 시에만 실행된다.
  useEffect(() => () => {
    try { roRef.current?.disconnect(); } catch (_) {}
    try { wheelRef.current?.el.removeEventListener('wheel', wheelRef.current.fn); } catch (_) {}
    try { wsRef.current?.close(); } catch (_) {}
    try { termRef.current?.dispose(); } catch (_) {}
  }, []);

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

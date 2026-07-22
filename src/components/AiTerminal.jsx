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

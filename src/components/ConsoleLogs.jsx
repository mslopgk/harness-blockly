import React, { useEffect, useRef } from 'react';

export default function ConsoleLogs({ logs, onClearConsole }) {
  const containerRef = useRef(null);

  // Auto-scroll to bottom of logs on new logs
  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="console-card">
      <div className="panel-header">
        <div className="panel-title-group">
          <i className="fa-solid fa-terminal icon-green"></i>
          <h3>실행 출력</h3>
        </div>
        <button 
          className="btn btn-secondary btn-sm" 
          id="btn-clear-console"
          onClick={onClearConsole}
          title="출력 내용을 모두 지웁니다"
        >
          <i className="fa-solid fa-trash-can"></i> 지우기
        </button>
      </div>
      <div 
        ref={containerRef}
        id="console-logs" 
        className="console-body"
      >
        {logs.map((log, idx) => {
          let logClass = 'log-line output';
          if (log.startsWith('[Runtime Error]') || log.startsWith('[Parser Error]')) {
            logClass = 'log-line error';
          } else if (log.startsWith('[System]') || log.startsWith('[Sync-Engine]')) {
            logClass = 'log-line system';
          } else if (log.startsWith('[Library Call]') || log.startsWith('[AI Agent]')) {
            logClass = 'log-line executing';
          }
          return (
            <div key={idx} className={logClass}>
              {log}
            </div>
          );
        })}
      </div>
    </div>
  );
}

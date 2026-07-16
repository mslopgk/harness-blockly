import React, { useState } from 'react';

// 로봇 연결 UI (좌측 "Robot" 탭) — 순수 화면 전용.
// 백엔드 호출 없음(fetch 없음), 가짜 데이터 없음. 로컬 상태로 상호작용만 보여준다.
// 실제 배선(포트 조회 / 연결 / 해제)은 아래 주석 지점에 나중에 연결한다.

const DEVICES = [
  { id: 'lite', label: 'Magician Lite (팔)' },
  { id: 'go', label: 'Magician GO (카)' },
];

export default function RobotConnect() {
  const [device, setDevice] = useState('lite');
  const [port, setPort] = useState('');
  const [connected, setConnected] = useState(false);
  const [connectedPort, setConnectedPort] = useState(null);

  const connect = () => {
    if (!port.trim()) return;
    // TODO(백엔드 배선): 실제 연결 요청. 지금은 화면 상태만 토글.
    setConnected(true);
    setConnectedPort(port.trim());
  };

  const disconnect = () => {
    // TODO(백엔드 배선): 실제 연결 해제 요청. 지금은 화면 상태만 토글.
    setConnected(false);
    setConnectedPort(null);
  };

  return (
    <div className="robot-connect-panel" style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 14 }}>
      {/* 상태 */}
      <div>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>로봇 연결</div>
        <div id="robot-status" style={{ fontSize: 13 }}>
          {connected ? (
            <span style={{ color: '#178a4c' }}>
              <i className="fa-solid fa-circle" style={{ fontSize: 8, marginRight: 6 }}></i>
              연결됨{connectedPort ? ` — ${connectedPort}` : ''}
            </span>
          ) : (
            <span style={{ opacity: 0.7 }}>
              <i className="fa-regular fa-circle" style={{ fontSize: 8, marginRight: 6 }}></i>
              연결 안 됨
            </span>
          )}
        </div>
      </div>

      {/* 기기 유형 */}
      <div>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>기기 유형</div>
        <div style={{ display: 'flex', gap: 8 }}>
          {DEVICES.map((d) => (
            <button
              key={d.id}
              id={`robot-device-${d.id}`}
              className={`btn btn-sm ${device === d.id ? 'btn-primary' : 'btn-secondary'}`}
              aria-pressed={device === d.id}
              onClick={() => setDevice(d.id)}
              disabled={connected}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>

      {/* 포트 (백엔드 배선 전이라 직접 입력; 배선 시 드롭다운으로 대체) */}
      <div>
        <div style={{ fontWeight: 600, marginBottom: 6 }}>포트</div>
        {/* TODO(백엔드 배선): 포트 목록을 조회해 드롭다운으로 교체 */}
        <input
          id="robot-port-input"
          type="text"
          value={port}
          onChange={(e) => setPort(e.target.value)}
          placeholder="예: COM5"
          disabled={connected}
          style={{ width: '100%', padding: '6px 8px', boxSizing: 'border-box' }}
        />
      </div>

      {/* 연결 / 해제 */}
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          id="robot-connect-btn"
          className="btn btn-primary"
          onClick={connect}
          disabled={!port.trim() || connected}
          style={{ flex: 1 }}
        >
          <i className="fa-solid fa-plug"></i> 연결
        </button>
        <button
          id="robot-disconnect-btn"
          className="btn btn-secondary"
          onClick={disconnect}
          disabled={!connected}
          style={{ flex: 1 }}
        >
          <i className="fa-solid fa-plug-circle-xmark"></i> 연결 해제
        </button>
      </div>

      <div style={{ fontSize: 12, opacity: 0.6 }}>
        ※ 화면 전용 — 아직 실제 연결은 되지 않습니다(백엔드 배선 예정).
      </div>
    </div>
  );
}

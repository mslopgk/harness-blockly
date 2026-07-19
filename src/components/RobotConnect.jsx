import React, { useState, useEffect, useCallback } from 'react';

// 로봇 연결 UI (좌측 "Robot" 탭). 백엔드 /api/robot/* (dobotkit + DobotLink)로 실제 배선됨.
//  - 포트 조회: DobotLink SearchDobot 결과를 드롭다운으로.
//  - 연결: 장치 연결 + 상태 읽기(팔=pose, 카=battery)로 링크 검증.
//  - 해제: DisconnectDobot.
// 전제: DobotLink.exe 실행. 미실행/오류는 백엔드가 {ok:false,error,hint}로 돌려주며 화면에 표시.
// 연결 상태는 onConnectedChange로 상위(App)에 올려, 캘리브레이션 이동이 같은 포트를 쓰게 한다.

const DEVICES = [
  { id: 'lite', label: 'Magician Lite (팔)' },
  { id: 'go', label: 'Magician GO (카)' },
];

async function postJson(url, body) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
  try { return await r.json(); } catch (_) { return { ok: false, error: `서버 응답 오류 (${r.status})` }; }
}

// 상태 객체(팔 pose / 카 battery)를 한 줄 요약으로.
function summarizeStatus(device, status) {
  if (!status) return '';
  if (device === 'go' && status.battery) {
    const b = status.battery;
    const pct = typeof b.powerPercentage === 'number' ? Math.round(b.powerPercentage * 100) : null;
    const v = typeof b.powerVoltage === 'number' ? b.powerVoltage.toFixed(1) : null;
    return `배터리 ${pct != null ? pct + '%' : ''}${v ? ` · ${v}V` : ''}`.trim();
  }
  if (status.pose && typeof status.pose.x === 'number') {
    const p = status.pose;
    return `현재 위치 x${Math.round(p.x)} y${Math.round(p.y)} z${Math.round(p.z)}`;
  }
  return '';
}

export default function RobotConnect({ onConnectedChange }) {
  const [device, setDevice] = useState('lite');
  const [ports, setPorts] = useState([]);
  const [port, setPort] = useState('');
  const [loadingPorts, setLoadingPorts] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [connected, setConnected] = useState(false);
  const [connectedPort, setConnectedPort] = useState(null);
  const [statusLine, setStatusLine] = useState('');
  const [error, setError] = useState('');

  const notify = useCallback((conn) => {
    if (typeof onConnectedChange === 'function') onConnectedChange(conn);
  }, [onConnectedChange]);

  const fetchPorts = useCallback(async (dev) => {
    setLoadingPorts(true);
    setError('');
    const j = await postJson('/api/robot/ports', { device: dev });
    setLoadingPorts(false);
    if (j.ok && Array.isArray(j.ports)) {
      setPorts(j.ports);
      // 아직 포트 미선택이면 첫 포트를 기본 선택.
      setPort((prev) => prev || (j.ports[0] || ''));
      if (j.ports.length === 0) setError('연결 가능한 포트가 없습니다. 로봇 전원/USB와 DobotLink 연결을 확인하세요.');
    } else {
      setPorts([]);
      setError((j.error || '포트 조회 실패') + (j.hint ? ` — ${j.hint}` : ''));
    }
  }, []);

  // 탭 진입 / 기기 유형 변경 시 포트 조회(읽기 전용). 연결 중에는 재조회하지 않는다.
  useEffect(() => {
    if (connected) return;
    fetchPorts(device);
  }, [device, connected, fetchPorts]);

  const connect = async () => {
    if (!port.trim() || connecting) return;
    setConnecting(true);
    setError('');
    const j = await postJson('/api/robot/connect', { device, port: port.trim() });
    setConnecting(false);
    if (j.ok) {
      const p = j.port || port.trim();
      setConnected(true);
      setConnectedPort(p);
      setStatusLine(summarizeStatus(device, j.status));
      notify({ connected: true, device, port: p });
    } else {
      setError((j.error || '연결 실패') + (j.hint ? ` — ${j.hint}` : ''));
    }
  };

  const disconnect = async () => {
    setConnecting(true);
    await postJson('/api/robot/disconnect', { device, port: connectedPort || port });
    setConnecting(false);
    setConnected(false);
    setConnectedPort(null);
    setStatusLine('');
    notify({ connected: false, device, port: null });
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
              연결됨{connectedPort ? ` — ${connectedPort}` : ''}{statusLine ? ` · ${statusLine}` : ''}
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
              onClick={() => { setDevice(d.id); setPort(''); }}
              disabled={connected || connecting}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>

      {/* 포트: DobotLink 조회 결과 드롭다운 + 새로고침 + 수동 입력 폴백 */}
      <div>
        <div style={{ fontWeight: 600, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
          포트
          <button
            id="robot-ports-refresh"
            className="btn btn-secondary btn-xs"
            onClick={() => fetchPorts(device)}
            disabled={connected || loadingPorts}
            title="DobotLink에서 포트 다시 조회"
          >
            <i className={`fa-solid fa-rotate ${loadingPorts ? 'fa-spin' : ''}`}></i> 조회
          </button>
        </div>
        {ports.length > 0 && (
          <select
            id="robot-port-select"
            value={ports.includes(port) ? port : ''}
            onChange={(e) => setPort(e.target.value)}
            disabled={connected || connecting}
            style={{ width: '100%', padding: '6px 8px', boxSizing: 'border-box', marginBottom: 6 }}
          >
            <option value="" disabled>포트 선택…</option>
            {ports.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        )}
        <input
          id="robot-port-input"
          type="text"
          value={port}
          onChange={(e) => setPort(e.target.value)}
          placeholder={loadingPorts ? '포트 조회 중…' : '예: COM8 (팔) / COM5 (카)'}
          disabled={connected || connecting}
          style={{ width: '100%', padding: '6px 8px', boxSizing: 'border-box' }}
        />
      </div>

      {/* 연결 / 해제 */}
      <div style={{ display: 'flex', gap: 8 }}>
        <button
          id="robot-connect-btn"
          className="btn btn-primary"
          onClick={connect}
          disabled={!port.trim() || connected || connecting}
          style={{ flex: 1 }}
        >
          <i className={`fa-solid ${connecting ? 'fa-spinner fa-spin' : 'fa-plug'}`}></i> {connecting && !connected ? '연결 중…' : '연결'}
        </button>
        <button
          id="robot-disconnect-btn"
          className="btn btn-secondary"
          onClick={disconnect}
          disabled={!connected || connecting}
          style={{ flex: 1 }}
        >
          <i className="fa-solid fa-plug-circle-xmark"></i> 연결 해제
        </button>
      </div>

      {error && (
        <div id="robot-error" style={{ fontSize: 12.5, color: '#c0392b', lineHeight: 1.5 }}>
          <i className="fa-solid fa-triangle-exclamation" style={{ marginRight: 6 }}></i>{error}
        </div>
      )}
      <div style={{ fontSize: 12, opacity: 0.6 }}>
        ※ DobotLink.exe가 실행 중이어야 합니다. 팔은 보통 COM8, 카는 COM5 계열입니다(자동 선택이 어긋나면 직접 지정).
      </div>
    </div>
  );
}

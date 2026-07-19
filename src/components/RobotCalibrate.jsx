import React, { useState, useRef, useEffect, useCallback } from 'react';
import { estimateAffine, reprojectionError } from '../utils/affineCalib';
import defaultCalib from '../data/robotCalib.default.json';

// 카메라↔로봇 캘리브레이션 UI (Robot 탭). 프론트 전용.
//  - 기본: 저장/동봉 캘리값 자동 로드 → 학생 무작업.
//  - 재보정(접근 1): 로봇이 알려진 프리셋으로 스스로 이동[훅] → 화면에서 엔드이펙터 클릭
//    → (픽셀↔로봇 mm) 대응 → 아핀 2x3 풀이 → 저장. 조깅 없음.
//
// dobotkit 미확정 → 로봇 실제 이동은 onMoveToPreset 훅 하나로만 남긴다(기본=스텁).
// 저장값을 학생 파이썬이 읽어 쓰는 소비부도 dobotkit 확정 후 배선.

const STORAGE_KEY = 'blockpy.robotCalib.v1';
const PRESETS = defaultCalib.presets || [[200, -80], [200, 80], [300, 80], [300, -80]];

// 로드 우선순위: localStorage(사용자 재보정 저장값) > 동봉 seed > 미측정.
function loadCalib() {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const j = JSON.parse(raw);
      if (j && Array.isArray(j.M)) return { M: j.M, measured: true, pairs: j.pairs || [], source: 'saved' };
    }
  } catch (_) { /* localStorage 불가/파싱 실패 → seed 로 폴백 */ }
  if (defaultCalib && Array.isArray(defaultCalib.M)) {
    return { M: defaultCalib.M, measured: true, pairs: defaultCalib.pairs || [], source: 'seed' };
  }
  return { M: null, measured: false, pairs: [], source: 'none' };
}

function saveCalib(M, pairs) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, M, pairs }));
}

// 기본 스텁: 팔 미연결. 실제로 로봇을 움직이지 않고 즉시 반환한다.
// onMoveToPreset(preset, meta) — meta.first=true면 이동 전에 원점복귀(홈).
async function stubMove(preset, _meta) {
  console.warn('[RobotCalibrate] onMoveToPreset 미연결 (팔 연결 대기):', preset);
  return { moved: false };
}

export default function RobotCalibrate({ onMoveToPreset }) {
  const robotWired = typeof onMoveToPreset === 'function';
  const move = robotWired ? onMoveToPreset : stubMove;

  const [calib, setCalib] = useState(loadCalib);          // {M, measured, pairs, source}
  const [mode, setMode] = useState('idle');               // 'idle' | 'capturing' | 'solved'
  const [stepIndex, setStepIndex] = useState(0);
  const [pairs, setPairs] = useState([]);                 // [[ [u,v],[x,y] ], ...]
  const [lastPixel, setLastPixel] = useState(null);       // [u,v] 마지막 클릭(표시용)
  const [solved, setSolved] = useState(null);             // {M, err:{mean,max}}
  const [error, setError] = useState('');
  const [camError, setCamError] = useState('');

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const wrapRef = useRef(null);

  // ── 웹캠 스트림: 'capturing' 동안만 켠다(패널 보기만으로 카메라 권한 요구 안 함) ──
  useEffect(() => {
    let cancelled = false;
    if (mode !== 'capturing') return undefined;
    setCamError('');
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setCamError('이 환경에서 카메라를 쓸 수 없습니다(getUserMedia 미지원).');
      return undefined;
    }
    navigator.mediaDevices.getUserMedia({ video: true })
      .then((stream) => {
        if (cancelled) { stream.getTracks().forEach((t) => t.stop()); return; }
        streamRef.current = stream;
        if (videoRef.current) {
          videoRef.current.srcObject = stream;
          videoRef.current.play().catch(() => {});
        }
      })
      .catch(() => { if (!cancelled) setCamError('카메라를 열 수 없습니다(권한 거부 또는 장치 없음).'); });
    return () => {
      cancelled = true;
      if (streamRef.current) {
        streamRef.current.getTracks().forEach((t) => t.stop());
        streamRef.current = null;
      }
    };
  }, [mode]);

  const startRecalib = useCallback(async () => {
    setPairs([]);
    setLastPixel(null);
    setSolved(null);
    setError('');
    setStepIndex(0);
    setMode('capturing');
    // 첫 프리셋: home=true (원점복귀 후 이동)로 절대좌표 신뢰성 확보.
    try { await move(PRESETS[0], { first: true }); } catch (_) { /* 이동 실패는 진행을 막지 않음(advisory) */ }
  }, [move]);

  const cancel = useCallback(() => {
    setMode('idle');
    setPairs([]);
    setLastPixel(null);
    setSolved(null);
    setError('');
  }, []);

  const resetToDefault = useCallback(() => {
    try { window.localStorage.removeItem(STORAGE_KEY); } catch (_) { /* noop */ }
    setCalib(loadCalib());
    cancel();
  }, [cancel]);

  // 화면 클릭 → 프레임 픽셀 좌표(표시 크기와 실제 프레임 크기 스케일 보정) → 현재 프리셋과 대응 기록.
  const onCanvasClick = useCallback(async (e) => {
    if (mode !== 'capturing') return;
    const wrap = wrapRef.current;
    const vid = videoRef.current;
    if (!wrap) return;
    const rect = wrap.getBoundingClientRect();
    const dx = e.clientX - rect.left;
    const dy = e.clientY - rect.top;
    const fw = (vid && vid.videoWidth) ? vid.videoWidth : rect.width;
    const fh = (vid && vid.videoHeight) ? vid.videoHeight : rect.height;
    const u = rect.width ? (dx * fw) / rect.width : dx;
    const v = rect.height ? (dy * fh) / rect.height : dy;
    const pixel = [Math.round(u), Math.round(v)];
    setLastPixel(pixel);

    const preset = PRESETS[stepIndex];
    const nextPairs = [...pairs, [pixel, preset]];
    setPairs(nextPairs);

    const nextIndex = stepIndex + 1;
    if (nextIndex < PRESETS.length) {
      setStepIndex(nextIndex);
      try { await move(PRESETS[nextIndex], { first: false }); } catch (_) { /* advisory */ }
    } else {
      // 마지막 점 → 풀이
      try {
        const M = estimateAffine(nextPairs);
        const err = reprojectionError(M, nextPairs);
        setSolved({ M, err });
        setMode('solved');
        setError('');
      } catch (ex) {
        setError(ex.message || '아핀 풀이 실패');
        // capturing 유지 — 사용자가 취소/다시 하도록
      }
    }
  }, [mode, stepIndex, pairs, move]);

  const saveSolved = useCallback(() => {
    if (!solved) return;
    try {
      saveCalib(solved.M, pairs);
      setCalib({ M: solved.M, measured: true, pairs, source: 'saved' });
      setMode('idle');
    } catch (_) {
      setError('저장 실패(localStorage 불가) — 이번 세션에만 적용됩니다.');
      setCalib({ M: solved.M, measured: true, pairs, source: 'session' });
      setMode('idle');
    }
  }, [solved, pairs]);

  // ── 렌더 ──
  const statusLine = calib.measured
    ? `고정 캘리브레이션 사용 중${calib.pairs && calib.pairs.length
        ? ` · 오차 ${reprojectionError(calib.M, calib.pairs).mean.toFixed(1)}mm` : ''}`
    : '미측정 — 최초 1회 재보정이 필요합니다.';

  return (
    <div className="robot-calibrate-panel" style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12, borderTop: '1px solid rgba(0,0,0,0.08)' }}>
      <div style={{ fontWeight: 600 }}>캘리브레이션</div>
      <div id="calib-status" style={{ fontSize: 13, opacity: calib.measured ? 1 : 0.85, color: calib.measured ? 'inherit' : '#b45309' }}>
        {statusLine}
      </div>

      {mode === 'idle' && (
        <div style={{ display: 'flex', gap: 8 }}>
          <button id="calib-start" className="btn btn-primary btn-sm" onClick={startRecalib}>
            <i className="fa-solid fa-crosshairs"></i> 재보정 시작
          </button>
          <button id="calib-reset" className="btn btn-secondary btn-sm" onClick={resetToDefault}>초기화</button>
        </div>
      )}

      {mode === 'capturing' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span id="calib-step">점 {stepIndex + 1}/{PRESETS.length} · 로봇 ({PRESETS[stepIndex][0]}, {PRESETS[stepIndex][1]})</span>
            <span id="calib-robot-badge" style={{ fontSize: 11, padding: '1px 6px', borderRadius: 8, background: robotWired ? '#dcfce7' : '#fee2e2', color: robotWired ? '#166534' : '#991b1b' }}>
              {robotWired ? '로봇 이동됨' : '로봇 미연결(dobotkit 대기)'}
            </span>
          </div>
          <div style={{ fontSize: 12, opacity: 0.7 }}>화면에서 <b>엔드이펙터(집게 끝)</b>를 클릭하세요.</div>
          {camError ? (
            <div id="calib-cam-error" style={{ color: '#c0392b', fontSize: 13 }}>{camError}</div>
          ) : (
            <div
              ref={wrapRef}
              id="calib-video-wrap"
              onClick={onCanvasClick}
              style={{ position: 'relative', width: '100%', maxWidth: 360, aspectRatio: '4 / 3', background: '#000', cursor: 'crosshair', borderRadius: 6, overflow: 'hidden' }}
            >
              <video ref={videoRef} muted playsInline style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }} />
            </div>
          )}
          {lastPixel && (
            <div style={{ fontSize: 12, opacity: 0.75 }}>
              마지막 클릭: 픽셀({lastPixel[0]}, {lastPixel[1]}) · 기록 {pairs.length}/{PRESETS.length}
            </div>
          )}
          {error && <div id="calib-error" style={{ color: '#c0392b', fontSize: 13 }}>{error}</div>}
          <div style={{ display: 'flex', gap: 8 }}>
            <button id="calib-cancel" className="btn btn-secondary btn-sm" onClick={cancel}>취소</button>
          </div>
        </div>
      )}

      {mode === 'solved' && solved && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div id="calib-solved" style={{ fontSize: 13, color: '#166534' }}>
            풀이 완료 · 재투영 오차 평균 {solved.err.mean.toFixed(1)}mm / 최대 {solved.err.max.toFixed(1)}mm
          </div>
          <div style={{ fontSize: 11, fontFamily: 'monospace', opacity: 0.7 }}>
            M = [[{solved.M[0].map((n) => n.toFixed(3)).join(', ')}], [{solved.M[1].map((n) => n.toFixed(3)).join(', ')}]]
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button id="calib-save" className="btn btn-primary btn-sm" onClick={saveSolved}>저장</button>
            <button id="calib-redo" className="btn btn-secondary btn-sm" onClick={startRecalib}>다시</button>
            <button id="calib-cancel2" className="btn btn-secondary btn-sm" onClick={cancel}>취소</button>
          </div>
        </div>
      )}
    </div>
  );
}

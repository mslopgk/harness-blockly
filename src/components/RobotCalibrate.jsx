import React, { useState, useRef, useEffect, useCallback } from 'react';
import { estimateAffine, reprojectionError } from '../utils/affineCalib';
import defaultCalib from '../data/robotCalib.default.json';

// 카메라↔로봇 캘리브레이션 UI (Robot 탭). 프론트 전용.
//
// ── eye-in-hand(팔 끝 카메라) 2단계 방식 ─────────────────────────────────────
// 카메라가 엔드이펙터에 붙어 팔과 함께 움직이므로, "팔을 옮기며 엔드이펙터를 클릭"하는
// 고정카메라(eye-to-hand) 방식은 클릭 픽셀이 항상 같은 자리에 뭉쳐 아핀이 퇴화한다.
// 대신:
//   1단계(표시): 팔이 프리셋 4곳을 순서대로 '가리킨다'(낮은 markZ). 학생이 그 지점 매트에
//                스티커를 붙인다 → 각 스티커의 로봇좌표가 확정된다.
//   2단계(관측): 팔이 '관측 자세'(고정, 높은 observation)로 이동해 멈춘다. 카메라가 4개
//                스티커를 모두 본다. 학생이 스티커(또는 그 위 블록)를 화면에서 클릭한다
//                → (픽셀 ↔ 로봇좌표) 대응이 화면 전체로 넓게 퍼져 아핀이 잘 풀린다.
// 관측 자세에서의 픽셀→로봇 아핀 하나면 충분하다(검출도 항상 같은 관측 자세에서 하므로).
//
// markZ / observation 은 리그별로 다르니 robotCalib.default.json 에서 튜닝한다.

const STORAGE_KEY = 'blockpy.robotCalib.v1';
const PRESETS = defaultCalib.presets || [[200, -80], [200, 80], [300, 80], [300, -80]];
const MARK_Z = typeof defaultCalib.markZ === 'number' ? defaultCalib.markZ : 0;
const OBSERVATION = Array.isArray(defaultCalib.observation) ? defaultCalib.observation : [250, 0, 120];

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

// 계약 4 — 보정값을 워크스페이스(robot_calib.json)로도 내보낸다. runtime/robotvision.py 가 이 파일을
// 읽어 픽셀→로봇 좌표를 변환하므로, 파이썬이 observation/markZ 까지 알아야 한다.
// localStorage 저장은 그대로 둔다(백엔드가 꺼져 있어도 화면은 동작해야 한다) — 여기 실패는 전부 무시.
function pushCalibToBackend(M, pairs, measured) {
  try {
    fetch('/api/robot/calib', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        version: 1,
        measured: !!measured,
        M,
        pairs: pairs || [],
        observation: OBSERVATION,
        markZ: MARK_Z,
      }),
    }).catch(() => {});
  } catch (_) { /* fetch 미지원/차단 환경 — 화면 동작에 영향 없음 */ }
}

// App(계약 1 상태 송출)이 이 패널을 열지 않고도 보정 준비 여부를 알 수 있게 하는 읽기 전용 스냅샷.
// 알 수 없으면 null(→ 상태에서 calib 키를 통째로 뺀다).
export function calibReadySnapshot() {
  try { return !!loadCalib().measured; } catch (_) { return null; }
}

// 기본 스텁: 팔 미연결. 실제로 로봇을 움직이지 않고 즉시 반환한다.
// onMoveToPreset([x,y], meta) — meta.first=true면 이동 전 홈, meta.z=목표 z(mm).
async function stubMove(preset, _meta) {
  console.warn('[RobotCalibrate] onMoveToPreset 미연결 (팔 연결 대기):', preset);
  return { moved: false };
}

export default function RobotCalibrate({ onMoveToPreset, onCalibChange }) {
  const robotWired = typeof onMoveToPreset === 'function';
  const move = robotWired ? onMoveToPreset : stubMove;

  const [calib, setCalib] = useState(loadCalib);          // {M, measured, pairs, source}
  const [mode, setMode] = useState('idle');               // 'idle' | 'marking' | 'observing' | 'solved'
  const [markIndex, setMarkIndex] = useState(0);          // 표시 단계 진행(프리셋 인덱스)
  const [clickIndex, setClickIndex] = useState(0);        // 관측 단계 진행(클릭 인덱스)
  const [pairs, setPairs] = useState([]);                 // [[ [u,v],[x,y] ], ...]
  const [lastPixel, setLastPixel] = useState(null);       // [u,v] 마지막 클릭(표시용)
  const [solved, setSolved] = useState(null);             // {M, err:{mean,max}}
  const [error, setError] = useState('');
  const [camError, setCamError] = useState('');
  const [moving, setMoving] = useState(false);            // 팔 이동 중(버튼 잠금)

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const wrapRef = useRef(null);

  // 보정 준비 여부를 상위(App)에 올린다 → 계약 1 상태 송출의 calib.ready.
  // 콜백은 ref 로 잡아 effect 의존성에서 뺀다(부모가 매 렌더 새 함수를 넘겨도 재호출 루프가 없다).
  const onCalibChangeRef = useRef(onCalibChange);
  onCalibChangeRef.current = onCalibChange;
  useEffect(() => {
    const cb = onCalibChangeRef.current;
    if (typeof cb === 'function') cb(!!calib.measured);
  }, [calib.measured]);

  // ── 웹캠 스트림: '관측' 단계 동안만 켠다(패널 보기만으로 카메라 권한 요구 안 함) ──
  useEffect(() => {
    let cancelled = false;
    if (mode !== 'observing') return undefined;
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

  const reset = useCallback(() => {
    setPairs([]); setLastPixel(null); setSolved(null); setError('');
    setMarkIndex(0); setClickIndex(0);
  }, []);

  // 1단계 시작: 팔이 첫 프리셋을 가리킨다(홈 후 이동, 낮은 markZ).
  const startRecalib = useCallback(async () => {
    reset();
    setMode('marking');
    setMoving(true);
    try { await move(PRESETS[0], { first: true, z: MARK_Z }); }
    catch (e) { setError(`이동 실패: ${e.message || e}`); }
    finally { setMoving(false); }
  }, [move, reset]);

  // 1단계 다음: 다음 프리셋 가리키기 → 모두 표시했으면 관측 자세로.
  const nextMark = useCallback(async () => {
    const ni = markIndex + 1;
    if (ni < PRESETS.length) {
      setMarkIndex(ni);
      setMoving(true);
      try { await move(PRESETS[ni], { first: false, z: MARK_Z }); }
      catch (e) { setError(`이동 실패: ${e.message || e}`); }
      finally { setMoving(false); }
    } else {
      // 관측 자세로 이동 후 2단계.
      setMoving(true);
      try { await move([OBSERVATION[0], OBSERVATION[1]], { first: false, z: OBSERVATION[2] }); }
      catch (e) { setError(`관측 자세 이동 실패: ${e.message || e}`); }
      finally { setMoving(false); }
      setClickIndex(0); setLastPixel(null); setError('');
      setMode('observing');
    }
  }, [markIndex, move]);

  const cancel = useCallback(() => { setMode('idle'); reset(); }, [reset]);

  const resetToDefault = useCallback(() => {
    try { window.localStorage.removeItem(STORAGE_KEY); } catch (_) { /* noop */ }
    const back = loadCalib();
    setCalib(back);
    // 파이썬 쪽(robot_calib.json)도 화면과 같은 값으로 되돌린다 — 안 그러면 지운 사용자 보정이
    // 워크스페이스 파일에 남아 화면과 로봇이 서로 다른 보정을 쓰게 된다.
    pushCalibToBackend(back.M, back.pairs, back.measured);
    cancel();
  }, [cancel]);

  // 2단계 클릭 → 프레임 픽셀 좌표(표시크기↔실제프레임 스케일 보정) → 현재 스티커의 로봇좌표와 대응 기록.
  const onCanvasClick = useCallback((e) => {
    if (mode !== 'observing') return;
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

    const preset = PRESETS[clickIndex];
    const nextPairs = [...pairs, [pixel, preset]];
    setPairs(nextPairs);

    const ni = clickIndex + 1;
    if (ni < PRESETS.length) {
      setClickIndex(ni);
    } else {
      try {
        const M = estimateAffine(nextPairs);
        const err = reprojectionError(M, nextPairs);
        setSolved({ M, err });
        setMode('solved');
        setError('');
      } catch (ex) {
        setError(ex.message || '아핀 풀이 실패');
        // observing 유지 — 취소/다시 하도록. (여전히 퇴화면 스티커를 더 넓게 퍼뜨려 다시.)
      }
    }
  }, [mode, clickIndex, pairs]);

  const saveSolved = useCallback(() => {
    if (!solved) return;
    // localStorage 와 **함께** 워크스페이스 파일로도 내보낸다(계약 4). 백엔드 실패는 무시된다.
    pushCalibToBackend(solved.M, pairs, true);
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
    <div className="robot-calibrate-panel" style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12, borderTop: '1px solid var(--line)' }}>
      <div style={{ fontWeight: 600 }}>캘리브레이션 <span style={{ fontWeight: 400, fontSize: 11, opacity: 0.6 }}>(팔끝 카메라 · 2단계)</span></div>
      <div id="calib-status" style={{ fontSize: 13, opacity: calib.measured ? 1 : 0.85, color: calib.measured ? 'inherit' : 'var(--warn-ink)' }}>
        {statusLine}
      </div>

      {mode === 'idle' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 12, opacity: 0.7, lineHeight: 1.5 }}>
            ① 팔이 매트 위 {PRESETS.length}곳을 차례로 가리킵니다 → 그 자리에 <b>스티커</b>를 붙이세요.
            ② 팔이 <b>관측 자세</b>로 올라간 뒤, 각 스티커를 화면에서 클릭하면 보정됩니다.
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button id="calib-start" className="btn btn-primary btn-sm" onClick={startRecalib}>
              <i className="fa-solid fa-crosshairs"></i> 재보정 시작
            </button>
            <button id="calib-reset" className="btn btn-secondary btn-sm" onClick={resetToDefault}>초기화</button>
          </div>
        </div>
      )}

      {mode === 'marking' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span id="calib-mark-step">표시 {markIndex + 1}/{PRESETS.length} · 로봇 ({PRESETS[markIndex][0]}, {PRESETS[markIndex][1]})</span>
            <span id="calib-robot-badge" style={{ fontSize: 11, padding: '1px 6px', borderRadius: 8, background: 'var(--surface)', border: `1px solid ${robotWired ? 'var(--run)' : 'var(--stop)'}`, color: robotWired ? 'var(--run-ink)' : 'var(--stop-ink)' }}>
              {robotWired ? (moving ? '팔 이동 중…' : '팔이 가리킴') : '로봇 미연결 — 좌표에 수동으로 스티커'}
            </span>
          </div>
          <div style={{ fontSize: 12, opacity: 0.75, lineHeight: 1.5 }}>
            팔끝이 가리키는 <b>매트 위치</b>에 스티커를 붙이세요. 다 붙였으면 [다음 지점].
            {robotWired ? '' : ' (팔 미연결: 위 로봇좌표 지점에 직접 스티커를 붙이세요.)'}
          </div>
          {error && <div id="calib-error" style={{ color: 'var(--stop-ink)', fontSize: 13 }}>{error}</div>}
          <div style={{ display: 'flex', gap: 8 }}>
            <button id="calib-next-mark" className="btn btn-primary btn-sm" onClick={nextMark} disabled={moving}>
              {markIndex + 1 < PRESETS.length ? '다음 지점' : '관측 자세로 →'}
            </button>
            <button id="calib-cancel" className="btn btn-secondary btn-sm" onClick={cancel}>취소</button>
          </div>
        </div>
      )}

      {mode === 'observing' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div style={{ fontSize: 13 }}>
            <span id="calib-click-step">클릭 {clickIndex + 1}/{PRESETS.length}</span> · 스티커의 로봇 ({PRESETS[clickIndex][0]}, {PRESETS[clickIndex][1]})
          </div>
          <div style={{ fontSize: 12, opacity: 0.75, lineHeight: 1.5 }}>
            관측 자세로 이동했습니다(팔 고정). <b>{clickIndex + 1}번째 스티커</b>(또는 그 위 블록)를 화면에서 클릭하세요.
          </div>
          {camError ? (
            <div id="calib-cam-error" style={{ color: 'var(--stop-ink)', fontSize: 13 }}>{camError}</div>
          ) : (
            <div
              ref={wrapRef}
              id="calib-video-wrap"
              onClick={onCanvasClick}
              style={{ position: 'relative', width: '100%', maxWidth: 420, aspectRatio: '4 / 3', background: 'var(--media-bg)', cursor: 'crosshair', borderRadius: 'var(--r-panel)', overflow: 'hidden' }}
            >
              <video ref={videoRef} muted playsInline style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }} />
            </div>
          )}
          {lastPixel && (
            <div style={{ fontSize: 12, opacity: 0.75 }}>
              마지막 클릭: 픽셀({lastPixel[0]}, {lastPixel[1]}) · 기록 {pairs.length}/{PRESETS.length}
            </div>
          )}
          {error && <div id="calib-error" style={{ color: 'var(--stop-ink)', fontSize: 13 }}>{error} <button className="btn btn-secondary btn-sm" style={{ marginLeft: 6 }} onClick={startRecalib}>처음부터</button></div>}
          <div style={{ display: 'flex', gap: 8 }}>
            <button id="calib-cancel" className="btn btn-secondary btn-sm" onClick={cancel}>취소</button>
          </div>
        </div>
      )}

      {mode === 'solved' && solved && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <div id="calib-solved" style={{ fontSize: 13, color: 'var(--run-ink)' }}>
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

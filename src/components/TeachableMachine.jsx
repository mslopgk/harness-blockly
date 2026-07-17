import React, { useState, useRef, useEffect, useCallback } from 'react';
import { featurize, buildHead, trainHead, predictTop, serializeModel } from '../utils/teachable';

// Teachable Machine 패널 (TM 탭). 프론트 전용.
//  idle → collecting(클래스별 웹캠 샘플 수집) → trained(라이브 미리보기) → 저장.
//  MobileNet 임베딩 + 작은 dense head 학습. 저장은 <이름>.json (blockpy-tm-v1) → /api/fs/file.
//  블록/파이썬 연동 없음(후속 단계).

const CAPTURE_MS = 100; // 누르는 동안 프레임 캡처 간격

export default function TeachableMachine() {
  const [classes, setClasses] = useState([
    { name: '클래스 1', samples: [] }, // samples: tf.Tensor2D [1,D]
    { name: '클래스 2', samples: [] },
  ]);
  const [mode, setMode] = useState('idle');        // 'idle' | 'collecting' | 'training' | 'trained'
  const [capturingIdx, setCapturingIdx] = useState(-1);
  const [status, setStatus] = useState('클래스별로 웹캠 샘플을 모은 뒤 학습하세요.');
  const [camError, setCamError] = useState('');
  const [preview, setPreview] = useState(null);    // {label, confidence}
  const [filename, setFilename] = useState('my-model');
  const [saveStatus, setSaveStatus] = useState('');
  const [trainedInfo, setTrainedInfo] = useState(null); // {epochs}

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const headRef = useRef(null);
  const captureTimer = useRef(null);
  const previewRAF = useRef(null);

  const camActive = mode === 'collecting' || mode === 'trained';

  // ── 웹캠: 수집/미리보기 중에만 켠다 ──
  useEffect(() => {
    let cancelled = false;
    if (!camActive) return undefined;
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
  }, [camActive]);

  // ── 한 프레임 → 임베딩 → 해당 클래스에 추가 ──
  const captureOne = useCallback(async (idx) => {
    const vid = videoRef.current;
    if (!vid || !vid.videoWidth) return;
    try {
      const emb = await featurize(vid);
      setClasses((prev) => {
        const next = prev.map((c, i) => (i === idx ? { ...c, samples: [...c.samples, emb] } : c));
        return next;
      });
    } catch (e) {
      setCamError(e.message || '샘플 수집 실패');
    }
  }, []);

  const startCapture = useCallback((idx) => {
    if (mode === 'idle') setMode('collecting');
    setCapturingIdx(idx);
    captureOne(idx);
    captureTimer.current = setInterval(() => captureOne(idx), CAPTURE_MS);
  }, [mode, captureOne]);

  const stopCapture = useCallback(() => {
    if (captureTimer.current) { clearInterval(captureTimer.current); captureTimer.current = null; }
    setCapturingIdx(-1);
  }, []);

  const addClass = useCallback(() => {
    setClasses((prev) => [...prev, { name: `클래스 ${prev.length + 1}`, samples: [] }]);
  }, []);

  const renameClass = useCallback((idx, name) => {
    setClasses((prev) => prev.map((c, i) => (i === idx ? { ...c, name } : c)));
  }, []);

  // ── 학습 ──
  const canTrain = classes.length >= 2 && classes.every((c) => c.samples.length > 0);

  const train = useCallback(async () => {
    if (!canTrain) { setStatus('클래스가 2개 이상이고, 각 클래스에 샘플이 1개 이상 있어야 학습할 수 있습니다.'); return; }
    stopCapture();
    setMode('training');
    setStatus('학습 중…');
    try {
      const inputDim = classes[0].samples[0].shape[1];
      const head = await buildHead(inputDim, classes.length);
      const samples = classes.flatMap((c, ci) => c.samples.map((embedding) => ({ classIndex: ci, embedding })));
      const epochs = 20;
      await trainHead(head, samples, classes.length, {
        epochs,
        onEpoch: (e) => setStatus(`학습 중… epoch ${e + 1}/${epochs}`),
      });
      headRef.current = head;
      setTrainedInfo({ epochs });
      setMode('trained');
      setStatus('학습 완료 — 카메라로 실시간 예측을 확인하세요.');
    } catch (e) {
      setMode('idle');
      setStatus('학습 실패: ' + (e.message || e));
    }
  }, [canTrain, classes, stopCapture]);

  // ── 라이브 미리보기 루프 (trained 동안) ──
  useEffect(() => {
    if (mode !== 'trained' || !headRef.current) return undefined;
    let stop = false;
    const labels = classes.map((c) => c.name);
    const tick = async () => {
      if (stop) return;
      const vid = videoRef.current;
      if (vid && vid.videoWidth) {
        try {
          const emb = await featurize(vid);
          const p = await predictTop(headRef.current, emb, labels);
          emb.dispose();
          if (!stop) setPreview({ label: p.label, confidence: p.confidence });
        } catch (_) { /* 프레임 스킵 */ }
      }
      previewRAF.current = setTimeout(tick, 250);
    };
    tick();
    return () => { stop = true; if (previewRAF.current) clearTimeout(previewRAF.current); };
  }, [mode, classes]);

  // ── 저장: <이름>.json → /api/fs/file, 실패 시 브라우저 다운로드 폴백 ──
  const save = useCallback(async () => {
    if (!headRef.current) { setSaveStatus('먼저 학습을 완료하세요.'); return; }
    const cleaned = String(filename || '').trim().replace(/\.json$/i, '');
    if (!cleaned) { setSaveStatus('파일 이름을 입력하세요.'); return; }
    const fname = cleaned + '.json';
    setSaveStatus('저장 중…');
    try {
      const json = await serializeModel({ head: headRef.current, labels: classes.map((c) => c.name) });
      try {
        const r = await fetch('/api/fs/file', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: fname, content: json }),
        });
        if (!r.ok) throw new Error('HTTP ' + r.status);
        setSaveStatus(`저장됨: ${fname} (워크스페이스)`);
      } catch (backendErr) {
        // 백엔드 미가동 → 브라우저 다운로드 폴백
        const blob = new Blob([json], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url; a.download = fname; a.click();
        URL.revokeObjectURL(url);
        setSaveStatus(`다운로드됨: ${fname} (백엔드 미가동 — 폴백)`);
      }
    } catch (e) {
      setSaveStatus('저장 실패: ' + (e.message || e));
    }
  }, [filename, classes]);

  return (
    <div className="tm-panel" style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontWeight: 600 }}>Teachable Machine</div>
      <div id="tm-status" style={{ fontSize: 13, opacity: 0.85 }}>{status}</div>

      {/* 웹캠 미리보기 */}
      {camError ? (
        <div id="tm-cam-error" style={{ color: '#c0392b', fontSize: 13 }}>{camError}</div>
      ) : (
        <div
          id="tm-webcam-wrap"
          style={{ position: 'relative', width: '100%', maxWidth: 320, aspectRatio: '4 / 3', background: '#000', borderRadius: 6, overflow: 'hidden', display: camActive ? 'block' : 'none' }}
        >
          <video ref={videoRef} muted playsInline style={{ width: '100%', height: '100%', objectFit: 'contain', display: 'block' }} />
          {mode === 'trained' && preview && (
            <div id="tm-preview-overlay" style={{ position: 'absolute', left: 8, bottom: 8, background: 'rgba(0,0,0,0.6)', color: '#fff', padding: '4px 8px', borderRadius: 6, fontSize: 13 }}>
              <span id="tm-preview-label">{preview.label}</span> · {(preview.confidence * 100).toFixed(0)}%
            </div>
          )}
        </div>
      )}

      {/* 클래스 목록 */}
      <div id="tm-classes" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {classes.map((c, i) => (
          <div id={`tm-class-${i}`} key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <input
              id={`tm-classname-${i}`}
              value={c.name}
              onChange={(e) => renameClass(i, e.target.value)}
              style={{ flex: '1 1 100px', minWidth: 80 }}
            />
            <span id={`tm-count-${i}`} style={{ fontSize: 12, opacity: 0.7, minWidth: 48 }}>샘플 {c.samples.length}</span>
            <button
              id={`tm-capture-${i}`}
              className="btn btn-secondary btn-sm"
              onMouseDown={() => startCapture(i)}
              onMouseUp={stopCapture}
              onMouseLeave={() => { if (capturingIdx === i) stopCapture(); }}
              disabled={mode === 'training'}
            >
              {capturingIdx === i ? '수집 중…' : '누르는 동안 수집'}
            </button>
          </div>
        ))}
        <button id="tm-add-class" className="btn btn-secondary btn-sm" onClick={addClass} disabled={mode === 'training'}>
          <i className="fa-solid fa-plus"></i> 클래스 추가
        </button>
      </div>

      {/* 학습 */}
      <button id="tm-train" className="btn btn-primary btn-sm" onClick={train} disabled={!canTrain || mode === 'training'}>
        {mode === 'training' ? '학습 중…' : '학습'}
      </button>

      {/* 학습 완료 + 저장 */}
      {mode === 'trained' && (
        <div id="tm-trained" style={{ display: 'flex', flexDirection: 'column', gap: 8, borderTop: '1px solid rgba(0,0,0,0.08)', paddingTop: 8 }}>
          <div style={{ fontSize: 13, color: '#166534' }}>학습 완료 (epoch {trainedInfo ? trainedInfo.epochs : ''})</div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <input id="tm-filename" value={filename} onChange={(e) => setFilename(e.target.value)} placeholder="모델 파일 이름" style={{ flex: '1 1 120px', minWidth: 100 }} />
            <span style={{ fontSize: 12, opacity: 0.6 }}>.json</span>
            <button id="tm-save" className="btn btn-primary btn-sm" onClick={save}>저장</button>
          </div>
          {saveStatus && <div id="tm-save-status" style={{ fontSize: 13 }}>{saveStatus}</div>}
        </div>
      )}
    </div>
  );
}

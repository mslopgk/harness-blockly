import React, { useState, useRef, useEffect, useCallback } from 'react';
import { featurize, buildHead, trainHead, predictTop } from '../utils/teachable';

// Teachable Machine 패널 (TM 탭).
//  idle → collecting(클래스별 웹캠 샘플 수집) → trained(라이브 미리보기) → 저장.
//
//  샘플 하나 = { embedding: tf.Tensor2D [1,D], jpeg: data URL }.
//   - embedding: 브라우저 TF.js MobileNet — 패널 안에서 즉시 학습/라이브 미리보기용(피드백 전용).
//   - jpeg: 원본 프레임 — "저장" 시 백엔드로 보내 파이썬 runtime/tm.py 가 다시 학습한다.
//  저장 산출물은 <이름>.npz (파이썬 네이티브)라 학생 코드에서 tm.load_model('<이름>.npz') 로 바로
//  쓸 수 있다. 브라우저 TF.js MobileNet 과 파이썬 Keras MobileNetV2 는 임베딩 공간이 달라서
//  브라우저에서 학습한 head 를 그대로 내보낼 수는 없다 — 그래서 프레임을 보내 파이썬이 학습한다.

const CAPTURE_MS = 100;        // 누르는 동안 프레임 캡처 간격
const CAPTURE_MAX_SIDE = 224;  // 백엔드로 보낼 JPEG 의 긴 변 (MobileNet 입력 크기)
const MAX_SAMPLES = 600;       // 백엔드 /api/tm/train 의 상한과 동일

// 비디오 현재 프레임 → 축소된 JPEG data URL (백엔드 학습용 원본 프레임).
function frameToJpeg(vid) {
  const w = vid.videoWidth;
  const h = vid.videoHeight;
  if (!w || !h) return '';
  const scale = Math.min(1, CAPTURE_MAX_SIDE / Math.max(w, h));
  const cw = Math.max(1, Math.round(w * scale));
  const ch = Math.max(1, Math.round(h * scale));
  const canvas = document.createElement('canvas'); // 오프스크린 — DOM 에 붙이지 않는다
  canvas.width = cw;
  canvas.height = ch;
  canvas.getContext('2d').drawImage(vid, 0, 0, cw, ch);
  return canvas.toDataURL('image/jpeg', 0.8);
}

export default function TeachableMachine() {
  const [classes, setClasses] = useState([
    { name: '클래스 1', samples: [] }, // samples: [{ embedding: tf.Tensor2D [1,D], jpeg: dataURL }]
    { name: '클래스 2', samples: [] },
  ]);
  const [mode, setMode] = useState('idle');        // 'idle' | 'collecting' | 'training' | 'trained'
  const [capturingIdx, setCapturingIdx] = useState(-1);
  const [status, setStatus] = useState('클래스별로 웹캠 샘플을 모은 뒤 학습하세요.');
  const [camError, setCamError] = useState('');
  const [preview, setPreview] = useState(null);    // {label, confidence}
  const [filename, setFilename] = useState('my-model');
  const [saveStatus, setSaveStatus] = useState('');
  const [saving, setSaving] = useState(false);     // 백엔드(파이썬) 학습 진행 중
  const [trainedInfo, setTrainedInfo] = useState(null); // {epochs}

  const videoRef = useRef(null);
  const streamRef = useRef(null);
  const headRef = useRef(null);
  const captureTimer = useRef(null);
  const previewRAF = useRef(null);
  const classesRef = useRef(classes);

  const camActive = mode === 'collecting' || mode === 'trained';

  // classesRef 는 매 렌더 최신 classes 를 반영(언마운트 정리 시 최신 상태를 읽기 위함).
  useEffect(() => {
    classesRef.current = classes;
  });

  // 언마운트 시: 진행 중인 캡처 타이머 정리(누르는 도중 탭 전환 등으로 언마운트되는 경우 대비).
  useEffect(() => () => {
    if (captureTimer.current) clearInterval(captureTimer.current);
  }, []);

  // 언마운트 시: 수집된 샘플 텐서 + 학습된 head 모델 dispose(TF.js 메모리 누수 방지).
  // (샘플의 jpeg 는 그냥 문자열이라 dispose 대상이 아니다 — embedding 만 정리한다.)
  useEffect(() => () => {
    classesRef.current.forEach((c) => c.samples.forEach((s) => {
      try { s.embedding.dispose(); } catch (_) {}
    }));
    if (headRef.current) { try { headRef.current.dispose(); } catch (_) {} }
  }, []);

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

  // ── 한 프레임 → (브라우저 임베딩 + 원본 JPEG) → 해당 클래스에 추가 ──
  // 임베딩은 패널 안 즉석 학습/미리보기용, JPEG 는 저장 시 파이썬 학습용.
  const captureOne = useCallback(async (idx) => {
    const vid = videoRef.current;
    if (!vid || !vid.videoWidth) return;
    if (classesRef.current.reduce((n, c) => n + c.samples.length, 0) >= MAX_SAMPLES) {
      setCamError(`샘플은 최대 ${MAX_SAMPLES}장까지 모을 수 있습니다.`);
      return;
    }
    try {
      const jpeg = frameToJpeg(vid); // 임베딩 전에 떠야 같은 순간의 프레임이 잡힌다
      const emb = await featurize(vid);
      setClasses((prev) => prev.map((c, i) => (
        i === idx ? { ...c, samples: [...c.samples, { embedding: emb, jpeg }] } : c
      )));
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
    let head = null;
    try {
      const inputDim = classes[0].samples[0].embedding.shape[1];
      head = await buildHead(inputDim, classes.length);
      const samples = classes.flatMap((c, ci) => c.samples.map((s) => ({ classIndex: ci, embedding: s.embedding })));
      const epochs = 20;
      await trainHead(head, samples, classes.length, {
        epochs,
        onEpoch: (e) => setStatus(`학습 중… epoch ${e + 1}/${epochs}`),
      });
      if (headRef.current) { headRef.current.dispose(); }
      headRef.current = head;
      setTrainedInfo({ epochs });
      setMode('trained');
      setStatus('학습 완료 — 카메라로 실시간 예측을 확인하세요.');
    } catch (e) {
      if (head) { try { head.dispose(); } catch (_) {} }
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

  // ── 저장: 수집한 원본 프레임을 백엔드로 보내 파이썬(runtime/tm.py)이 학습·저장 → <이름>.npz ──
  // 브라우저에서 학습한 head 를 내보내지 않는 이유: TF.js MobileNet 임베딩 ≠ Keras MobileNetV2
  // 임베딩이라 파이썬 tm.load_model 이 그 가중치를 재사용할 수 없다. 프레임을 보내 다시 학습한다.
  const canSave = classes.length >= 2
    && classes.every((c) => String(c.name || '').trim() && c.samples.some((s) => s.jpeg))
    && new Set(classes.map((c) => String(c.name || '').trim())).size === classes.length;

  const save = useCallback(async () => {
    if (!canSave) {
      setSaveStatus('클래스가 2개 이상이고, 각 클래스에 이름과 샘플이 1장 이상 있어야 저장할 수 있습니다(이름 중복 불가).');
      return;
    }
    const cleaned = String(filename || '').trim().replace(/\.(npz|json)$/i, '');
    if (!cleaned) { setSaveStatus('파일 이름을 입력하세요.'); return; }
    const labels = classes.map((c) => String(c.name).trim());
    const samples = classes.flatMap((c, i) => c.samples
      .filter((s) => s.jpeg)
      .map((s) => ({ label: labels[i], jpegBase64: s.jpeg })));
    setSaving(true);
    setSaveStatus('파이썬으로 학습 중… (수십 초 걸릴 수 있어요)');
    try {
      const r = await fetch('/api/tm/train', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ filename: cleaned + '.npz', labels, samples, epochs: 30 }),
      });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const d = await r.json();
      if (d && d.ok) {
        setSaveStatus(`저장 완료: ${d.path} — 코드에서 tm.load_model('${d.path}') 로 사용하세요.`);
      } else {
        const err = (d && d.error) || '알 수 없는 오류';
        setSaveStatus(`학습/저장 실패: ${err}${d && d.hint ? ` (${d.hint})` : ''}`);
      }
    } catch (e) {
      setSaveStatus(`학습/저장 실패: 백엔드에 연결할 수 없습니다 (${e.message || e}). 서버(npm run server)가 실행 중인지 확인하세요.`);
    } finally {
      setSaving(false);
    }
  }, [canSave, filename, classes]);

  return (
    <div className="tm-panel" style={{ padding: 12, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ fontWeight: 600 }}>Teachable Machine</div>
      <div id="tm-status" style={{ fontSize: 13, opacity: 0.85 }}>{status}</div>

      {/* 웹캠 미리보기 — 박스는 mode 와 무관하게 항상 같은 크기로 렌더링한다.
          (이전엔 display:none↔block 로 토글해서 idle→collecting 전환 시 박스가 나타나며
          아래 클래스 목록/캡처 버튼을 밀어냈다 — 누르고 있던 버튼이 커서 밑에서 빠져나가
          mouseleave 로 캡처가 즉시 끊기는 버그였다. 박스 높이를 고정해 해결.) */}
      {camError ? (
        <div id="tm-cam-error" style={{ color: 'var(--stop-ink)', fontSize: 13 }}>{camError}</div>
      ) : (
        <div
          id="tm-webcam-wrap"
          style={{ position: 'relative', width: '100%', maxWidth: 320, aspectRatio: '4 / 3', background: 'var(--media-bg)', borderRadius: 'var(--r-control)', overflow: 'hidden' }}
        >
          <video ref={videoRef} muted playsInline style={{ width: '100%', height: '100%', objectFit: 'contain', display: camActive ? 'block' : 'none' }} />
          {!camActive && (
            <div id="tm-webcam-placeholder" style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--faint)', fontSize: 13 }}>
              카메라 미리보기
            </div>
          )}
          {mode === 'trained' && preview && (
            <div id="tm-preview-overlay" style={{ position: 'absolute', left: 8, bottom: 8, background: 'var(--scrim-strong)', color: '#fff', padding: '4px 8px', borderRadius: 'var(--r-control)', fontSize: 13 }}>
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
        <div id="tm-trained" style={{ display: 'flex', flexDirection: 'column', gap: 8, borderTop: '1px solid var(--line)', paddingTop: 8 }}>
          <div style={{ fontSize: 13, color: 'var(--run-ink)' }}>학습 완료 (epoch {trainedInfo ? trainedInfo.epochs : ''})</div>
          <div style={{ fontSize: 12, opacity: 0.7 }}>
            저장하면 모아 둔 사진으로 <b>파이썬이 다시 학습</b>해 <code>.npz</code> 모델을 워크스페이스에 만듭니다.
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <input id="tm-filename" value={filename} onChange={(e) => setFilename(e.target.value)} placeholder="모델 파일 이름" disabled={saving} style={{ flex: '1 1 120px', minWidth: 100 }} />
            <span style={{ fontSize: 12, opacity: 0.6 }}>.npz</span>
            <button id="tm-save" className="btn btn-primary btn-sm" onClick={save} disabled={saving || !canSave}>
              {saving ? '학습 중…' : '저장'}
            </button>
          </div>
          {saveStatus && <div id="tm-save-status" style={{ fontSize: 13 }}>{saveStatus}</div>}
        </div>
      )}
    </div>
  );
}

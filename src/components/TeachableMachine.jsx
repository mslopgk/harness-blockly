import React, { useState, useRef, useEffect, useCallback } from 'react';
import { ensureTf, featurize, buildHead, trainHead, predictTop } from '../utils/teachable';

// Teachable Machine 패널 (TM 탭).
//
//  화면 구성은 구글 티처블머신 "이미지 프로젝트" 를 그대로 옮겼다 — 왼쪽 이름표(클래스) 열,
//  가운데 학습, 오른쪽 미리보기. 우리 수업 용어(한국어)와 우리 저장 방식(.npz)만 우리 것이다.
//
//    ┌ 이름표(클래스) ┐   ┌ 학습 ┐   ┌ 미리보기 ┐
//    │ 이름 · 샘플수  │ → │ 학습 │ → │ 입력 켜기 │
//    │ 웹캠/업로드    │   │ 진행 │   │ 출력 막대 │
//    │ 누르는 동안…   │   │ 고급 │   │ 저장(.npz)│
//
//  샘플 하나 = { embedding: tf.Tensor2D [1,D], jpeg: data URL }.
//   - embedding: 브라우저 TF.js MobileNet — 패널 안에서 즉시 학습/라이브 미리보기용(피드백 전용).
//   - jpeg: 원본 프레임 — "저장" 시 백엔드로 보내 파이썬 runtime/tm.py 가 다시 학습한다.
//  저장 산출물은 <이름>.npz (파이썬 네이티브)라 학생 코드에서 tm.load_model('<이름>.npz') 로 바로
//  쓸 수 있다. 브라우저 TF.js MobileNet 과 파이썬 Keras MobileNetV2 는 임베딩 공간이 달라서
//  브라우저에서 학습한 head 를 그대로 내보낼 수는 없다 — 그래서 프레임을 보내 파이썬이 학습한다.
//  (티처블머신의 "Export Model"(클라우드/TF.js)은 흉내내지 않는다. 우리는 파이썬 .npz 다.)

const CAPTURE_MS = 100;        // 누르는 동안 프레임 캡처 간격
const CAPTURE_MAX_SIDE = 224;  // 백엔드로 보낼 JPEG 의 긴 변 (MobileNet 입력 크기)
const MAX_SAMPLES = 600;       // 백엔드 /api/tm/train 의 상한과 동일
const MAX_THUMBS = 60;         // 카드에 실제로 그리는 썸네일 수(600장을 다 그리면 메모리가 터진다)

// 고급 설정 기본값 — 티처블머신과 같은 항목/기본값 배치.
const DEF_EPOCHS = 30;         // 백엔드 /api/tm/train 의 기본값과 같게 맞춘다
const DEF_BATCH = 16;
const DEF_LR = 0.001;

// video/img 의 현재 그림 → 축소된 JPEG data URL (백엔드 학습용 원본 프레임).
function frameToJpeg(el) {
  const w = el.videoWidth || el.naturalWidth || 0;
  const h = el.videoHeight || el.naturalHeight || 0;
  if (!w || !h) return '';
  const scale = Math.min(1, CAPTURE_MAX_SIDE / Math.max(w, h));
  const cw = Math.max(1, Math.round(w * scale));
  const ch = Math.max(1, Math.round(h * scale));
  const canvas = document.createElement('canvas'); // 오프스크린 — DOM 에 붙이지 않는다
  canvas.width = cw;
  canvas.height = ch;
  canvas.getContext('2d').drawImage(el, 0, 0, cw, ch);
  return canvas.toDataURL('image/jpeg', 0.8);
}

// File → 디코드된 HTMLImageElement (업로드 샘플용).
function fileToImage(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();
    img.onload = () => { URL.revokeObjectURL(url); resolve(img); };
    img.onerror = () => { URL.revokeObjectURL(url); reject(new Error(`${file.name} 을(를) 읽을 수 없습니다.`)); };
    img.src = url;
  });
}

function disposeSamples(list) {
  (list || []).forEach((s) => { try { s.embedding.dispose(); } catch (_) {} });
}

// props
//   onStateChange?(s)  — 이 패널의 상태가 "실제로 바뀔 때만" 부른다(렌더마다 부르지 않는다).
//     s = { labels: ["캔","플라스틱"], samples: [31,28], trained: true, model: "분리수거.npz" }
//     model 은 백엔드 저장이 성공한 뒤에만 들어간다(저장 전에는 키 자체가 없다).
//     App.jsx(담당 C)가 .blockpy/state.json 의 tm 칸을 채우는 데 쓴다. 없어도 정상 동작한다.
export default function TeachableMachine({ onStateChange }) {
  const [classes, setClasses] = useState([
    { name: '클래스 1', samples: [] }, // samples: [{ embedding: tf.Tensor2D [1,D], jpeg: dataURL }]
    { name: '클래스 2', samples: [] },
  ]);
  const [mode, setMode] = useState('idle');        // 'idle' | 'collecting' | 'training' | 'trained'
  const [capturingIdx, setCapturingIdx] = useState(-1);
  const [camOwner, setCamOwner] = useState(-1);    // 웹캠을 켠 이름표 카드(-1 = 아무도 안 씀)
  const [previewOn, setPreviewOn] = useState(false); // 오른쪽 미리보기 입력 켜기/끄기
  const [menuIdx, setMenuIdx] = useState(-1);      // 열려 있는 ⋮ 메뉴
  // 첫 문구는 위 안내와 겹치지 않게, 학생이 바로 막히는 지점을 알려준다 —
  // 카메라는 저절로 켜지지 않고 '웹캠' 이나 '누르는 동안 수집' 을 누를 때 켜진다.
  const [status, setStatus] = useState('이름을 적고 "누르는 동안 수집" 을 누르면 카메라가 켜집니다.');
  const [camError, setCamError] = useState('');
  const [preview, setPreview] = useState(null);    // {label, confidence, all:[...]}
  const [filename, setFilename] = useState('내모델');
  const [saveStatus, setSaveStatus] = useState('');
  const [saving, setSaving] = useState(false);     // 백엔드(파이썬) 학습 진행 중
  const [trainedInfo, setTrainedInfo] = useState(null); // {epochs}
  const [savedModel, setSavedModel] = useState('');     // 저장에 성공한 .npz 파일명(바깥에 알린다)
  const [progress, setProgress] = useState(0);     // 0..1 학습 진행
  const [advOpen, setAdvOpen] = useState(false);
  const [epochs, setEpochs] = useState(DEF_EPOCHS);
  const [batchSize, setBatchSize] = useState(DEF_BATCH);
  const [learningRate, setLearningRate] = useState(DEF_LR);

  const camVideoRef = useRef(null);      // 이름표 카드 안의 수집용 미리보기
  const previewVideoRef = useRef(null);  // 오른쪽 미리보기
  const fileInputs = useRef([]);
  const streamRef = useRef(null);
  const headRef = useRef(null);
  const captureTimer = useRef(null);
  const previewRAF = useRef(null);
  const classesRef = useRef(classes);
  const capturingRef = useRef(-1);

  const camActive = camOwner >= 0 || previewOn;
  const total = classes.reduce((n, c) => n + c.samples.length, 0);

  // classesRef 는 매 렌더 최신 classes 를 반영(언마운트 정리 시 최신 상태를 읽기 위함).
  useEffect(() => { classesRef.current = classes; });
  useEffect(() => { capturingRef.current = capturingIdx; }, [capturingIdx]);

  // ── 바깥(App)에 상태 알리기 ──
  // 값이 실제로 달라졌을 때만 부른다 — App 이 이 콜백으로 네트워크 요청을 보내기 때문에
  // 렌더마다 부르면 안 된다. 모르는 값은 넣지 않는다(model 은 저장 성공 후에만).
  const lastEmitRef = useRef('');
  useEffect(() => {
    if (typeof onStateChange !== 'function') return;
    const snap = {
      labels: classes.map((c) => String(c.name == null ? '' : c.name)),
      samples: classes.map((c) => c.samples.length),
      trained: mode === 'trained',
    };
    if (savedModel) snap.model = savedModel;
    const key = JSON.stringify(snap);
    if (key === lastEmitRef.current) return;
    lastEmitRef.current = key;
    onStateChange(snap);
  }, [classes, mode, savedModel, onStateChange]);

  // 언마운트 시: 진행 중인 캡처 타이머 정리(누르는 도중 탭 전환 등으로 언마운트되는 경우 대비).
  useEffect(() => () => {
    if (captureTimer.current) clearInterval(captureTimer.current);
  }, []);

  // 언마운트 시: 수집된 샘플 텐서 + 학습된 head 모델 dispose(TF.js 메모리 누수 방지).
  // (샘플의 jpeg 는 그냥 문자열이라 dispose 대상이 아니다 — embedding 만 정리한다.)
  useEffect(() => () => {
    classesRef.current.forEach((c) => disposeSamples(c.samples));
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
        [camVideoRef.current, previewVideoRef.current].forEach((v) => {
          if (!v) return;
          v.srcObject = stream;
          v.play().catch(() => {});
        });
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

  // 카드가 바뀌거나 미리보기가 켜지면 새로 붙은 <video> 에 같은 스트림을 다시 물린다.
  // (하나의 MediaStream 을 두 video 가 같이 쓸 수 있다 — 카메라를 두 번 열지 않는다.)
  useEffect(() => {
    const stream = streamRef.current;
    if (!stream) return;
    [camVideoRef.current, previewVideoRef.current].forEach((v) => {
      if (!v || v.srcObject === stream) return;
      v.srcObject = stream;
      v.play().catch(() => {});
    });
  }, [camOwner, previewOn, mode]);

  // ── 한 프레임 → (브라우저 임베딩 + 원본 JPEG) → 해당 이름표에 추가 ──
  // 임베딩은 패널 안 즉석 학습/미리보기용, JPEG 는 저장 시 파이썬 학습용.
  const addSample = useCallback(async (idx, el) => {
    if (classesRef.current.reduce((n, c) => n + c.samples.length, 0) >= MAX_SAMPLES) {
      setCamError(`샘플은 최대 ${MAX_SAMPLES}장까지 모을 수 있습니다.`);
      return;
    }
    const jpeg = frameToJpeg(el); // 임베딩 전에 떠야 같은 순간의 그림이 잡힌다
    const emb = await featurize(el);
    setClasses((prev) => prev.map((c, i) => (
      i === idx ? { ...c, samples: [...c.samples, { embedding: emb, jpeg }] } : c
    )));
  }, []);

  const captureOne = useCallback(async (idx) => {
    const vid = camVideoRef.current;
    if (!vid || !vid.videoWidth) return;
    try {
      await addSample(idx, vid);
    } catch (e) {
      setCamError(e.message || '샘플 수집 실패');
    }
  }, [addSample]);

  const startCapture = useCallback((idx) => {
    if (mode === 'idle') setMode('collecting');
    setCamOwner(idx);          // 카드 안 미리보기를 이 카드로 옮긴다(= 카메라 켜기)
    capturingRef.current = idx;
    setCapturingIdx(idx);
    captureOne(idx);
    if (captureTimer.current) clearInterval(captureTimer.current);
    captureTimer.current = setInterval(() => captureOne(idx), CAPTURE_MS);
  }, [mode, captureOne]);

  const stopCapture = useCallback(() => {
    if (captureTimer.current) { clearInterval(captureTimer.current); captureTimer.current = null; }
    capturingRef.current = -1;
    setCapturingIdx(-1);
  }, []);

  // 버튼 밖에서 손을 떼도 수집이 멈추게(누른 채 창 밖으로 나가는 경우).
  useEffect(() => {
    if (capturingIdx < 0) return undefined;
    const up = () => stopCapture();
    window.addEventListener('mouseup', up);
    return () => window.removeEventListener('mouseup', up);
  }, [capturingIdx, stopCapture]);

  // ⋮ 메뉴는 바깥을 누르면 닫힌다.
  useEffect(() => {
    if (menuIdx < 0) return undefined;
    const close = (e) => { if (!e.target.closest || !e.target.closest('.tm-kebab-wrap')) setMenuIdx(-1); };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [menuIdx]);

  // 학습해 둔 모델은 이름표 개수가 바뀌면 더 이상 쓸 수 없다(출력 칸 수가 달라진다).
  const invalidateModel = useCallback(() => {
    if (headRef.current) { try { headRef.current.dispose(); } catch (_) {} headRef.current = null; }
    setPreview(null);
    setTrainedInfo(null);
    setMode((m) => (m === 'trained' ? 'collecting' : m));
  }, []);

  const addClass = useCallback(() => {
    setClasses((prev) => [...prev, { name: `클래스 ${prev.length + 1}`, samples: [] }]);
    invalidateModel();
  }, [invalidateModel]);

  // dispose 는 상태 갱신 함수 밖에서 한다(갱신 함수는 순수해야 하고, StrictMode 에서 두 번 불린다).
  const removeClass = useCallback((idx) => {
    setMenuIdx(-1);
    const cur = classesRef.current;
    if (cur.length <= 2) return;  // 학습에는 이름표가 2개 이상 필요하다
    disposeSamples(cur[idx].samples);
    setClasses((prev) => prev.filter((_, i) => i !== idx));
    setCamOwner((o) => (o === idx ? -1 : (o > idx ? o - 1 : o)));
    invalidateModel();
  }, [invalidateModel]);

  const clearClass = useCallback((idx) => {
    setMenuIdx(-1);
    const cur = classesRef.current;
    if (!cur[idx]) return;
    disposeSamples(cur[idx].samples);
    setClasses((prev) => prev.map((c, i) => (i === idx ? { ...c, samples: [] } : c)));
  }, []);

  const renameClass = useCallback((idx, name) => {
    setClasses((prev) => prev.map((c, i) => (i === idx ? { ...c, name } : c)));
  }, []);

  const toggleCam = useCallback((idx) => {
    setCamOwner((o) => (o === idx ? -1 : idx));
    if (mode === 'idle') setMode('collecting');
  }, [mode]);

  // ── 업로드: 파일에서 샘플 넣기(티처블머신 Upload) ──
  const onUpload = useCallback(async (idx, fileList) => {
    const files = Array.from(fileList || []).filter((f) => /^image\//.test(f.type));
    if (!files.length) return;
    if (mode === 'idle') setMode('collecting');
    setCamError('');
    setStatus(`사진 ${files.length}장을 읽는 중…`);
    for (const f of files) {
      try {
        const img = await fileToImage(f);
        await addSample(idx, img);
      } catch (e) {
        setCamError(e.message || '사진을 읽지 못했습니다.');
      }
    }
    setStatus('사진을 넣었습니다. 이름표마다 30장 이상이면 학습해 보세요.');
  }, [mode, addSample]);

  // ── 학습 ──
  const canTrain = classes.length >= 2 && classes.every((c) => c.samples.length > 0);

  const train = useCallback(async () => {
    if (!canTrain) { setStatus('이름표가 2개 이상이고, 이름표마다 사진이 1장 이상 있어야 학습할 수 있습니다.'); return; }
    stopCapture();
    setMode('training');
    setProgress(0);
    setStatus('학습 중…');
    const ep = Math.min(200, Math.max(1, Math.round(Number(epochs) || DEF_EPOCHS)));
    const bs = Math.min(512, Math.max(1, Math.round(Number(batchSize) || DEF_BATCH)));
    const lr = Math.min(1, Math.max(0.00001, Number(learningRate) || DEF_LR));
    let head = null;
    try {
      const inputDim = classes[0].samples[0].embedding.shape[1];
      head = await buildHead(inputDim, classes.length);
      // buildHead 는 학습률 0.001 로 컴파일한다 — 고급 설정에서 바꿨을 때만 다시 컴파일한다.
      if (lr !== DEF_LR) {
        const tf = await ensureTf();
        head.compile({ optimizer: tf.train.adam(lr), loss: 'categoricalCrossentropy', metrics: ['accuracy'] });
      }
      const samples = classes.flatMap((c, ci) => c.samples.map((s) => ({ classIndex: ci, embedding: s.embedding })));
      await trainHead(head, samples, classes.length, {
        epochs: ep,
        batchSize: bs,
        onEpoch: (e) => {
          setProgress((e + 1) / ep);
          setStatus(`학습 중… ${e + 1}/${ep}번째`);
        },
      });
      if (headRef.current) { headRef.current.dispose(); }
      headRef.current = head;
      setTrainedInfo({ epochs: ep });
      setProgress(1);
      setMode('trained');
      setCamOwner(-1);       // 티처블머신처럼 학습이 끝나면 미리보기로 넘어간다
      setPreviewOn(true);
      setStatus('학습 완료 — 카메라에 대 보고 맞히는지 확인하세요.');
    } catch (e) {
      if (head) { try { head.dispose(); } catch (_) {} }
      setMode('collecting');
      setProgress(0);
      setStatus('학습 실패: ' + (e.message || e));
    }
  }, [canTrain, classes, stopCapture, epochs, batchSize, learningRate]);

  // ── 라이브 미리보기 루프 (trained + 입력 켬 동안) ──
  useEffect(() => {
    if (mode !== 'trained' || !previewOn || !headRef.current) return undefined;
    let stop = false;
    const labels = classes.map((c) => c.name);
    const tick = async () => {
      if (stop) return;
      const vid = previewVideoRef.current;
      if (vid && vid.videoWidth) {
        try {
          const emb = await featurize(vid);
          const p = await predictTop(headRef.current, emb, labels);
          emb.dispose();
          if (!stop) setPreview({ label: p.label, confidence: p.confidence, all: p.all });
        } catch (_) { /* 프레임 스킵 */ }
      }
      previewRAF.current = setTimeout(tick, 250);
    };
    tick();
    return () => { stop = true; if (previewRAF.current) clearTimeout(previewRAF.current); };
  }, [mode, previewOn, classes]);

  // ── 저장: 수집한 원본 프레임을 백엔드로 보내 파이썬(runtime/tm.py)이 학습·저장 → <이름>.npz ──
  // 브라우저에서 학습한 head 를 내보내지 않는 이유: TF.js MobileNet 임베딩 ≠ Keras MobileNetV2
  // 임베딩이라 파이썬 tm.load_model 이 그 가중치를 재사용할 수 없다. 프레임을 보내 다시 학습한다.
  const canSave = classes.length >= 2
    && classes.every((c) => String(c.name || '').trim() && c.samples.some((s) => s.jpeg))
    && new Set(classes.map((c) => String(c.name || '').trim())).size === classes.length;

  const save = useCallback(async () => {
    if (!canSave) {
      setSaveStatus('이름표가 2개 이상이고, 이름표마다 이름과 샘플이 1장 이상 있어야 저장할 수 있습니다(이름 중복 불가).');
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

    // 준비 상태 폴링 — tensorflow 가 없으면 백엔드가 먼저 그것을 내려받는다(휠만 335MB, 수 분).
    // 그동안 화면이 "수십 초" 인 채로 굳으면 학생은 멈춘 줄 안다. 그래서 서버가 열어 둔
    // GET /api/tm/prepare-status 를 2초마다 읽어 진행 상황을 그대로 보여 준다.
    // 저장이 끝나면 반드시 멈춘다(아래 finally).
    let prepTimer = null;
    const stopPrepPoll = () => { if (prepTimer) { clearInterval(prepTimer); prepTimer = null; } };
    prepTimer = setInterval(async () => {
      try {
        const pr = await fetch('/api/tm/prepare-status');
        if (!pr.ok) return;
        const ps = await pr.json();
        if (ps && ps.installing) {
          const tail = Array.isArray(ps.log) && ps.log.length ? ps.log[ps.log.length - 1] : '';
          setSaveStatus(`AI 학습 준비물을 내려받는 중입니다. 몇 분 걸립니다…${tail ? ` — ${tail.slice(0, 80)}` : ''}`);
        }
      } catch (_) { /* 폴링 실패는 무시 — 저장 자체는 계속 진행된다 */ }
    }, 2000);

    try {
      const r = await fetch('/api/tm/train', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        // 백엔드 /api/tm/train 이 받는 값은 filename / labels / samples / epochs 뿐이다.
        // 묶음 크기·학습률은 받지 않으므로 보내지 않는다(보내도 무시된다).
        body: JSON.stringify({
          filename: cleaned + '.npz',
          labels,
          samples,
          epochs: Math.min(200, Math.max(1, Math.round(Number(epochs) || DEF_EPOCHS))),
        }),
      });
      if (!r.ok) throw new Error('HTTP ' + r.status);
      const d = await r.json();
      if (d && d.ok) {
        setSavedModel(String(d.path || ''));
        stopPrepPoll();
        setSaveStatus(`저장 완료: ${d.path} — 코드에서 tm.load_model('${d.path}') 로 사용하세요.`);
      } else {
        const err = (d && d.error) || '알 수 없는 오류';
        stopPrepPoll();
        setSaveStatus(`학습/저장 실패: ${err}${d && d.hint ? ` (${d.hint})` : ''}`);
      }
    } catch (e) {
      stopPrepPoll();
      setSaveStatus(`학습/저장 실패: 백엔드에 연결할 수 없습니다 (${e.message || e}). 서버(npm run server)가 실행 중인지 확인하세요.`);
    } finally {
      setSaving(false);
    }
  }, [canSave, filename, classes, epochs]);

  const pct = (v) => `${Math.round((v || 0) * 100)}%`;

  return (
    <div className="tm-panel">
      {/* 팝업 헤더가 "티처블머신" 이라고 알려주므로 제목을 또 쓰지 않는다. */}
      <p className="bpy-phint">
        웹캠으로 사진을 모아 AI에게 직접 가르칩니다. <b>이름표마다 30장 이상</b> 모으면 잘 맞혀요.
      </p>

      {camError && <div id="tm-cam-error" className="bpy-alert stop tm-alert">{camError}</div>}

      <div className="tm-board">
        {/* ── 왼쪽: 이름표(클래스) 열 ───────────────────────────────────── */}
        <div className="tm-col tm-col-classes">
          <div id="tm-classes" className="tm-classes">
            {classes.map((c, i) => {
              const n = c.samples.length;
              const camHere = camOwner === i;
              const shots = c.samples.slice(-MAX_THUMBS);
              const hidden = n - shots.length;
              return (
                <div id={`tm-class-${i}`} key={i} className={`tm-class${camHere ? ' live' : ''}`}>
                  <div className="tm-class-head">
                    <input
                      id={`tm-classname-${i}`}
                      className="tm-name"
                      value={c.name}
                      aria-label={`${i + 1}번째 이름표의 이름`}
                      title="눌러서 이름을 바꿀 수 있어요"
                      onChange={(e) => renameClass(i, e.target.value)}
                    />
                    <span id={`tm-count-${i}`} className={`tm-count${n >= 30 ? ' ok' : ''}`}>
                      이미지 샘플 {n}개
                    </span>
                    <span className="tm-kebab-wrap">
                      <button
                        type="button"
                        className="tm-kebab"
                        aria-label={`${c.name} 메뉴`}
                        aria-expanded={menuIdx === i}
                        onClick={() => setMenuIdx((m) => (m === i ? -1 : i))}
                      >⋮</button>
                      {menuIdx === i && (
                        <div className="tm-menu" role="menu">
                          <button type="button" role="menuitem" onClick={() => clearClass(i)} disabled={n === 0}>
                            <i className="fa-solid fa-eraser"></i> 사진 모두 비우기
                          </button>
                          <button type="button" role="menuitem" onClick={() => removeClass(i)} disabled={classes.length <= 2}>
                            <i className="fa-solid fa-trash"></i> 이 이름표 지우기
                          </button>
                        </div>
                      )}
                    </span>
                  </div>

                  {/* 높이 고정 — 카메라가 켜져도 아래 버튼이 밀리지 않게(누른 채로 버튼이
                      커서 밑에서 빠져나가 수집이 끊기던 버그의 재발 방지). */}
                  <div className="tm-class-body">
                    <div className="tm-slot">
                      {camHere ? (
                        <video ref={camVideoRef} muted playsInline />
                      ) : (
                        <div className="tm-slot-ph">
                          <i className="fa-solid fa-video"></i>
                          <span>카메라 꺼짐</span>
                        </div>
                      )}
                      {camHere && capturingIdx === i && <span className="tm-rec">● 수집 중</span>}
                    </div>
                    <div className="tm-thumbs">
                      {shots.length === 0 && <div className="tm-thumbs-ph">모은 사진이 여기에 쌓여요</div>}
                      {shots.map((s, k) => (
                        <img key={k} className="tm-thumb" src={s.jpeg} alt="" draggable="false" />
                      ))}
                      {hidden > 0 && <span className="tm-more">+{hidden}</span>}
                    </div>
                  </div>

                  <div className="tm-class-foot">
                    <button
                      type="button"
                      className={`tm-inbtn${camHere ? ' on' : ''}`}
                      onClick={() => toggleCam(i)}
                      disabled={mode === 'training'}
                    >
                      <i className="fa-solid fa-camera-rotate"></i> 웹캠 {camHere ? '끄기' : '켜기'}
                    </button>
                    <button
                      type="button"
                      className="tm-inbtn"
                      onClick={() => fileInputs.current[i] && fileInputs.current[i].click()}
                      disabled={mode === 'training'}
                    >
                      <i className="fa-solid fa-folder-open"></i> 사진 넣기
                    </button>
                    <input
                      ref={(el) => { fileInputs.current[i] = el; }}
                      id={`tm-upload-${i}`}
                      className="tm-file"
                      type="file"
                      accept="image/*"
                      multiple
                      aria-label={`${c.name} 에 사진 넣기`}
                      onChange={(e) => {
                        // FileList 는 살아 있는 객체다 — value 를 비우기 전에 배열로 떠 둔다.
                        const picked = Array.from(e.target.files || []);
                        e.target.value = '';  // 같은 파일을 다시 골라도 change 가 다시 난다
                        onUpload(i, picked);
                      }}
                    />
                    {/* 카드의 주인공 — 한 줄 전체를 쓰므로 라벨이 바뀌어도 폭/위치가 고정된다 */}
                    <button
                      id={`tm-capture-${i}`}
                      type="button"
                      className={`tm-shoot${capturingIdx === i ? ' on' : ''}`}
                      onMouseDown={() => startCapture(i)}
                      onMouseUp={stopCapture}
                      onMouseLeave={() => { if (capturingRef.current === i) stopCapture(); }}
                      disabled={mode === 'training'}
                    >
                      <i className="fa-solid fa-camera"></i>
                      {capturingIdx === i ? '수집 중…' : '누르는 동안 수집'}
                    </button>
                  </div>
                </div>
              );
            })}
            <button id="tm-add-class" type="button" className="tm-addcls" onClick={addClass} disabled={mode === 'training'}>
              <i className="fa-solid fa-plus"></i> 클래스 추가
            </button>
          </div>
        </div>

        <div className="tm-arrow" aria-hidden="true"><i className="fa-solid fa-chevron-right"></i></div>

        {/* ── 가운데: 학습 ─────────────────────────────────────────────── */}
        <div className="tm-col tm-col-train">
          <div className="tm-card">
            <h4 className="tm-cardhead">학습</h4>
            <button
              id="tm-train"
              type="button"
              className="btn btn-primary tm-trainbtn"
              onClick={train}
              disabled={!canTrain || mode === 'training'}
            >
              {mode === 'training' ? '학습 중…' : '학습'}
            </button>

            <div className="tm-prog" role="progressbar" aria-valuemin={0} aria-valuemax={100}
              aria-valuenow={Math.round(progress * 100)} aria-label="학습 진행">
              <span className="tm-prog-fill" style={{ width: pct(progress) }} />
            </div>

            <div id="tm-status" className="bpy-note tm-status">{status}</div>

            {!canTrain && mode !== 'training' && (
              <div className="bpy-note">이름표 2개 이상 · 이름표마다 사진이 있어야 학습할 수 있어요.
                (지금까지 모은 사진 {total}장)</div>
            )}

            <div className={`tm-adv${advOpen ? ' open' : ''}`}>
              <button type="button" className="tm-adv-toggle" onClick={() => setAdvOpen((v) => !v)} aria-expanded={advOpen}>
                <i className={`fa-solid fa-chevron-${advOpen ? 'down' : 'right'}`}></i> 고급 설정
              </button>
              {advOpen && (
                <div className="tm-adv-body">
                  <label className="tm-advrow">
                    <span>반복 횟수</span>
                    <input className="bpy-field tm-num" type="number" min="1" max="200" step="1"
                      value={epochs} onChange={(e) => setEpochs(e.target.value)} disabled={mode === 'training'} />
                  </label>
                  <label className="tm-advrow">
                    <span>묶음 크기</span>
                    <input className="bpy-field tm-num" type="number" min="1" max="512" step="1"
                      value={batchSize} onChange={(e) => setBatchSize(e.target.value)} disabled={mode === 'training'} />
                  </label>
                  <label className="tm-advrow">
                    <span>학습률</span>
                    <input className="bpy-field tm-num" type="number" min="0.00001" max="1" step="0.0001"
                      value={learningRate} onChange={(e) => setLearningRate(e.target.value)} disabled={mode === 'training'} />
                  </label>
                  <div className="bpy-note">
                    <b>반복 횟수</b>는 저장할 때 파이썬 학습에도 그대로 전달됩니다.{' '}
                    <b>묶음 크기</b>·<b>학습률</b>은 이 화면의 미리보기 학습에만 쓰이고,{' '}
                    저장할 때 파이썬은 <b>기본값으로 학습합니다</b>.
                  </div>
                  <button type="button" className="tm-adv-reset"
                    onClick={() => { setEpochs(DEF_EPOCHS); setBatchSize(DEF_BATCH); setLearningRate(DEF_LR); }}>
                    기본값으로 되돌리기
                  </button>
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="tm-arrow" aria-hidden="true"><i className="fa-solid fa-chevron-right"></i></div>

        {/* ── 오른쪽: 미리보기 ─────────────────────────────────────────── */}
        <div className="tm-col tm-col-preview">
          <div className="tm-card">
            <h4 className="tm-cardhead">
              미리보기
              <label className="tm-switch" title="미리보기 카메라 켜기/끄기">
                <input type="checkbox" id="tm-preview-toggle" checked={previewOn}
                  onChange={(e) => setPreviewOn(e.target.checked)} />
                <span className="tm-switch-track"><span className="tm-switch-knob" /></span>
                <span className="tm-switch-lb">입력 {previewOn ? '켬' : '끔'}</span>
              </label>
            </h4>

            {/* 카메라 + (출력·저장) — 패널이 넓으면 나란히, 좁으면 카메라 아래로 접힌다 */}
            <div className="tm-preview-body">
            <div id="tm-webcam-wrap" className="tm-cam">
              {previewOn ? (
                <video ref={previewVideoRef} muted playsInline />
              ) : (
                <div id="tm-webcam-placeholder" className="tm-cam-ph">
                  <i className="fa-solid fa-video"></i>
                  입력을 켜면 카메라가 보입니다
                </div>
              )}
              {mode === 'trained' && preview && (
                <div id="tm-preview-overlay" className="tm-pred">
                  <span id="tm-preview-label">{preview.label}</span>
                  <b>{pct(preview.confidence)}</b>
                </div>
              )}
            </div>

            {mode === 'trained' ? (
              <div id="tm-trained" className="tm-result">
                <div className="bpy-alert run">
                  학습 완료{trainedInfo ? ` (${trainedInfo.epochs}번 반복)` : ''} — 카메라에 대 보고 맞히는지 확인하세요.
                </div>
                <div className="tm-out">
                  <div className="tm-out-h">출력</div>
                  {classes.map((c, i) => {
                    const p = preview && preview.all ? (preview.all[i] || 0) : 0;
                    const top = preview && preview.all && p === Math.max(...preview.all);
                    return (
                      <div className={`tm-bar-row${top ? ' top' : ''}`} key={i}>
                        <span className="tm-bar-lb" title={c.name}>{c.name}</span>
                        <span className="tm-bar"><span className="tm-bar-fill" style={{ width: pct(p) }} /></span>
                        <span className="tm-bar-pc">{pct(p)}</span>
                      </div>
                    );
                  })}
                </div>

                <div className="tm-save">
                  <div className="tm-save-h">모델 저장</div>
                  <div className="bpy-note">
                    저장하면 모아 둔 사진으로 <b>파이썬이 다시 학습</b>해 <code>.npz</code> 모델을 워크스페이스에 만듭니다.
                    코드에서는 <code>tm.load_model("이름.npz")</code> 로 씁니다.
                  </div>
                  <div className="tm-saverow">
                    <input id="tm-filename" className="bpy-field" value={filename} onChange={(e) => setFilename(e.target.value)}
                      placeholder="모델 파일 이름" aria-label="모델 파일 이름" disabled={saving} />
                    <span className="tm-ext">.npz</span>
                    <button id="tm-save" type="button" className="btn btn-primary bpy-act" onClick={save} disabled={saving || !canSave}>
                      {saving ? '학습 중…' : '저장'}
                    </button>
                  </div>
                  {saveStatus && <div id="tm-save-status" className="bpy-note strong">{saveStatus}</div>}
                </div>
              </div>
            ) : (
              <div className="bpy-note tm-result-ph">
                학습을 마치면 여기에 이름표별 확률 막대와 <b>저장</b> 칸이 나타납니다.
              </div>
            )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

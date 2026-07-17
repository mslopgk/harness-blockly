// teachable.js — Teachable Machine(TF.js + MobileNet 전이학습) 래퍼. 브라우저 전용.
//   - MobileNet(v2)은 임베딩 추출기로만 사용, 로컬 vendored(/vendor/mobilenet/model.json) 로드.
//   - 작은 dense head 만 학습/저장. 저장 형식은 tmPack 의 blockpy-tm-v1.
//   - tf.js 는 동적 import 로 지연 로드(메인 번들 비대화 방지).
//   - 테스트 훅: window.__TM_TEST_FEATURIZER(input)->number[] 가 있으면 MobileNet 대신 사용.
import { packEnvelope, unpackEnvelope } from './tmPack.js';

const MOBILENET_URL = '/vendor/mobilenet/model.json';
const IMAGE_SIZE = 224;
const BASE_ID = 'mobilenet-v2';

let _tf = null;
let _base = null; // 로드된 mobilenet 모델

async function ensureTf() {
  if (_tf) return _tf;
  _tf = await import('@tensorflow/tfjs');
  return _tf;
}

function testFeaturizer() {
  return (typeof window !== 'undefined' && window.__TM_TEST_FEATURIZER) || null;
}

async function ensureBase() {
  if (_base) return _base;
  await ensureTf();
  const mobilenet = await import('@tensorflow-models/mobilenet');
  try {
    _base = await mobilenet.load({ version: 2, alpha: 1.0, modelUrl: MOBILENET_URL });
  } catch (e) {
    throw new Error('MobileNet 로드 실패 — 오프라인 자산이 없습니다. `npm run vendor` 를 온라인에서 실행하세요. (' + e.message + ')');
  }
  return _base;
}

// input(HTMLVideo/Image/Canvas) -> 임베딩 텐서 [1, D].
async function featurize(input) {
  const tf = await ensureTf();
  const fake = testFeaturizer();
  if (fake) {
    const vec = await fake(input);
    return tf.tensor2d(Array.from(vec), [1, vec.length]);
  }
  const base = await ensureBase();
  return tf.tidy(() => {
    const img = tf.browser.fromPixels(input);
    return base.infer(img, true); // embedding=true → pre-logits 특징벡터
  });
}

async function buildHead(inputDim, numClasses) {
  const tf = await ensureTf();
  const model = tf.sequential();
  model.add(tf.layers.dense({ inputShape: [inputDim], units: 100, activation: 'relu' }));
  model.add(tf.layers.dense({ units: numClasses, activation: 'softmax' }));
  model.compile({ optimizer: tf.train.adam(0.001), loss: 'categoricalCrossentropy', metrics: ['accuracy'] });
  return model;
}

// samples: [{classIndex, embedding: tf.Tensor2D [1,D]}, ...]
async function trainHead(head, samples, numClasses, opts = {}) {
  const tf = await ensureTf();
  const xs = tf.concat(samples.map((s) => s.embedding), 0);
  const ys = tf.oneHot(tf.tensor1d(samples.map((s) => s.classIndex), 'int32'), numClasses);
  try {
    return await head.fit(xs, ys, {
      epochs: opts.epochs || 20,
      batchSize: Math.min(opts.batchSize || 16, samples.length),
      shuffle: true,
      callbacks: opts.onEpoch ? { onEpochEnd: (e, logs) => opts.onEpoch(e, logs) } : undefined,
    });
  } finally {
    xs.dispose();
    ys.dispose();
  }
}

// embedding [1,D] -> {index, label, confidence, all}
async function predictTop(head, embedding, labels) {
  const logits = head.predict(embedding);
  const data = await logits.data();
  logits.dispose();
  let best = 0;
  for (let i = 1; i < data.length; i++) if (data[i] > data[best]) best = i;
  return { index: best, label: labels[best], confidence: data[best], all: Array.from(data) };
}

// {head, labels, imageSize?, base?} -> blockpy-tm-v1 JSON 문자열
async function serializeModel({ head, labels, imageSize = IMAGE_SIZE, base = BASE_ID }) {
  const tf = await ensureTf();
  let captured = null;
  await head.save(tf.io.withSaveHandler(async (artifacts) => {
    captured = artifacts;
    return { modelArtifactsInfo: { dateSaved: new Date(), modelTopologyType: 'JSON' } };
  }));
  return packEnvelope({
    labels,
    imageSize,
    base,
    artifacts: {
      modelTopology: captured.modelTopology,
      weightSpecs: captured.weightSpecs,
      weightData: captured.weightData,
    },
  });
}

// blockpy-tm-v1 JSON -> {head, labels, imageSize, base}
async function deserializeModel(jsonString) {
  const tf = await ensureTf();
  const { labels, imageSize, base, artifacts } = unpackEnvelope(jsonString);
  const head = await tf.loadLayersModel(tf.io.fromMemory({
    modelTopology: artifacts.modelTopology,
    weightSpecs: artifacts.weightSpecs,
    weightData: artifacts.weightData,
  }));
  return { head, labels, imageSize, base };
}

const api = {
  ensureTf, featurize, buildHead, trainHead, predictTop, serializeModel, deserializeModel, IMAGE_SIZE, BASE_ID,
};
if (typeof window !== 'undefined') window.BlockPyTM = api;

export { ensureTf, featurize, buildHead, trainHead, predictTop, serializeModel, deserializeModel, IMAGE_SIZE, BASE_ID };

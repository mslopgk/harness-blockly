// tmPack.js — Teachable Machine 모델 봉투(blockpy-tm-v1) 직렬화/역직렬화. 순수 로직(tf 의존 없음).
//
// 저장 형식: { format, labels, imageSize, base, head:{ modelTopology, weightSpecs, weightData(base64) } }
// head(분류기)만 담는다. MobileNet 특징추출기는 저장하지 않고 런타임에 로컬 vendored 를 재사용한다.
//
// 브라우저·Node 양쪽 동작: base64 는 Buffer(있으면) 아니면 btoa/atob 사용.
// 레포 관례상 순수 ESM export (bare module.exports 금지 — Vite dev 흰화면 원인).

const FORMAT = 'blockpy-tm-v1';

// ArrayBuffer -> base64 문자열.
function abToBase64(buf) {
  const bytes = new Uint8Array(buf);
  if (typeof Buffer !== 'undefined') return Buffer.from(bytes).toString('base64');
  let bin = '';
  for (let i = 0; i < bytes.length; i++) bin += String.fromCharCode(bytes[i]);
  return btoa(bin);
}

// base64 문자열 -> ArrayBuffer.
function base64ToAb(b64) {
  if (typeof Buffer !== 'undefined') {
    const buf = Buffer.from(b64, 'base64');
    return buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength);
  }
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

// tf.io save handler 가 준 artifacts({modelTopology, weightSpecs, weightData:ArrayBuffer})를 단일 JSON 문자열로.
function packEnvelope({ labels, imageSize, base, artifacts }) {
  if (!Array.isArray(labels) || labels.length < 2) {
    throw new Error('라벨(클래스)은 2개 이상이어야 저장할 수 있습니다.');
  }
  if (!artifacts) throw new Error('head 아티팩트(모델 가중치)가 필요합니다.');
  return JSON.stringify({
    format: FORMAT,
    labels,
    imageSize,
    base,
    head: {
      modelTopology: artifacts.modelTopology,
      weightSpecs: artifacts.weightSpecs,
      weightData: abToBase64(artifacts.weightData),
    },
  });
}

// 단일 JSON(문자열/객체) -> {labels, imageSize, base, artifacts:{modelTopology, weightSpecs, weightData:ArrayBuffer}}.
function unpackEnvelope(jsonStringOrObj) {
  const j = typeof jsonStringOrObj === 'string' ? JSON.parse(jsonStringOrObj) : jsonStringOrObj;
  if (!j || j.format !== FORMAT) {
    throw new Error('지원하지 않는 모델 형식입니다: ' + (j && j.format));
  }
  const h = j.head || {};
  return {
    labels: j.labels,
    imageSize: j.imageSize,
    base: j.base,
    artifacts: {
      modelTopology: h.modelTopology,
      weightSpecs: h.weightSpecs,
      weightData: base64ToAb(h.weightData),
    },
  };
}

export { FORMAT, abToBase64, base64ToAb, packEnvelope, unpackEnvelope };

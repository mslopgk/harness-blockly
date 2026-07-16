// affineCalib.js — 카메라 픽셀 → 로봇 mm 아핀(2x3) 변환, 순수 JS 최소제곱.
//
// pairs = [ [[u,v],[x,y]], ... ]   u,v = 픽셀좌표 · x,y = 로봇 mm좌표
// M     = [ [a,b,c], [d,e,f] ]     x = a*u+b*v+c ,  y = d*u+e*v+f
//
// 커리큘럼 파이썬 common 의 estimate_affine / apply_affine 을 프론트로 미러한 것.
// Blockly/DOM 의존 없음(순수). 레포 util 관례대로 module.exports (node require 로 검증 가능,
// Vite 는 default import 로 소비). 블록 코어와 무관.

// 3x3 선형계 (M·p = b) 를 부분피벗 가우스-조던 소거로 푼다. 특이하면 null.
function solve3(A, b) {
  // 증강행렬 [A|b] (파괴적 복사)
  const m = [
    [A[0][0], A[0][1], A[0][2], b[0]],
    [A[1][0], A[1][1], A[1][2], b[1]],
    [A[2][0], A[2][1], A[2][2], b[2]],
  ];
  for (let col = 0; col < 3; col++) {
    // 부분 피벗: 이 열에서 절댓값이 가장 큰 행을 위로
    let piv = col;
    for (let r = col + 1; r < 3; r++) {
      if (Math.abs(m[r][col]) > Math.abs(m[piv][col])) piv = r;
    }
    if (Math.abs(m[piv][col]) < 1e-12) return null; // 특이(해 없음/무수)
    if (piv !== col) { const t = m[piv]; m[piv] = m[col]; m[col] = t; }
    // 다른 모든 행에서 이 열을 소거 → 대각화
    for (let r = 0; r < 3; r++) {
      if (r === col) continue;
      const f = m[r][col] / m[col][col];
      for (let k = col; k < 4; k++) m[r][k] -= f * m[col][k];
    }
  }
  return [m[0][3] / m[0][0], m[1][3] / m[1][1], m[2][3] / m[2][2]];
}

// 정규방정식 A^T A p = A^T t 구성. 각 대응점의 A행 = [u, v, 1], 목표 t = (axis 0=x, 1=y).
function normalEqn(pairs, axis) {
  const ATA = [[0, 0, 0], [0, 0, 0], [0, 0, 0]];
  const ATb = [0, 0, 0];
  for (const [[u, v], xy] of pairs) {
    const t = xy[axis];
    const row = [u, v, 1];
    for (let i = 0; i < 3; i++) {
      ATb[i] += row[i] * t;
      for (let j = 0; j < 3; j++) ATA[i][j] += row[i] * row[j];
    }
  }
  return [ATA, ATb];
}

function det3(m) {
  return (
    m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) -
    m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) +
    m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0])
  );
}

// 픽셀점이 3개 미만이거나 거의 한 직선/중복 → 정규행렬 ATA 가 특이(det≈0, 규모 상대).
function isDegenerate(pairs) {
  if (!pairs || pairs.length < 3) return true;
  const [ATA] = normalEqn(pairs, 0);
  const scale = ATA[0][0] + ATA[1][1] + ATA[2][2]; // trace ≈ 데이터 규모
  if (scale <= 0) return true;
  return Math.abs(det3(ATA)) <= 1e-9 * scale * scale * scale;
}

// 대응점들로 아핀 2x3 를 최소제곱 추정. n<3 또는 퇴화면 throw.
function estimateAffine(pairs) {
  if (!pairs || pairs.length < 3) {
    throw new Error('아핀 추정에는 대응점 3개 이상이 필요합니다.');
  }
  if (isDegenerate(pairs)) {
    throw new Error('대응점이 거의 한 직선 위에 있습니다 — 점을 넓게 퍼뜨려 다시 찍으세요.');
  }
  const [ATAx, ATbx] = normalEqn(pairs, 0);
  const [ATAy, ATby] = normalEqn(pairs, 1);
  const px = solve3(ATAx, ATbx);
  const py = solve3(ATAy, ATby);
  if (!px || !py) throw new Error('아핀 변환을 풀 수 없습니다(퇴화된 대응점).');
  return [px, py];
}

// 아핀 M 으로 픽셀 [u,v] → 로봇 [x,y] mm.
function applyAffine(M, uv) {
  const u = uv[0], v = uv[1];
  return [
    M[0][0] * u + M[0][1] * v + M[0][2],
    M[1][0] * u + M[1][1] * v + M[1][2],
  ];
}

// 등록 대응점 재투영 오차(mm): {mean, max}.
function reprojectionError(M, pairs) {
  if (!pairs || pairs.length === 0) return { mean: 0, max: 0 };
  let sum = 0, max = 0;
  for (const [[u, v], [x, y]] of pairs) {
    const p = applyAffine(M, [u, v]);
    const e = Math.hypot(p[0] - x, p[1] - y);
    sum += e;
    if (e > max) max = e;
  }
  return { mean: sum / pairs.length, max };
}

export { estimateAffine, applyAffine, isDegenerate, reprojectionError };

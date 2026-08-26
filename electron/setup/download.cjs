// 온라인 설치본용 내려받기 도우미.
//
// 왜 있나: 전부 담으면 설치파일이 1.2GB 다(파이썬 199MB + opencode 172MB + DobotLink 401MB…).
// 그래서 앱 본체만 담아 배포하고, 나머지는 첫 실행 때 여기서 받아 갖춘다.
//
// 지켜야 할 것 — 이 셋이 없으면 교실에서 설치가 조용히 깨진다:
//   1) 크기·해시 검증. 반쯤 받다 끊긴 파일을 그대로 쓰면 한참 뒤 알 수 없는 오류로 터진다.
//   2) 재시도. 학교 네트워크는 자주 끊긴다.
//   3) 진행률. 335MB 를 말없이 받으면 사용자는 멈춘 줄 안다.
const fs = require('fs');
const path = require('path');
const https = require('https');
const http = require('http');
const crypto = require('crypto');

const MAX_TRIES = 3;

function human(bytes) {
  if (!bytes || bytes < 0) return '?';
  const mb = bytes / 1048576;
  return mb >= 1 ? mb.toFixed(1) + 'MB' : Math.round(bytes / 1024) + 'KB';
}

// npm 의 integrity('sha512-<base64>') 와 python.org 의 sha256(hex) 를 모두 받는다.
function verifyDigest(file, spec) {
  if (!spec) return { ok: true, why: '해시 미지정' };
  const buf = fs.readFileSync(file);
  if (spec.sha256) {
    const got = crypto.createHash('sha256').update(buf).digest('hex');
    return { ok: got === spec.sha256, why: 'sha256 ' + got.slice(0, 12) };
  }
  if (spec.sha512) {
    const got = crypto.createHash('sha512').update(buf).digest('base64');
    return { ok: got === spec.sha512, why: 'sha512 ' + got.slice(0, 12) };
  }
  if (spec.integrity) {
    const m = /^sha512-(.+)$/.exec(spec.integrity);
    if (!m) return { ok: true, why: 'integrity 형식 모름' };
    const got = crypto.createHash('sha512').update(buf).digest('base64');
    return { ok: got === m[1], why: 'integrity ' + got.slice(0, 12) };
  }
  return { ok: true, why: '해시 미지정' };
}

// 리다이렉트를 따라가며 한 번 받는다. onProgress(받은바이트, 전체바이트)
function fetchOnce(url, dest, onProgress, depth) {
  depth = depth || 0;
  return new Promise(function (resolve, reject) {
    if (depth > 5) return reject(new Error('리다이렉트가 너무 많습니다'));
    const lib = url.indexOf('https:') === 0 ? https : http;
    const req = lib.get(url, { timeout: 60000 }, function (res) {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        const next = new URL(res.headers.location, url).toString();
        return resolve(fetchOnce(next, dest, onProgress, depth + 1));
      }
      if (res.statusCode !== 200) {
        res.resume();
        return reject(new Error('HTTP ' + res.statusCode));
      }
      const total = Number(res.headers['content-length'] || 0);
      let got = 0;
      const out = fs.createWriteStream(dest);
      res.on('data', function (c) { got += c.length; if (onProgress) onProgress(got, total); });
      res.pipe(out);
      out.on('finish', function () { out.close(function () { resolve({ bytes: got, total: total }); }); });
      out.on('error', reject);
      res.on('error', reject);
    });
    req.on('timeout', function () { req.destroy(new Error('응답이 없습니다(60초)')); });
    req.on('error', reject);
  });
}

// 한 항목을 받아 검증한다. 이미 받아 둔 것이 검증을 통과하면 다시 받지 않는다.
// item: { id, label, url, sha256?, sha512?, integrity?, bytes? }
async function download(item, dest, onEvent) {
  function say(msg, extra) {
    if (!onEvent) return;
    const e = { id: item.id, label: item.label, msg: msg };
    if (extra) Object.assign(e, extra);
    onEvent(e);
  }

  if (fs.existsSync(dest)) {
    // 재사용 판정은 **엄격해야 한다**. 실측: 크기 허용 오차를 1KB 로 뒀더니, 해시가 없는 항목에서
    // 7바이트가 덧붙은 깨진 파일을 정상으로 보고 그대로 썼다. 그래서
    //   - 해시가 있으면 해시로 판정하고
    //   - 해시가 없으면 크기가 **정확히** 같을 때만 재사용하며
    //   - 해시도 크기도 없으면(내용이 바뀌는 get-pip 같은 것) 재사용하지 않고 다시 받는다.
    const hasDigest = !!(item.sha256 || item.sha512 || item.integrity);
    const v = verifyDigest(dest, item);
    const sizeOk = item.bytes ? fs.statSync(dest).size === item.bytes : false;
    if (v.ok && (hasDigest || sizeOk)) { say('이미 받아 둔 것을 씁니다'); return { reused: true }; }
    fs.unlinkSync(dest);   // 검증 실패 = 반쯤 받다 끊겼거나 손상된 파일. 지우고 다시 받는다.
  }

  fs.mkdirSync(path.dirname(dest), { recursive: true });
  let lastErr = null;
  for (let attempt = 1; attempt <= MAX_TRIES; attempt++) {
    const tmp = dest + '.part';
    try {
      say(attempt === 1 ? '내려받는 중 (' + human(item.bytes) + ')' : '다시 시도 ' + attempt + '/' + MAX_TRIES);
      let lastPct = -1;
      await fetchOnce(item.url, tmp, function (got, total) {
        const t = total || item.bytes || 0;
        if (!t) return;
        const pct = Math.floor((got / t) * 100);
        if (pct !== lastPct && pct % 5 === 0) { lastPct = pct; say('내려받는 중 ' + pct + '%', { percent: pct }); }
      });
      const v = verifyDigest(tmp, item);
      if (!v.ok) throw new Error('파일이 깨졌습니다 (' + v.why + ')');
      fs.renameSync(tmp, dest);
      say('받기 완료', { percent: 100 });
      return { reused: false };
    } catch (e) {
      lastErr = e;
      try { if (fs.existsSync(dest + '.part')) fs.unlinkSync(dest + '.part'); } catch (_) { /* noop */ }
      if (attempt < MAX_TRIES) await new Promise(function (r) { setTimeout(r, 2000 * attempt); });
    }
  }
  throw new Error(item.label + ' 내려받기 실패: ' + (lastErr && lastErr.message));
}

module.exports = { download: download, verifyDigest: verifyDigest, human: human };

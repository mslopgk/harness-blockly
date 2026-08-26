// 온라인 설치본의 "첫 실행 준비" 절차.
//
// 설치파일에는 앱 본체만 들어 있고, 무거운 것(파이썬·AI 도우미·DobotLink·tensorflow)은
// 여기서 받아 갖춘다. 받는 목록과 출처·해시는 manifest.json 에 있다.
//
// 어디에 두나: 설치 폴더가 아니라 **userData**(%APPDATA%/BlockPy) 아래에 둔다.
//   - 설치 폴더는 쓰기 권한이 없을 수 있다(관리자 설치·정책 PC).
//   - 앱을 지웠다 다시 깔아도 받아 둔 것을 그대로 재사용한다.
//
// 멱등이다. 이미 갖춰진 단계는 건너뛴다. 중간에 실패해도 다시 부르면 이어서 한다.
const fs = require('fs');
const path = require('path');
const os = require('os');
const { execFileSync, spawnSync } = require('child_process');
const { download, human } = require('./download.cjs');

const MANIFEST = require('./manifest.json');

// PowerShell 로 zip 을 푼다(윈도우 기본 제공, 별도 의존성 없음).
function unzip(zipPath, destDir) {
  fs.mkdirSync(destDir, { recursive: true });
  execFileSync('powershell.exe', [
    '-NoProfile', '-NonInteractive', '-Command',
    `Expand-Archive -LiteralPath '${zipPath.replace(/'/g, "''")}' -DestinationPath '${destDir.replace(/'/g, "''")}' -Force`,
  ], { stdio: 'pipe', timeout: 300000 });
}

// npm 패키지(.tgz)에서 파일 하나만 꺼낸다. tar 는 윈도우 10 이상에 기본으로 있다.
function extractFromTgz(tgzPath, innerPath, destFile) {
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'bpy-tgz-'));
  try {
    execFileSync('tar', ['-xzf', tgzPath, '-C', tmp, innerPath], { stdio: 'pipe', timeout: 600000 });
    const src = path.join(tmp, innerPath);
    if (!fs.existsSync(src)) throw new Error(`꾸러미 안에 ${innerPath} 가 없습니다`);
    fs.mkdirSync(path.dirname(destFile), { recursive: true });
    fs.copyFileSync(src, destFile);
  } finally {
    try { fs.rmSync(tmp, { recursive: true, force: true }); } catch (_) { /* noop */ }
  }
}

// 임베더블 파이썬은 ._pth 가 있으면 격리 모드로 돌아 site-packages 와 PYTHONPATH 를 무시한다.
// 그대로 두면 pip 로 깐 것도, server.js 가 넘기는 runtime(=tm 모듈)도 import 되지 않는다.
// ._pth 는 **BOM 이 붙으면 첫 줄이 깨져 encodings 조차 못 찾는다** — 반드시 ASCII·BOM 없이 쓴다.
function preparePythonPath(pyDir) {
  const pth = fs.readdirSync(pyDir).find((f) => /^python\d+\._pth$/.test(f));
  if (!pth) throw new Error('파이썬 ._pth 파일을 찾지 못했습니다');
  const zipName = pth.replace('._pth', '.zip');
  const lines = [
    zipName,
    '.',
    'Lib\\site-packages',
    '',
    '# site enabled so student programs can import pip packages (numpy/cv2/dobotkit/tensorflow)',
    'import site',
  ];
  fs.writeFileSync(path.join(pyDir, pth), lines.join('\r\n'), { encoding: 'ascii' });
  fs.mkdirSync(path.join(pyDir, 'Lib', 'site-packages'), { recursive: true });

  // 격리 모드에서도 PYTHONPATH 를 살린다 — server.js 가 runtime 폴더를 그 변수로 넘긴다.
  const pthHook = 'import os,sys; [sys.path.insert(0,p) for p in os.environ.get("PYTHONPATH","").split(os.pathsep) if p and p not in sys.path]';
  fs.writeFileSync(path.join(pyDir, 'Lib', 'site-packages', '_blockpy_pythonpath.pth'), pthHook, { encoding: 'ascii' });
}

// pip 이름 ↔ import 이름이 다른 것만 적는다(나머지는 같다).
const IMPORT_NAME = { 'opencv-python': 'cv2' };

// 무엇이 갖춰져야 "준비 완료" 인지는 **매니페스트에서 끌어온다**.
// 하드코딩하면 매니페스트를 고쳐도 판정이 따라오지 않아, 안 깔린 것을 깔렸다고 하거나 그 반대가 된다.
function requiredImports() {
  return MANIFEST.pip.packages
    .map((s) => s.split(/[=<>!~ ]/)[0].trim())
    .filter(Boolean)
    .map((n) => IMPORT_NAME[n] || n.replace(/-/g, '_'));
}

function pyOk(pyExe) {
  if (!fs.existsSync(pyExe)) return false;
  const mods = requiredImports();
  if (!mods.length) return true;
  // import 는 tensorflow 가 끼면 수십 초가 걸린다. 설치 여부 판정에는 find_spec 이면 충분하다.
  const probe = 'import importlib.util,sys;'
    + 'missing=[m for m in ' + JSON.stringify(mods) + ' if importlib.util.find_spec(m) is None];'
    + 'sys.exit(1 if missing else 0)';
  const r = spawnSync(pyExe, ['-c', probe], { timeout: 120000 });
  return r.status === 0;
}

/**
 * 준비 절차 전체. onEvent({step, msg, percent?}) 로 진행 상황을 알린다.
 * root: userData 경로. 결과물은 root/runtime/{python,opencode} 와 root/runtime/mobilenet_v2_weights.h5
 */
async function ensureRuntime(root, onEvent) {
  const say = (step, msg, extra) => { if (onEvent) onEvent(Object.assign({ step, msg }, extra || {})); };
  const cache = path.join(root, 'downloads');
  const rt = path.join(root, 'runtime');
  const pyDir = path.join(rt, 'python');
  const pyExe = path.join(pyDir, 'python.exe');
  const ocExe = path.join(rt, 'opencode', 'opencode.exe');
  const weights = path.join(rt, 'mobilenet_v2_weights.h5');
  // 매니페스트에 없는 항목을 찾으면 알아볼 수 없는 오류(undefined.label)가 난다 — 여기서 분명히 말한다.
  const item = (id) => MANIFEST.downloads.find((d) => d.id === id);
  const need = (id) => {
    const it = item(id);
    if (!it) throw new Error('manifest.json 에 "' + id + '" 항목이 없습니다');
    return it;
  };
  const result = { pythonExe: null, opencodeExe: null, weights: null, warnings: [] };

  // ── 1) 파이썬 + 꾸러미 ─────────────────────────────────────────────────
  if (pyOk(pyExe)) {
    say('python', '파이썬은 이미 준비돼 있습니다');
  } else {
    const zip = path.join(cache, 'python-embed.zip');
    say('python', '파이썬을 준비합니다');
    await download(need('python'), zip, (e) => say('python', e.msg, e));
    fs.rmSync(pyDir, { recursive: true, force: true });
    unzip(zip, pyDir);
    preparePythonPath(pyDir);

    const getPip = path.join(cache, 'get-pip.py');
    await download(need('get-pip'), getPip, (e) => say('python', e.msg, e));
    say('python', 'pip 를 설치합니다');
    execFileSync(pyExe, [getPip, '--no-warn-script-location'], { stdio: 'pipe', timeout: 600000 });

    // tensorflow 가 가장 크다(휠 335MB). 한 번에 설치해 의존성 충돌을 pip 가 풀게 한다.
    say('python', 'AI 학습 준비물을 내려받습니다. 몇 분 걸립니다', { heavy: true });
    execFileSync(pyExe, ['-m', 'pip', 'install', '--no-warn-script-location'].concat(MANIFEST.pip.packages),
      { stdio: 'pipe', timeout: 3600000 });
    if (!pyOk(pyExe)) throw new Error('파이썬 꾸러미 설치를 마쳤지만 import 가 되지 않습니다');
    say('python', '파이썬 준비 완료');
  }
  result.pythonExe = pyExe;

  // ── 2) AI 도우미(opencode) ────────────────────────────────────────────
  if (fs.existsSync(ocExe)) {
    say('opencode', 'AI 도우미는 이미 준비돼 있습니다');
  } else {
    const tgz = path.join(cache, 'opencode.tgz');
    say('opencode', 'AI 도우미를 준비합니다');
    await download(need('opencode'), tgz, (e) => say('opencode', e.msg, e));
    extractFromTgz(tgz, need('opencode').extract, ocExe);
    say('opencode', 'AI 도우미 준비 완료');
  }
  result.opencodeExe = ocExe;

  // ── 3) MobileNet 가중치 (없어도 학습은 되지만 그때 인터넷이 필요하다) ──
  try {
    if (!item('mobilenet')) throw new Error('manifest.json 에 mobilenet 항목이 없습니다');
    await download(item('mobilenet'), weights, (e) => say('mobilenet', e.msg, e));
    result.weights = weights;
  } catch (e) {
    result.warnings.push('AI 학습 밑바탕을 받지 못했습니다 — 첫 학습 때 인터넷이 필요합니다: ' + e.message);
  }

  // ── 4) DobotLink (선택) — 로봇팔을 쓸 때만 필요하므로 실패해도 멈추지 않는다 ──
  const dl = item('dobotlink');   // 선택 — 없거나 실패해도 준비 절차를 멈추지 않는다
  const installed = path.join(process.env.LOCALAPPDATA || '', 'Programs', 'DobotLink', 'DobotLink.exe');
  if (fs.existsSync(installed)) {
    say('dobotlink', 'DobotLink 는 이미 설치돼 있습니다');
  } else {
    try {
      if (!dl) throw new Error('manifest.json 에 dobotlink 항목이 없습니다');
      const exe = path.join(cache, 'DobotLink-Setup.exe');
      say('dobotlink', '로봇팔 연결 프로그램을 준비합니다 (' + human(dl.bytes) + ')');
      await download(dl, exe, (e) => say('dobotlink', e.msg, e));
      say('dobotlink', 'DobotLink 설치 창을 엽니다 — 안내를 따라 진행해 주세요');
      spawnSync(exe, [], { stdio: 'ignore', timeout: 1800000 });
      try { fs.unlinkSync(exe); } catch (_) { /* noop */ }   // 400MB 를 돌려준다
    } catch (e) {
      result.warnings.push('DobotLink 를 설치하지 못했습니다 — 로봇팔을 쓰려면 직접 설치해야 합니다: ' + e.message);
    }
  }

  return result;
}

module.exports = { ensureRuntime };

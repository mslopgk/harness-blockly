// Build the Windows desktop installer and drop it in the repo's release/ folder.
//
// Why the detour: electron-builder extracts the Electron framework into <output>/win-unpacked via a
// `win-unpacked.tmp` → `win-unpacked` rename that throws EPERM on this repo's drive (E:). So we
// stage the heavy output under the user's home (on C:, where the rename works) and copy ONLY the
// final installer (+ blockmap) back into <repo>/release/ — the artifact lands in the project without
// fighting the EPERM, and the multi-hundred-MB win-unpacked never touches the repo drive.
//
// Run via `npm run dist` (which vendors offline assets + vite-builds first, then calls this).
const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const repo = path.join(__dirname, '..');
const staging = process.env.BLOCKPY_RELEASE_DIR || path.join(os.homedir(), 'blockpy-release');
const releaseDir = path.join(repo, 'release');

console.log('[build-desktop] staging output ->', staging);
// npmRebuild=false: node-pty 1.1.0 은 node-addon-api(N-API) 로 만들어져 있고
// prebuilds/win32-x64/*.node 를 함께 배포한다. N-API 바이너리는 Node ↔ Electron ABI 가 호환되므로
// 다시 컴파일할 필요가 없다. 반대로 리빌드를 시도하면 winpty 소스 빌드 단계에서
// 'GetCommitHash.bat' 이 없어 node-gyp 이 실패한다(실측: 설치파일 빌드가 여기서 멈췄다).
execFileSync(
  'npx',
  ['electron-builder', '--win', 'nsis', '--config.npmRebuild=false', `--config.directories.output=${staging}`],
  { stdio: 'inherit', cwd: repo, shell: true },
);

fs.mkdirSync(releaseDir, { recursive: true });
let copied = 0;
for (const f of fs.readdirSync(staging)) {
  if (/^BlockPy-Setup-.*\.exe(\.blockmap)?$/.test(f)) {
    fs.copyFileSync(path.join(staging, f), path.join(releaseDir, f));
    copied++;
    console.log('[build-desktop] ->', path.join('release', f));
  }
}
if (!copied) {
  console.error('[build-desktop] no installer found in', staging);
  process.exit(1);
}
console.log(`[build-desktop] done — installer in ${releaseDir}`);

// 위젯이 실제로 그려지는지 브라우저에서 확인한다. JSON 이 유효한 것만으로는
// 부족하다 — 키 이름을 바꾼 뒤 막대가 NaN% 로 그려질 수 있다.
import { chromium } from '@playwright/test';

const BASE = 'http://127.0.0.1:8899';
const PAGES = [
  '수업_중등2차시_가위바위보_핸드트래킹/사이트/sheet.html',
  '수업_중등2차시_가위바위보_핸드트래킹/사이트/plan.html',
  '수업_AI분리수거_로봇팔/사이트/logic.html',
  '수업_AI분리수거_로봇팔/사이트/sheet.html',
];

const b = await chromium.launch();
const p = await (await b.newContext({ viewport: { width: 1280, height: 900 } })).newPage();
const errs = [];
p.on('pageerror', (e) => errs.push('JS 오류: ' + e.message));
p.on('console', (m) => { if (m.type() === 'error') errs.push('console: ' + m.text()); });

let fail = 0;
for (const rel of PAGES) {
  errs.length = 0;
  await p.goto(`${BASE}/${rel}`, { waitUntil: 'load' });
  await p.waitForTimeout(1200);
  const r = await p.evaluate(() => {
    const out = { threshold: 0, nan: 0, flowBtns: 0, emptyLab: 0, steps: 0 };
    document.querySelectorAll('.ic-threshold').forEach((w) => {
      out.threshold++;
      w.querySelectorAll('.th-fill').forEach((f) => {
        if (/NaN|undefined/.test(f.textContent) || /NaN/.test(f.style.width)) out.nan++;
      });
      w.querySelectorAll('.th-lab').forEach((l) => { if (!l.textContent.trim()) out.emptyLab++; });
    });
    document.querySelectorAll('.ic-flow .fl-pick button').forEach((btn) => {
      out.flowBtns++;
      if (/NaN|undefined/.test(btn.textContent)) out.nan++;
    });
    out.steps = document.querySelectorAll('.ic-steps .st-line').length;
    return out;
  });
  const ok = r.nan === 0 && r.emptyLab === 0 && errs.length === 0;
  if (!ok) fail++;
  console.log(`${ok ? 'OK  ' : 'FAIL'} ${rel}`);
  console.log(`      임계값위젯 ${r.threshold} · 순서도버튼 ${r.flowBtns} · 단계줄 ${r.steps} · NaN ${r.nan} · 빈라벨 ${r.emptyLab}`);
  errs.slice(0, 4).forEach((e) => console.log('      ' + e));
}
await b.close();
console.log(fail ? `\n실패 ${fail}쪽` : '\n전부 정상');
process.exit(fail ? 1 : 0);

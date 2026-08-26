// 강의자료용 실제 프로그램 캡처 — Playwright 로 결정적·고해상도로 뽑는다.
//
// 왜 스크립트인가: 손으로 찍은 캡처는 UI 가 바뀌면 낡고, 다시 찍는 절차가 사람 머릿속에만 남는다
// (인쇄물 PDF 가 낡았던 것과 같은 실패). 패널 디자인을 고칠 때마다 이 스크립트를 다시 돌리면 된다.
//
// 사용법 (dev 서버 :3000 + 백엔드 :3001 이 떠 있어야 함):
//   node tools/capture_lecture_ui.mjs
//   node tools/capture_lecture_ui.mjs --only=P05,P06     # 일부만
//
// 산출물: 강의자료개발/_공용/프로그램캡처_20260731/  (파일명 = 캡처 ID_설명.png)
import { chromium } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const OUT = path.resolve(
  'C:/Users/user/busan-robotics/강의자료개발/_공용/프로그램캡처_20260731'
);
const BASE = process.env.BLOCKPY_URL || 'http://localhost:3000';
const only = (process.argv.find((a) => a.startsWith('--only=')) || '').split('=')[1];
const want = only ? new Set(only.split(',').map((s) => s.trim())) : null;
const pick = (id) => !want || want.has(id) || want.has(id.replace(/b$/, ''));

fs.mkdirSync(OUT, { recursive: true });
const shots = [];

async function shoot(page, id, name, target) {
  if (!pick(id)) return;
  const file = path.join(OUT, `${id}_${name}.png`);
  const loc = typeof target === 'string' ? page.locator(target) : target;
  if (loc && loc !== page) await loc.screenshot({ path: file });
  else await page.screenshot({ path: file });
  const kb = Math.round(fs.statSync(file).size / 1024);
  shots.push(`${id}_${name}.png (${kb}KB)`);
  console.log('  ✓', `${id}_${name}.png`, kb + 'KB');
}

// 팝업이 열리고 애니메이션(.16s)이 끝난 뒤를 찍는다 — 반투명 중간 프레임이 찍히면 안 된다.
async function openRail(page, key) {
  await page.locator(`#tab-btn-${key}`).click();
  await page.locator('.bpy-aux-popup.open').waitFor({ state: 'visible' });
  await page.waitForTimeout(400);
}
async function closeRail(page) {
  const pop = page.locator('.bpy-aux-popup.open');
  if (await pop.count()) {
    await page.locator('.bpy-aux-close').first().click();
    await page.waitForTimeout(250);
  }
}

const run = async () => {
  const browser = await chromium.launch({
    args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'],
  });
  const ctx = await browser.newContext({
    viewport: { width: 1600, height: 900 },
    deviceScaleFactor: 2,          // 인쇄·슬라이드에 넣어도 글자가 깨지지 않게 2배
    permissions: ['camera'],
  });
  const page = await ctx.newPage();
  console.log('→', BASE);
  await page.goto(BASE);
  // 앱이 **완전히** 준비될 때까지 기다린다.
  // 실측 문제: 툴박스가 뜬 뒤 2.5초만 기다리고 찍었더니, P01(첫 화면)이 부팅 중인 순간으로
  // 남았다 — 가운데 블록 판에 "Converting… introspecting libraries & building blocks" 스피너,
  // 실행 출력에는 "[Pyodide] Downloading Python runtime (~28 MB, one-time)". 이 그림이 강의자료
  // 19곳에 첫 화면으로 실려 학생이 처음 보는 장면이 로딩 화면이었다.
  // 조건 셋을 모두 만족할 때 찍는다: 툴박스 렌더 · 변환 오버레이 소멸 · 시작 데모 블록 등장.
  await page.locator('.blocklyToolbox').waitFor({ state: 'visible', timeout: 60000 });
  await page.locator('.convert-overlay').waitFor({ state: 'detached', timeout: 180000 }).catch(() => {});
  await page.waitForFunction(() => {
    const ws = window.__blocklyWorkspace;
    return ws && typeof ws.getAllBlocks === 'function' && ws.getAllBlocks(false).length > 0;
  }, { timeout: 180000 }).catch(() => {});
  await page.waitForTimeout(2500);

  // ── 기본 화면 ──
  await shoot(page, 'P01', '전체화면', page);
  await shoot(page, 'P02', '상단바', '.bpy-topbar');
  await shoot(page, 'P03', '툴박스', '.blocklyToolbox');
  await shoot(page, 'P04', 'AI도우미터미널', '.bpy-termcol');

  // 툴박스를 끝까지 내려 dobotkit · tm 이 보이는 상태 — 기존 캡처에 이 둘이 안 잡혀 있었다
  if (pick('P05')) {
    await page.locator('.blocklyToolbox').evaluate((el) => { el.scrollTop = el.scrollHeight; });
    await page.waitForTimeout(400);
    await shoot(page, 'P05', '툴박스_dobotkit_tm', '.blocklyToolbox');
    await page.locator('.blocklyToolbox').evaluate((el) => { el.scrollTop = 0; });
  }

  // ── 좌측 rail 패널 4개 (재설계본) ──
  for (const [id, key, name] of [
    ['P06', 'files', '파일패널'],
    ['P07', 'ai', 'AI패널'],
    ['P08', 'robot', '로봇패널'],
    ['P09', 'tm', 'TM패널'],
  ]) {
    if (!pick(id)) continue;
    await openRail(page, key);
    await shoot(page, id, name, '.bpy-aux-popup.open');
    await shoot(page, id + 'b', name + '_전체화면', page);
    await closeRail(page);
  }

  // ── AI 도우미 터미널: opencode 가 자동 실행된 화면 ──
  // 옛 P04 는 자동 실행 배선 이전(빈 PowerShell)이라 자료에 쓸 수 없다. 이것이 학생이 보는 화면이다.
  // opencode TUI 는 뜨는 데 몇 초 걸리므로 프롬프트 문구가 보일 때까지 기다린다.
  if (pick('P16')) {
    const term = page.locator('.ai-terminal-screen');
    await term.waitFor({ state: 'visible' });
    for (let i = 0; i < 30; i++) {                 // 최대 30초
      await page.waitForTimeout(1000);
      const txt = await term.innerText().catch(() => '');
      if (/opencode|Ask anything/i.test(txt)) break;
    }
    await shoot(page, 'P16', 'AI도우미_opencode', '.bpy-termcol');
    await shoot(page, 'P16b', 'AI도우미_opencode_전체화면', page);
  }

  // ── TM 을 실제로 써 본 상태: 3클래스 수집 완료 → 학습 완료 ──
  // 강의자료가 필요한 것은 빈 패널이 아니라 "학생 화면과 같은 상태" 다.
  // 카메라는 가짜 미디어스트림(초록 테스트 패턴)이라 실제 물체는 보이지 않는다 —
  // 자료에 넣을 때 그 사실을 캡션에 밝힌다.
  if (pick('P14') || pick('P15')) {
    await openRail(page, 'tm');
    await page.locator('#tm-add-class').click();            // 3클래스
    await page.waitForTimeout(300);
    for (const [i, name] of [[0, '캔'], [1, '플라스틱'], [2, '종이']]) {
      const f = page.locator(`#tm-classname-${i}`);
      await f.fill(name);
      const shot = page.locator(`#tm-capture-${i}`);
      await shot.hover();
      await page.mouse.down();
      // headless 는 GPU 가 없어 MobileNet 임베딩이 초당 1장 수준이다. 자료 문구인
      // '클래스마다 30장 이상' 과 화면이 어긋나지 않도록 충분히 길게 누른다.
      await page.waitForTimeout(46000);
      await page.mouse.up();
      await page.waitForTimeout(300);
    }
    await shoot(page, 'P14', 'TM_수집완료', '.bpy-aux-popup.open');
    await shoot(page, 'P14b', 'TM_수집완료_전체화면', page);

    await page.locator('#tm-filename').fill('분리수거').catch(() => {});
    await page.locator('#tm-train').click();
    await page.locator('#tm-trained').waitFor({ state: 'visible', timeout: 60000 });
    await page.waitForTimeout(1500);                          // 실시간 예측 배지가 뜰 시간
    await shoot(page, 'P15', 'TM_학습완료', '.bpy-aux-popup.open');
    await shoot(page, 'P15b', 'TM_학습완료_전체화면', page);
    await closeRail(page);
  }

  // ── 예제 갤러리(예시창) ──
  if (pick('P10')) {
    await page.locator('.bpy-btn', { hasText: '예제' }).first().click();
    await page.locator('.bpy-aux-popup.open').waitFor({ state: 'visible' });
    await page.waitForTimeout(600);
    await shoot(page, 'P10', '예제갤러리', '.bpy-aux-popup.open');
    await shoot(page, 'P10b', '예제갤러리_전체화면', page);
    await closeRail(page);
  }

  // ── 실제 수업 코드: 파이썬 코드 탭 · 블록 작업실 · 변환 ──
  // 1차시 예제(m1_ai_sorting)를 코드로 밀어넣고, 실제 화면 상태를 찍는다.
  if (pick('P11') || pick('P12') || pick('P13')) {
    const code = await fetch(`${BASE}/examples/m1_ai_sorting.py`).then((r) => r.text());
    await page.evaluate((src) => {
      // 앱이 노출한 테스트 훅이 없으므로 편집기 대신 상태를 직접 갈아끼우지 않고,
      // CodeMirror 문서를 직접 교체한다(사용자가 붙여넣은 것과 같은 경로).
      const cm = document.querySelector('.cm-content');
      if (!cm) return;
      const view = cm.cmView && cm.cmView.view;
      if (view) view.dispatch({ changes: { from: 0, to: view.state.doc.length, insert: src } });
    }, code);
    await page.waitForTimeout(800);

    await page.locator('.bpy-vtabs .tab-btn', { hasText: '파이썬' }).first().click();
    await page.waitForTimeout(600);
    await shoot(page, 'P11', '파이썬코드_수업예제', '.bpy-views');
    await shoot(page, 'P11b', '파이썬코드_전체화면', page);

    // 변환 → 블록 작업실
    await page.locator('.bpy-btn.conv').click();
    await page.waitForTimeout(3000);
    await page.locator('.bpy-vtabs .tab-btn', { hasText: '블록' }).first().click();
    await page.waitForTimeout(1200);
    await shoot(page, 'P12', '블록작업실_수업예제', '.bpy-views');
    await shoot(page, 'P12b', '블록작업실_전체화면', page);

    // 실행 → 실행 출력(작동창)
    await page.locator('.bpy-btn.run').click();
    await page.waitForTimeout(6000);
    await shoot(page, 'P13', '실행출력', '.bpy-outpane');
    await shoot(page, 'P13b', '실행출력_전체화면', page);
  }

  // ── 블록 전용(중등) 캡처 ──────────────────────────────────────────────
  // 중등 수업은 파이썬을 타이핑하지 않는다. 그래서 강의자료에 넣을 그림도 **블록 화면**이어야
  // 한다(P11 파이썬 코드 캡처는 중등 자료에서 쓰지 않는다 — 고등/교사용으로만 남긴다).
  // 코드를 편집기에 밀어넣고 변환하는 것은 어디까지나 **캡처를 만드는 방법**이고, 학생에게
  // 시키는 절차가 아니다. 학생은 툴박스에서 블록을 끌어다 같은 모양을 만든다.
  // 예제는 **갤러리 UI 로** 불러온다. 편집기(CodeMirror)에 값을 직접 밀어넣는 방식은
  // 실측에서 무시됐다 — React 상태가 되돌려서, 화면에는 시작 데모(conf=0.92 …)가 그대로
  // 남은 채 캡처됐다. 갤러리 클릭은 학생이 실제로 하는 경로라 결과가 화면과 반드시 일치한다.
  const blockShot = async (id, label, exampleId) => {
    if (!pick(id)) return;
    await page.locator('.bpy-btn', { hasText: '예제' }).first().click();
    await page.locator('.bpy-aux-popup.open').waitFor({ state: 'visible' });
    await page.locator(`[data-example-id="${exampleId}"]`).click();
    await page.waitForTimeout(1500);
    await closeRail(page);
    await page.locator('.bpy-btn.conv').click();          // 수업 예제는 자동 변환되지 않는다
    // 고정 대기(4.5초)는 부족했다 — 라이브러리 introspection 이 백엔드를 타서 더 걸린다.
    // "Converting…" 오버레이가 사라질 때까지 기다린다(실측 캡처에 오버레이가 찍혔다).
    await page.locator('.convert-overlay').waitFor({ state: 'detached', timeout: 120000 });
    await page.waitForTimeout(1200);
    await page.locator('.bpy-vtabs .tab-btn', { hasText: '블록' }).first().click();
    await page.waitForTimeout(1500);
    // 변환 직후 화면은 프로그램의 일부만 보인다(위·왼쪽이 잘림). 강의자료에는 **프로그램 전체**가
    // 한 장에 들어가야 하므로 전체가 보이도록 맞춘다.
    await page.evaluate(() => {
      const ws = window.__blocklyWorkspace;
      if (!ws) return;
      if (typeof ws.zoomToFit === 'function') ws.zoomToFit();
      if (typeof ws.scrollCenter === 'function') ws.scrollCenter();
    });
    await page.waitForTimeout(900);
    await shoot(page, id, label, '.bpy-views');
    await shoot(page, id + 'b', label + '_전체화면', page);
  };
  await blockShot('P17', '블록_1차시_완성', 'lesson-m1-sorting');
  await blockShot('P18', '블록_2차시_완성', 'lesson-m2-rps');

  // 툴박스에서 해당 칸을 눌러 **꺼낼 블록 목록(flyout)** 이 열린 상태 — "어디서 꺼내나요" 에
  // 답하는 그림. 기존 P03/P05 는 칸 이름만 보이고 실제 블록은 보이지 않았다.
  const flyoutShot = async (id, label, category) => {
    if (!pick(id)) return;
    // 실측 클래스명: 행 = .blocklyToolboxCategory, 이름 = .blocklyToolboxCategoryLabel
    // (.blocklyTreeLabel 은 이 벤더 빌드에 없다 — 30초 타임아웃으로 실패했다)
    // 라벨을 그대로 클릭하면 스크롤 중 다른 카테고리 div 가 포인터를 가로챈다 → 행을 잡고 force.
    const row = page
      .locator('.blocklyToolboxCategory')
      .filter({ has: page.locator('.blocklyToolboxCategoryLabel', { hasText: new RegExp(`^${category}$`) }) })
      .first();
    await row.scrollIntoViewIfNeeded();
    await page.waitForTimeout(300);
    await row.click({ force: true });
    // .blocklyFlyout 은 2개(수평·수직)라 strict mode 위반 → 보이는 것 하나만 기다린다.
    await page.locator('.blocklyFlyout').first().waitFor({ state: 'visible', timeout: 15000 });
    await page.waitForTimeout(900);
    await shoot(page, id, label, '.bpy-views');
  };
  await flyoutShot('P19', '블록꺼내기_tm', 'tm');
  await flyoutShot('P20', '블록꺼내기_dobotkit', 'dobotkit');

  await browser.close();
  console.log(`\n완료: ${shots.length}장 → ${OUT}`);
};

run().catch((e) => { console.error('실패:', e.message); process.exit(1); });

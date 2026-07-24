# BlockPy 리디자인 — "놀이형 IDE"(시안 B) 디자인 시스템 스펙

부산과학관 AI·로보틱스 커리큘럼용 블록코딩 학습 플랫폼(BlockPy)의 전면 UI 개편.
시안 B(놀이형 IDE)를 소스오브트루스로, Scratch 3.0/Bitblock 톤의 **밝고 둥글고 친근한 아동 교육용** 룩.
**핵심 원칙: 기능은 하나도 빼지 않는다(외형만 개편).** 모든 기능·탭·엔드포인트는 그대로 유지한다.

## 1. 컬러 토큰 (`:root`)

```
--bg: #eef3fb;              /* 앱 배경 (좌상단 radial #dfeafe 그라디언트) */
--panel: #ffffff;          /* 카드/패널 */
--ink: #1f2b46;            /* 본문 텍스트 */
--muted: #7c89a6;          /* 보조 텍스트 */
--line: #e3e9f4;           /* 보더/디바이더 */
--accent: #4d97ff;         /* 브랜드 액센트(파랑) */
--accent-d: #2f7cf0;       /* 액센트 진한톤(텍스트/보더) */
--accent-wash: #eaf2ff;    /* 액센트 배경 워시(활성 탭/행) */

/* 세맨틱 */
--run: #4fbf6a; --run-d:#3faa58;   /* 실행(초록) */
--stop: #eb5757;                   /* 정지(빨강) */
--success:#4fbf6a; --warning:#ffab19; --error:#eb5757;

/* Blockly 카테고리 팔레트(Scratch 표준 + dobotkit/tm 확장) */
--c-motion:#4c97ff; --c-looks:#9966ff; --c-sound:#cf63cf; --c-events:#ffbf00;
--c-control:#ffab19; --c-sensing:#5cb1d6; --c-oper:#59c059; --c-vars:#ff8c1a; --c-myblk:#ff6680;
--c-dobot:#14b8a6; --c-tm:#b94fbb;   /* 로봇/티처블머신 확장 색 */

/* 터미널(다크) */
--term-bg:#141a2e; --term-line:#24304f; --term-ink:#c9d6f5;
--term-g:#78e6a6; --term-b:#6fb6ff; --term-y:#ffd97a; --term-m:#c79cff; --term-d:#6b789e;
```

**다크 모드**: 토큰 기반이라 라이트 우선 + `:root[data-theme="dark"]`/`@media (prefers-color-scheme:dark)`로
`--bg`/`--panel`/`--ink`/`--line`만 재정의해 확장(2차 목표). 컴포넌트는 토큰만 참조(하드코딩 hex 금지).

## 2. 타이포그래피

- **UI/본문**: `"Pretendard","Malgun Gothic","Apple SD Gothic Neo",system-ui,-apple-system,sans-serif`
  — Pretendard는 self-host(가변폰트 woff2 번들). 없으면 Malgun Gothic 폴백.
- **코드/터미널**: `"D2Coding","Consolas","Menlo",ui-monospace,monospace`
- 스케일(px): 11 / 12.5 / 13 / 14 / 19(브랜드) — 굵기 본문 600, 강조 700, 브랜드 800.
- 숫자 정렬 열엔 `font-variant-numeric: tabular-nums`.

## 3. 셰이프 & 효과

- 라운드: 대형 컨테이너 22, 카드/패널 18, 버튼·칩·행 10~12, 블록 9(스택 첫/끝 12~16).
- 그림자(부드럽게, 남발 금지):
  - 앱 프레임 `0 30px 80px rgba(31,43,70,.18)`
  - 버튼 컬러 글로우(run/conv/accent): `0 5px 12px rgba(<color>,.35~.4)`
  - 블록 퍼즐감: `0 3px 0 rgba(0,0,0,.14), 0 6px 12px rgba(31,43,70,.14)`
- 활성 상태: `--accent-wash` 배경 + `--accent-d` 텍스트(+탭은 `inset 0 -2px var(--accent)`).
- 8px 간격 리듬. 패널 간 gap 12.

## 4. 레이아웃 (전면 재구성 — 카드형 IDE)

```
┌─ topbar 60px ────────────────────────────────────────────────────────────┐
│ [로고 BlockPy] [main.py 칩] ……spacer…… [예제][Convert][Save][정지][▶Run] │
├──────────────────────────────────────────────────────────────────────────┤
│ body (flex, gap12, pad12)                                                  │
│ ┌rail 66┐ ┌files 236┐ ┌toolbox 150┐ ┌─ stage (flex1) ───────────────────┐ │
│ │ 아이콘 │ │ 파일트리 │ │ 카테고리   │ │ ┌ views(flex1): [블록][파이썬]    │ │
│ │ 7탭+   │ │ +퀵버튼  │ │ 27개 컬러  │ │ │ [정규화][AST] 탭 + 캔버스(도트) │ │
│ │ 마스코트│ │          │ │ 원형 아이콘│ │ └─────────────────────────────── │ │
│ └────────┘ └──────────┘ └───────────┘ │ ┌ dock 230: [터미널 flex1.5]     │ │
│                                        │ │           [로봇/AI/TM flex1]    │ │
│                                        │ └─────────────────────────────── │ │
│                                        └───────────────────────────────── │ │
└──────────────────────────────────────────────────────────────────────────┘
```

- **rail(66px)**: 세로 아이콘 탭 7개 = Files / Variable / Terminal / Logs / AI / Robot / TM.
  선택 시 files 컬럼 내용이 바뀜. 맨 아래 **마스코트**(원형).
- **files(236px)**: 현재 선택된 사이드탭 패널(파일트리 등). 하단 퀵버튼 그리드.
- **toolbox(150px)**: Blockly 카테고리 레일. 각 항목 = 원형 컬러 점(`--c-*`) + 한국어 라벨.
  카테고리 전체: Values, Collections, Operators, Access, Variables, Control flow, Functions,
  Built-ins, Classes, Exceptions, Imports, Sugar, Async, Text, Match, Types, dobotkit,
  random, time, datetime, math, statistics, json, functools, re, cv2, tm. (스크롤)
- **stage(flex1)**: 상단 **views** 카드(뷰 탭 4개 + Blockly 캔버스, 도트 그리드 배경) +
  하단 **dock**(230px): 좌 터미널(다크, 탭: Terminal/AI/Logs) + 우 카드(Robot 상태 / TM / Run 출력, 탭 전환).
- 뷰 탭 4개: **Visual Blocks / Python Source / Desugared / AST**. 우측에 레이아웃/전체화면 툴.

## 5. 반드시 유지할 기능 (회귀 0)

- 상단: 프로젝트 칩(main.py), Save, **Run(초록)**, 정지(빨강), **Convert(블록↔코드)**, 예제, 이미지 삽입, 레이아웃 토글, 전체화면.
- 사이드탭 7개: Files/Variable/Terminal/Logs/AI/Robot/TM — 각 패널 콘텐츠 동일 기능.
- 뷰 4개: Visual Blocks(Blockly)/Python Source(에디터)/Desugared/AST — 파이썬↔블록 무손실 변환 그대로.
- AI 도우미 터미널(node-pty WebSocket) 그대로. 편집기 자동 리로드, 로봇 연결/캘리, TM 수집/학습.
- Blockly 카테고리·블록 색은 `--c-*` 팔레트로 재색상(기능·lowering 불변).

## 6. 에셋 (Higgsfield 생성 → `public/assets/`)

- **마스코트 로봇** BlockPy 캐릭터: 표정 3~4종(기본/성공응원/생각중/에러위로). Nano Banana 2. 투명배경 PNG.
- **빈 상태 일러스트**: 파일없음 / TM 샘플0 / 로봇 미연결. GPT Image 2. 밝은 파스텔.
- 나머지 아이콘은 **인라인 SVG**(Lucide 계열, stroke 1.75). 이모지 아이콘 금지(마스코트 제외).

## 7. 구현 방침

- `src/index.css` 토큰/컴포넌트 전면 개편(기존 Claude 에디토리얼 토큰 대체, 셀렉터 충돌 주의).
- `src/App.jsx` 및 하위 컴포넌트 레이아웃을 위 구조로 재배치(기능 배선은 보존, 클래스/구조만 변경).
- 접근성: 대비 4.5:1, 포커스 링 유지, 아이콘 버튼 aria-label, `prefers-reduced-motion` 존중.
- 검증: 기존 Playwright/node 테스트 통과 + 브라우저 실검증(레이아웃/오버플로우/기능).

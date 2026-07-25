# 툴박스 디자인 = MakeCode 그대로 (실측 스펙)

지시: **툴박스 디자인은 MakeCode 와 똑같이.** 블록 색 자체는 엔트리 팔레트(디자인 v2 §B)를 유지하고,
**툴박스(카테고리 열) 의 크롬만** MakeCode 규격으로 맞춘다. 두 축은 독립이므로 충돌하지 않는다.

## 근거 (Microsoft MakeCode `microsoft/pxt` → `theme/toolbox.less` 실측)

```less
div.blocklyTreeRow {
    line-height: 22px;
    margin-bottom: 3px;        /* 행 사이 3px 간격 */
    padding-right: 8px;
    height: 100%;
    cursor: pointer;
}
div.blocklyTreeRoot div div div div div.blocklyTreeRow {
    border-left-width: 12px !important;   /* ★ MakeCode 시그니처: 굵은 12px 카테고리색 좌측 바 */
    padding-left: 0px !important;
}
div.blocklyTreeRow:not(.blocklyTreeSelected):hover {
    background-color: var(--pxt-target-background3-hover);   /* 미묘한 hover */
}
div.blocklyTreeSeparator {
    border-bottom: solid var(--pxt-target-stencil3) 1px;
    height: 0;
    margin: 5px 0;             /* 그룹 구분선 */
}
span.blocklyTreeLabel {
    padding: 0 3px;
    vertical-align: middle;
    font-weight: 200;          /* ★ 라이트 웨이트(굵지 않다) */
    font-size: 1.15rem;        /* 중첩 행은 1rem */
    cursor: pointer;
}
span.blocklyTreeIcon {
    width: 30px;               /* ★ 아이콘 슬롯 30px */
    font-size: 1.3rem;
    margin: 0 0.25em;
    text-align: center;
    vertical-align: middle;
    height: 100%;
}
/* ★ 선택 상태: 행 배경이 '카테고리 색'으로 꽉 채워지고, 라벨/아이콘은 툴박스 배경색(=밝은색)으로 반전 */
.blocklyTreeSelected .blocklyTreeLabel { color: var(--pxt-target-background3); }
.blocklyTreeSelected .blocklyTreeIcon  { color: var(--pxt-target-background3); }
```

## 우리가 맞춰야 할 항목 (현재와의 차이)

| 항목 | MakeCode 규격 | 현재 BlockPy | 조치 |
|---|---|---|---|
| 좌측 컬러 바 | **12px** 굵게, 카테고리색 | 얇음/없음 | 12px 로 |
| 선택 상태 | **행 전체가 카테고리색**, 텍스트 흰색 반전 | accent-wash + accent 텍스트 | MakeCode 방식으로 교체 |
| 라벨 굵기 | **200 (라이트)** | 700 (볼드) | 라이트로 |
| 라벨 크기 | 1.15rem (중첩 1rem) | 13px | 1.05~1.15rem 급 |
| 아이콘 | **30px 슬롯**, 1.3rem | `width:0` 로 숨김 | 카테고리별 아이콘 노출 |
| 행 간격 | margin-bottom **3px** | 없음 | 3px |
| 그룹 구분선 | 1px, margin 5px 0 | 없음 | 상위/라이브러리 그룹 사이 삽입 |
| hover | 미묘한 배경 틴트 | surface-soft | 유지(동등) |
| 툴박스 배경 | 밝은 단색(타깃 background3) | 흰색 | 유지 |

## 아이콘 정책
MakeCode 는 자체 아이콘 폰트('Icons', 'brand-icons', xicon)를 쓴다. 우리는 **외부 폰트 금지(오프라인 Electron)** 이므로:
- 카테고리별 **인라인 SVG** 또는 유니코드 기하 문자 중 하나를 30px 슬롯에 넣는다(이모지 금지).
- Blockly 는 카테고리에 `cssConfig`/`icon` 클래스를 붙일 수 있으므로, `irToolbox.js` 의 카테고리 정의에
  아이콘 클래스를 부여하고 CSS `::before` 로 SVG mask 또는 문자를 렌더한다.
- 색: 비선택 시 카테고리색, 선택 시 툴박스 배경색(흰색)으로 반전 — MakeCode 와 동일.

## Blockly 클래스 주의
현대 Blockly(v10+)는 `.blocklyToolboxCategory` / `.blocklyToolboxCategoryLabel` /
`.blocklyToolboxCategoryContainer[aria-selected]` 를 쓰고, 레거시는 `.blocklyTreeRow` / `.blocklyTreeLabel` /
`.blocklyTreeSelected` 를 쓴다. **두 계열 셀렉터를 모두 커버**해야 한다(현재 코드에도 둘 다 존재).
카테고리 색은 Blockly 가 인라인 스타일(좌측 border 색)로 넣으므로, CSS 로 색을 덮지 말고 **굵기/레이아웃만** 규정하고
선택 상태의 배경 채움은 JS 에서 인라인 색을 읽어 적용한다(현재 `BlocklyEditor.jsx` 에 이미 라벨 색칠 로직이 있으니 확장).

## 불변 조건
- 블록 색 = 엔트리 팔레트(디자인 v2 §B) 유지. 툴박스 크롬만 MakeCode.
- 기능 회귀 0(변환/lowering 불변, 카테고리 구성·순서 불변).

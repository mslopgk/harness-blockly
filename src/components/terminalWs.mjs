// /api/terminal 의 WebSocket URL 을 현재 문서 위치에서 만든다. dev(Vite ws 프록시)와
// 패키징(same-origin) 모두 상대적으로 올바른 호스트/포트를 쓰게 한다. 순수 함수 — 유닛테스트 대상.
export function terminalWsUrl(loc) {
  const proto = loc.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${loc.host}/api/terminal`;
}

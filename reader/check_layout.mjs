/* 브라우저 레이아웃 점검. 파이썬 단위 테스트로는 잡을 수 없는 종류를 본다.
 *
 *   node reader/check_layout.mjs        (서버가 떠 있어야 한다)
 *
 * 왜 필요한가: KaTeX 는 접근성용 MathML 을 .katex-mathml { position: absolute } 로 숨긴다.
 * 스크롤 컨테이너가 positioned 가 아니면 그 요소들의 기준이 문서 전체가 되어
 * overflow 에 잘리지 않고 문서 높이를 늘려버린다. 실제로 문서가 12,680px 헛스크롤했다.
 * 눈으로는 "빈 화면이 계속 스크롤된다" 로만 보여서 원인을 짚기 어렵다.
 *
 * 외부 패키지를 쓰지 않는다. Chrome DevTools Protocol 을 node 내장 WebSocket 으로 직접 부른다.
 */
import { readFileSync } from 'node:fs';
const cfg = JSON.parse(readFileSync(new URL('../config.json', import.meta.url), 'utf8'));
const CHROME = process.env.CHROME || cfg.chrome;
// 로컬은 어떤 host 설정이든 항상 열려 있다 (0.0.0.0 포함).
const URL_ = process.env.READER_URL || `http://localhost:${cfg.port || 8765}/`;
const PORT = 9422;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const { spawn } = await import('node:child_process');

const chrome = spawn(CHROME, [
  '--headless=new', `--remote-debugging-port=${PORT}`, '--disable-gpu',
  '--window-size=1400,900', '--user-data-dir=/tmp/reader-layout-check', 'about:blank',
], { stdio: 'ignore' });

let targets;
for (let i = 0; i < 40; i++) {
  try { targets = await (await fetch(`http://127.0.0.1:${PORT}/json`)).json(); break; }
  catch { await sleep(250); }
}
if (!targets) { console.error('Chrome 을 띄우지 못했습니다.'); chrome.kill(); process.exit(2); }

const ws = new WebSocket(targets.find((t) => t.type === 'page').webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener('open', r));
let id = 0; const pending = new Map();
ws.addEventListener('message', (e) => {
  const m = JSON.parse(e.data);
  if (pending.has(m.id)) { pending.get(m.id)(m.result); pending.delete(m.id); }
});
const send = (method, params = {}) => new Promise((res) => {
  const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params }));
});

await send('Page.enable');
await send('Runtime.enable');
await send('Page.navigate', { url: URL_ });
await sleep(6000);   // 페이지 이미지 + 텍스트 레이어 + KaTeX 렌더 대기

// 질문 관련 항목은 화면에 렌더된 것을 센다. 기본 렌즈('이 절')는 대부분을
// 걸러내므로 '전체'로 넓혀야 실제로 있는 것과 보이는 것이 맞는다.
await send('Runtime.evaluate', { expression: "lens = 'all'; renderThread();" });
await sleep(600);

const { result } = await send('Runtime.evaluate', {
  returnByValue: true,
  expression: `(() => {
    const de = document.documentElement, q = (s) => document.querySelector(s);
    const scroll = q('#pageScroll'), pages = q('#pages');
    // 연속 스크롤: 현재 페이지 박스를 기준으로 잰다
    const box = q('.pageBox.current') || pages.querySelector('.pageBox[data-filled]');
    const img = box && box.querySelector('img');
    const ir = img ? img.getBoundingClientRect() : {bottom:0, right:0};

    let maxBottom = -1e9, maxRight = -1e9;
    for (const s of (box ? box.querySelectorAll('.tl span') : [])) {
      const r = s.getBoundingClientRect();
      if (r.bottom > maxBottom) maxBottom = r.bottom;
      if (r.right > maxRight) maxRight = r.right;
    }
    return {
      documentScrollsBy: de.scrollHeight - de.clientHeight,
      bodyScrollsBy: document.body.scrollHeight - document.body.clientHeight,
      pageScrollsHorizontally: scroll.scrollWidth - scroll.clientWidth,
      textLayerSpans: box ? box.querySelectorAll('.tl span').length : 0,
      pageBoxes: pages.querySelectorAll('.pageBox').length,
      appPosition: getComputedStyle(document.getElementById('app')).position,
      overscroll: getComputedStyle(document.body).overscrollBehaviorY,
      questionPageLinks: document.querySelectorAll('#thread .meta .pageRef[data-page]').length,
      // 페이지에 묶인 질문 수. 질문이 없거나 전부 '책 전체' 면 링크가 0 이어도 정상이다.
      pageAnchoredQuestions: (typeof items === 'undefined' ? []
        : items.filter((i) => i.question.scope !== 'book')).length,
      imagesInDom: pages.querySelectorAll('img').length,
      textBelowImage: Math.round(maxBottom - ir.bottom),
      textRightOfImage: Math.round(maxRight - ir.right),
      katexRendered: document.querySelectorAll('.katex').length,
      // let 선언은 window 에 붙지 않는다. 전역 스코프에서 식별자로 직접 읽는다.
      tocEntries: (typeof tocItems === 'undefined' ? 0 : tocItems.length),
      lensButtons: document.querySelectorAll('#lensBar button').length,
      lensScopeText: (document.querySelector('#lensScope') || {}).textContent || '',
    };
  })()`,
});

// 패널 검사는 따로 한다. openSide() 가 텍스트 레이어를 비동기로 다시 그리므로
// 주 측정과 섞으면 재렌더 도중을 재게 되어 '0 spans' 같은 유령 실패가 난다.
// (실제로 그렇게 만들었다가 한 번 겪었다.)
await send('Runtime.evaluate', { expression: "openSide('toc')" });
await sleep(1500);
const panelProbe = await send('Runtime.evaluate', {
  returnByValue: true,
  expression: `(() => {
    const p = document.querySelector('#sidePanel').getBoundingClientRect();
    const b0 = document.querySelector('.pageBox.current') || document.querySelector('.pageBox[data-filled]');
    const i = b0.getBoundingClientRect();
    return { overlaps: p.right > i.left + 1, pageWidth: Math.round(i.width),
             spansAfterToggle: b0.querySelectorAll('.tl span').length };
  })()`,
});
await send('Runtime.evaluate', { expression: "openSide('toc')" });

// 목차 클릭이 실제로 그 페이지에 도착하는가.
// 패널이 닫히면 페이지 폭이 바뀌어 모든 박스 높이가 재계산되므로,
// 이동과 재레이아웃의 순서가 틀리면 조용히 엉뚱한 곳에 서 있게 된다.
// 다른 점검은 전부 통과하면서 이것만 깨졌던 적이 있다.
await send('Runtime.evaluate', { expression: "openSide('toc')" });
await sleep(900);
const navProbe = await send('Runtime.evaluate', {
  returnByValue: true, awaitPromise: true,
  expression: `(async () => {
    const item = [...document.querySelectorAll('#tocList .toc-item')]
      .find((x) => x.querySelector('.toc-label').textContent.startsWith('6 '));
    if (!item) return { ok: false, why: '목차에 6장이 없다' };
    const want = Number(item.dataset.page);
    item.click();
    await new Promise((r) => setTimeout(r, 1500));
    return { ok: true, want, got: page,
             panelClosed: document.querySelector('#sidePanel').hidden };
  })()`,
});
await send('Runtime.evaluate', { expression: "if (!sidePanel.hidden) openSide(sideMode)" });

// 영역 선택이 실제로 되는가 — 스크롤한 상태에서, 터치로.
// 오버레이를 #pageScroll 기준으로 두면 스크롤 콘텐츠 맨 위에 고정되어
// 첫 페이지를 벗어나는 순간 화면 밖(-341,950px)으로 사라진다. 실제로 그렇게 깨졌고,
// 다른 점검 15개는 전부 통과했다. 터치는 mouse* 만 듣던 시절 아무 일도 일어나지 않았다.
await send('Emulation.setTouchEmulationEnabled', { enabled: true, maxTouchPoints: 5 });
await send('Runtime.evaluate', { expression: 'goto(252); toggleRegionMode(true)' });
await sleep(1500);
const spot = (await send('Runtime.evaluate', {
  returnByValue: true,
  expression: `(() => {
    const b = document.querySelector('.pageBox[data-page="252"]');
    if (!b) return null;
    const r = b.getBoundingClientRect(), o = document.querySelector('#regionOverlay').getBoundingClientRect();
    return { x: Math.round(r.left + r.width * 0.2), y: Math.round(r.top + r.height * 0.4),
             overlayVisible: o.bottom > 0 && o.top < window.innerHeight };
  })()`,
})).result.value;
let regionProbe = { drawn: false, overlayVisible: false };
if (spot) {
  regionProbe.overlayVisible = spot.overlayVisible;
  const touch = (type, pts) => send('Input.dispatchTouchEvent', { type, touchPoints: pts });
  await touch('touchStart', [{ x: spot.x, y: spot.y }]);
  for (let i = 1; i <= 6; i++) await touch('touchMove', [{ x: spot.x + i * 40, y: spot.y + i * 20 }]);
  await touch('touchEnd', []);
  await sleep(600);
  const r = await send('Runtime.evaluate', { returnByValue: true, expression: 'JSON.stringify(region)' });
  const val = r.result.value;
  regionProbe.drawn = !!val && val !== 'null';
  regionProbe.value = val;
}

ws.close(); chrome.kill();
const m = result.value;
if (!m) {
  console.error(`페이지를 읽지 못했습니다: ${URL_}`);
  console.error('서버가 떠 있는지, config.json 의 host 와 맞는지 확인하십시오.');
  process.exit(2);
}
const pp = panelProbe.result.value;
const nav = navProbe.result.value;
const rp = regionProbe;

const checks = [
  ['문서 전체가 스크롤되지 않는다', m.documentScrollsBy === 0, `documentScrollsBy=${m.documentScrollsBy}`],
  ['body 가 스크롤되지 않는다', m.bodyScrollsBy === 0, `bodyScrollsBy=${m.bodyScrollsBy}`],
  ['책 영역이 가로로 스크롤되지 않는다', m.pageScrollsHorizontally === 0, `${m.pageScrollsHorizontally}px`],
  ['텍스트 레이어가 생성되었다', m.textLayerSpans > 50, `${m.textLayerSpans} spans`],
  ['텍스트 레이어가 이미지 아래로 넘치지 않는다', m.textBelowImage <= 0, `${m.textBelowImage}px`],
  ['텍스트 레이어가 이미지 오른쪽으로 넘치지 않는다', m.textRightOfImage <= 0, `${m.textRightOfImage}px`],
  ['목차 색인이 로드되었다 (FR-12)', m.tocEntries > 200, `${m.tocEntries} entries`],
  ['렌즈 선택지가 4개다 (FR-13)', m.lensButtons === 4, `${m.lensButtons} buttons`],
  ['렌즈 범위가 표시된다 (FR-13)', /\d+\/\d+건/.test(m.lensScopeText), m.lensScopeText || '(비어 있음)'],
  ['패널이 본문을 덮지 않는다 (FR-12)', !pp.overlaps, pp.overlaps ? '덮고 있음' : '밀어냄'],
  ['패널을 열어도 지면이 보인다', pp.pageWidth > 200, `${pp.pageWidth}px`],
  ['패널 토글 후 텍스트 레이어가 다시 그려진다', pp.spansAfterToggle > 50, `${pp.spansAfterToggle} spans`],
  ['모든 페이지의 자리가 잡혀 있다 (FR-1)', m.pageBoxes === cfg.pageCount, `${m.pageBoxes} / ${cfg.pageCount}`],
  ['화면 밖 페이지는 메모리에서 비운다', m.imagesInDom > 0 && m.imagesInDom <= 12, `${m.imagesInDom} images`],
  ['목차 클릭이 그 페이지로 데려간다 (FR-12)', nav.ok && nav.want === nav.got,
   nav.ok ? `목차 p.${nav.want} → 도착 p.${nav.got}` : nav.why],
  ['스크롤 후에도 영역 오버레이가 화면에 있다 (FR-3)', rp.overlayVisible,
   rp.overlayVisible ? '보임' : '화면 밖 — 스크롤 콘텐츠 맨 위에 고정됨'],
  ['터치 드래그로 영역이 잡힌다 (FR-3)', rp.drawn, rp.value || '(없음)'],
  ['모바일에서 문서가 밀리지 않는다', m.appPosition === 'fixed' && m.overscroll === 'none',
   `#app=${m.appPosition}, overscroll-y=${m.overscroll}`],
  ['질문에서 물었던 페이지로 갈 수 있다',
   m.pageAnchoredQuestions === 0 || m.questionPageLinks > 0,
   m.pageAnchoredQuestions === 0
     ? '해당 질문 없음 — 확인 생략'
     : `${m.questionPageLinks} 개 링크 / 질문 ${m.pageAnchoredQuestions} 건`],
];

let failed = 0;
for (const [name, ok, detail] of checks) {
  console.log(`${ok ? '  PASS' : '  FAIL'}  ${name}  (${detail})`);
  if (!ok) failed++;
}
console.log(`\nKaTeX 렌더된 수식: ${m.katexRendered}개`);
console.log(failed ? `\n${failed}개 실패` : '\n전부 통과');
process.exit(failed ? 1 : 0);

'use strict';
/* book_reader — 뷰어.
   서버하고만 이야기한다. 워커의 존재는 모른다. */

const MIN_PAGE = -33, MAX_PAGE = 676;   // 책 페이지 범위 (PDF 710쪽, 오프셋 34)
const POLL_MS = 2000;

const $ = (id) => document.getElementById(id);
const el = {
  book: $('book'), scroll: $('pageScroll'),
  pages: $('pages'), regionOverlay: $('regionOverlay'), regionBox: $('regionBox'),
  zoomLevel: $('zoomLevel'),
  pageInput: $('pageInput'), pageRange: $('pageRange'),
  textPanel: $('textPanel'), textPanelBody: $('textPanelBody'),
  thread: $('thread'), status: $('status'), chips: $('contextChips'),
  input: $('questionInput'), hint: $('contextHint'), divider: $('divider'), qa: $('qa'),
  sidePanel: $('sidePanel'), tocList: $('tocList'), searchInput: $('searchInput'),
  searchResults: $('searchResults'), lensBar: $('lensBar'), lensScope: $('lensScope'),
  slowHint: $('slowHint'), connBanner: $('connBanner'),
};

let page = 1;
let selectedText = null;
let region = null;          // {page,x,y,w,h} — 150dpi 렌더 이미지 픽셀 기준
let selectedPage = null;    // 선택한 문장이 있는 페이지 (현재 페이지와 다를 수 있다)
const wordCache = new Map();   // page -> bbox 데이터
let boxObserver = null;
let zoom = 100;             // 페이지 표시 폭(%). 줄이면 앞뒤 페이지가 한 화면에 들어온다
let items = [];             // {question, answer}
let pollTimer = null;
let tocItems = [];          // FR-12 목차 색인 (서버에서 1회 로드)
let lens = 'section';       // FR-13 렌즈: page | section | chapter | all
let sideMode = null;        // 'toc' | 'search' | null
let autoHideSide = true;    // 목차·검색에서 항목을 고르면 패널을 자동으로 닫는다

// ---------------------------------------------------------------- 유틸

let connected = true;

/** 서버가 죽으면 화면이 조용히 멈춘다. 그걸 눈에 보이게 한다. */
function setConnected(ok) {
  if (ok === connected) return;
  connected = ok;
  if (!el.connBanner) return;        // 요소가 없다고 상태 추적이 멈추면 안 된다
  el.connBanner.hidden = ok;
  if (!ok) {
    el.connBanner.innerHTML =
      '서버 연결이 끊겼습니다 <span class="muted">— 맥에서 서버가 꺼졌거나 네트워크가 끊겼습니다</span>'
      + '<button data-testid="qa-reconnect" id="reconnectBtn">다시 연결</button>';
  }
}

/** 문서가 놓인 자리를 기준으로 주소를 만든다.
 *
 * code-server 의 /proxy/8765/ 처럼 하위 경로에 얹혀 프록시되면
 * '/api/...' 는 프록시가 아니라 code-server 자신을 부른다 — 404 로 죽는다.
 * document.baseURI 에 붙이면 어디에 얹히든 같은 서버로 간다.
 */
const url = (path) => new URL(path.replace(/^\//, ''), document.baseURI).href;

const api = async (path, opts) => {
  let res;
  try {
    res = await fetch(url(path), opts);
  } catch (e) {
    setConnected(false);          // 네트워크 자체가 끊긴 경우
    throw e;
  }
  setConnected(true);
  if (!res.ok) throw new Error(`${path} -> ${res.status}`);
  return res.headers.get('content-type')?.includes('json') ? res.json() : res.text();
};

/** 대기 중인 질문이 없으면 폴링도 없다. 그래서 따로 확인한다. */
async function heartbeat() {
  try { await api('/api/state'); } catch { /* setConnected 가 이미 처리 */ }
}
setInterval(heartbeat, 8000);

const escapeHtml = (s) => (s ?? '').replace(/[&<>"']/g,
  (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** 수식을 떼어내 자리표시자로 바꾼다. escape 대상에서 보호하기 위해서다. */
function stashMath(src, math) {
  return src.replace(/\$\$([\s\S]+?)\$\$|\$([^$\n]+?)\$/g, (m, block, inline) => {
    math.push({ tex: block ?? inline, display: block !== undefined });
    return ` M${math.length - 1} `;
  });
}

function popMath(html, math) {
  return html.replace(/ M(\d+) /g, (_, i) => {
    const { tex, display } = math[+i];
    try {
      return katex.renderToString(tex, { displayMode: display, throwOnError: false });
    } catch {
      return `<code>${escapeHtml(tex)}</code>`;   // 렌더 실패해도 원문은 보여준다
    }
  });
}

/** 문단 구조 없이 한 줄짜리 서식만. 표 셀에 쓴다. */
function renderInline(src) {
  const math = [];
  let s = stashMath(src, math);
  s = escapeHtml(s)
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/&lt;br\s*\/?&gt;/gi, '<br>');   // 모델이 셀 안에서 쓰는 유일한 태그
  return popMath(s, math);
}

/** 마크다운 표를 꺼내 HTML 로 바꾸고 자리표시자를 남긴다.
 *
 *  표 안에서 `|` 는 열 구분자라 모델이 `\|` 로 이스케이프한다.
 *  그런데 LaTeX 에서 `\|` 는 이중 세로선(‖)이라 켓 표기가 깨진다
 *  ($a\|0\rangle$ → a‖0⟩). 셀을 나눈 뒤 되돌려 준다. */
function stashTables(src, tables) {
  const lines = src.split('\n');
  const out = [];
  const splitRow = (line) => line
    .replace(/^\s*\|/, '').replace(/\|\s*$/, '')
    .split(/(?<!\\)\|/)
    .map((c) => c.replace(/\\\|/g, '|').trim());

  for (let i = 0; i < lines.length; i++) {
    const isRow = (n) => n < lines.length && /^\s*\|/.test(lines[n]);
    const isSep = (n) => n < lines.length && /^\s*\|[\s:|-]+\|?\s*$/.test(lines[n])
                         && lines[n].includes('-');
    if (!(isRow(i) && isSep(i + 1))) { out.push(lines[i]); continue; }

    const head = splitRow(lines[i]);
    let j = i + 2;
    const body = [];
    while (isRow(j) && !isSep(j)) { body.push(splitRow(lines[j])); j++; }

    const th = head.map((c) => `<th>${renderInline(c)}</th>`).join('');
    const tr = body.map((r) =>
      `<tr>${r.map((c) => `<td>${renderInline(c)}</td>`).join('')}</tr>`).join('');
    tables.push(`<div class="tableWrap"><table><thead><tr>${th}</tr></thead>`
                + `<tbody>${tr}</tbody></table></div>`);
    out.push(` T${tables.length - 1} `);
    i = j - 1;
  }
  return out.join('\n');
}

/** 마크다운 최소 렌더 + KaTeX. */
function renderRich(src) {
  if (!src) return '';
  const tables = [];
  const math = [];
  let s = stashTables(src, tables);
  s = stashMath(s, math);

  s = escapeHtml(s);
  s = s.replace(/^### (.*)$/gm, '<h4>$1</h4>')
       .replace(/^## (.*)$/gm, '<h3>$1</h3>')
       .replace(/^# (.*)$/gm, '<h3>$1</h3>')
       .replace(/^---$/gm, '<hr>')
       .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
       .replace(/`([^`]+)`/g, '<code>$1</code>')
       .replace(/\n{2,}/g, '</p><p>')
       .replace(/\n/g, '<br>');

  s = popMath(s, math);
  s = s.replace(/ T(\d+) /g, (_, i) => tables[+i]);   // 표는 문단 밖으로
  return `<p>${s}</p>`;
}

// ---------------------------------------------------------------- 책 페이지 (연속 스크롤)

// 표지(책 p.-33)만 종횡비가 다르다. 나머지 709쪽은 1328x1758 로 균일 — 실측 확인.
// 기본값으로 자리를 잡아두고, 이미지가 실제로 오면 그 페이지 박스만 보정한다.
const DEFAULT_ASPECT = 1758 / 1328;

const boxOf = (n) => el.pages.querySelector(`.pageBox[data-page="${n}"]`);
/** #pages 안에는 페이지 박스 말고 영역 선택 오버레이도 있다.
 *  children 을 그냥 돌면 오버레이를 페이지로 세어 높이를 건드리고
 *  data-page 가 없어 NaN 페이지를 만들어낸다. */
const pageBoxes = () => el.pages.querySelectorAll('.pageBox');

/** 710개 페이지의 자리를 미리 만든다. 이미지는 아직 넣지 않는다.
 *  자리를 다 잡아둬야 스크롤바 길이와 위치가 책 전체를 반영한다. */
function buildPageBoxes() {
  const frag = document.createDocumentFragment();
  for (let n = MIN_PAGE; n <= MAX_PAGE; n++) {
    const box = document.createElement('div');
    box.className = 'pageBox';
    box.dataset.page = n;
    box.dataset.aspect = DEFAULT_ASPECT;
    box.innerHTML = `<div class="tl"></div><div class="pageNo">p.${n}</div>`;
    frag.appendChild(box);
  }
  el.pages.appendChild(frag);
  layoutBoxes();

  // 화면 근처만 그린다. 멀어지면 이미지와 텍스트 레이어를 버려 메모리를 되돌린다.
  boxObserver = new IntersectionObserver((entries) => {
    for (const e of entries) {
      const n = Number(e.target.dataset.page);
      if (e.isIntersecting) fillBox(n); else emptyBox(n);
    }
    updateCurrentPage();
  }, { root: el.scroll, rootMargin: '150% 0px' });

  for (const box of pageBoxes()) boxObserver.observe(box);
}

/** 표시 폭이 바뀌면(창 크기, 패널 개폐, 분할 이동) 모든 자리 높이를 다시 잡는다. */
function setZoom(pct) {
  const keep = page;                       // 폭이 바뀌면 스크롤 좌표가 통째로 달라진다
  zoom = Math.max(40, Math.min(140, Math.round(pct / 10) * 10));
  el.zoomLevel.textContent = `${zoom}%`;
  el.pages.style.maxWidth = `${Math.round(900 * zoom / 100)}px`;
  relayoutKeeping(keep);                   // 보던 페이지를 그대로 유지한다
}

function layoutBoxes() {
  const w = el.pages.clientWidth;
  if (!w) return;
  for (const box of pageBoxes()) {
    box.style.height = `${Math.round(w * Number(box.dataset.aspect))}px`;
  }
}

async function fillBox(n) {
  const box = boxOf(n);
  if (!box || box.dataset.filled) return;
  box.dataset.filled = '1';

  const img = document.createElement('img');
  img.alt = `책 p.${n}`;
  img.loading = 'lazy';
  img.src = url(`/api/page/${n}/image`);
  img.onload = () => {
    const aspect = img.naturalHeight / img.naturalWidth;
    if (Math.abs(aspect - Number(box.dataset.aspect)) > 0.001) {
      box.dataset.aspect = aspect;               // 표지처럼 규격이 다른 페이지 보정
      box.style.height = `${Math.round(el.pages.clientWidth * aspect)}px`;
    }
    drawTextLayer(n);
  };
  box.insertBefore(img, box.firstChild);
}

function emptyBox(n) {
  const box = boxOf(n);
  if (!box || !box.dataset.filled) return;
  delete box.dataset.filled;
  box.querySelector('img')?.remove();
  box.querySelector('.tl').innerHTML = '';
}

/** 투명 텍스트 레이어. bbox 좌표를 실제 표시 크기로 스케일한다.
 *  박스 크기가 바뀌면 반드시 다시 불러야 한다 — 안 그러면 드래그 선택이 글자와 어긋난다. */
async function drawTextLayer(n) {
  const box = boxOf(n);
  if (!box || !box.dataset.filled) return;
  const layer = box.querySelector('.tl');
  let data = wordCache.get(n);
  if (!data) {
    try { data = await api(`/api/page/${n}/words`); wordCache.set(n, data); }
    catch { return; }
  }
  if (!box.dataset.filled) return;              // 그리는 사이에 화면 밖으로 나갔다

  const w = box.clientWidth, h = box.clientHeight;
  const sx = w / data.pageWidth, sy = h / data.pageHeight;
  const frag = document.createDocumentFragment();
  for (const word of data.words) {
    const el2 = document.createElement('span');
    el2.textContent = word.t + ' ';
    el2.style.left = `${word.x * sx}px`;
    el2.style.top = `${word.y * sy}px`;
    el2.style.fontSize = `${word.h * sy}px`;
    frag.appendChild(el2);
  }
  layer.innerHTML = '';
  layer.appendChild(frag);
}

function redrawVisibleLayers() {
  layoutBoxes();
  for (const box of pageBoxes()) {
    if (box.dataset.filled) drawTextLayer(Number(box.dataset.page));
  }
}

/** 폭이 바뀌면 모든 박스 높이가 달라져 스크롤 좌표가 통째로 어긋난다.
 *  재레이아웃 뒤에는 반드시 보던 페이지로 다시 데려다 놓아야 한다.
 *  (목차 클릭이 먹히지 않던 원인이 이것이었다 — 스크롤한 직후 패널이 닫히며
 *   레이아웃이 바뀌어 방금 맞춘 위치가 날아갔다.) */
function relayoutKeeping(target) {
  const keep = target ?? page;
  redrawVisibleLayers();
  goto(keep);
}

/** '지금 보고 있는 페이지' = 화면에 가장 넓게 보이는 페이지.
 *
 *  두 페이지가 걸쳐 있을 때 어느 쪽에 질문이 붙는지를 정하는 규칙이다.
 *  중심 거리로 고르면 정확히 반씩 걸친 순간 판정이 임의적으로 튄다.
 *  '더 많이 보이는 쪽'이 "주로 보고 있는 페이지"라는 직관과 맞는다.
 *  (문장이나 영역을 지목했다면 그쪽이 우선한다 — selectedPage 참조) */
function updateCurrentPage() {
  const top = el.scroll.scrollTop, bottom = top + el.scroll.clientHeight;
  let best = null, bestArea = -1;
  for (const box of pageBoxes()) {
    const t = box.offsetTop, b = t + box.offsetHeight;
    const visible = Math.min(b, bottom) - Math.max(t, top);
    if (visible > bestArea) { bestArea = visible; best = box; }
  }
  if (!best || bestArea <= 0) return;
  const n = Number(best.dataset.page);
  for (const box of pageBoxes()) box.classList.toggle('current', box === best);
  if (n === page) return;
  page = n;
  el.pageInput.value = n;
  if (el.textPanel.open) {
    api(`/api/page/${n}/text`).then((t) => { el.textPanelBody.textContent = t; }).catch(() => {});
  }
  renderChips();
  renderThread();                    // 렌즈 범위가 페이지를 따라간다 (FR-13)
  if (sideMode === 'toc') renderToc();
  saveState(n);
}

let saveTimer = null;
function saveState(n) {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    api('/api/state', { method: 'PUT', headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ lastBookPage: n }) }).catch(() => {});
  }, 400);
}

/** 지목했던 영역까지 데려가고, 어디였는지 잠깐 표시한다.
 *  페이지만 가면 "이 페이지 어디였더라" 를 다시 찾아야 한다. */
async function gotoRegion(n, region) {
  goto(n);
  await fillBox(n);                       // 아직 안 그려졌을 수 있다
  for (let i = 0; i < 40; i++) {          // 이미지가 실제 크기를 가질 때까지
    const b = boxOf(n);
    if (b && b.clientWidth > 0 && b.querySelector('img')?.complete) break;
    await new Promise((r) => setTimeout(r, 50));
  }
  const box = boxOf(n);
  if (!box) return;
  const k = box.clientWidth / 1328;       // 렌더 픽셀 -> 화면 픽셀
  const top = box.offsetTop + region.y * k;
  el.scroll.scrollTo({ top: Math.max(0, top - el.scroll.clientHeight * 0.3), behavior: 'smooth' });

  box.querySelector('.regionFlash')?.remove();
  const flash = document.createElement('div');
  flash.className = 'regionFlash';
  Object.assign(flash.style, {
    left: `${region.x * k}px`, top: `${region.y * k}px`,
    width: `${region.w * k}px`, height: `${region.h * k}px`,
  });
  box.appendChild(flash);
  setTimeout(() => flash.remove(), 2600);
}

/** 특정 페이지로 이동 — 이제 '스크롤해서 데려간다'. */
function goto(n, { smooth = false } = {}) {
  n = Math.max(MIN_PAGE, Math.min(MAX_PAGE, Math.trunc(n)));
  const box = boxOf(n);
  if (!box) return;
  el.scroll.scrollTo({ top: box.offsetTop - 16, behavior: smooth ? 'smooth' : 'auto' });
  updateCurrentPage();
}

// ---------------------------------------------------------------- 선택 (문장 / 영역)

function clearSelection() {
  selectedText = null; region = null; selectedPage = null; renderChips();
}

document.addEventListener('selectionchange', () => {
  if (el.book.classList.contains('region-mode')) return;
  const sel = document.getSelection();
  if (!sel || sel.isCollapsed) return;
  const node = sel.anchorNode?.nodeType === 1 ? sel.anchorNode : sel.anchorNode?.parentElement;
  const box = node?.closest?.('.pageBox');
  if (!box) return;
  const t = sel.toString().replace(/\s+/g, ' ').trim();
  if (t.length > 1) {
    selectedText = t;
    // 연속 스크롤에서는 고른 문장이 화면 중앙 페이지와 다를 수 있다.
    // 질문의 맥락은 '고른 자리' 를 따르는 편이 정확하다.
    selectedPage = Number(box.dataset.page);
    renderChips();
  }
});

function setupRegionSelect() {
  let start = null, startBox = null;

  // Pointer Events 를 쓴다. 마우스·터치·펜이 같은 경로로 들어온다.
  // mouse* 만 듣던 때에는 태블릿에서 드래그가 스크롤로 먹혀 아무 일도 일어나지 않았다.
  // 오버레이가 #pages 안에 있으므로 좌표를 #pages 기준으로 재면 된다
  // (페이지 박스의 offsetTop 과 같은 좌표계다).
  const pointIn = (e) => {
    const r = el.pages.getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };
  const boxAt = (y) => [...el.pages.querySelectorAll('.pageBox')].find(
    (b) => y >= b.offsetTop && y <= b.offsetTop + b.offsetHeight);

  el.regionOverlay.addEventListener('pointerdown', (e) => {
    start = pointIn(e);
    startBox = boxAt(start.y);
    if (!startBox) { start = null; return; }
    el.regionOverlay.setPointerCapture(e.pointerId);   // 손가락이 밖으로 나가도 계속 받는다
    e.preventDefault();
    Object.assign(el.regionBox.style, { display: 'block',
      left: `${start.x}px`, top: `${start.y}px`, width: '0px', height: '0px' });
  });

  el.regionOverlay.addEventListener('pointermove', (e) => {
    if (!start) return;
    e.preventDefault();
    const q = pointIn(e);
    Object.assign(el.regionBox.style, {
      left: `${Math.min(q.x, start.x)}px`, top: `${Math.min(q.y, start.y)}px`,
      width: `${Math.abs(q.x - start.x)}px`, height: `${Math.abs(q.y - start.y)}px` });
  });

  const finish = (e) => {
    if (!start || !startBox) { start = null; return; }
    const q = pointIn(e);
    const k = 1328 / startBox.clientWidth;        // 표시 크기 -> 150dpi 렌더 픽셀
    const box = {
      page: Number(startBox.dataset.page),
      x: Math.round((Math.min(q.x, start.x) - startBox.offsetLeft) * k),
      y: Math.round((Math.min(q.y, start.y) - startBox.offsetTop) * k),
      w: Math.round(Math.abs(q.x - start.x) * k),
      h: Math.round(Math.abs(q.y - start.y) * k),
    };
    start = null; startBox = null;
    el.regionBox.style.display = 'none';
    if (box.w > 12 && box.h > 12) {
      region = box; selectedPage = box.page; renderChips(); toggleRegionMode(false);
    }
  };
  el.regionOverlay.addEventListener('pointerup', finish);
  el.regionOverlay.addEventListener('pointercancel', () => {
    start = null; startBox = null; el.regionBox.style.display = 'none';
  });
}

function toggleRegionMode(on) {
  el.book.classList.toggle('region-mode', on);
  el.regionOverlay.hidden = !on;
  $('regionBtn').classList.toggle('on', on);
}

function renderChips() {
  el.chips.innerHTML = '';
  if (selectedText) {
    const c = document.createElement('span');
    c.className = 'chip';
    c.innerHTML = `<span>“${escapeHtml(selectedText.slice(0, 90))}”</span>`;
    const b = document.createElement('button');
    b.textContent = '×'; b.title = '선택 해제';
    b.onclick = () => { selectedText = null; if (!region) selectedPage = null; renderChips(); };
    c.appendChild(b); el.chips.appendChild(c);
  }
  if (region) {
    const c = document.createElement('span');
    c.className = 'chip';
    c.innerHTML = `<span>p.${region.page} 영역 ${region.w}×${region.h}px</span>`;
    const b = document.createElement('button');
    b.textContent = '×'; b.title = '영역 해제';
    b.onclick = () => { region = null; if (!selectedText) selectedPage = null; renderChips(); };
    c.appendChild(b); el.chips.appendChild(c);
  }
  el.hint.textContent = askScope === 'book'
    ? '책 전체를 대상으로 질문합니다 (별도 대화)'
    : `책 p.${selectedPage ?? page} 맥락으로 전송됩니다`;
}

// ---------------------------------------------------------------- 목차 색인 (FR-12/13)

/** 이 페이지가 속한 가장 깊은 항목. 목차는 페이지 오름차순이다. */
function locate(bookPage) {
  let found = null;
  for (const it of tocItems) { if (it.page <= bookPage) found = it; else break; }
  return found;
}

/** 장 > 절 > 소절 조상 사슬. 렌즈 선택지가 여기서 나온다. */
function ancestors(bookPage) {
  let i = -1;
  for (let k = 0; k < tocItems.length; k++) { if (tocItems[k].page <= bookPage) i = k; else break; }
  if (i < 0) return [];
  const chain = [tocItems[i]];
  let want = tocItems[i].depth - 1;
  for (let j = i - 1; j >= 0 && want > 0; j--) {
    if (tocItems[j].depth === want) { chain.push(tocItems[j]); want--; }
  }
  return chain.reverse();
}

/** 해당 항목이 차지하는 페이지 범위. 하위 소절을 포함한다. */
function pageRange(number) {
  const i = tocItems.findIndex((it) => it.number === number);
  if (i < 0) return null;
  const me = tocItems[i];
  for (let j = i + 1; j < tocItems.length; j++) {
    if (tocItems[j].depth <= me.depth) return [me.page, tocItems[j].page - 1];
  }
  return [me.page, MAX_PAGE];
}

/** 렌즈 기준 범위. all 이면 null. */
function lensRange() {
  if (lens === 'all') return null;
  if (lens === 'page') return [page, page];
  const chain = ancestors(page);
  if (!chain.length) return [page, page];
  const target = lens === 'chapter' ? chain[0] : chain[chain.length - 1];
  return pageRange(target.number) || [page, page];
}

/** 질문 하나가 현재 렌즈에 걸리는가.
 *  물었던 자리뿐 아니라 **답변이 인용한 페이지**도 본다 —
 *  p.252 에서 물었는데 답이 p.250~262 를 인용했다면 p.258 을 읽을 때도 관련 질문이다. */
function inLens(it, range) {
  // 책 전체 질문은 어느 절에도 속하지 않는다. '전체' 에서만 보인다.
  if (it.question.scope === 'book') return !range;
  if (!range) return true;
  const [lo, hi] = range;
  if (it.question.bookPage >= lo && it.question.bookPage <= hi) return true;
  return (it.answer?.bookPages || []).some((p) => p >= lo && p <= hi);
}

/** 절 번호 -> 질문 개수. 목차 배지의 재료.
 *  질문이 쌓였을 때 "어디서 물었더라" 를 찾는 것이 이 기능의 요점이다. */
function questionCounts() {
  const counts = new Map();
  for (const it of items) {
    for (const a of ancestors(it.question.bookPage)) {
      counts.set(a.number, (counts.get(a.number) || 0) + 1);
    }
  }
  return counts;
}

// ---------------------------------------------------------------- 목차 / 검색 패널

function renderToc() {
  const counts = questionCounts();
  const here = new Set(ancestors(page).map((a) => a.number));
  el.tocList.innerHTML = tocItems.map((it) => {
    const n = counts.get(it.number) || 0;
    const label = it.number === it.title ? it.title : `${it.number} ${it.title}`;
    return `<div class="toc-item d${it.depth}${here.has(it.number) ? ' here' : ''}"
                 data-testid="toc-item" data-page="${it.page}" title="p.${it.page}">
      <span class="toc-label">${escapeHtml(label)}</span>
      ${n ? `<span class="toc-count" title="이 범위의 질문 ${n}개">${n}</span>` : ''}
    </div>`;
  }).join('');
  // :last-of-type 은 '형제 중 마지막 div' 를 뜻하지 '마지막 .here' 가 아니다.
  // 그래서 아무것도 못 잡고 목차가 현재 위치로 스크롤되지 않았다.
  const heres = el.tocList.querySelectorAll('.toc-item.here');
  const active = heres[heres.length - 1];
  if (active && sideMode === 'toc') active.scrollIntoView({ block: 'center' });
}

async function runSearch(q) {
  if (q.trim().length < 2) { el.searchResults.innerHTML = ''; return; }
  el.searchResults.innerHTML = '<div class="muted" style="padding:8px">검색 중…</div>';
  try {
    const { results } = await api(`/api/search?q=${encodeURIComponent(q)}`);
    el.searchResults.innerHTML = results.length
      ? results.map((r) => `<div class="search-hit" data-testid="search-hit" data-page="${r.page}">
           <div class="hit-head">p.${r.page} <span class="muted">${escapeHtml(r.section)}</span></div>
           <div class="hit-snip">…${escapeHtml(r.snippet)}…</div></div>`).join('')
      : '<div class="muted" style="padding:8px">결과 없음. 수식은 검색되지 않습니다.</div>';
  } catch (e) {
    el.searchResults.innerHTML = `<div class="muted" style="padding:8px">검색 실패: ${escapeHtml(e.message)}</div>`;
  }
}

function openSide(mode) {
  sideMode = (sideMode === mode) ? null : mode;
  el.sidePanel.hidden = !sideMode;
  $('tocBtn').classList.toggle('on', sideMode === 'toc');
  $('searchBtn').classList.toggle('on', sideMode === 'search');
  el.searchInput.parentElement.hidden = sideMode !== 'search';
  el.tocList.hidden = sideMode !== 'toc';
  el.searchResults.hidden = sideMode !== 'search';
  if (sideMode === 'toc') renderToc();
  if (sideMode === 'search') el.searchInput.focus();
  // 패널이 본문을 밀어내므로 페이지 폭이 바뀐다.
  // 자리 높이와 텍스트 레이어를 다시 잡고, 보던 페이지로 되돌려 놓는다.
  relayoutKeeping();
}

// ---------------------------------------------------------------- Q&A

const openSteps = new Set();   // 폴링 재렌더 시 '지나온 단계' 열림 상태 보존
const collapsedGroups = new Set();   // 접어둔 그룹 (재렌더 시 유지)
let askScope = 'page';         // 'page' = 지금 보는 곳 / 'book' = 책 전체

/** 진행 상황 (FR-10). 워커가 실제로 호출한 도구를 서버가 옮겨 적은 것만 보여준다. */
function progressHtml(a) {
  const steps = a.progress || [];
  const elapsed = a.startedAt
    ? Math.max(0, Math.round((Date.now() - Date.parse(a.startedAt)) / 1000))
    : null;
  const mmss = elapsed === null ? ''
    : (elapsed >= 60 ? `${Math.floor(elapsed / 60)}분 ${elapsed % 60}초 경과` : `${elapsed}초 경과`);

  // activity 는 도구를 쓰지 않는 구간(모델이 생각하고 쓰는 시간)의 실시간 상태다.
  // 이게 없으면 마지막 도구 호출 문구가 몇 분씩 그대로 얼어붙는다.
  const live = a.activity
    ? escapeHtml(a.activity) + (a.activityTokens > 0 ? ` <span class="muted">약 ${a.activityTokens.toLocaleString()} 토큰</span>` : '')
    : null;

  if (!steps.length && !live) {
    return `<div class="progress"><span class="dot"></span>시작하는 중…<span class="muted"> ${mmss}</span></div>`;
  }
  const last = live || (steps.length ? escapeHtml(steps[steps.length - 1].label) : '조사 중');
  const past = live ? steps : steps.slice(0, -1);
  const openAttr = openSteps.has(a.id) ? ' open' : '';
  const history = past.length
    ? `<details class="progress-past" data-steps="${a.id}"${openAttr}><summary>지나온 단계 ${past.length}개</summary>
         <ol>${past.map((s) => `<li>${escapeHtml(s.label)}</li>`).join('')}</ol></details>`
    : '';
  return `<div class="progress"><span class="dot"></span>${last}<span class="muted"> · ${mmss}</span></div>${history}`;
}

function itemHtml(it) {
  const q = it.question, a = it.answer || {};
  const st = a.status || 'pending';
  const badge = {
    pending: '<span class="badge wait">대기 중</span>',
    running: '<span class="badge run">조사 중…</span>',
    error: '<span class="badge err">실패</span>',
  }[st] || '';

  // 물었던 자리로 돌아갈 수 있게 페이지 번호를 누를 수 있게 한다.
  // 답변의 근거 배지와 같은 방식이라 조작이 일관된다.
  // 책 전체 질문은 돌아갈 '그 자리' 가 없으므로 배지만 보여준다.
  const where = q.scope === 'book'
    ? '<span class="badge book">책 전체</span>'
    : `<span class="pageRef" data-page="${q.bookPage}"`
      + (q.region ? ` data-region='${JSON.stringify(q.region)}'` : '')
      + ` title="${q.region ? '지목했던 영역으로 이동' : '이 질문을 했던 페이지로 이동'}">`
      + `책 p.${q.bookPage}${q.region ? ' ▣' : ''}</span>`;
  const parts = [`<div class="q">${escapeHtml(q.question)}</div>`,
                 `<div class="meta">${where} · ${(q.createdAt || '').replace('T', ' ').replace('Z', '')} ${badge}</div>`];
  if (q.selectedText) parts.push(`<blockquote>${escapeHtml(q.selectedText)}</blockquote>`);
  if (q.cropPath) parts.push(`<img class="crop" src="${url('/api/crop/' + q.id)}" alt="선택한 영역">`);
  if (['pending', 'running'].includes(st) && !a.partial) parts.push(progressHtml(a));

  // 쓰이는 대로 보여준다. 심화는 3분 넘게 걸리는데 그동안 빈 화면일 이유가 없다.
  if (!a.summary && a.partial) {
    parts.push(`<div class="body streaming" data-testid="qa-partial">`
      + `${renderRich(a.partial)}<span class="caret"></span></div>`);
  }
  if (a.summary) parts.push(`<div class="body">${renderRich(a.summary)}</div>`);
  if (!a.detail && a.partial && a.partialField === 'detail') {
    parts.push(`<div class="detail streaming" data-testid="qa-partial">`
      + `${renderRich(a.partial)}<span class="caret"></span></div>`);
  }
  if (a.detail) {
    parts.push(`<div class="detail">${renderRich(a.detail)}</div>`);
  } else if (a.summary && st !== 'running' && st !== 'pending') {
    parts.push(`<button data-testid="qa-expand-button" data-expand="${q.id}">＋ 더 자세히</button>`);
  }
  parts.push(`<button class="del" data-testid="qa-delete" data-del="${q.id}" title="휴지통으로 보냅니다">삭제</button>`);
  if (st === 'error') {
    parts.push(`<div class="meta">${escapeHtml(a.error || '')}</div>`,
               `<button data-testid="qa-retry-button" data-retry="${q.id}">↻ 다시 시도</button>`);
  }

  const src = [];
  if (a.bookPages?.length) {
    src.push('근거: ' + a.bookPages.map((p) => `<span class="pageRef" data-page="${p}">p.${p}</span>`).join(''));
  }
  for (const l of a.webLinks || []) {
    src.push(`<a href="${escapeHtml(l.url)}" target="_blank" rel="noreferrer">${escapeHtml(l.title || l.url)}</a>`);
  }
  if (src.length) parts.push(`<div class="sources">${src.join(' · ')}</div>`);

  return `<article class="qaItem" data-testid="qa-item" data-id="${q.id}">${parts.join('')}</article>`;
}

/** 질문을 절 단위로 묶는다. 하나뿐이면 묶지 않는다 (괜한 껍데기를 만들지 않는다). */
function groupItems(shown) {
  const groups = new Map();
  for (const it of shown) {
    const key = it.question.scope === 'book'
      ? '__book__'
      : (ancestors(it.question.bookPage).slice(-1)[0]?.number ?? '?');
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(it);
  }
  return groups;
}

function groupLabel(key) {
  if (key === '__book__') return '책 전체';
  const it = tocItems.find((x) => x.number === key);
  return it ? (it.number === it.title ? it.title : `${it.number} ${it.title}`) : key;
}

function renderThread({ scroll = false } = {}) {
  const range = lensRange();
  const shown = items.filter((it) => inLens(it, range));

  if (!shown.length) {
    el.thread.innerHTML = `<div class="empty" data-testid="qa-empty">
         ${items.length ? '이 범위에는 질문이 없습니다. 보기를 넓혀보세요.' : '아직 질문이 없습니다.'}
       </div>`;
  } else {
    const groups = groupItems(shown);
    el.thread.innerHTML = groups.size <= 1
      ? shown.map(itemHtml).join('')
      : [...groups.entries()].map(([key, list]) => {
          const first = list[0].question.bookPage;
          const open = collapsedGroups.has(key) ? '' : ' open';
          return `<details class="qaGroup" data-testid="qa-group" data-group="${key}"${open}>
            <summary><span class="gname">${escapeHtml(groupLabel(key))}</span>
              <span class="gcount">${list.length}</span>
              ${key === '__book__' ? '' : `<span class="gpage" data-page="${first}">p.${first}</span>`}
            </summary>${list.map(itemHtml).join('')}</details>`;
        }).join('');
  }
  const chain = ancestors(page);
  const where = { page: `p.${page}`,
                  section: chain.length ? `${chain[chain.length - 1].number} ${chain[chain.length - 1].title}` : `p.${page}`,
                  chapter: chain.length ? `${chain[0].number} ${chain[0].title}` : `p.${page}`,
                  all: '책 전체' }[lens];
  el.lensScope.textContent = `${where} · ${shown.length}/${items.length}건`;
  if (scroll) el.thread.scrollTop = el.thread.scrollHeight;
}

/** 대화가 길어져 느려지고 있는지 판단한다 (같은 장 안에서만 비교).
 *
 *  절대 시간으로만 보면 원래 무거운 질문을 오해한다.
 *  이 장에서 가장 빨랐던 답변 대비 얼마나 느려졌는지를 함께 본다. */
function slowdownHint() {
  const ch = ancestors(selectedPage ?? page)[0]?.number;
  if (!ch) return null;
  const times = items
    .filter((it) => it.question.chapter === ch && it.answer?.summaryMs)
    .map((it) => it.answer.summaryMs);
  if (times.length < 3) return null;              // 표본이 적으면 판단하지 않는다
  const last = times[times.length - 1], fastest = Math.min(...times);
  if (last < 40000 || last < fastest * 1.8) return null;
  return { ch, last: Math.round(last / 1000), fastest: Math.round(fastest / 1000) };
}

function renderSlowdown() {
  if (!el.slowHint) return;          // 힌트 하나가 화면 전체를 죽이지 않도록
  const hint = slowdownHint();
  el.slowHint.hidden = !hint;
  if (hint) {
    el.slowHint.innerHTML =
      `${hint.ch}장 대화가 길어져 느려지고 있습니다 ` +
      `<span class="muted">${hint.fastest}초 → ${hint.last}초</span> ` +
      `<button data-testid="qa-reset-inline" id="resetInline">↺ 이 장 초기화</button>`;
  }
}

function busyCount() {
  return items.filter((i) => ['pending', 'running'].includes(i.answer?.status)).length;
}

function setStatus(text) { el.status.textContent = text; }

async function refresh() {
  const busy = items.filter((i) => ['pending', 'running'].includes(i.answer?.status));
  if (!busy.length) { stopPolling(); setStatus('준비됨'); return; }
  await Promise.all(busy.map(async (i) => {
    try { i.answer = await api(`/api/answer/${i.question.id}`); } catch {}
  }));
  renderThread();
  renderSlowdown();
  const n = busyCount();
  setStatus(n ? `조사 중… (대기 ${n}건)` : '준비됨');
  if (!n) stopPolling();
}

function startPolling() { if (!pollTimer) pollTimer = setInterval(refresh, POLL_MS); }
function stopPolling() { clearInterval(pollTimer); pollTimer = null; }

async function ask() {
  const text = el.input.value.trim();
  if (!text && !selectedText && !region) { el.input.focus(); return; }
  const payload = { bookPage: selectedPage ?? page, question: text, selectedText,
                    scope: askScope,
                    region: region ? { x: region.x, y: region.y, w: region.w, h: region.h } : null };
  el.input.value = '';
  const chipSel = selectedText, chipRegion = region;
  clearSelection();
  try {
    const { id } = await api('/api/ask', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    items.push({
      question: {
        id, bookPage: payload.bookPage, question: text, scope: askScope,
        selectedText: chipSel, cropPath: chipRegion ? 'pending' : null,
        createdAt: new Date().toISOString().slice(0, 19),
      },
      answer: { status: 'pending' },
    });
    renderThread({ scroll: true });
    setStatus(`조사 중… (대기 ${busyCount()}건)`);
    startPolling();
  } catch (e) {
    setStatus(`전송 실패: ${e.message}`);
  }
}

// ---------------------------------------------------------------- 이벤트

el.thread.addEventListener('toggle', (e) => {
  const d = e.target;
  if (!d.dataset?.steps) return;
  d.open ? openSteps.add(d.dataset.steps) : openSteps.delete(d.dataset.steps);
}, true);

el.thread.addEventListener('toggle', (e) => {
  const d = e.target;
  if (!d.dataset?.group) return;
  d.open ? collapsedGroups.delete(d.dataset.group) : collapsedGroups.add(d.dataset.group);
}, true);

el.thread.addEventListener('click', async (e) => {
  const t = e.target;
  if (t.dataset.page) {
    if (t.dataset.region) {
      try { return gotoRegion(Number(t.dataset.page), JSON.parse(t.dataset.region)); }
      catch { /* 좌표가 깨졌으면 페이지까지만 */ }
    }
    return goto(Number(t.dataset.page));
  }

  if (t.dataset.del) {
    // 한 번 더 눌러야 지워진다. 답변 하나에 몇 분씩 걸리므로 실수로 날리면 아프다.
    if (t.dataset.armed !== '1') {
      t.dataset.armed = '1'; t.textContent = '정말 지울까요?'; t.classList.add('armed');
      setTimeout(() => { if (t.dataset.armed === '1') {
        t.dataset.armed = ''; t.textContent = '삭제'; t.classList.remove('armed'); } }, 4000);
      return;
    }
    await api(`/api/question/${t.dataset.del}/delete`, { method: 'POST' });
    items = items.filter((i) => i.question.id !== t.dataset.del);
    renderThread();
    setStatus('휴지통으로 옮겼습니다 (qa/trash/)');
    return;
  }
  if (t.dataset.expand) {
    t.disabled = true; t.textContent = '심화 조사 중…';
    await api(`/api/answer/${t.dataset.expand}/expand`, { method: 'POST' });
    const it = items.find((i) => i.question.id === t.dataset.expand);
    if (it) it.answer.status = 'pending';
    startPolling(); setStatus('심화 조사 중…');
  }
  if (t.dataset.retry) {
    t.disabled = true;
    await api(`/api/answer/${t.dataset.retry}/retry`, { method: 'POST' });
    const it = items.find((i) => i.question.id === t.dataset.retry);
    if (it) it.answer.status = 'pending';
    startPolling();
  }
});

el.connBanner.addEventListener('click', (e) => {
  if (e.target.id === 'reconnectBtn') location.reload();
});

$('scopeBtn').onclick = () => {
  askScope = askScope === 'book' ? 'page' : 'book';
  $('scopeBtn').classList.toggle('on', askScope === 'book');
  renderChips();
};

el.lensBar.addEventListener('click', (e) => {
  const v = e.target.dataset?.lens;
  if (!v) return;
  lens = v;
  for (const b of el.lensBar.querySelectorAll('button')) b.classList.toggle('on', b.dataset.lens === v);
  renderThread();
});

el.sidePanel.addEventListener('click', (e) => {
  const hit = e.target.closest('[data-page]');
  if (!hit) return;
  const target = Number(hit.dataset.page);
  // 닫으면 폭이 바뀌어 좌표가 달라진다. 먼저 닫아 레이아웃을 확정하고 그 다음 이동한다.
  if (autoHideSide && sideMode) openSide(sideMode);
  goto(target);
});

let searchTimer = null;
el.searchInput.addEventListener('input', () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => runSearch(el.searchInput.value), 250);
});
$('zoomOut').onclick = () => setZoom(zoom - 10);
$('zoomIn').onclick = () => setZoom(zoom + 10);
$('tocBtn').onclick = () => openSide('toc');
$('searchBtn').onclick = () => openSide('search');
$('sideClose').onclick = () => openSide(sideMode);
$('sidePin').onchange = (e) => { autoHideSide = !e.target.checked; };

$('prevBtn').onclick = () => goto(page - 1, { smooth: true });
$('nextBtn').onclick = () => goto(page + 1, { smooth: true });
el.pageInput.onchange = () => goto(Number(el.pageInput.value));
$('regionBtn').onclick = () => toggleRegionMode(el.regionOverlay.hidden);
$('textBtn').onclick = () => {
  el.textPanel.open = !el.textPanel.open;
  if (el.textPanel.open) {
    api(`/api/page/${page}/text`).then((t) => { el.textPanelBody.textContent = t; }).catch(() => {});
  }
};
$('askBtn').onclick = ask;
async function resetChapter() {
  const ch = ancestors(selectedPage ?? page)[0]?.number;
  await api('/api/session/reset', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ chapter: ch, bookPage: page }),
  });
  setStatus(`${ch ?? '현재'}장 대화 맥락을 초기화했습니다`);
  el.slowHint.hidden = true;
}
$('resetBtn').onclick = resetChapter;
el.slowHint.addEventListener('click', (e) => {
  if (e.target.id === 'resetInline') resetChapter();
});

el.input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); ask(); }
});
document.addEventListener('keydown', (e) => {
  if (document.activeElement === el.input || document.activeElement === el.pageInput) return;
  if (e.key === 'ArrowLeft') goto(page - 1, { smooth: true });
  if (e.key === 'ArrowRight') goto(page + 1, { smooth: true });
  if (e.key === '-' || e.key === '_') setZoom(zoom - 10);
  if (e.key === '=' || e.key === '+') setZoom(zoom + 10);
  if (e.key === 't' || e.key === 'T') openSide('toc');
  if (e.key === '/') { e.preventDefault(); openSide('search'); }
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && sideMode) openSide(sideMode);
});
let scrollTick = null;
el.scroll.addEventListener('scroll', () => {
  if (scrollTick) return;
  scrollTick = requestAnimationFrame(() => { scrollTick = null; updateCurrentPage(); });
}, { passive: true });

window.addEventListener('resize', () => relayoutKeeping());

// 좌우 분할 리사이즈
el.divider.addEventListener('mousedown', (e) => {
  e.preventDefault();
  const move = (ev) => {
    const pct = Math.max(25, Math.min(75, (ev.clientX / window.innerWidth) * 100));
    el.book.style.flex = `1 1 ${pct}%`;
    el.qa.style.flex = `1 1 ${100 - pct}%`;
  };
  const up = () => {
    document.removeEventListener('mousemove', move);
    document.removeEventListener('mouseup', up);
    relayoutKeeping();
  };
  document.addEventListener('mousemove', move);
  document.addEventListener('mouseup', up);
});

// ---------------------------------------------------------------- 시작

(async function init() {
  el.pageRange.textContent = `/ ${MAX_PAGE}`;
  setupRegionSelect();
  try {
    const [state, hist, toc] = await Promise.all([
      api('/api/state'), api('/api/history'), api('/api/toc')]);
    tocItems = toc.items || [];
    items = hist.items || [];
    renderThread();
    renderSlowdown();
    el.thread.scrollTop = el.thread.scrollHeight;
    buildPageBoxes();
    goto(state.lastBookPage ?? 1);        // FR-7: 읽던 위치에서 재시작
    if (busyCount()) startPolling();
  } catch (e) {
    setStatus(`서버 연결 실패: ${e.message}`);
  }
  renderChips();
})();

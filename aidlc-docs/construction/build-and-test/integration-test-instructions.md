# Integration Test Instructions

컴포넌트 경계를 넘는 흐름을 검증합니다. 단위 테스트는 `server.py` 내부만 보므로
poppler·워커·`claude` CLI 와의 실제 상호작용은 여기서만 드러납니다.
실제로 이 단계에서 결함 1건이 발견되었습니다 (아래 IT-3).

## 준비

```bash
/Users/junho/venv_folders/qc_env/bin/python reader/server.py &
until curl -sf http://localhost:8765/api/state >/dev/null; do sleep 0.25; done
```

## IT-1 — 정적 자산 제공

```bash
for p in / /app.js /style.css /vendor/katex/katex.min.js /vendor/katex/katex.min.css; do
  curl -s -o /dev/null -w "$p %{http_code} %{size_download}\n" http://localhost:8765$p
done
```
**기대**: 전부 200. KaTeX js ≈ 275KB, css ≈ 21KB.
**결과 (2026-08-26)**: 통과 — 2994 / 13637 / 5554 / 275414 / 21201 B

## IT-2 — 페이지 렌더 (서버 ↔ poppler)

```bash
curl -s -o /dev/null -w "%{http_code} %{content_type} %{size_download}\n" \
  http://localhost:8765/api/page/252/image
```
**기대**: `200 image/png` 300KB 내외.
**결과**: 통과 — 200 image/png 315226 B

## IT-3 — 단어 좌표 (서버 ↔ poppler) ⚠ 결함이 발견된 지점

```bash
curl -s http://localhost:8765/api/page/252/words | head -c 200
```
**기대**: `pageWidth`/`pageHeight`/`words` 를 담은 JSON.

**최초 결과**: **실패** — `ParseError: not well-formed (invalid token): line 14, column 82`
원인은 `pdftotext -bbox` 가 수식 글리프를 XML 1.0 금지 제어문자로 내보내는 것.
단위 테스트는 합성 XML을 써서 이 상황을 재현하지 못했다.

**수정 후 결과**: 통과 — `pageWidth 637.2 / pageHeight 843.8 / 494개 단어`,
첫 단어가 `252`(지면에 인쇄된 페이지 번호)로 오프셋 +34 재확인, 제어문자 잔존 없음.

## IT-4 — 추출 텍스트 정합성

```bash
curl -s http://localhost:8765/api/page/252/text | head -c 60
```
**기대**: `252  Quantum search algorithms` 로 시작 (지면 헤더와 일치).
**결과**: 통과

## IT-5 — 질의응답 전체 경로 (뷰어 → 서버 → 크롭 → 워커 → claude → 파일 → 폴링)

```bash
QID=$(curl -s -X POST http://localhost:8765/api/ask -H 'Content-Type: application/json' \
  -d '{"bookPage":252,"question":"이 수식이 무엇을 뜻하는지 설명해 주세요.",
       "region":{"x":250,"y":1050,"w":800,"h":130}}' | python3 -c "import json,sys;print(json.load(sys.stdin)['id'])")
ls -l qa/crops/$QID.png
until curl -s http://localhost:8765/api/answer/$QID | grep -q summary_ready; do sleep 3; done
curl -s http://localhost:8765/api/answer/$QID
```

**기대**: 크롭 PNG 생성 → `pending` → `running` → `summary_ready`, `summary`/`bookPages` 채워짐.

**결과**: 통과. 크롭 17,485 B, 24초 만에 `summary_ready` (`summaryMs` 20,029).
질문에 텍스트 단서를 주지 않고 **영역만 지목했는데도** 워커가 크롭 이미지를 판독해
식 (6.11)임을 정확히 식별하고 주변 문맥과 연결했다. `bookPages: [252]`.

## IT-6 — 기록 축적 및 복원

```bash
tail -20 qa/history.md
curl -s http://localhost:8765/api/history
```
**기대**: `history.md` 헤더가 보존된 채 새 항목이 덧붙어 있고,
`/api/history` 가 질문·답변·크롭 유무를 담은 항목을 돌려준다.
**결과**: 통과 — 기존 헤더 보존, 1개 항목 복원, `crop: True`

## IT-7 — 읽던 위치 저장/복원 (FR-7)

```bash
curl -s -X PUT http://localhost:8765/api/state -H 'Content-Type: application/json' -d '{"lastBookPage":252}'
curl -s http://localhost:8765/api/state
```
**기대**: `lastBookPage` 가 252로 갱신되고 `updatedAt` 이 바뀐다.
**결과**: 통과

## IT-8 — 규칙 격리 (NFR-7)

워커와 동일한 조건(cwd `~/.qc-book-tutor`, 동일 `--add-dir`)으로 사소한 프롬프트를 실행하고
`cache_creation_input_tokens` 를 본다.

**기준**: AI-DLC 트리 안 22,759 / 프로젝트 밖 13,410. 17,000 미만이면 규칙 미로드.
**결과**: 통과 — **14,880**. 추가로 워커에게 "당신 CLAUDE.md의 가장 중요한 규칙"을 물으니
튜터 지침("소프트웨어 개발 작업이 아니다")을 답변. AI-DLC 규칙이 아님을 이중 확인.

## IT-9 — 브라우저 레이아웃 (실제 Chrome 계측) ⚠ 결함이 발견된 지점

```bash
node reader/check_layout.mjs
```

Chrome DevTools Protocol 로 실제 렌더링 수치를 잰다. 외부 패키지 없이 node 내장 WebSocket 만 쓴다.

**기대**: 15개 항목 전부 PASS, `documentScrollsBy = 0`.

**최초 결과**: **실패** — `documentScrollsBy = 12680`. 화면상으로는 "아래로 스크롤하면
빈 화면이 계속 나온다" 로만 보였다.

원인은 **KaTeX 의 숨겨진 MathML**. KaTeX 는 접근성을 위해 보이는 수식과 별개로
`<span class="katex-mathml">` 안에 MathML 을 하나 더 넣고 `position: absolute` + `clip` 으로 숨긴다.
절대 위치 요소의 기준(containing block)은 가장 가까운 **positioned 조상**인데,
`#thread` 에 `position` 이 없어 기준이 문서 전체가 되었다.
그러면 `#thread` 의 `overflow: auto` 에 잘리지 않고 문서 높이를 스레드 내용만큼(13,609px) 늘린다.
**수정**: `#thread` 와 `.qaItem` 에 `position: relative`.

**역검증**: `position: relative` 를 임시로 제거하고 다시 돌리면 이 점검이 `documentScrollsBy=12680`
으로 정확히 잡아낸다 (exit 1). 회귀 감지가 실제로 동작함을 확인했다.

**교훈**: 절대 위치를 쓰는 서드파티 렌더러(KaTeX 등)를 스크롤 컨테이너 안에 넣을 때는
그 컨테이너를 positioned 로 만들어야 한다. 이 계열의 버그는 서버 응답으로도,
파이썬 단위 테스트로도 잡히지 않는다.

## 아직 검증되지 않은 것 — 브라우저 UI

사용자가 브라우저에서 직접 확인 완료 (2026-08-26):

- [x] 투명 텍스트 레이어가 페이지 이미지와 정렬됨
- [x] 영역 선택 사각형이 의도한 좌표를 잡음
- [x] KaTeX 렌더링 정상 (계측상 364개 수식 렌더)
- [x] 좌우 분할 리사이즈, 페이지 이동 키
- [x] 재시작 후 마지막 페이지에서 열림
- [x] 문서 전체 헛스크롤 — 발견되어 IT-9 로 수정·고정

### IT-9 보강 — 점검이 스스로를 망가뜨린 사례

패널이 본문을 덮지 않는지 확인하려고 점검 안에서 `openSide('toc')` 를 호출했더니
`텍스트 레이어가 생성되었다` 가 `0 spans` 로 실패했다.
`openSide()` 가 `drawTextLayer()` 를 **비동기로** 부르기 때문에,
레이어를 비운 직후·다시 채우기 전에 측정한 것이었다.

측정과 조작을 분리하고(주 측정은 부작용 없음, 패널 검사는 별도 단계에서 재렌더를 기다린 뒤 수행)
해결했다. 겸사겸사 `패널 토글 후 텍스트 레이어가 다시 그려진다` 항목을 추가해,
패널 개폐 시 레이어 재계산이 빠지는 회귀를 잡도록 했다 —
이게 빠지면 드래그 선택이 글자와 어긋난다.

### IT-10 — 목차 클릭 이동 (연속 스크롤 도입 후 발견된 결함)

```bash
node reader/check_layout.mjs        # '목차 클릭이 그 페이지로 데려간다' 항목
```

**증상**: 목차에서 챕터를 골라도 그 페이지로 가지 않았다.

**원인**: `goto()` 로 스크롤한 **직후에 패널이 닫히면서** 페이지 폭이 넓어지고
710개 박스의 높이가 전부 재계산되어, 방금 맞춘 스크롤 좌표가 통째로 어긋났다.
연속 스크롤에서는 폭이 바뀌면 좌표계 자체가 달라진다.

**수정**: `relayoutKeeping()` 을 도입해 재레이아웃 후 보던 페이지로 되돌린다.
같은 계열의 지점 네 곳(패널 개폐, 분할선 드래그, 창 크기 변경, 폭 조절)에 모두 적용.
추가로 목차 클릭은 패널을 먼저 닫아 레이아웃을 확정한 뒤 이동한다.

**역검증에서 배운 것**: 처음에는 '순서 뒤집기' 변이로 확인하려 했는데 **통과했다**.
`openSide()` 가 이미 위치를 복원하므로 순서는 부차적이었던 것이다.
진짜 수정 지점(위치 복원)을 제거하는 변이를 넣자 비로소
`목차 p.248 → 도착 p.139` 로 실패했다.
**통과하는 변이 검사는 감시가 없다는 증거다** — 무엇을 망가뜨려야 하는지 틀리면
지키지도 않는 감시를 지킨다고 착각하게 된다.

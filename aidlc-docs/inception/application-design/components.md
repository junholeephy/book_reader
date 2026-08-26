# Components

## 배치

```
/Users/junho/coding_work/qc_book/          <- AI-DLC 프로젝트 트리
  reader/
    index.html                             <- C1 뷰어
    app.js  style.css
    vendor/katex/                          <- KaTeX 벤더링 (~592KB)
    server.py                              <- C2 미니 서버
    start.sh                               <- 서버 기동 + 브라우저 열기
  refs/                                    <- 기존 검색 자산 (nc.sh, 추출 텍스트, 목차)
  qa/                                      <- C4 파일 계약 (런타임 생성)
    state.json  questions/  answers/  crops/  history.md
  cache/pages/                             <- 렌더 PNG / bbox 캐시

/Users/junho/.qc-book-tutor/               <- C3 워커. AI-DLC 트리 바깥 (NFR-7)
  CLAUDE.md                                <- 짧은 "책 튜터" 지침
  ask.sh                                   <- claude -p 래퍼
  schema-summary.json  schema-detail.json
```

**핵심 제약**: C3는 반드시 `qc_book/` **바깥**에 있어야 한다. `CLAUDE.md` 자동 탐색이 상위 디렉터리로
거슬러 올라가므로 하위에 두면 AI-DLC 규칙이 로드되어 NFR-7이 깨진다.
실측: 트리 안 22,759 토큰 vs 밖 13,410 토큰.

---

## C1 — 뷰어 (`reader/index.html` + `app.js`)

**목적**: 책을 읽고, 모르는 부분을 지목해 묻고, 답을 읽는 단일 화면.

**책임**
- 좌측: 페이지 PNG 표시 + 그 위에 **투명 텍스트 레이어**(단어 bbox 좌표로 배치) → 산문 드래그 선택 (FR-3)
- 좌측: **영역 선택 모드** — 사각형을 드래그해 수식·회로도 블록을 지목 (FR-3 확장, Q6=B)
- 좌측: 현재 페이지의 추출 텍스트를 접었다 펼 수 있는 패널 (FR-2)
- 페이지 이동. **표시는 항상 책 페이지 번호** (FR-1)
- 우측: 질문 입력, 선택 문장/영역 미리보기, 전송 (FR-4)
- 우측: 답변을 요약 → "더 자세히" 확장 2층으로 표시, KaTeX로 수식 렌더 (FR-5)
- 우측: 누적 Q&A 기록 표시 (FR-6)
- 페이지 이동 시 위치 저장, 재방문 시 복원 (FR-7)
- 답변 대기 중에도 읽기 계속 가능. 대기 건수 표시 (FR-8, Q4=A)

**하지 않는 것**: PDF를 직접 파싱하지 않는다. Claude를 직접 호출하지 않는다.

**의존**: KaTeX(로컬 벤더링) 외 외부 라이브러리 없음. 바닐라 JS.

---

## C2 — 미니 서버 (`reader/server.py`)

**목적**: 브라우저와 파일시스템·poppler·워커 사이의 유일한 중개자.

**책임**
- 정적 파일 제공 (`index.html`, `app.js`, `vendor/`)
- 페이지 렌더: `pdftoppm -png -r 150` → `cache/pages/` 캐시 (실측 0.209초/페이지)
- 페이지 텍스트: `refs/nielsen-chuang.txt`에서 `\f` 단위로 잘라 제공
- 페이지 단어 좌표: `pdftotext -bbox` → JSON 변환 후 캐시
- 영역 크롭: `pdftoppm -x -y -W -H` → `qa/crops/<id>.png` (실측 0.039초)
- 질문 접수 → `qa/questions/<id>.json` 기록 → **워커를 백그라운드로 실행** (논블로킹)
- 답변 상태 조회 (폴링 대상)
- 읽던 위치 저장/복원 (`qa/state.json`)
- Q&A 히스토리를 `qa/history.md`에 누적

**실행 환경**: `/Users/junho/venv_folders/qc_env/bin/python` (NFR-1). 표준 라이브러리만 사용
(`http.server`, `subprocess`, `json`, `threading`, `xml.etree`). `localhost` 바인딩.

**하지 않는 것**: LLM을 직접 호출하지 않는다. 답변 내용을 해석하지 않는다 (그대로 전달).

---

## C3 — 답변 워커 (`~/.qc-book-tutor/`)

**목적**: 질문 하나를 받아 Claude Code를 헤드리스로 돌려 구조화된 답변을 만든다.

**책임**
- `claude -p` 호출. **필수 플래그** (실측으로 확정):
  - `--allowedTools "Bash Read WebSearch"` — **없으면 모든 도구가 거부된다**
  - `--permission-mode dontAsk`
  - `--output-format json`, `--json-schema <schema>`
  - `--add-dir <refs>` `--add-dir <pdf 디렉터리>`
  - `--session-id <고정 UUID>` — 대화 맥락 유지 (Q2=A)
  - `< /dev/null` — **없으면 3초 지연 + stderr 경고** (실측)
  - stderr를 stdout에 병합하지 않을 것 — JSON 파싱이 깨진다
- 조사 절차 (FR-9): `refs/nc.sh find` → 필요시 PDF 페이지/크롭 이미지 판독 → 필요시 웹 검색
- 2단계 답변 생성 (아래 services.md 참조)

**자체 `CLAUDE.md`**: "책 튜터" 지침만. AI-DLC 규칙 없음 (NFR-7).

---

## C4 — 파일 계약 (`qa/`)

브라우저와 워커는 서로를 모른다. 이 파일들이 유일한 접점이다.

| 경로 | 역할 | 형식 |
|---|---|---|
| `qa/state.json` | 읽던 위치, 고정 세션 ID | JSON |
| `qa/questions/<id>.json` | 질문 + 맥락 | JSON |
| `qa/answers/<id>.json` | 답변 (요약/심화/출처) | JSON |
| `qa/crops/<id>.png` | 영역 선택 이미지 | PNG |
| `qa/history.md` | 사람이 읽는 누적 학습 노트 (FR-6) | Markdown |

**JSON과 Markdown을 둘 다 두는 이유**: JSON은 기계 계약(뷰어가 파싱해 2층으로 렌더),
Markdown은 사람이 읽는 영구 기록. FR-6의 "마크다운으로 축적"은 `history.md`가 충족한다.

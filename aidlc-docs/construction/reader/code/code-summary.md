# Code Generation Summary — Unit: `reader`

## 생성된 파일

### 애플리케이션 코드 (워크스페이스)

| 파일 | 역할 | 규모 |
|---|---|---|
| `reader/server.py` | 미니 서버. PDF 접근 계층 + 질의응답 계층 + HTTP 라우팅 | ~430줄 |
| `reader/index.html` | 뷰어 마크업. 모든 인터랙티브 요소에 `data-testid` | ~70줄 |
| `reader/app.js` | 뷰어 로직. 텍스트 레이어, 영역 선택, Q&A, KaTeX 렌더 | ~330줄 |
| `reader/style.css` | 스타일 | ~140줄 |
| `reader/start.sh` | 서버 기동 + 브라우저 열기 (포트 충돌 감지 포함) | ~28줄 |
| `reader/test_server.py` | 단위 테스트 (stdlib unittest) | ~150줄 |
| `reader/README.md` | 실행·조작·문제 해결 |  |
| `reader/vendor/katex/` | KaTeX 벤더링 (js 272K + css 24K + woff2 20개 296K = 592K) |  |

### 애플리케이션 코드 (워크스페이스 밖 — NFR-7 의도적 배치)

| 파일 | 역할 |
|---|---|
| `~/.qc-book-tutor/CLAUDE.md` | "책 튜터" 지침. AI-DLC 규칙 없음. SUMMARY/DETAIL 모드별 조사 깊이 규정 |
| `~/.qc-book-tutor/ask.sh` | `claude -p` 래퍼. 세션 생성/이어받기 처리 |
| `~/.qc-book-tutor/schema-summary.json` | 요약 단계 구조화 출력 스키마 |
| `~/.qc-book-tutor/schema-detail.json` | 심화 단계 구조화 출력 스키마 |

### 런타임 데이터 (생성됨, gitignore)

`qa/state.json`, `qa/history.md`, `qa/{questions,answers,crops}/`, `cache/pages/`

---

## 생성 중 발견하고 고친 결함 2건

두 건 모두 **실제로 돌려보고** 발견했다. 코드만 읽어서는 드러나지 않았다.

### 1. `ask.sh` 가 호출자의 cwd를 물려받았다 — NFR-7 위반

`cd "$TUTOR"` 가 없어서, 프로젝트 디렉터리에서 호출하면 `claude` 의 cwd가 프로젝트 트리 안이 되고
AI-DLC `CLAUDE.md` 가 그대로 로드됐다. 격리 설계의 핵심이 무력화되는 결함이었다.
초기 측정치(요약 20.5초)도 이 상태에서 나온 값이라 무효.

**수정**: 스크립트 상단에서 `cd "$TUTOR"`. 호출자가 어디서 부르든 튜터 디렉터리에서 실행된다.

### 2. `--session-id` 는 재사용할 수 없다

두 번째 호출부터 `Error: Session ID ... is already in use` 로 즉시 실패했다.
`--session-id` 는 세션을 *생성*하는 플래그이고, 이어받으려면 `--resume` 을 써야 한다.
Q2(맥락 유지)가 통째로 동작하지 않는 결함이었다.

**수정**: 마커 파일(`.session-started`)로 세션 생성 여부를 판단해 첫 호출은 `--session-id`,
이후는 `--resume`. 마커와 실제 상태가 어긋나면 반대 플래그로 한 번 자동 재시도한다
(세션 초기화로 새 UUID가 발급되는 경우가 정상 경로에 있다).

---

## 실측치

| 항목 | 값 | 비고 |
|---|---|---|
| 요약 단계 | **25.0초** | 목표 15~30초 충족 (cwd 수정 후 재측정) |
| 심화 단계 | **2분 52초** | 6,406자, 책 p.251~255 인용 |
| 페이지 렌더 | 0.209초 / 308KB | 150dpi, 캐시 후 즉시 |
| 영역 크롭 | 0.039초 | |
| KaTeX 벤더링 | 592KB | CSS의 폰트 참조를 woff2 20개로 정리 (60→20) |

---

## 요구사항 추적

| 요구사항 | 구현 위치 |
|---|---|
| FR-1 책 본문 | `server.render_page`, `app.js goto()` |
| FR-2 추출 텍스트 | `server.page_text`, `#textPanel` |
| FR-3 선택 캡처 | `server.page_words` + `drawTextLayer` (문장), `crop_region` + `setupRegionSelect` (영역) |
| FR-4 질문 전송 | `server.submit_question`, `app.js ask()` |
| FR-5 단계적 답변 | 워커 2모드 + `renderRich()` KaTeX |
| FR-6 기록 축적 | `server.append_history` (덧붙이기 전용), `load_history` |
| FR-7 위치 복원 | `read_state`/`write_state`, `init()` |
| FR-8 유실 방지 | 질문 파일 선기록, 실패 시 보존 + 재시도 버튼 |
| FR-9 조사 파이프라인 | `~/.qc-book-tutor/CLAUDE.md` + `ask.sh` |
| NFR-1 실행 환경 | `qc_env` 파이썬, 표준 라이브러리만, 127.0.0.1 바인딩 |
| NFR-2 단순성 | 상주 프로세스 1개, WebSocket/프레임워크 없음 |
| NFR-3 응답성 | 논블로킹 제출, 대기 중일 때만 2초 폴링 |
| NFR-4 데이터 소유 | 전부 로컬. KaTeX도 벤더링 |
| NFR-5 비용 | API 키 미사용 |
| NFR-6 상태 명확성 | `pending/running/summary_ready/detail_ready/error` + 대기 건수 배지 |
| NFR-7 규칙 격리 | 워커를 `~/.qc-book-tutor/` 에 배치 + `cd "$TUTOR"` |

## 정적 검사 결과

- `server.py`, `test_server.py` — 컴파일 및 임포트 통과
- `start.sh`, `ask.sh` — `bash -n` 통과
- `app.js` — `node --check` 통과

**단위 테스트 33개 전부 통과.** 변이 검사로 회귀 감지 능력까지 확인했습니다.

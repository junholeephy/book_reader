# Code Generation Plan — Unit: `reader`

> **이 문서가 Code Generation의 단일 진실 공급원입니다.** 각 단계를 완료하는 즉시 `[x]` 로 표시합니다.

## 유닛 맥락

- **유닛명**: `reader` (Units Generation을 건너뛰었으므로 전체가 단일 유닛)
- **워크스페이스 루트**: `/Users/junho/coding_work/qc_book`
- **Python**: `/Users/junho/venv_folders/qc_env/bin/python` (3.13.1, 표준 라이브러리만)
- **외부 의존**: poppler (설치됨), `claude` CLI (설치됨), KaTeX (벤더링 예정)
- **다른 유닛 의존**: 없음
- **데이터베이스**: 없음 (파일 계약이 저장소 역할)

### 코드 위치

| 종류 | 경로 |
|---|---|
| 애플리케이션 코드 | `qc_book/reader/` , `~/.qc-book-tutor/` |
| 런타임 데이터 | `qc_book/qa/` , `qc_book/cache/` |
| 문서 (마크다운) | `aidlc-docs/construction/reader/code/` |

**주의**: `~/.qc-book-tutor/` 는 워크스페이스 밖이지만 NFR-7(AI-DLC 규칙 격리)이 요구하는
의도적 배치입니다. 트리 안에 두면 격리가 깨집니다.

---

## 생성 단계

### Step 1 — 프로젝트 구조 스캐폴드
- [x] `reader/`, `reader/vendor/`, `qa/questions/`, `qa/answers/`, `qa/crops/`, `cache/pages/` 생성
- [x] `.gitignore` 에 `cache/`, `qa/` 추가 (런타임 산출물)
- *추적*: 없음 (구조)

### Step 2 — KaTeX 벤더링
- [x] npm 레지스트리에서 katex 0.16.11 tarball 다운로드
- [x] `katex.min.js`, `katex.min.css`, `fonts/*.woff2` 만 `reader/vendor/katex/` 로 추출
- [x] `ttf`/`woff` 변형은 제외 (용량 절반 절감, 최신 브라우저는 woff2 지원)
- [x] CSS의 폰트 경로가 로컬을 가리키는지 확인
- *추적*: FR-5 (수식 렌더), NFR-4 (오프라인)

### Step 3 — 파일 계약 초기화
- [x] `qa/state.json` 기본값 생성 (`lastBookPage: 1`, 신규 `sessionId` UUID)
- [x] `qa/history.md` 헤더 생성
- *추적*: FR-6, FR-7

### Step 4 — 서버: PDF 접근 계층 (`reader/server.py` 일부)
- [x] `BOOK_PAGE_OFFSET = 34` 상수와 `to_pdf_page()` — **변환은 여기서만**
- [x] `render_page()` — `pdftoppm -png -r 150`, `cache/pages/` 캐시
- [x] `page_words()` — `pdftotext -bbox` → `xml.etree` 파싱 → WordBox 배열, 캐시
      (빈 `<word></word>` 는 제외 — 수식 글리프)
- [x] `page_text()` — `refs/nielsen-chuang.txt` 를 `\f` 로 분할
- [x] `crop_region()` — `pdftoppm -x -y -W -H`
- *추적*: FR-1, FR-2, FR-3

### Step 5 — 서버: 질의응답 계층 (`reader/server.py` 나머지)
- [x] `submit_question()` — id 발급, 질문 기록, 크롭 생성, 큐 투입 후 즉시 반환
- [x] 단일 워커 큐 (`queue.Queue` + 데몬 스레드 1개) — 세션 경합 방지 위해 **순차 처리**
- [x] `run_worker(qid, mode)` — `subprocess.run(..., stdin=DEVNULL)`, stderr 분리
- [x] 답변 병합 + `history.md` **덧붙이기** (덮어쓰기 금지)
- [x] HTTP 라우팅 (component-methods.md의 10개 엔드포인트)
- [x] 실패 시 `status="error"` 기록, 질문 파일 보존
- *추적*: FR-4, FR-5, FR-6, FR-8, NFR-6

### Step 6 — 답변 워커 (`~/.qc-book-tutor/`)
- [x] `CLAUDE.md` — 짧은 "책 튜터" 지침 (AI-DLC 규칙 없음)
      - 페이지 매핑 규칙, `nc.sh` 사용법, 요약/심화 단계별 조사 깊이, LaTeX 표기 규칙
      - **요약 단계에서는 웹 검색 지양, 도구 사용 최소화** (30초 목표)
- [x] `schema-summary.json`, `schema-detail.json`
- [x] `ask.sh` — 필수 플래그 전부 포함:
      `--allowedTools "Bash Read WebSearch"` / `--permission-mode dontAsk` /
      `--json-schema` / `--add-dir` ×2 / `--session-id` / `< /dev/null` / stderr 미병합
- *추적*: FR-9, NFR-5, NFR-7

### Step 7 — 뷰어: 레이아웃 (`reader/index.html`, `style.css`)
- [x] 좌우 2분할, 리사이즈 가능한 구분선
- [x] 상단 툴바: 페이지 이동, 페이지 번호 입력, 텍스트 패널 토글, 영역 선택 모드 토글
- [x] 우측: 대화 기록 영역 + 질문 입력 영역 + 상태 표시줄
- [x] 모든 인터랙티브 요소에 `data-testid` 부여 (`{component}-{role}` 규칙)
- *추적*: FR-1, FR-2, FR-4, NFR-6

### Step 8 — 뷰어: 본문 표시와 선택 (`reader/app.js` 일부)
- [x] 페이지 이미지 로드 + 투명 텍스트 레이어 배치 (bbox → `이미지폭/페이지폭` 스케일)
- [x] 산문 드래그 선택 캡처, 인용 미리보기
- [x] **영역 선택 모드** — 사각형 드래그 → 이미지 픽셀 좌표 캡처, 미리보기
- [x] 추출 텍스트 접이식 패널
- *추적*: FR-1, FR-2, FR-3

### Step 9 — 뷰어: Q&A 패널 (`reader/app.js` 일부)
- [x] 질문 전송 (페이지 번호 + 선택 문장 + 영역 자동 첨부)
- [x] 대기 중일 때만 2초 폴링, 대기 건수 표시
- [x] 요약 표시 → "더 자세히" 버튼 → 심화 확장
- [x] KaTeX 렌더 (`$...$`, `$$...$$`)
- [x] 근거 표시: 책 페이지 번호(클릭 시 해당 페이지로 이동), 웹 링크
- [x] 오류 시 재시도 버튼
- *추적*: FR-4, FR-5, FR-8, NFR-6

### Step 10 — 뷰어: 상태 복원
- [x] 시작 시 `GET /api/state` → 마지막 페이지로 이동
- [x] 페이지 이동마다 `PUT /api/state`
- [x] 시작 시 `GET /api/history` → 이전 대화 복원
- [x] "대화 초기화" 버튼 (새 `sessionId` 발급)
- *추적*: FR-6, FR-7

### Step 11 — 기동 스크립트 (`reader/start.sh`)
- [x] `qc_env` 파이썬으로 서버 기동 + 브라우저 열기 (한 번의 실행)
- [x] 포트 사용 중이면 알려주고 종료
- *추적*: Q3

### Step 12 — 단위 테스트 (`reader/test_server.py`)
- [x] 페이지 번호 변환 (`to_pdf_page`) — 알려진 기준점 검증: 책 6→40, 166→200, 252→286
- [x] bbox 파서 — 빈 `<word>` 제외, 좌표 스케일
- [x] `history.md` 덧붙이기 — 기존 내용 보존 확인
- [x] 질문 id 발급 유일성
- [x] 표준 라이브러리 `unittest` 사용 (외부 테스트 프레임워크 미설치)
- *참고*: PBT 확장은 비활성이므로 속성 기반 테스트는 작성하지 않음

### Step 13 — 실행 문서 (`reader/README.md`)
- [x] 실행 방법, 조작법, 파일 구조
- [x] 알려진 한계 (수식은 드래그 불가 → 영역 선택 사용)
- [x] 문제 해결 (워커 실패, 포트 충돌, 세션 초기화)

### Step 14 — 코드 요약 문서
- [x] `aidlc-docs/construction/reader/code/code-summary.md` — 생성 파일 목록, 요구사항 추적, 검증 방법

---

## 요구사항 추적 요약

| 요구사항 | 담당 단계 |
|---|---|
| FR-1 책 본문 | 4, 8 |
| FR-2 추출 텍스트 | 4, 8 |
| FR-3 선택 캡처 | 4, 8 |
| FR-4 질문 전송 | 5, 7, 9 |
| FR-5 단계적 답변 | 2, 5, 6, 9 |
| FR-6 기록 축적 | 3, 5, 10 |
| FR-7 위치 복원 | 3, 10 |
| FR-8 유실 방지 | 5, 9 |
| FR-9 조사 파이프라인 | 6 |
| NFR-1 실행 환경 | 5, 11 |
| NFR-2 단순성 | 전 단계 |
| NFR-3 응답성 | 5, 6, 9 |
| NFR-4 데이터 소유 | 2 |
| NFR-5 비용 | 6 |
| NFR-6 상태 명확성 | 5, 7, 9 |
| NFR-7 규칙 격리 | 6 |

## 범위

- **총 14단계**
- **생성 파일 약 12개** — `server.py`, `index.html`, `app.js`, `style.css`, `start.sh`,
  `test_server.py`, `README.md`, 워커 4종(`CLAUDE.md`, `ask.sh`, 스키마 2), 요약 문서 1
- **벤더링** — KaTeX ~592KB
- 테스트는 이 단계에서 **작성만** 하고, 실행은 Build and Test 단계에서 합니다

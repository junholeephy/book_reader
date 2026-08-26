# book_reader

PDF 교재를 읽으면서 막히는 부분을 그 자리에서 물어보는 로컬 도구.

왼쪽에 책 원본이 뜨고, 읽다가 막히는 부분을 오른쪽에서 물어보면
Claude Code가 **책 원문과 (필요할 때) 웹을 근거로** 답합니다.
질문·답변은 학습 노트로 쌓이고, 브라우저를 껐다 켜도 읽던 페이지에서 다시 시작합니다.

```
┌─────────────────────────┬──────────────────────┐
│  책 페이지 (원본 렌더)    │  질문하기             │
│  · 연속 스크롤 / 폭 조절  │  · 요약 먼저 (~25초)  │
│  · 문장 드래그 선택       │  · 더 자세히 (~3분)   │
│  · 수식은 영역으로 지목   │  · 근거 페이지 표시    │
│  · 목차(T) / 검색(/)     │  · 절 단위로 모아보기  │
└─────────────────────────┴──────────────────────┘
```

---

> **이 도구는 책을 포함하지 않습니다.** 읽을 PDF 는 직접 준비하셔야 하고,
> 그에 대한 정당한 권리를 가지고 계셔야 합니다.
> PDF 에서 만들어지는 것(추출 텍스트·페이지 이미지·질문 기록)은 전부 로컬에 머물며
> `.gitignore` 대상입니다. 자세한 내용은 [NOTICE.md](NOTICE.md) 를 보십시오.

## 시작하기

```bash
git clone https://github.com/junholeephy/book_reader.git
cd book_reader
./setup.sh /path/to/your/book.pdf --python /path/to/venv/bin/python
./reader/start.sh
```

`setup.sh` 가 하는 일:

1. PDF 를 분석해 **총 페이지 수 · 쪽번호 오프셋 · 목차 범위를 자동 검출**
2. `config.json` 생성
3. 본문 텍스트와 목차를 `refs/` 로 추출 *(저장소에 올라가지 않습니다 — 저작물)*
4. KaTeX 내려받아 벤더링
5. 답변 워커를 `~/.book-reader-tutor/` 에 설치

**쪽번호 오프셋**은 지면에 인쇄된 번호를 읽어 알아냅니다.
700쪽짜리 교재로 검증했을 때 표본 8개가 만장일치로 정답을 가리켰습니다.
검출이 빗나가면 `config.json` 의 `pageOffset` 을 직접 고치면 됩니다.

### 사전 조건

| 항목 | 확인 |
|---|---|
| poppler | `which pdftoppm pdftotext pdfinfo` — 없으면 `brew install poppler` |
| Claude CLI | `~/.local/bin/claude` |
| Python 3 | 표준 라이브러리만 씁니다. `pip install` 불필요 |
| Chrome | 레이아웃 점검용 (선택) |

---

### 원격에서 보기

SSH 로 접속해 작업하면서 눈앞의 브라우저로 보려면 터널을 쓰십시오.

```bash
ssh -N -L 8765:localhost:8765 <user>@<host>    # 노트북에서 별도 터미널
```

서버는 `127.0.0.1` 에만 묶여 있어 터널 없이는 밖에서 닿지 않습니다 — 의도된 것입니다.
`start.sh` 가 SSH 세션을 감지하면 접속 정보에 맞춘 명령을 출력합니다.
자세한 내용은 [reader/README.md](reader/README.md#원격에서-보기-ssh).

---

## 구조

```
book_reader/
├── reader/                 리딩 어시스턴트
│   ├── index.html app.js style.css     뷰어 (바닐라 JS)
│   ├── server.py  config.py            미니 서버 · 설정/자동 검출
│   ├── start.sh                        기동
│   ├── toc.py                          목차 색인 (검색·네비·앵커링 공용)
│   ├── test_server.py test_toc.py      단위 테스트
│   ├── check_layout.mjs                브라우저 레이아웃 점검
│   ├── vendor/katex/                   수식 렌더 (오프라인, 592KB)
│   └── README.md                       ← 조작법은 여기
│
├── tutor/                  답변 워커 템플릿 (setup.sh 가 홈에 설치)
│   ├── CLAUDE.md.tmpl                  "책 튜터" 지침
│   ├── ask.sh                          claude -p 래퍼
│   └── schema-*.json                   답변 구조 스키마
│
├── setup.sh                설치 · 자동 검출
├── config.example.json     설정 예시
│
├── refs/                   책 검색 자산 (gitignore — PDF 에서 생성)
│   ├── book.txt                        전체 추출 텍스트
│   ├── toc-raw.txt                     목차
│   └── nc.sh                           조회 헬퍼 (아래 참조)
│
├── qa/                     런타임 데이터 (gitignore)
│   ├── history.md                      학습 노트 — 사람이 읽는 기록
│   ├── questions/ answers/ crops/      기계용 기록
│   └── state.json                      마지막 페이지, 대화 세션 ID
│
├── cache/pages/            렌더된 페이지 PNG (gitignore)
├── aidlc-docs/             설계 문서 (아래 참조)
└── CLAUDE.md               AI-DLC 개발 워크플로 규칙

~/.book-reader-tutor/       설치된 워커 — 의도적으로 이 트리 바깥
```

### 워커가 프로젝트 밖에 있는 이유

Claude Code는 `CLAUDE.md` 를 **상위 디렉터리로 거슬러 올라가며** 찾습니다.
워커를 저장소 안에 두면 책에 대한 질문 하나마다 개발 규칙 전체가 로드됩니다.
책 질문에 개발 워크플로 규칙은 필요 없습니다.

실측: 프로젝트 트리 안 **22,759 토큰** vs 바깥 **13,410 토큰** — 질문당 약 9,300 토큰 차이.

---

## 책 검색 헬퍼 (`refs/nc.sh`)

뷰어 없이 터미널에서 바로 책을 뒤질 때 씁니다.

```bash
./refs/nc.sh find 'Grover iteration'   # 검색 — 책 페이지 번호와 함께 표시
./refs/nc.sh page 252                  # 해당 페이지 추출 텍스트
./refs/nc.sh page 252 254              # 페이지 범위
./refs/nc.sh layout 252                # 레이아웃 보존 (표에 유용)
./refs/nc.sh pdfpage 252               # → 286. PDF 뷰어로 직접 열 때
```

**페이지 매핑: `PDF 페이지 = 책 페이지 + 오프셋`** (오프셋은 `config.json` 에 있습니다)

> **주의 — 추출 텍스트는 수식이 소실됩니다.** `nc.sh` 가 주는 텍스트에는 수식 기호가 빠져 있습니다. 수식이 필요하면 원본 페이지를 이미지로 봐야 합니다.
> 뷰어의 왼쪽 화면이 바로 그 원본이고, 워커도 필요할 때 원본 페이지를 직접 판독합니다.

---

## 어떻게 동작하는가

```
브라우저 ──HTTP──▶ 미니 서버 ──파일──▶ qa/ ──▶ ask.sh ──▶ claude -p
   ▲                                                          │
   └──────────── 답변 파일 ◀───────────────────────────────────┘
```

**브라우저와 Claude Code는 직접 통신하지 않습니다.** 파일시스템이 유일한 접점입니다.
덕분에 답변 도중 무슨 일이 생겨도 질문이 유실되지 않고, 워커를 통째로 교체해도 나머지는 그대로입니다.

상주하는 프로세스는 **미니 서버 하나뿐**입니다. Claude Code 세션을 띄워둘 필요가 없습니다 —
질문이 올 때마다 `claude -p` 가 짧게 태어나 답하고 사라집니다. API 키도, 질문당 과금도 없습니다.

### 답변이 두 단계인 이유

요약과 심화를 한 번에 만들었더니 **첫 글자를 보기까지 2분 25초**가 걸렸습니다.
생성을 두 단계로 나눠 첫 응답을 **약 25초**로 줄였고, 심화를 안 누르는 질문에서는
그 비용을 아예 치르지 않습니다.

기다리는 동안에는 워커가 **실제로** 무엇을 하는지 보여줍니다 —
`책에서 "Grover iteration" 검색 중` / `책 p.252 원본 페이지 판독 중` / `생각 정리 중 · 약 200 토큰`.
지어낸 진행바가 아니라 워커의 실제 도구 호출과 생성 상태를 옮긴 것입니다.

---

## 실측치

| 항목 | 값 |
|---|---|
| 요약 답변 | 20~25초 |
| 심화 답변 | 172~248초 (6,400~7,900자) |
| 페이지 렌더 | 0.209초 / 315KB (150dpi, 이후 캐시) |
| 영역 크롭 | 0.039초 |
| 워커 컨텍스트 | 14,880 토큰 (AI-DLC 격리 상태) |
| 단위 테스트 | 54개 / 0.06초 |
| 레이아웃 점검 | 15개 항목 (실제 Chrome 계측) |
| 목차 색인 | 254개 항목 (12장 / 72절 / 162소절 / 부록·참고문헌) |

---

## 알려진 한계

**수식은 드래그로 선택되지 않습니다.** PDF가 수식을 문자로 내보내지 않기 때문입니다
(실제로는 `\x04` 같은 제어문자로 나옵니다). 수식을 물을 때는 **▣ 영역 선택**으로
사각형을 그리면 그 부분을 이미지로 잘라 함께 보냅니다.

**진행 표시가 최대 30초쯤 고정될 수 있습니다.** 도구가 실행되는 동안에는 이벤트가 나오지 않습니다.
그 사이에도 경과 시간은 계속 올라갑니다.

**검색은 수식을 찾지 못합니다.** 추출 텍스트 기반이라 산문만 잡힙니다.

**대화가 길어지면 느려집니다.** 맥락을 이어가도록 세션을 고정하기 때문입니다.
**↺ 대화 초기화** 로 끊으면 됩니다.

---

## 테스트

```bash
# 단위 테스트
/Users/junho/venv_folders/qc_env/bin/python -m unittest discover -s reader -p 'test_*.py' -v

# 브라우저 레이아웃 점검 (서버가 떠 있어야 함)
node reader/check_layout.mjs
```

레이아웃 점검은 실제 Chrome 을 헤드리스로 띄워 수치를 잽니다.
문서가 헛스크롤하거나 텍스트 레이어가 이미지 밖으로 넘치는 종류의 결함은
서버 응답으로도 파이썬 테스트로도 잡히지 않습니다.

통합 검증 절차는 [aidlc-docs/construction/build-and-test/integration-test-instructions.md](aidlc-docs/construction/build-and-test/integration-test-instructions.md) 에 실행 명령과 기대값이 함께 정리되어 있습니다.

---

## 설계 문서 (`aidlc-docs/`)

이 프로젝트는 [AI-DLC](CLAUDE.md) 워크플로로 만들어졌습니다. 결정의 근거가 전부 남아 있습니다.

| 문서 | 내용 |
|---|---|
| [requirements.md](aidlc-docs/inception/requirements/requirements.md) | FR-1~FR-13, NFR-1~NFR-7, 범위 밖 항목 |
| [execution-plan.md](aidlc-docs/inception/plans/execution-plan.md) | 실행/생략한 단계와 근거, 품질 게이트 |
| [application-design.md](aidlc-docs/inception/application-design/application-design.md) | 컴포넌트, 파일 계약, 요구사항 추적 |
| [code-summary.md](aidlc-docs/construction/reader/code/code-summary.md) | 생성 파일 목록, 구현 중 잡은 결함 |
| [build-and-test-summary.md](aidlc-docs/construction/build-and-test/build-and-test-summary.md) | 테스트 결과, 품질 게이트 판정 |
| [audit.md](aidlc-docs/audit.md) | 전체 대화·결정 기록 |

워크플로 규칙 파일 자체(`.aidlc-rule-details/`)는 제3자 콘텐츠라 저장소에 담지 않았습니다.
설계 결정의 **결과물**만 `aidlc-docs/` 에 있습니다. [NOTICE.md](NOTICE.md) 참조.

### 설계가 측정으로 뒤집힌 지점들

문서를 읽을 때 참고가 되도록, 추측이 틀렸던 곳을 모아 둡니다.

| 처음 생각 | 실제 |
|---|---|
| Artifact로 만들면 어디서나 접속 가능 | 내장 Claude는 웹 검색·PDF 접근 불가. 게다가 교재 전문 호스팅은 저작권 문제 |
| `pdftoppm` vs `pdf.js` 양자택일 | `pdftotext -bbox` 로 투명 텍스트 레이어 → 의존성 0으로 둘 다 확보 |
| `--permission-mode dontAsk` 면 도구가 돈다 | **전면 거부.** `--allowedTools` 명시가 필수 |
| `--session-id` 로 대화를 이어간다 | 재사용 불가. 두 번째부터 `--resume` 이어야 함 |
| 수식 글리프는 빈 `<word></word>` | 제어문자가 들어 있어 XML 파싱이 통째로 깨짐 |
| 답변은 10~30초 | 깊은 질문 하나에 **2분 25초** → 2단계 분리의 계기 |
| 도구 호출만 보여주면 진행 표시 완성 | 마지막 도구 이후 **156초 정지**. 생성 델타까지 봐야 함 |
| 빈 화면 스크롤은 텍스트 레이어 문제 | KaTeX 의 숨겨진 MathML 이 `position: absolute` 로 문서를 **12,680px** 늘림 |
| 목차 클릭 안 됨은 클릭 핸들러 문제 | 이동 **후** 패널이 닫히며 박스 높이가 재계산되어 좌표가 날아감 |

---

## 이 프로젝트의 방침

- **개인 학습 도구입니다.** 다중 사용자·인증·원격 접속·모바일 대응은 범위 밖입니다 (YAGNI)
- **책은 저장소에 들어가지 않습니다.** PDF·추출 텍스트·목차·질문 기록 전부 gitignore 대상입니다
- **로컬에 머뭅니다.** 저작권 있는 교재를 외부 호스팅에 올리지 않습니다
- **표준 라이브러리 우선.** 외부 JS 의존성은 KaTeX 하나뿐이고, 그것도 벤더링해서 오프라인 동작합니다
- **AI-DLC는 개발할 때만 씁니다.** 책에 대한 질문에는 개입하지 않습니다 (NFR-7)

---

## 저작권 주의사항

**이 저장소에는 책이 없습니다.** 본문·목차·페이지 이미지 어느 것도 커밋되지 않습니다.
`setup.sh` 가 **사용자의 PDF 에서** 생성하고, 생성물은 전부 `.gitignore` 대상입니다.

| 파일 | 커밋 여부 |
|---|---|
| `refs/book.txt` (책 전문 텍스트) | ❌ |
| `refs/toc-raw.txt` (목차) | ❌ |
| `cache/pages/*.png` (페이지 이미지) | ❌ |
| `qa/` (질문·답변·학습 노트·잘라낸 이미지) | ❌ |
| `config.json` (PDF 경로 등) | ❌ |
| 코드·문서 | ✅ |

- 읽으려는 PDF 에 대한 **정당한 권리**(구매·구독·이용 허락)를 가지고 계셔야 합니다
- 생성된 텍스트·이미지·답변을 **재배포하지 마십시오.** 개인 학습 용도입니다
- 답변은 책의 문장과 수식을 인용합니다. 인용문을 모아 배포하는 용도로 쓰지 마십시오

커밋 전에 한 번 확인하는 습관을 권합니다:

```bash
git check-ignore -v refs/book.txt cache/pages/1.png qa/state.json config.json
```

> `.gitignore` 는 `#` 을 **줄 맨 앞에서만** 주석으로 봅니다.
> `qa/    # 질문 기록` 처럼 줄 끝에 주석을 달면 그 줄 전체가 패턴이 되어
> **아무것도 걸러지지 않습니다.** 이 저장소를 만들 때 실제로 겪었고,
> 하마터면 책 전문과 페이지 이미지 240장을 올릴 뻔했습니다.

## 라이선스

코드와 문서는 [MIT License](LICENSE) 입니다.

사용자가 제공하는 PDF 와 그로부터 파생된 모든 것은 적용 범위가 아닙니다.

제3자 구성 요소(KaTeX MIT · Poppler GPL-2.0 · Claude Code)와
보증 관련 고지는 [NOTICE.md](NOTICE.md) 에 정리했습니다.

**답변은 LLM 이 생성하며 틀릴 수 있습니다.** 중요한 내용은 원문을 직접 확인하십시오.

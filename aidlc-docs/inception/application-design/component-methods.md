# Component Methods

> 시그니처와 입출력 계약만 정의한다. 상세 로직은 Code Generation에서.

## C2 — 미니 서버 HTTP 인터페이스

| Method | Path | 입력 | 출력 |
|---|---|---|---|
| GET | `/` | — | `index.html` |
| GET | `/api/page/{bookPage}/image` | — | `image/png` (캐시됨) |
| GET | `/api/page/{bookPage}/text` | — | `text/plain` — 추출 텍스트 |
| GET | `/api/page/{bookPage}/words` | — | `application/json` — 아래 WordBox 배열 |
| POST | `/api/ask` | AskRequest | `{"id": "..."}` (즉시 반환, 논블로킹) |
| GET | `/api/answer/{id}` | — | AnswerStatus |
| POST | `/api/answer/{id}/expand` | — | `{"status":"running"}` — 심화 답변 요청 |
| GET | `/api/history` | — | `{"items": [HistoryItem]}` |
| GET | `/api/state` | — | State |
| PUT | `/api/state` | State | `{"ok": true}` |

**모든 `{bookPage}` 는 책 페이지 번호.** 서버가 `pdfPage = bookPage + 34` 로 변환한다.
변환은 서버 한 곳에서만 일어난다 — 뷰어와 워커는 책 번호만 다룬다.

### 내부 메서드 (server.py)

```python
def render_page(book_page: int) -> Path
    # cache/pages/{pdf_page}.png 없으면 pdftoppm -png -r 150 -f N -l N
    # 실측 0.209s / 308KB

def page_words(book_page: int) -> list[dict]
    # pdftotext -bbox -f N -l N -> xml.etree 파싱 -> WordBox 배열, 캐시
    # 주의: 수식 글리프는 빈 <word></word> 로 나온다 -> 텍스트 없는 항목은 제외

def page_text(book_page: int) -> str
    # refs/nielsen-chuang.txt 를 \f 로 분할한 pdf_page 번째 레코드

def crop_region(book_page: int, x: int, y: int, w: int, h: int, qid: str) -> Path
    # pdftoppm -x -y -W -H -> qa/crops/{qid}.png   (실측 0.039s)
    # 좌표는 150dpi 렌더 이미지 픽셀 기준

def submit_question(req: AskRequest) -> str
    # id 생성 -> qa/questions/{id}.json 기록 -> threading 으로 워커 실행 -> id 즉시 반환

def run_worker(qid: str, mode: str) -> None
    # mode: "summary" | "detail"
    # subprocess.run([tutor/ask.sh, qid, mode], stdin=DEVNULL, capture_output=True)
    # 성공 -> qa/answers/{id}.json 갱신, history.md 추가
    # 실패 -> status="error", error 메시지 기록 (질문은 유실되지 않음, FR-8)
```

---

## 데이터 계약

### WordBox
```json
{"t": "Grover", "x": 128.4, "y": 100.1, "w": 12.6, "h": 8.0}
```
좌표는 `pdftotext -bbox` 가 함께 알려주는 `page width/height` 기준.
뷰어가 `이미지 픽셀폭 / 페이지폭` 비율로 스케일한다.
**주의**: `pdfinfo` 의 페이지 크기와 다를 수 있으므로 반드시 `-bbox` 출력의 값을 쓴다.

### AskRequest
```json
{
  "bookPage": 252,
  "question": "이게 왜 회전이 되는 건가요?",
  "selectedText": "the Grover iteration can be regarded as a rotation",
  "region": {"x": 250, "y": 1050, "w": 800, "h": 130}
}
```
`selectedText` 와 `region` 은 각각 선택 사항. 둘 다 없으면 페이지 번호만 맥락으로 전달된다.

### Question (`qa/questions/{id}.json`)
```json
{
  "id": "20260826-162730-4f1a",
  "createdAt": "2026-08-26T16:27:30Z",
  "bookPage": 252,
  "question": "...",
  "selectedText": "...",
  "cropPath": "qa/crops/20260826-162730-4f1a.png"
}
```

### Answer (`qa/answers/{id}.json`)
```json
{
  "id": "20260826-162730-4f1a",
  "status": "pending | running | summary_ready | detail_ready | error",
  "summary": "핵심 요약. 수식은 $...$ / $$...$$ LaTeX",
  "detail": "심화 설명 (요청 시에만 채워짐)",
  "bookPages": [250, 251, 252],
  "webLinks": [{"title": "...", "url": "..."}],
  "error": null,
  "summaryMs": 21000,
  "detailMs": 145000
}
```

### State (`qa/state.json`)
```json
{"lastBookPage": 252, "sessionId": "c3235638-...", "updatedAt": "2026-08-26T16:27:30Z"}
```
`sessionId` 는 `claude -p --session-id` 에 넘기는 고정 UUID (Q2=A, 맥락 유지).
뷰어의 "대화 초기화" 버튼이 새 UUID를 발급한다.

---

## C3 — 워커 인터페이스

```bash
ask.sh <question-id> <mode>      # mode = summary | detail
```

- `qa/questions/<id>.json` 을 읽어 프롬프트를 조립
- `qa/crops/<id>.png` 가 있으면 프롬프트에 그 경로를 명시해 워커가 Read 하도록 지시
- stdout 으로 스키마에 맞는 JSON 하나만 출력
- **호출 규약** (실측으로 확정):
  ```
  claude -p "$PROMPT" \
    --output-format json --json-schema "$SCHEMA" \
    --permission-mode dontAsk --allowedTools "Bash Read WebSearch" \
    --add-dir "$REFS" --add-dir "$PDFDIR" \
    --session-id "$SESSION_ID" \
    < /dev/null 2>/dev/null
  ```
  `--allowedTools` 누락 시 모든 도구 거부. `< /dev/null` 누락 시 3초 지연.
  `2>&1` 사용 금지 — stderr 경고가 JSON을 오염시킨다.

### 스키마

`schema-summary.json` — `{summary, bookPages, webLinks}` (detail 없음, 짧게)
`schema-detail.json` — `{detail, bookPages, webLinks}`

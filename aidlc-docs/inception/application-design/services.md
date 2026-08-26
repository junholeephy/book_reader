# Services / Orchestration

## S1 — 페이지 열람 서비스

**흐름**: 브라우저가 책 페이지 N을 요청 → 서버가 세 자원을 병렬 제공

1. `GET /api/page/N/image` — `pdftoppm` 렌더 (캐시 히트 시 즉시)
2. `GET /api/page/N/words` — `pdftotext -bbox` 파싱 (캐시)
3. `GET /api/page/N/text` — 추출 텍스트 슬라이스

뷰어는 1을 배경으로 깔고 2로 투명 텍스트 레이어를 얹는다. 3은 접힌 패널에 넣는다.
이동 즉시 `PUT /api/state` 로 위치를 저장한다 (FR-7).

**캐시 정책**: 최초 방문 시 렌더 후 디스크 캐시. 710페이지 전부 캐시해도 약 200MB.
사전 렌더는 하지 않는다 (YAGNI) — 실제로 읽는 페이지만 쌓인다.

---

## S2 — 질의응답 서비스 ⭐ 2단계 구조

### 왜 2단계인가 (측정에 근거한 설계)

리허설 실측: 깊이 있는 질문 하나에 **144,951ms (9턴)**.
당초 사용자에게 "10~30초"라고 말했던 추정은 틀렸다.

요약과 심화를 한 번에 만들면 사용자는 **첫 글자를 보기까지 2분 넘게** 기다린다.
FR-5는 이미 "요약 먼저 → 더 자세히 확장"이라는 2층 구조를 요구하고 있으므로,
**생성도 두 번에 나누면** 요구사항을 그대로 만족시키면서 체감 지연이 크게 줄어든다.

| 단계 | 트리거 | 도구 사용 | 목표 시간 |
|---|---|---|---|
| **Stage 1 — 요약** | 질문 전송 즉시 | `nc.sh` 검색 위주, 웹 검색 지양 | 15~30초 |
| **Stage 2 — 심화** | "더 자세히" 클릭 시에만 | 페이지 이미지 판독 + 필요시 웹 검색 | 60~150초 |

심화를 아예 안 누르는 질문도 많을 것이므로, 평균 비용도 함께 줄어든다.

### 흐름

```
[뷰어]  질문 + 페이지 + (선택 문장 | 영역)  --POST /api/ask-->  [서버]
[서버]  qa/questions/<id>.json 기록
        (영역이 있으면) pdftoppm 크롭 -> qa/crops/<id>.png
        answers/<id>.json 을 status=pending 으로 생성
        <id> 즉시 반환                      -- 논블로킹, 사용자는 계속 읽는다 (Q4=A)
        백그라운드 스레드로 ask.sh <id> summary 실행
[워커]  claude -p (schema-summary)  -> stdout JSON
[서버]  answers/<id>.json 에 summary 병합, status=summary_ready
        history.md 에 추가
[뷰어]  GET /api/answer/<id> 폴링 -> 요약 표시 + "더 자세히" 버튼

  ... 사용자가 "더 자세히" 클릭 ...

[뷰어]  POST /api/answer/<id>/expand
[서버]  ask.sh <id> detail  (같은 --session-id 이므로 요약 시점의 맥락을 이어받는다)
[뷰어]  폴링 -> 심화 설명 확장 표시
```

### 동시성

- 질문은 **순차 처리**한다. 서버가 단일 워커 큐를 유지하고 하나씩 실행한다.
  이유: 같은 `--session-id` 를 공유하므로 병렬 실행 시 대화 상태가 경합한다.
- 대기 중인 질문 수를 `GET /api/answer/*` 응답에 담아 뷰어가 "대기 N건"을 표시한다 (FR-8, NFR-6).

### 실패 처리

워커가 실패하면 `status="error"`, `error` 필드에 메시지를 남긴다.
**질문 파일은 지우지 않는다** — 재시도 버튼으로 다시 큐에 넣을 수 있다 (FR-8).

---

## S3 — 기록 서비스 (FR-6)

`qa/history.md` 에 다음 형식으로 **덧붙이기만** 한다 (덮어쓰지 않는다).

```markdown
## [2026-08-26 16:27] 책 p.252

**질문**: 이게 왜 회전이 되는 건가요?

**선택한 문장**: > the Grover iteration can be regarded as a rotation

**요약**: ...

<details><summary>심화</summary>

...

</details>

**근거**: 책 p.250, 251, 252 / [Nature — ...](https://...)

---
```

뷰어는 재시작 시 `GET /api/history` 로 이 기록을 복원해 우측 패널에 보여준다.

**기록은 두 겹으로 남는다**:
1. `qa/history.md` — 사람이 읽는 학습 노트. 에디터로 열어도 되고 검색해도 된다
2. `qa/answers/*.json` + `qa/questions/*.json` — 기계 계약. 뷰어 렌더링용

여기에 더해 `--session-id` 를 고정하므로 Claude Code 자체의 세션 기록에도 대화가 남는다.

---

## S4 — 기동 서비스 (`start.sh`)

```bash
#!/bin/bash
# 서버를 띄우고 브라우저를 연다. 한 번의 실행으로 둘 다.
/Users/junho/venv_folders/qc_env/bin/python reader/server.py &
sleep 1
open http://localhost:8765
wait
```

launchd 로 백그라운드 상주시키지 않는다 — 터미널에 로그가 보이는 편이 디버깅에 유리하고,
사용자가 Q3에서 "상태가 눈에 보이는" 수동 실행 계열을 택했다.

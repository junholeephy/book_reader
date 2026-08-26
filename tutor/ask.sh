#!/bin/bash
# 질문 하나에 대해 Claude Code를 헤드리스로 돌려 구조화된 답변을 stdout으로 낸다.
#
#   ask.sh <question-id> <summary|detail>
#
# 호출 규약은 실측으로 확정되었다. 아래 다섯 가지를 어기면 동작하지 않는다:
#   1. --allowedTools 없으면 모든 도구가 거부된다 (dontAsk 단독으로는 Bash조차 못 쓴다)
#   2. < /dev/null 없으면 stdin을 3초간 기다린 뒤 경고를 낸다
#   3. stderr를 stdout에 병합하면(2>&1) 그 경고가 JSON을 오염시킨다
#   4. 반드시 튜터 디렉터리에서 실행해야 한다. 호출자의 cwd를 물려받으면
#      프로젝트 트리 안에서 돌게 되어 AI-DLC CLAUDE.md가 로드된다 (NFR-7 위반)
#   5. --session-id 는 세션을 '생성'한다. 두 번째부터는 --resume 을 써야 한다
#      (재사용하면 "Session ID ... is already in use" 로 즉시 실패)
set -euo pipefail

QID="${1:?usage: ask.sh <question-id> <summary|detail>}"
MODE="${2:?usage: ask.sh <question-id> <summary|detail> [session-id]}"
SESSION_ARG="${3:-}"

TUTOR="$(cd "$(dirname "$0")" && pwd)"
# 경로는 setup.sh 가 설치 시 써 놓는다. 저장소의 스크립트 자체에는 경로가 없다.
# shellcheck source=/dev/null
. "$TUTOR/config.env"
REFS="$PROJECT/refs"
QA="$PROJECT/qa"
CLAUDE="${CLAUDE:-$HOME/.local/bin/claude}"

# NFR-7: claude 의 cwd 가 프로젝트 트리 안이면 AI-DLC 규칙이 로드된다.
# 호출자가 어디서 부르든 여기서 실행한다.
cd "$TUTOR"

SCHEMA_FILE="$TUTOR/schema-$MODE.json"
[ -f "$SCHEMA_FILE" ] || { echo "unknown mode: $MODE" >&2; exit 2; }

# 세션 ID는 서버가 장(chapter)별로 골라 넘겨준다.
# 장이 바뀌면 다른 세션이 오므로 맥락이 자동으로 갈린다.
if [ -n "$SESSION_ARG" ]; then
  SESSION_ID="$SESSION_ARG"
else
  SESSION_ID="$("$PY" -c "
import json,pathlib
st=json.loads(pathlib.Path('$QA/state.json').read_text())
print(next(iter(st.get('sessions',{}).values()), st.get('sessionId','')))
")"
fi

# 프롬프트 조립은 파이썬에 맡긴다 (따옴표·개행 이스케이프를 셸에서 다루면 깨진다).
PROMPT="$("$PY" - "$QID" "$MODE" "$QA" "$REFS" <<'PY'
import json, pathlib, sys

qid, mode, qa_dir, refs = sys.argv[1:5]
q = json.loads(pathlib.Path(qa_dir, "questions", f"{qid}.json").read_text())

parts = [f"[모드: {mode.upper()}]", ""]
parts.append(f"사용자는 지금 책 p.{q['bookPage']} 를 읽고 있습니다.")
parts.append(f"(PDF 페이지로는 {q['bookPage'] + 34} 입니다.)")

if q.get("selectedText"):
    parts += ["", "본문에서 다음 부분을 지목했습니다:", f'"""{q["selectedText"]}"""']

if q.get("cropPath"):
    parts += ["",
              "그리고 페이지의 특정 영역을 사각형으로 지목했습니다. "
              f"Read 도구로 이 이미지를 반드시 확인하십시오:",
              f"  {q['cropPath']}",
              "이 영역이 질문의 대상입니다 (수식이나 회로도일 가능성이 높습니다)."]

parts += ["", "질문:", q["question"] or "(이 부분을 설명해 주세요)"]

if mode == "summary":
    parts += ["",
              "SUMMARY 모드입니다. 30초 안에 끝내십시오. 웹 검색은 쓰지 마십시오.",
              f"근거 페이지가 필요하면 {refs}/nc.sh find 를 쓰십시오.",
              "3~5문장으로 핵심만 답하십시오."]
else:
    parts += ["",
              "DETAIL 모드입니다. 시간을 써도 좋으니 제대로 설명하십시오.",
              f"책 검색: {refs}/nc.sh find <정규식>",
              "수식·회로도가 관련되면 Read 도구의 pages 파라미터로 PDF 페이지를 이미지로 읽으십시오.",
              "필요하면 웹도 검색하십시오.",
              "배경 원리와 왜 그런 결과가 나오는지, 트레이드오프까지 설명하십시오."]

print("\n".join(parts))
PY
)"

# 세션이 이미 만들어졌으면 --resume, 처음이면 --session-id.
# 마커 파일이 세션 ID와 일치하는지로 판단한다 (초기화 시 새 UUID가 발급되면 자동으로 재생성).
mkdir -p "$TUTOR/.sessions"
MARKER="$TUTOR/.sessions/$SESSION_ID"
if [ -f "$MARKER" ]; then
  SESSION_ARGS=(--resume "$SESSION_ID")
else
  SESSION_ARGS=(--session-id "$SESSION_ID")
fi

# stream-json 으로 내보낸다. 도구를 쓸 때마다 이벤트가 한 줄씩 나오므로
# 서버가 그것을 읽어 "지금 무엇을 조사 중인지"를 화면에 띄울 수 있다 (FR-10).
# --verbose 가 없으면 print 모드에서 stream-json 이 거부된다.
# 마지막 줄(type=result)에 최종 답변이 담긴다. 파싱은 서버가 한다.
run_claude() {
  "$CLAUDE" -p "$PROMPT" \
    --output-format stream-json --verbose --include-partial-messages \
    --json-schema "$(cat "$SCHEMA_FILE")" \
    --permission-mode dontAsk \
    --allowedTools "Bash Read WebSearch" \
    --add-dir "$REFS" \
    --add-dir "$PDFDIR" \
    --add-dir "$QA" \
    "$@" \
    < /dev/null
}

# 세션 인자가 틀렸을 때만 반대로 재시도한다. 스트림을 흘려보내면서 판단해야 하므로
# 첫 줄이 나오기 전에 실패하는 경우(= 세션 오류)만 재시도 대상이다.
if ! run_claude "${SESSION_ARGS[@]}"; then
  if [ "${SESSION_ARGS[0]}" = "--resume" ]; then
    run_claude --session-id "$SESSION_ID"
  else
    run_claude --resume "$SESSION_ID"
  fi
fi
touch "$MARKER"

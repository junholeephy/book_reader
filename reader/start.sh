#!/bin/bash
# 서버를 띄우고 브라우저를 연다. 한 번의 실행으로 둘 다.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ -f "$ROOT/config.json" ] || { echo "설정이 없습니다. ./setup.sh <PDF 경로> 를 먼저 실행하세요." >&2; exit 1; }
read -r PY PORT <<< "$(python3 -c "
import json;c=json.load(open('$ROOT/config.json'));print(c.get('python','python3'), c.get('port',8765))")"

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "포트 $PORT 가 이미 사용 중입니다."
  echo "  이미 떠 있다면: open http://localhost:$PORT"
  exit 1
fi

"$PY" "$ROOT/reader/server.py" &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT INT TERM
for _ in $(seq 1 40); do
  curl -sf "http://localhost:$PORT/api/state" >/dev/null 2>&1 && break
  sleep 0.25
done
open "http://localhost:$PORT"
wait $SERVER_PID

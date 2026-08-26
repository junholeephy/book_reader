#!/bin/bash
# 서버를 백그라운드로 띄운다. SSH 연결이 끊겨도 살아남는다.
#
#   ./reader/serve.sh          기동 (이미 떠 있으면 주소만 알려준다)
#   ./reader/serve.sh stop     중지
#   ./reader/serve.sh log      로그 보기
#
# 태블릿 Termux 처럼 세션이 자주 끊기는 환경을 위한 것이다.
# start.sh 는 포그라운드라 SSH 가 끊기면 서버도 같이 죽는다.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin:/opt/local/bin"
[ -f "$ROOT/config.json" ] || { echo "설정이 없습니다. ./setup.sh <PDF 경로> 먼저." >&2; exit 1; }

read -r PY PORT HOST <<< "$(python3 -c "
import json;c=json.load(open('$ROOT/config.json'))
print(c.get('python','python3'), c.get('port',8765), c.get('host','127.0.0.1'))")"
PIDFILE="$ROOT/qa/server.pid"
LOG="$ROOT/qa/server.log"

addr() {
  "$PY" -c "
import sys; sys.path.insert(0,'$ROOT/reader')
import config; print(config.resolve_host('$HOST')[0])"
}
running() { [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }

case "${1:-start}" in
  stop)
    running && { kill "$(cat "$PIDFILE")"; rm -f "$PIDFILE"; echo "중지했습니다."; } \
            || echo "떠 있지 않습니다."
    ;;
  log)
    tail -n "${2:-40}" "$LOG" 2>/dev/null || echo "로그가 없습니다."
    ;;
  start)
    if running; then
      echo "이미 떠 있습니다 (pid $(cat "$PIDFILE"))."
    else
      mkdir -p "$ROOT/qa"
      nohup "$PY" "$ROOT/reader/server.py" >> "$LOG" 2>&1 &
      echo $! > "$PIDFILE"
      for _ in $(seq 1 40); do
        curl -sf "http://$(addr):$PORT/api/state" >/dev/null 2>&1 && break
        sleep 0.25
      done
      running || { echo "기동 실패. 로그:" >&2; tail -20 "$LOG" >&2; rm -f "$PIDFILE"; exit 1; }
      echo "기동했습니다 (pid $(cat "$PIDFILE"))."
    fi
    echo
    echo "    http://$(addr):$PORT"
    echo
    echo "  중지: ./reader/serve.sh stop   로그: ./reader/serve.sh log"
    ;;
  *) echo "usage: serve.sh [start|stop|log]" >&2; exit 2 ;;
esac

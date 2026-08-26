#!/bin/bash
# 책 서버를 켜고 끄는 유일한 진입점.
#
#   ./reader/serve.sh              기동 (이미 떠 있으면 주소만 알려준다)
#   ./reader/serve.sh stop         중지
#   ./reader/serve.sh log [N]      로그 보기
#   ./reader/serve.sh url [local|remote]   주소만 (스크립트용)
#   ./reader/serve.sh fg           포그라운드로 (디버깅용, Ctrl+C 로 종료)
#
# 기본은 백그라운드다. 태블릿 Termux 처럼 세션이 자주 끊기는 환경에서
# 포그라운드로 띄우면 SSH 가 끊길 때 서버도 같이 죽는다.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin:/opt/local/bin"
[ -f "$ROOT/config.json" ] || { echo "설정이 없습니다. ./setup.sh <PDF 경로> 먼저." >&2; exit 1; }

read -r PY PORT HOST <<< "$(python3 -c "
import json;c=json.load(open('$ROOT/config.json'))
print(c.get('python','python3'), c.get('port',8765), c.get('host','127.0.0.1'))")"
PIDFILE="$ROOT/qa/server.pid"
LOG="$ROOT/qa/server.log"

# 접속 가능한 주소 전부. 로컬과 tailnet 을 동시에 열기 때문에 하나가 아니다.
addrs() {
  "$PY" -c "
import sys; sys.path.insert(0,'$ROOT/reader')
import config
for h in config.resolve_hosts('$HOST')[0]:
    print('localhost' if h == '127.0.0.1' else h)"
}
# 다른 기기에서 쓸 주소. 로컬이 아닌 것이 있으면 그것, 없으면 localhost.
# SSH 로 원격에서 부르면 localhost 는 부르는 쪽 기기를 가리켜 쓸모가 없다.
remote_addr() { addrs | grep -v '^localhost$' | head -1 || true; }
addr() { a="$(remote_addr)"; [ -n "$a" ] && echo "$a" || echo localhost; }
running() { [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; }
# pid 파일이 없어도 이미 떠 있을 수 있다 (fg 로 띄웠거나 pid 파일이 지워진 경우).
# 포트를 확인하는 것보다 실제로 응답하는지 보는 편이 확실하다.
serving() { curl -sf --max-time 2 "http://localhost:$PORT/api/state" 2>/dev/null | grep -q lastBookPage; }

case "${1:-start}" in
  stop)
    if running; then
      kill "$(cat "$PIDFILE")"; rm -f "$PIDFILE"; echo "중지했습니다."
    elif serving; then
      # fg 나 직접 실행으로 띄운 경우 pid 파일이 없다. 포트를 잡고 있는 프로세스를 찾는다.
      PIDS="$(lsof -nP -iTCP:"$PORT" -sTCP:LISTEN -t 2>/dev/null || true)"
      if [ -n "$PIDS" ]; then
        echo "$PIDS" | xargs kill && echo "중지했습니다 (다른 곳에서 띄운 서버)."
      else
        echo "떠 있는데 프로세스를 찾지 못했습니다." >&2
      fi
    else
      echo "떠 있지 않습니다."
    fi
    ;;
  url)                      # 스크립트에서 주소만 받아갈 때
    case "${2:-remote}" in
      local)  echo "http://localhost:$PORT" ;;
      *)      echo "http://$(addr):$PORT" ;;
    esac
    ;;
  log)
    tail -n "${2:-40}" "$LOG" 2>/dev/null || echo "로그가 없습니다."
    ;;
  fg)                       # 포그라운드. 로그가 터미널로 흐른다
    if running || serving; then
      echo "이미 떠 있습니다. ./reader/serve.sh stop 으로 먼저 끄십시오." >&2
      exit 1
    fi
    exec "$PY" -u "$ROOT/reader/server.py"
    ;;
  start)
    if running; then
      echo "이미 떠 있습니다 (pid $(cat "$PIDFILE"))."
    elif serving; then
      echo "이미 떠 있습니다 (다른 곳에서 띄운 서버 — pid 를 모릅니다)."
    else
      mkdir -p "$ROOT/qa"
      # -u 가 없으면 파일로 리다이렉트할 때 stdout 이 블록 버퍼링되어
      # 로그가 8KB 찰 때까지 비어 있다. booklog 가 아무것도 못 보여준다.
      nohup "$PY" -u "$ROOT/reader/server.py" >> "$LOG" 2>&1 &
      echo $! > "$PIDFILE"
      # 프로세스가 살아 있는 것만으로는 부족하다. 포트를 못 잡고 곧 죽는 중일 수도 있다.
      # 실제로 응답할 때까지 기다린다.
      for _ in $(seq 1 40); do
        serving && break
        sleep 0.25
      done
      if ! serving; then
        echo "기동 실패. 로그:" >&2
        tail -20 "$LOG" >&2
        kill "$(cat "$PIDFILE")" 2>/dev/null || true
        rm -f "$PIDFILE"
        exit 1
      fi
      echo "기동했습니다 (pid $(cat "$PIDFILE"))."
    fi
    echo
    if [ -n "${SSH_CONNECTION:-}" ]; then
      # 원격에서 불렀다. 여기서 쓸 주소를 먼저 보여준다.
      R="$(remote_addr)"
      [ -n "$R" ] && echo "    http://$R:$PORT      <- 지금 쓰는 기기에서"
      echo "    http://localhost:$PORT   (책이 있는 컴퓨터에서)"
    else
      addrs | while read -r a; do echo "    http://$a:$PORT"; done
    fi
    echo
    echo "  중지: ./reader/serve.sh stop   로그: ./reader/serve.sh log"

    if [ -z "${SSH_CONNECTION:-}" ] && [ "$HOST" = "127.0.0.1" ] && command -v open >/dev/null; then
      open "http://localhost:$PORT"        # 이 컴퓨터 앞에 앉아 있다
    elif [ -n "${SSH_CONNECTION:-}" ] && [ "$HOST" = "127.0.0.1" ]; then
      # 원격에서 불렀는데 로컬에만 묶여 있다. 터널이 필요하다.
      SERVER_IP="$(echo "$SSH_CONNECTION" | awk '{print $3}')"
      cat <<MSG

  이 서버는 localhost 에만 열려 있습니다. 보고 계신 기기에서 열려면
  터미널을 하나 더 열고 터널을 만드십시오:

      ssh -N -L $PORT:localhost:$PORT ${USER}@${SERVER_IP}

  그다음 http://localhost:$PORT
  (config.json 의 host 를 "tailscale" 로 두면 터널 없이 바로 열립니다)
MSG
    fi
    ;;
  *) echo "usage: serve.sh [start|stop|fg|log [N]|url [local|remote]]" >&2; exit 2 ;;
esac

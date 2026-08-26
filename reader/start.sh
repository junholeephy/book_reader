#!/bin/bash
# 서버를 띄우고 브라우저를 연다. 한 번의 실행으로 둘 다.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

# SSH 로 명령을 직접 실행하면 로그인 셸이 아니라 /opt/homebrew/bin 이 PATH 에 없다.
# poppler 가 통째로 안 보이므로 알려진 위치를 덧붙인다.
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin:/opt/local/bin"

[ -f "$ROOT/config.json" ] || { echo "설정이 없습니다. ./setup.sh <PDF 경로> 를 먼저 실행하세요." >&2; exit 1; }
read -r PY PORT HOST <<< "$(python3 -c "
import json;c=json.load(open('$ROOT/config.json'))
print(c.get('python','python3'), c.get('port',8765), c.get('host','127.0.0.1'))")"

# host 가 127.0.0.1 이 아니면 헬스체크와 안내에 쓸 실제 주소를 구한다
BIND="127.0.0.1"
if [ "$HOST" = "tailscale" ]; then
  for t in tailscale /Applications/Tailscale.app/Contents/MacOS/Tailscale \
           /usr/local/bin/tailscale /opt/homebrew/bin/tailscale; do
    command -v "$t" >/dev/null 2>&1 || [ -x "$t" ] || continue
    BIND="$("$t" ip -4 2>/dev/null | head -1)"; [ -n "$BIND" ] && break
  done
elif [ "$HOST" != "127.0.0.1" ] && [ "$HOST" != "localhost" ]; then
  BIND="$HOST"
fi
[ "$BIND" = "0.0.0.0" ] && BIND="127.0.0.1"

# 포트가 이미 쓰이고 있으면, 그게 우리 서버인지부터 확인한다.
# serve.sh 로 띄워두었거나 다른 기기에서 먼저 켰을 수 있다 — 그러면 그냥 붙으면 된다.
ATTACHED=""
if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  if curl -sf "http://localhost:$PORT/api/state" 2>/dev/null | grep -q lastBookPage; then
    echo "이미 떠 있는 서버에 연결합니다."
    ATTACHED=1
  else
    echo "포트 $PORT 를 다른 프로그램이 쓰고 있습니다." >&2
    echo "  확인: lsof -nP -iTCP:$PORT -sTCP:LISTEN" >&2
    exit 1
  fi
fi

if [ -z "$ATTACHED" ]; then
  "$PY" "$ROOT/reader/server.py" &
  SERVER_PID=$!
  # 우리가 띄운 것만 정리한다. 붙은 경우에 끄면 남의 세션을 끊는다.
  trap 'kill $SERVER_PID 2>/dev/null || true' EXIT INT TERM
fi
for _ in $(seq 1 40); do
  curl -sf "http://localhost:$PORT/api/state" >/dev/null 2>&1 && break
  sleep 0.25
done

if [ "$HOST" != "127.0.0.1" ] && [ "$HOST" != "localhost" ]; then
  # 로컬과 외부 주소를 동시에 연다. 터널이 필요 없다.
  cat <<MSG

  ── 접속 주소 ─────────────────────────────────────────────
      http://localhost:$PORT      (이 컴퓨터)
      http://$BIND:$PORT   (다른 기기)
  ──────────────────────────────────────────────────────────

MSG
  [ -z "${SSH_CONNECTION:-}" ] && open "http://localhost:$PORT"
elif [ -n "${SSH_CONNECTION:-}" ]; then
  # SSH 로 들어와 있다. 여기서 open 을 부르면 브라우저가 '이 머신' 에서 열린다 —
  # 눈앞에 있는 화면이 아니므로 아무 소용이 없다. 대신 터널 방법을 안내한다.
  # 서버는 127.0.0.1 에만 묶여 있으므로 터널 없이는 밖에서 닿지 않는다 (의도된 것).
  SERVER_IP="$(echo "$SSH_CONNECTION" | awk '{print $3}')"
  USER_AT="${USER}@${SERVER_IP}"
  cat <<MSG

  ── SSH 세션에서 실행 중입니다 ────────────────────────────────
  서버는 이 머신의 localhost:$PORT 에만 열려 있습니다.
  보고 계신 노트북에서 열려면 SSH 터널을 만드십시오.

  가장 간단한 방법 — 이 세션은 그대로 두고, 노트북에서 터미널을 하나 더 열어:

      ssh -N -L $PORT:localhost:$PORT $USER_AT

  (-N 은 명령을 실행하지 않고 터널만 유지합니다. 그대로 두십시오.)

  그런 다음 노트북 브라우저에서:

      http://localhost:$PORT

  매번 하기 번거로우면 노트북의 ~/.ssh/config 에 넣어두십시오:

      Host bookreader
          HostName $SERVER_IP
          User $USER
          LocalForward $PORT localhost:$PORT

  그러면 앞으로는 ssh bookreader 만으로 터널이 함께 열립니다.
  ──────────────────────────────────────────────────────────

MSG
else
  open "http://localhost:$PORT"
fi

if [ -n "$ATTACHED" ]; then
  echo "  (이 서버는 다른 곳에서 띄운 것이라 Ctrl+C 로 꺼지지 않습니다)"
  echo "  중지하려면: ./reader/serve.sh stop"
else
  wait $SERVER_PID
fi

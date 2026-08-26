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

if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "포트 $PORT 가 이미 사용 중입니다."
  echo "  이미 떠 있다면: open http://localhost:$PORT"
  exit 1
fi

"$PY" "$ROOT/reader/server.py" &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null || true' EXIT INT TERM
for _ in $(seq 1 40); do
  curl -sf "http://$BIND:$PORT/api/state" >/dev/null 2>&1 && break
  sleep 0.25
done

if [ "$HOST" != "127.0.0.1" ] && [ "$HOST" != "localhost" ]; then
  # 이미 이 컴퓨터 밖에서 닿는 주소에 묶여 있다. 터널이 필요 없다.
  cat <<MSG

  ── 다른 기기에서 바로 열 수 있습니다 ─────────────────────
      http://$BIND:$PORT
  ──────────────────────────────────────────────────────────

MSG
  [ -z "${SSH_CONNECTION:-}" ] && open "http://$BIND:$PORT"
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

wait $SERVER_PID

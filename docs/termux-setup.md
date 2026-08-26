# 태블릿 Termux 에서 쓰기

안드로이드 태블릿의 Termux 에서 SSH 로 책 서버를 켜고, 크롬으로 읽는 설정.

## 0. 한 번만 하는 준비

### Termux 패키지

```bash
pkg update && pkg install openssh
pkg install termux-api        # 선택 — 크롬을 자동으로 띄우고 싶을 때
```

`termux-api` 는 Play 스토어의 **Termux:API** 앱도 함께 설치해야 동작합니다.
없어도 됩니다 (주소를 직접 크롬에 붙여넣으면 됩니다).

### SSH 키 (비밀번호 안 묻게)

```bash
ssh-keygen -t ed25519 -C "tab-s10"        # 계속 엔터
ssh-copy-id junho@100.85.159.32           # 맥 비밀번호 한 번만 입력
```

`ssh-copy-id` 가 없으면:

```bash
cat ~/.ssh/id_ed25519.pub | ssh junho@100.85.159.32 \
  'mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
```

### Tailscale

안드로이드 Tailscale 앱이 **연결됨** 상태여야 합니다. 이게 꺼져 있으면
`100.85.159.32` 로 닿지 않습니다.

## 1. `~/.ssh/config`

연결이 끊기지 않게 하고, 짧은 이름으로 부를 수 있게.

```
Host mac
    HostName 100.85.159.32
    User junho
    ServerAliveInterval 30
    ServerAliveCountMax 6
```

> **주소는 Tailscale IP 를 쓰십시오.** Termux 는 안드로이드 시스템 리졸버를 타는데
> Tailscale 앱의 MagicDNS 설정이 Termux 까지 항상 반영되지는 않습니다.
> IP 는 어느 네트워크에서든(LTE 포함) 그대로 동작합니다.

## 2. `~/.bashrc`

```bash
# ── book_reader ────────────────────────────────────────────────
BOOK_HOST=mac                              # ~/.ssh/config 의 Host 이름
BOOK_DIR=~/coding_work/qc_book             # 맥에서의 저장소 경로

# 서버를 켜고 주소를 띄운다
book() {
  local out url
  out=$(ssh "$BOOK_HOST" "cd $BOOK_DIR && ./reader/serve.sh") || { echo "$out"; return 1; }
  echo "$out"
  url=$(echo "$out" | grep -o 'http://[^ ]*' | head -1)
  [ -n "$url" ] || return 0
  if command -v termux-open-url >/dev/null 2>&1; then
    termux-open-url "$url"                 # 크롬이 바로 열린다
  else
    echo
    echo "  크롬에 붙여넣으세요:  $url"
  fi
}

alias bookstop="ssh $BOOK_HOST '$BOOK_DIR/reader/serve.sh stop'"
alias booklog="ssh $BOOK_HOST '$BOOK_DIR/reader/serve.sh log'"
alias mac="ssh $BOOK_HOST"                 # 그냥 맥에 붙을 때
# ───────────────────────────────────────────────────────────────
```

적용:

```bash
source ~/.bashrc
```

## 3. 쓰는 법

| 명령 | 하는 일 |
|---|---|
| `book` | 맥에서 서버를 켜고 크롬을 띄움 (이미 켜져 있으면 주소만) |
| `bookstop` | 맥의 서버를 끔 — **SSH 연결이 아니라 서버** |
| `booklog` | 서버 로그 — 요청 기록과 워커 실패 이유가 남습니다 |
| `mac` | 맥에 그냥 SSH 접속 |

서버는 `nohup` 으로 떠 있어서 **SSH 가 끊겨도 살아남습니다.**
태블릿에서 Termux 를 닫아도 읽던 페이지가 유지됩니다.

## 자주 겪는 것

**`ssh: Could not resolve hostname mac`**
`~/.ssh/config` 가 없거나 오타입니다. `ssh junho@100.85.159.32` 로 직접 확인해 보십시오.

**`Connection refused` / `No route to host`**
안드로이드 Tailscale 앱이 연결돼 있는지 확인하십시오.

**`기동 실패: pdftoppm 을(를) 찾지 못했습니다`**
맥에 poppler 가 없습니다: `brew install poppler`.
(PATH 문제는 스크립트가 알아서 처리합니다.)

**주소는 나오는데 크롬에서 안 열림**
맥 쪽 `config.json` 의 `host` 가 `tailscale` 인지 확인하십시오.
`127.0.0.1` 이면 맥 밖에서는 닿지 않습니다.

**답변이 안 옴**
`booklog` 로 서버 로그를 보십시오. 다음이 남습니다:

```
GET /api/page/252/image -> 200      요청 기록
POST /api/ask -> 200
worker exit 1: ...                  워커가 실패했다면 이유
```

`claude` CLI 로그인이 풀렸거나 사용량 한도에 걸리면 여기에 나옵니다. 맥에서 `claude` CLI 로그인이 풀렸을 수 있습니다.

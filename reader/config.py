"""설정 로딩과 자동 검출.

이 도구는 원래 Nielsen & Chuang 한 권을 위해 만들었고 경로·오프셋이 코드에 박혀 있었다.
저장소로 관리하게 되면서 책에 의존하는 값을 전부 여기로 모았다.

`config.json` 이 없으면 `setup.sh` 가 만든다. 손으로 써도 된다.
"""
import collections
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

# SSH 로 명령을 직접 실행하면(ssh host "cmd") 로그인 셸이 아니라
# ~/.zprofile 이 읽히지 않는다. macOS 기본 PATH(/etc/paths)에는 /opt/homebrew/bin 이 없어
# poppler 가 통째로 안 보인다. 도구 위치를 PATH 에 맡기지 않는다.
EXTRA_BIN_DIRS = [
    "/opt/homebrew/bin",      # Homebrew (Apple Silicon)
    "/usr/local/bin",         # Homebrew (Intel) / 직접 설치
    "/opt/local/bin",         # MacPorts
    "/usr/bin", "/bin",
]


def ensure_path() -> None:
    """알려진 설치 위치를 PATH 에 덧붙인다. 이미 있으면 건드리지 않는다."""
    current = os.environ.get("PATH", "").split(os.pathsep)
    added = [d for d in EXTRA_BIN_DIRS if d not in current and Path(d).is_dir()]
    if added:
        os.environ["PATH"] = os.pathsep.join(current + added)


def find_tool(name: str) -> str:
    """실행 파일의 절대 경로. 못 찾으면 빈 문자열."""
    ensure_path()
    found = shutil.which(name)
    if found:
        return found
    for d in EXTRA_BIN_DIRS:
        cand = Path(d, name)
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)
    return ""


DEFAULTS = {
    "pdf": "",                 # 필수 — 읽을 PDF의 절대 경로
    "pageOffset": "auto",      # PDF 페이지 = 책 페이지 + offset. "auto" 면 검출한다
    "tocPages": "auto",        # 목차가 실린 PDF 페이지 범위. "6-17" 형태 또는 "auto"
    "python": "python3",       # 서버를 돌릴 인터프리터
    "host": "127.0.0.1",       # 누가 접속할 수 있는가. 아래 resolve_host 참조
    "port": 8765,
    "dpi": 150,
    "tutorDir": "~/.book-reader-tutor",
    "chrome": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
}


def load() -> dict:
    ensure_path()
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        cfg.update(json.loads(CONFIG_PATH.read_text()))
    if not cfg["pdf"]:
        raise SystemExit(
            "config.json 에 pdf 경로가 없습니다.\n"
            "  ./setup.sh <PDF 경로>   로 만드십시오.")
    cfg["pdf"] = str(Path(cfg["pdf"]).expanduser())
    cfg["tutorDir"] = str(Path(cfg["tutorDir"]).expanduser())
    return cfg


def save(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- 자동 검출

def page_count(pdf: str) -> int:
    out = subprocess.run(["pdfinfo", pdf], capture_output=True, text=True,
                         stdin=subprocess.DEVNULL).stdout
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    if not m:
        raise SystemExit(f"pdfinfo 로 페이지 수를 읽지 못했습니다: {pdf}")
    return int(m.group(1))


def _page_text(pdf: str, pg: int, layout: bool = False) -> str:
    """목차 페이지는 -layout 없이는 텍스트가 아예 나오지 않는 경우가 있다 (N&C 실측).
    검출용으로는 -layout 을 쓴다."""
    cmd = ["pdftotext"] + (["-layout"] if layout else [])
    cmd += ["-f", str(pg), "-l", str(pg), pdf, "-"]
    return subprocess.run(cmd, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL).stdout


def detect_offset(pdf: str, total: int) -> int:
    """지면에 인쇄된 쪽번호를 읽어 'PDF 페이지 − 책 페이지' 를 알아낸다.

    머리말·꼬리말의 앞뒤 두 줄에서 정수를 찾아 후보를 모으고 최빈값을 고른다.
    본문 한가운데를 표본으로 삼는다 — 앞쪽은 로마숫자, 뒤쪽은 색인이라 잡음이 많다.
    (N&C 로 검증: 표본 8개 전부 34에 투표)
    """
    lo, hi = int(total * 0.2), int(total * 0.85)
    probes = [lo + (hi - lo) * i // 7 for i in range(8)]
    votes: collections.Counter = collections.Counter()
    for pg in probes:
        lines = [l.strip() for l in _page_text(pdf, pg).splitlines() if l.strip()]
        if not lines:
            continue
        for line in lines[:2] + lines[-2:]:
            for tok in re.findall(r"\b\d{1,4}\b", line):
                n = int(tok)
                if 1 <= n <= total:
                    votes[pg - n] += 1
    if not votes:
        return 0
    best, count = votes.most_common(1)[0]
    if count < 3:
        return 0            # 확신이 없으면 오프셋 없음으로 둔다. 사용자가 고칠 수 있다
    return best


def detect_toc_pages(pdf: str, total: int) -> str:
    """목차가 실린 PDF 페이지 범위를 찾는다.

    '제목 ......... 숫자' 꼴의 줄이 몰려 있는 앞쪽 페이지들을 목차로 본다.
    """
    entry = re.compile(r"\S.*?\s{2,}\d{1,4}\s*$")
    hits = []
    for pg in range(1, min(40, total) + 1):
        lines = [l for l in _page_text(pdf, pg, layout=True).splitlines() if l.strip()]
        if not lines:
            continue
        n = sum(1 for l in lines if entry.search(l))
        if n >= 6 and n / len(lines) > 0.4:
            hits.append(pg)
    if not hits:
        return ""
    return f"{hits[0]}-{hits[-1]}"


# ---------------------------------------------------------------- 바인딩 주소

def resolve_hosts(host: str) -> tuple[list[str], str]:
    """설정의 host 를 **바인딩할 주소 목록**으로 바꾼다.

    이 도구는 이 컴퓨터에서도, 다른 기기에서도 쓴다.
    그래서 tailscale 을 골라도 로컬 접속을 막지 않는다 — 둘 다 연다.

      127.0.0.1  이 컴퓨터에서만                      (기본값)
      tailscale  이 컴퓨터 + 내 tailnet 기기          <- 태블릿에서 볼 때
      0.0.0.0    같은 네트워크의 누구나                <- 권하지 않는다
      <주소>      이 컴퓨터 + 그 주소

    이 서버에는 인증이 없다. '어디에 묶느냐' 가 곧 접근 제어다.
    """
    if host in ("0.0.0.0", "::"):
        return [host], ("!! 같은 네트워크의 누구나 접속 가능합니다. "
                        "이 서버에는 인증이 없어 아무나 책을 열람하고 "
                        "당신 계정으로 질문을 던질 수 있습니다")

    if host in ("127.0.0.1", "localhost", ""):
        return ["127.0.0.1"], "이 컴퓨터에서만 접속 가능"

    if host == "tailscale":
        ip = _tailscale_ip()
        if not ip:
            # Tailscale 이 꺼져 있다고 서버를 못 띄울 이유는 없다.
            # 이 컴퓨터에서라도 읽을 수 있어야 한다.
            return ["127.0.0.1"], ("이 컴퓨터에서만 접속 가능 "
                                   "(Tailscale 주소를 찾지 못했습니다 — 앱이 연결되어 있는지 확인하십시오)")
        return ["127.0.0.1", ip], f"이 컴퓨터 + tailnet 기기 ({ip})"

    return ["127.0.0.1", host], f"이 컴퓨터 + {host}"


def resolve_host(host: str) -> tuple[str, str]:
    """이전 인터페이스. 대표 주소 하나만 돌려준다 (외부에서 볼 주소)."""
    hosts, note = resolve_hosts(host)
    return (hosts[-1], note)


# Tailscale 은 CGNAT 대역(100.64.0.0/10)을 쓴다. 이 형태가 아니면 IP 가 아니다.
_TS_IP = re.compile(r"^100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}$")


def _tailscale_ip() -> str:
    """이 머신의 tailnet IPv4 주소.

    CLI 를 먼저 쓰되 **출력을 반드시 검증한다.** GUI 세션이 없을 때
    Tailscale.app 의 CLI 는 IP 대신 오류 문구를 stdout 으로 뱉는다
    ("The Tailscale GUI failed to start: ..."). 그대로 바인딩 주소로 쓰면
    'encoding of hostname failed' 로 죽는다 — SSH 로 띄웠을 때 실제로 겪었다.

    CLI 가 실패하면 네트워크 인터페이스에서 직접 찾는다. 이쪽은 GUI 가 필요 없다.
    """
    for exe in ("tailscale",
                "/usr/local/bin/tailscale", "/opt/homebrew/bin/tailscale",
                "/Applications/Tailscale.app/Contents/MacOS/Tailscale"):
        path = shutil.which(exe) if "/" not in exe else (exe if Path(exe).exists() else None)
        if not path:
            continue
        try:
            out = subprocess.run([path, "ip", "-4"], capture_output=True, text=True,
                                 timeout=10, stdin=subprocess.DEVNULL).stdout
        except (OSError, subprocess.TimeoutExpired):
            continue
        for line in out.splitlines():
            if _TS_IP.match(line.strip()):
                return line.strip()

    # CLI 가 안 되면 인터페이스에서 직접 (GUI 불필요)
    try:
        out = subprocess.run(["/sbin/ifconfig"], capture_output=True, text=True,
                             timeout=10, stdin=subprocess.DEVNULL).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
    for m in re.finditer(r"inet (\S+)", out):
        if _TS_IP.match(m.group(1)):
            return m.group(1)
    return ""

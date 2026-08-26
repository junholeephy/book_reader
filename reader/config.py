"""설정 로딩과 자동 검출.

이 도구는 원래 Nielsen & Chuang 한 권을 위해 만들었고 경로·오프셋이 코드에 박혀 있었다.
저장소로 관리하게 되면서 책에 의존하는 값을 전부 여기로 모았다.

`config.json` 이 없으면 `setup.sh` 가 만든다. 손으로 써도 된다.
"""
import json
import re
import subprocess
import collections
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.json"

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

def resolve_host(host: str) -> tuple[str, str]:
    """설정의 host 를 실제 바인딩 주소로 바꾸고, 누가 닿을 수 있는지 한 줄로 설명한다.

    이 서버에는 인증이 없다. 그래서 '어디에 묶느냐' 가 곧 접근 제어다.
      127.0.0.1  이 컴퓨터에서만                (기본값)
      tailscale  내 tailnet 기기에서만          (Tailscale 이 만든 암호화 사설망)
      0.0.0.0    같은 네트워크의 누구나          <- 권하지 않는다
    """
    if host == "tailscale":
        ip = _tailscale_ip()
        if not ip:
            raise SystemExit(
                "Tailscale IP 를 찾지 못했습니다. Tailscale 이 실행 중인지 확인하거나\n"
                "  config.json 의 host 를 127.0.0.1 로 되돌리십시오.")
        return ip, f"tailnet 기기에서 접속 가능 ({ip})"
    if host in ("0.0.0.0", "::"):
        return host, ("!! 같은 네트워크의 누구나 접속 가능합니다. "
                      "이 서버에는 인증이 없어 아무나 책을 열람하고 "
                      "당신 계정으로 질문을 던질 수 있습니다")
    if host in ("127.0.0.1", "localhost"):
        return "127.0.0.1", "이 컴퓨터에서만 접속 가능"
    return host, f"{host} 로만 접속 가능"


def _tailscale_ip() -> str:
    """이 머신의 tailnet IPv4 주소 (100.x.y.z)."""
    for exe in ("tailscale",
                "/Applications/Tailscale.app/Contents/MacOS/Tailscale",
                "/usr/local/bin/tailscale", "/opt/homebrew/bin/tailscale"):
        try:
            out = subprocess.run([exe, "ip", "-4"], capture_output=True, text=True,
                                 timeout=10, stdin=subprocess.DEVNULL).stdout.strip()
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
        if out:
            return out.splitlines()[0].strip()
    return ""

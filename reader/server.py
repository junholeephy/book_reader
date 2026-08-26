#!/usr/bin/env python3
"""book_reader 미니 서버.

브라우저와 poppler/워커 사이의 유일한 중개자.
표준 라이브러리만 사용한다 (NFR-1).
"""
import json
import mimetypes
import queue
import re
import subprocess
import threading
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from time import monotonic
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import config
from toc import Toc

# ---------------------------------------------------------------- 설정

ROOT = Path(__file__).resolve().parent.parent
REFS = ROOT / "refs"
BOOK_TEXT = REFS / "book.txt"
TOC_RAW = REFS / "toc-raw.txt"
QA = ROOT / "qa"
CACHE = ROOT / "cache" / "pages"
STATIC = Path(__file__).resolve().parent

CFG = config.load()
PDF = Path(CFG["pdf"])
TUTOR = Path(CFG["tutorDir"])
HOST, HOST_NOTE = config.resolve_host(CFG.get("host", "127.0.0.1"))
PORT = int(CFG["port"])
DPI = int(CFG["dpi"])

# 책 페이지 -> PDF 페이지. 책마다 다르므로 설정에서 온다 (setup.sh 가 자동 검출).
# 이 변환은 서버 안에서만 일어난다. 뷰어와 파일 계약은 책 번호만 다룬다.
BOOK_PAGE_OFFSET = int(CFG["pageOffset"])
PDF_PAGE_COUNT = int(CFG["pageCount"])
MIN_BOOK_PAGE = 1 - BOOK_PAGE_OFFSET          # -33 (표지/서문 영역)
MAX_BOOK_PAGE = PDF_PAGE_COUNT - BOOK_PAGE_OFFSET  # 676


def to_pdf_page(book_page: int) -> int:
    return book_page + BOOK_PAGE_OFFSET


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_page(book_page: int) -> None:
    if not (MIN_BOOK_PAGE <= book_page <= MAX_BOOK_PAGE):
        raise ValueError(f"book page {book_page} out of range "
                         f"[{MIN_BOOK_PAGE}, {MAX_BOOK_PAGE}]")


# ---------------------------------------------------------------- PDF 접근 계층

def render_page(book_page: int) -> Path:
    """페이지를 PNG로 렌더링한다. 캐시 히트 시 즉시 반환. 실측 0.209s/page."""
    check_page(book_page)
    pdf_page = to_pdf_page(book_page)
    out = CACHE / f"{pdf_page}.png"
    if out.exists():
        return out
    CACHE.mkdir(parents=True, exist_ok=True)
    prefix = CACHE / f"tmp-{pdf_page}"
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(DPI), "-f", str(pdf_page), "-l", str(pdf_page),
         str(PDF), str(prefix)],
        check=True, stdin=subprocess.DEVNULL, capture_output=True)
    # pdftoppm은 -<페이지번호>를 접미사로 붙인다. 자릿수가 가변이라 glob으로 찾는다.
    produced = sorted(CACHE.glob(f"tmp-{pdf_page}-*.png"))
    if not produced:
        raise RuntimeError(f"pdftoppm produced no output for pdf page {pdf_page}")
    produced[0].rename(out)
    for leftover in produced[1:]:
        leftover.unlink()
    return out


# pdftotext -bbox 는 수식 글리프를 XML 1.0이 금지하는 제어문자로 내보낸다
# (예: 책 p.252의 합 기호가 <word ...>\x04</word>). 그대로 파싱하면 문서 전체가 깨진다.
# 허용 문자: #x9 #xA #xD #x20-#xD7FF #xE000-#xFFFD #x10000-#x10FFFF
_XML_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def page_words(book_page: int) -> dict:
    """단어별 bounding box. 투명 텍스트 레이어의 재료.

    수식 글리프는 제어문자로 나오므로 걸러낸 뒤, 내용이 비게 된 단어는 제외한다.
    페이지 크기는 pdfinfo가 아니라 -bbox 출력의 값을 써야 한다 (서로 다를 수 있음).
    """
    check_page(book_page)
    pdf_page = to_pdf_page(book_page)
    cached = CACHE / f"{pdf_page}.words.json"
    if cached.exists():
        return json.loads(cached.read_text())

    proc = subprocess.run(
        ["pdftotext", "-bbox", "-f", str(pdf_page), "-l", str(pdf_page), str(PDF), "-"],
        check=True, stdin=subprocess.DEVNULL, capture_output=True, text=True)
    root = ET.fromstring(_XML_ILLEGAL.sub("", proc.stdout))
    ns = {"x": "http://www.w3.org/1999/xhtml"}
    page = root.find(".//x:page", ns)
    if page is None:
        page = root.find(".//page")  # 네임스페이스 없는 변형 대비
    if page is None:
        raise RuntimeError(f"no <page> in bbox output for pdf page {pdf_page}")

    words = []
    for w in list(page):
        text = (w.text or "").strip()
        if not text:
            continue  # 수식 글리프 — 텍스트 레이어에 넣을 수 없다
        x0, y0 = float(w.get("xMin")), float(w.get("yMin"))
        x1, y1 = float(w.get("xMax")), float(w.get("yMax"))
        words.append({"t": text, "x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0})

    result = {
        "pageWidth": float(page.get("width")),
        "pageHeight": float(page.get("height")),
        "words": words,
    }
    cached.write_text(json.dumps(result))
    return result


_toc: Toc | None = None


def toc() -> Toc:
    """목차 색인. FR-11 검색 결과 라벨 · FR-12 네비게이션 · FR-13 질문 앵커링이 공유한다."""
    global _toc
    if _toc is None:
        _toc = Toc.load(TOC_RAW)
    return _toc


def search_book(query: str, limit: int = 60) -> list[dict]:
    """추출 텍스트 전체 검색 (FR-11).

    한계: 추출 텍스트 기반이므로 수식은 검색되지 않는다. 산문만 잡힌다.
    """
    q = query.strip()
    if len(q) < 2:
        return []
    try:
        rx = re.compile(q, re.IGNORECASE)
    except re.error:
        rx = re.compile(re.escape(q), re.IGNORECASE)

    hits = []
    pages = BOOK_TEXT.read_text(errors="replace").split("\f")
    for idx, text in enumerate(pages):
        book_page = idx + 1 - BOOK_PAGE_OFFSET
        if not (1 <= book_page <= MAX_BOOK_PAGE):
            continue          # 앞부분 목차 페이지가 검색어를 그대로 담고 있어 잡음이 된다
        m = rx.search(text)
        if not m:
            continue
        flat = " ".join(text.split())
        pos = len(" ".join(text[:m.start()].split()))
        snippet = flat[max(0, pos - 60):pos + 140]
        it = toc().locate(book_page)
        hits.append({
            "page": book_page,
            "section": f"{it['number']} {it['title']}" if it and it["number"] != it["title"]
                       else (it["title"] if it else ""),
            "snippet": snippet,
            "match": m.group(0),
        })
        if len(hits) >= limit:
            break
    return hits


def page_text(book_page: int) -> str:
    """추출 텍스트. 수식이 소실되어 있으므로 보조 수단이다."""
    check_page(book_page)
    pdf_page = to_pdf_page(book_page)
    pages = BOOK_TEXT.read_text(errors="replace").split("\f")
    idx = pdf_page - 1
    return pages[idx] if 0 <= idx < len(pages) else ""


def crop_region(book_page: int, x: int, y: int, w: int, h: int, qid: str) -> Path:
    """영역만 잘라낸 이미지. 수식·회로도를 지목할 때 쓴다. 실측 0.039s."""
    check_page(book_page)
    pdf_page = to_pdf_page(book_page)
    QA.joinpath("crops").mkdir(parents=True, exist_ok=True)
    prefix = QA / "crops" / f"tmp-{qid}"
    subprocess.run(
        ["pdftoppm", "-png", "-r", str(DPI), "-f", str(pdf_page), "-l", str(pdf_page),
         "-x", str(x), "-y", str(y), "-W", str(w), "-H", str(h), str(PDF), str(prefix)],
        check=True, stdin=subprocess.DEVNULL, capture_output=True)
    produced = sorted(QA.joinpath("crops").glob(f"tmp-{qid}-*.png"))
    if not produced:
        raise RuntimeError("pdftoppm produced no crop")
    out = QA / "crops" / f"{qid}.png"
    produced[0].rename(out)
    for leftover in produced[1:]:
        leftover.unlink()
    return out


# ---------------------------------------------------------------- 상태 / 기록

BOOK_SCOPE = "__book__"      # 특정 장에 속하지 않는 '책 전체' 질문


def chapter_key(book_page: int) -> str:
    """이 페이지가 속한 최상위 항목. 대화 세션을 가르는 단위다.

    절(6.1.3)로 가르면 같은 논증을 따라가는 도중에 맥락이 끊긴다.
    후속 질문은 대부분 인접 소절에서 나오므로 장이 맞는 단위다.
    """
    chain = toc().ancestors(book_page)
    return chain[0]["number"] if chain else "front"


def session_for(chapter: str) -> str:
    """장별 세션 ID. 없으면 새로 발급해 저장한다."""
    state = read_state()
    sessions = state.setdefault("sessions", {})
    if chapter not in sessions:
        sessions[chapter] = str(uuid.uuid4())
        write_state(state)
    return sessions[chapter]


def read_state() -> dict:
    p = QA / "state.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"lastBookPage": 1, "sessionId": str(uuid.uuid4()), "updatedAt": now_iso()}


def write_state(state: dict) -> None:
    state["updatedAt"] = now_iso()
    (QA / "state.json").write_text(json.dumps(state, indent=2) + "\n")


def append_history(question: dict, answer: dict) -> None:
    """history.md에 덧붙이기만 한다. 절대 덮어쓰지 않는다 (FR-6)."""
    ts = question.get("createdAt", now_iso()).replace("T", " ").rstrip("Z")
    lines = [f"\n## [{ts}] 책 p.{question['bookPage']}\n",
             f"\n**질문**: {question['question']}\n"]
    if question.get("selectedText"):
        quoted = question["selectedText"].replace("\n", " ")
        lines.append(f"\n**선택한 문장**: > {quoted}\n")
    if question.get("cropPath"):
        lines.append(f"\n**선택한 영역**: `{question['cropPath']}`\n")
    lines.append(f"\n**요약**:\n\n{answer.get('summary', '')}\n")
    if answer.get("detail"):
        lines.append(f"\n<details><summary>심화</summary>\n\n{answer['detail']}\n\n</details>\n")
    src = []
    if answer.get("bookPages"):
        src.append("책 p." + ", p.".join(str(p) for p in answer["bookPages"]))
    for link in answer.get("webLinks") or []:
        src.append(f"[{link.get('title', link.get('url'))}]({link.get('url')})")
    if src:
        lines.append(f"\n**근거**: {' / '.join(src)}\n")
    lines.append("\n---\n")
    with (QA / "history.md").open("a") as f:
        f.write("".join(lines))


def delete_question(qid: str) -> dict:
    """질문을 휴지통으로 옮긴다. 지우지 않는다.

    실수로 지운 것을 되돌릴 수 있어야 한다 — 답변 하나에 몇 분씩 들었다.
    학습 노트(history.md)는 건드리지 않는다. 그쪽은 영구 기록이고,
    가운데를 도려내면 파일이 깨질 위험이 있다.
    """
    if not re.fullmatch(r"[0-9a-zA-Z_-]{1,64}", qid):
        raise ValueError(f"bad question id: {qid}")
    trash = QA / "trash"
    trash.mkdir(parents=True, exist_ok=True)
    moved = []
    for src in ((QA / "questions" / f"{qid}.json"),
                (QA / "answers" / f"{qid}.json"),
                (QA / "crops" / f"{qid}.png")):
        if src.exists():
            dst = trash / f"{src.parent.name}-{src.name}"
            src.replace(dst)
            moved.append(str(dst.relative_to(QA)))
    return {"deleted": qid, "movedTo": moved}


def load_history() -> list:
    """뷰어 재시작 시 복원할 Q&A 목록 (기계용 JSON에서 읽는다)."""
    items = []
    for qf in sorted((QA / "questions").glob("*.json")):
        q = json.loads(qf.read_text())
        af = QA / "answers" / qf.name
        a = json.loads(af.read_text()) if af.exists() else {"status": "pending"}
        items.append({"question": q, "answer": a})
    return items


# ---------------------------------------------------------------- 워커 큐

_work_queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
_current: dict = {"id": None, "mode": None}


def answer_path(qid: str) -> Path:
    return QA / "answers" / f"{qid}.json"


def read_answer(qid: str) -> dict:
    p = answer_path(qid)
    return json.loads(p.read_text()) if p.exists() else {"id": qid, "status": "pending"}


def write_answer(qid: str, patch: dict) -> dict:
    ans = read_answer(qid)
    ans.update(patch)
    ans["id"] = qid
    answer_path(qid).write_text(json.dumps(ans, ensure_ascii=False, indent=2) + "\n")
    return ans


def describe_tool(name: str, inp: dict) -> str | None:
    """워커의 도구 호출을 사람이 읽는 한 줄로 옮긴다 (FR-10).

    지어내지 않는다. 실제로 일어난 일만 옮긴다.
    """
    if name == "Bash":
        cmd = inp.get("command", "")
        m = re.search(r"nc\.sh\s+find\s+['\"]?([^'\"|]+)", cmd)
        if m:
            return f'책에서 "{m.group(1).strip()}" 검색 중'
        m = re.search(r"nc\.sh\s+(?:page|layout)\s+(-?\d+)", cmd)
        if m:
            return f"책 p.{m.group(1)} 텍스트 확인 중"
        return "책 자료 확인 중"

    if name == "Read":
        path = str(inp.get("file_path", ""))
        if path.endswith(".png") and "/crops/" in path:
            return "지목하신 영역 판독 중"
        pages = str(inp.get("pages") or "").split("-")[0].strip()
        if pages.isdigit():
            return f"책 p.{int(pages) - BOOK_PAGE_OFFSET} 원본 페이지 판독 중"
        return f"{Path(path).name} 읽는 중"

    if name in ("WebSearch", "WebFetch"):
        q = inp.get("query") or inp.get("url") or ""
        return f"웹 검색: {str(q)[:60]}" if q else "웹 검색 중"

    if name == "StructuredOutput":
        return "답변 정리 중"
    return None


def run_worker(qid: str, mode: str) -> None:
    """ask.sh를 호출하고 stream-json 을 읽어가며 진행 상황을 기록한다.

    stdin=DEVNULL이 없으면 3초 지연 + stderr 경고가 붙는다 (실측).
    stderr를 stdout에 병합하면 그 경고가 스트림을 오염시킨다 — 반드시 분리한다.
    """
    started = datetime.now(timezone.utc)
    write_answer(qid, {"status": "running", "stage": mode,
                       "startedAt": now_iso(), "progress": []})

    q = json.loads((QA / "questions" / f"{qid}.json").read_text())
    sid = session_for(q.get("chapter") or chapter_key(q["bookPage"]))

    proc = subprocess.Popen(
        [str(TUTOR / "ask.sh"), qid, mode, sid],
        cwd=str(TUTOR),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, bufsize=1,
    )

    payload, progress, seen = None, [], set()
    activity, tokens, last_write = None, 0, 0.0

    def flush_activity(force: bool = False) -> None:
        """진행 문구를 파일에 반영한다. 델타는 초당 수십 번 오므로 2초로 조인다."""
        nonlocal last_write
        now = monotonic()
        if not force and now - last_write < 2.0:
            return
        last_write = now
        write_answer(qid, {"progress": progress, "activity": activity,
                           "activityTokens": tokens})

    for line in proc.stdout:                       # 한 줄이 곧 하나의 이벤트
        line = line.strip()
        if not line:
            continue
        try:
            evt = json.loads(line)
        except json.JSONDecodeError:
            continue                               # 스트림 중간의 비-JSON 줄은 무시
        kind = evt.get("type")

        if kind == "assistant":
            for block in evt.get("message", {}).get("content", []):
                if block.get("type") != "tool_use":
                    continue
                label = describe_tool(block.get("name", ""), block.get("input", {}))
                if label and label not in seen:     # 같은 문구가 연달아 쌓이지 않게
                    seen.add(label)
                    progress.append({"t": now_iso(), "label": label})
                    activity, tokens = None, 0
                    flush_activity(force=True)

        elif kind == "stream_event":
            # 도구를 쓰지 않는 구간(모델이 생각하고 답을 쓰는 시간)이 가장 길다.
            # 여기서 델타를 잡지 않으면 화면이 몇 분씩 얼어붙는다.
            ev = evt.get("event", {})
            if ev.get("type") == "content_block_start":
                bt = ev.get("content_block", {}).get("type")
                activity = {"thinking": "생각 정리 중",
                            "text": "답변 작성 중",
                            "tool_use": "답변 작성 중"}.get(bt, activity)
                tokens = 0
                flush_activity()
            elif ev.get("type") == "content_block_delta":
                est = ev.get("delta", {}).get("estimated_tokens")
                if isinstance(est, int):
                    tokens = max(tokens, est)
                elif activity is None:
                    activity = "답변 작성 중"
                flush_activity()

        elif kind == "result":
            payload = evt.get("result")

    activity, tokens = None, 0
    flush_activity(force=True)

    stderr = proc.stderr.read()
    proc.wait(timeout=60)
    elapsed = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)

    if proc.returncode != 0:
        write_answer(qid, {"status": "error",
                           "error": f"worker exit {proc.returncode}: {stderr[-800:]}"})
        return
    if payload is None:
        write_answer(qid, {"status": "error",
                           "error": f"worker produced no result line. stderr: {stderr[-400:]}"})
        return
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            write_answer(qid, {"status": "error",
                               "error": f"result was not JSON ({exc}): {payload[:400]}"})
            return

    patch = {"error": None}
    if mode == "summary":
        patch.update({"summary": payload.get("summary", ""), "status": "summary_ready",
                      "summaryMs": elapsed})
    else:
        patch.update({"detail": payload.get("detail", ""), "status": "detail_ready",
                      "detailMs": elapsed})
    for key in ("bookPages", "webLinks"):
        if payload.get(key):
            patch[key] = payload[key]
    ans = write_answer(qid, patch)

    if mode == "summary":
        q = json.loads((QA / "questions" / f"{qid}.json").read_text())
        append_history(q, ans)


def _worker_loop() -> None:
    """질문을 순차 처리한다. 같은 --session-id를 공유하므로 병렬 실행은 경합을 만든다."""
    while True:
        qid, mode = _work_queue.get()
        _current.update({"id": qid, "mode": mode})
        try:
            run_worker(qid, mode)
        except Exception as exc:  # 워커 하나의 실패가 큐를 죽이면 안 된다
            write_answer(qid, {"status": "error", "error": f"{type(exc).__name__}: {exc}"})
        finally:
            _current.update({"id": None, "mode": None})
            _work_queue.task_done()


def enqueue(qid: str, mode: str) -> None:
    write_answer(qid, {"status": "pending", "stage": mode})
    _work_queue.put((qid, mode))


def pending_count() -> int:
    return _work_queue.qsize() + (1 if _current["id"] else 0)


def submit_question(req: dict) -> str:
    book_page = int(req["bookPage"])
    check_page(book_page)
    qid = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    q = {
        "id": qid,
        "createdAt": now_iso(),
        "bookPage": book_page,
        "question": (req.get("question") or "").strip(),
        "selectedText": (req.get("selectedText") or "").strip() or None,
        "cropPath": None,
        "scope": "book" if req.get("scope") == "book" else "page",
    }
    # 책 전체 질문은 어느 장에도 묶지 않는다. 대화 세션도 따로 쓴다 —
    # 6장을 읽던 맥락이 "3장과 10장의 관계" 같은 질문에 끼어들면 안 된다.
    q["chapter"] = BOOK_SCOPE if q["scope"] == "book" else chapter_key(book_page)
    region = req.get("region")
    if region:
        box = {k: int(region[k]) for k in ("x", "y", "w", "h")}
        path = crop_region(book_page, box["x"], box["y"], box["w"], box["h"], qid)
        q["cropPath"] = str(path)
        # 좌표도 남긴다. 나중에 이 질문으로 돌아올 때 페이지가 아니라
        # 지목했던 그 자리까지 데려가기 위해서다. 단위는 150dpi 렌더 픽셀.
        q["region"] = box
    (QA / "questions" / f"{qid}.json").write_text(
        json.dumps(q, ensure_ascii=False, indent=2) + "\n")
    enqueue(qid, "summary")
    return qid


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "NCReader/1.0"

    def log_message(self, fmt, *args):  # 조용한 로그 (요청 1줄)
        print(f"  {self.command} {self.path} -> {args[1] if len(args) > 1 else ''}")

    # --- 응답 헬퍼

    def _send(self, code, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode(), "application/json; charset=utf-8")

    def _error(self, exc, code=400):
        self._json({"error": f"{type(exc).__name__}: {exc}"}, code)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    # --- 라우팅

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path.startswith("/api/"):
                return self._get_api(path)
            return self._get_static(path)
        except Exception as exc:
            self._error(exc, 500)

    def _get_api(self, path: str):
        parts = path.strip("/").split("/")          # api / ...
        if parts[1] == "page" and len(parts) == 4:
            book_page = int(parts[2])
            kind = parts[3]
            if kind == "image":
                data = render_page(book_page).read_bytes()
                return self._send(200, data, "image/png")
            if kind == "text":
                return self._send(200, page_text(book_page).encode(),
                                  "text/plain; charset=utf-8")
            if kind == "words":
                return self._json(page_words(book_page))
        if parts[1] == "answer" and len(parts) == 3:
            ans = read_answer(parts[2])
            ans["pending"] = pending_count()
            return self._json(ans)
        if parts[1] == "toc":
            return self._json({"items": toc().items})
        if parts[1] == "search":
            qs = parse_qs(urlparse(self.path).query)
            return self._json({"results": search_book((qs.get("q") or [""])[0])})
        if parts[1] == "history":
            return self._json({"items": load_history(), "pending": pending_count()})
        if parts[1] == "state":
            return self._json(read_state())
        if parts[1] == "crop" and len(parts) == 3:
            p = QA / "crops" / f"{parts[2]}.png"
            if p.exists():
                return self._send(200, p.read_bytes(), "image/png")
        self._json({"error": "not found"}, 404)

    def _get_static(self, path: str):
        rel = "index.html" if path == "/" else path.lstrip("/")
        target = (STATIC / rel).resolve()
        if not str(target).startswith(str(STATIC)) or not target.is_file():
            return self._json({"error": "not found"}, 404)
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        self._send(200, target.read_bytes(), ctype)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            parts = path.strip("/").split("/")
            if path == "/api/ask":
                qid = submit_question(self._body())
                return self._json({"id": qid, "pending": pending_count()})
            if parts[1] == "answer" and len(parts) == 4 and parts[3] == "expand":
                enqueue(parts[2], "detail")
                return self._json({"status": "pending", "pending": pending_count()})
            if parts[1] == "question" and len(parts) == 4 and parts[3] == "delete":
                return self._json(delete_question(parts[2]))
            if parts[1] == "answer" and len(parts) == 4 and parts[3] == "retry":
                ans = read_answer(parts[2])
                enqueue(parts[2], "detail" if ans.get("summary") else "summary")
                return self._json({"status": "pending", "pending": pending_count()})
            if path == "/api/session/reset":
                body = self._body()
                state = read_state()
                sessions = state.setdefault("sessions", {})
                if body.get("all"):
                    state["sessions"] = {}
                else:
                    ch = body.get("chapter") or chapter_key(int(body.get("bookPage", 1)))
                    sessions.pop(ch, None)          # 다음 질문 때 새로 발급된다
                write_state(state)
                return self._json(state)
            self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._error(exc, 500)

    def do_PUT(self):
        try:
            if urlparse(self.path).path == "/api/state":
                state = read_state()
                incoming = self._body()
                if "lastBookPage" in incoming:
                    state["lastBookPage"] = int(incoming["lastBookPage"])
                write_state(state)
                return self._json({"ok": True})
            self._json({"error": "not found"}, 404)
        except Exception as exc:
            self._error(exc, 500)


# ---------------------------------------------------------------- 기동

def preflight() -> None:
    problems = []
    for tool in ("pdftoppm", "pdftotext", "pdfinfo"):
        if not config.find_tool(tool):
            problems.append(
                f"{tool} 을(를) 찾지 못했습니다.\n"
                f"      설치되어 있다면 PATH 문제입니다 — SSH 로 명령을 직접 실행하면\n"
                f"      로그인 셸이 아니라 /opt/homebrew/bin 이 PATH 에 없습니다.\n"
                f"      설치되어 있지 않다면: brew install poppler")
    if not PDF.exists():
        problems.append(f"PDF 없음: {PDF}")
    if not BOOK_TEXT.exists():
        problems.append(f"추출 텍스트 없음: {BOOK_TEXT}")
    if not (TUTOR / "ask.sh").exists():
        problems.append(f"워커 없음: {TUTOR / 'ask.sh'}")
    if problems:
        raise SystemExit("기동 실패:\n  - " + "\n  - ".join(problems))


def main() -> None:
    preflight()
    for d in (QA / "questions", QA / "answers", QA / "crops", CACHE):
        d.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=_worker_loop, daemon=True).start()
    shown = "localhost" if HOST == "127.0.0.1" else HOST
    print(f"book_reader  http://{shown}:{PORT}")
    print(f"  접근    : {HOST_NOTE}")
    print(f"  PDF    : {PDF.name}")
    print(f"  워커   : {TUTOR}")
    print(f"  세션   : {read_state()['sessionId']}")
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()

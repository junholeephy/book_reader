"""목차 색인. FR-11(검색) · FR-12(네비게이션) · FR-13(질문 앵커링)이 함께 쓴다.

`refs/toc-raw.txt` (pdftotext -layout 으로 뽑은 목차)를 파싱해
"책 페이지 -> 어느 절인가" 를 답할 수 있게 만든다.

파싱에서 걸리는 두 가지 (실측으로 확인):
  1. 제목이 다음 줄로 넘어간다 — "5.4 General applications of the quantum Fourier"
     다음 줄에 "transform    234". 페이지 번호가 나올 때까지 이어붙여야 한다.
  2. 부록은 번호 체계가 다르다 — "Appendix 2: Group theory  610", "A2.1.1 Generators  611".
     처리하지 않으면 p.593 이후 모든 페이지가 12.6.5 로 잘못 매핑된다.
"""
import re
from bisect import bisect_right
from pathlib import Path

# "6.1.3" / "A2.1.1" / "Appendix 2:"
_NUMBERED = re.compile(r"^\s*(\d+(?:\.\d+)*)\s+(\S.*?)\s*$")
_APPENDIX_SUB = re.compile(r"^\s*(A\d+(?:\.\d+)*)\s+(\S.*?)\s*$")
_APPENDIX = re.compile(r"^\s*Appendix\s+(\d+)\s*:\s*(\S.*?)\s*$")
# 번호 없는 최상위 항목 — 이것이 없으면 p.649 이후가 마지막 부록으로 잘못 매핑된다
_UNNUMBERED = re.compile(r"^\s*(Bibliography|Index)\s{2,}(\d{1,3})\s*$")
# 제목과 페이지 번호는 공백 2칸 이상으로 갈린다
_WITH_PAGE = re.compile(r"^(.*?)\s{2,}(\d{1,3})\s*$")


def _depth(number: str) -> int:
    """장=1, 절=2, 소절=3. 부록은 장과 같은 층으로 본다."""
    if number.startswith("Appendix") or number in ("Bibliography", "Index"):
        return 1
    return number.lstrip("A").count(".") + 1


def parse_toc(raw: str) -> list[dict]:
    """[{number, title, page, depth}, ...] — 페이지 오름차순."""
    items: list[dict] = []
    pending: list[str] | None = None

    for line in raw.splitlines():
        if not line.strip():
            continue
        un = _UNNUMBERED.match(line)
        if un:
            items.append({"number": un.group(1), "title": un.group(1),
                          "page": int(un.group(2)), "depth": 1})
            pending = None
            continue
        for pattern, fmt in ((_APPENDIX, "Appendix {}"),
                             (_APPENDIX_SUB, "{}"),
                             (_NUMBERED, "{}")):
            m = pattern.match(line)
            if m:
                pending = [fmt.format(m.group(1)), m.group(2)]
                break
        else:
            if pending:                      # 넘어간 제목 이어붙이기
                pending[1] += " " + line.strip()

        if pending:
            pm = _WITH_PAGE.match(pending[1])
            if pm:
                number, title = pending[0], pm.group(1).strip()
                items.append({"number": number, "title": title,
                              "page": int(pm.group(2)), "depth": _depth(number)})
                pending = None

    items.sort(key=lambda it: it["page"])
    return items


class Toc:
    def __init__(self, raw: str):
        self.items = parse_toc(raw)
        self._pages = [it["page"] for it in self.items]

    @classmethod
    def load(cls, path: Path) -> "Toc":
        return cls(path.read_text(errors="replace"))

    def locate(self, book_page: int) -> dict | None:
        """이 페이지가 속한 가장 깊은 항목."""
        i = bisect_right(self._pages, book_page) - 1
        return self.items[i] if i >= 0 else None

    def ancestors(self, book_page: int) -> list[dict]:
        """장 -> 절 -> 소절 순서의 조상 사슬. 렌즈 선택지가 여기서 나온다.

        목차는 페이지 순이므로, 현재 항목에서 거슬러 올라가며
        더 얕은 깊이가 처음 나오는 것들을 모으면 된다.
        """
        i = bisect_right(self._pages, book_page) - 1
        if i < 0:
            return []
        chain = [self.items[i]]
        want = self.items[i]["depth"] - 1
        for j in range(i - 1, -1, -1):
            if want <= 0:
                break
            if self.items[j]["depth"] == want:
                chain.append(self.items[j])
                want -= 1
        return list(reversed(chain))

    def page_range(self, number: str) -> tuple[int, int] | None:
        """해당 절이 차지하는 책 페이지 범위 [시작, 끝].

        끝은 '같거나 더 얕은 깊이의 다음 항목' 직전까지다.
        하위 소절을 포함하려면 이렇게 해야 한다 (6.1 은 6.1.1~6.1.4 를 품는다).
        """
        for i, it in enumerate(self.items):
            if it["number"] != number:
                continue
            start = it["page"]
            for nxt in self.items[i + 1:]:
                if nxt["depth"] <= it["depth"]:
                    return (start, nxt["page"] - 1)
            return (start, 10_000)          # 마지막 항목
        return None

    def label(self, book_page: int) -> str:
        """`6.1.3 Geometric visualization` 형태. 없으면 페이지 표기."""
        it = self.locate(book_page)
        if not it:
            return f"p.{book_page}"
        if it["number"] == it["title"]:      # Bibliography / Index — 번호가 곧 제목
            return it["title"]
        return f"{it['number']} {it['title']}"

"""server.py 단위 테스트. 표준 라이브러리 unittest만 사용한다 (NFR-1).

실행: python -m unittest discover -s reader -v
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server  # noqa: E402


class TestPageMapping(unittest.TestCase):
    """오프셋은 실제 지면으로 검증된 값이다. 여기가 틀리면 모든 인용이 어긋난다."""

    def test_known_anchors(self):
        # 책 p.6 헤더 = PDF p.40, 책 p.166 = PDF p.200, 책 p.252 = PDF p.286 (육안 확인)
        self.assertEqual(server.to_pdf_page(6), 40)
        self.assertEqual(server.to_pdf_page(166), 200)
        self.assertEqual(server.to_pdf_page(252), 286)

    def test_offset_is_constant(self):
        for book in (-33, 1, 100, 676):
            self.assertEqual(server.to_pdf_page(book) - book, server.BOOK_PAGE_OFFSET)

    def test_range_bounds(self):
        self.assertEqual(server.to_pdf_page(server.MAX_BOOK_PAGE), server.PDF_PAGE_COUNT)
        self.assertEqual(server.to_pdf_page(server.MIN_BOOK_PAGE), 1)

    def test_out_of_range_rejected(self):
        with self.assertRaises(ValueError):
            server.check_page(server.MAX_BOOK_PAGE + 1)
        with self.assertRaises(ValueError):
            server.check_page(server.MIN_BOOK_PAGE - 1)

    def test_in_range_accepted(self):
        server.check_page(1)
        server.check_page(server.MAX_BOOK_PAGE)


# 실제 pdftotext -bbox 출력을 본떴다. 수식 글리프는 '비어 있는' 것이 아니라
# XML 1.0이 금지하는 제어문자(\x04 등)를 담고 있다 — 책 p.252에서 실측.
# 그대로 ET.fromstring에 넣으면 "not well-formed (invalid token)"으로 문서 전체가 깨진다.
BBOX_XML = """<?xml version="1.0"?>
<html xmlns="http://www.w3.org/1999/xhtml"><body><doc>
  <page width="637.2" height="843.8">
    <word xMin="10.0" yMin="20.0" xMax="40.0" yMax="30.0">Grover</word>
    <word xMin="50.0" yMin="20.0" xMax="55.0" yMax="34.0">\x04</word>
    <word xMin="60.0" yMin="20.0" xMax="90.0" yMax="30.0">iteration</word>
    <word xMin="95.0" yMin="20.0" xMax="99.0" yMax="30.0">   </word>
    <word xMin="99.0" yMin="20.0" xMax="103.0" yMax="30.0">\x01\x1f</word>
  </page>
</doc></body></html>
"""


class TestBboxParsing(unittest.TestCase):
    """수식 글리프는 제어문자로 나온다. 걸러내지 않으면 XML 파싱이 통째로 실패한다."""

    def test_control_characters_do_not_break_parsing(self):
        """회귀 테스트: 이 문자를 걸러내지 않아 /api/page/252/words 가 500으로 죽었다."""
        self.assertIn("\x04", BBOX_XML, "픽스처가 실제 상황을 재현해야 한다")
        got = self._parse()   # 예외가 나면 실패
        self.assertTrue(got["words"])

    def _parse(self):
        fake = mock.Mock(stdout=BBOX_XML)
        with mock.patch.object(server.subprocess, "run", return_value=fake):
            with tempfile.TemporaryDirectory() as tmp:
                with mock.patch.object(server, "CACHE", Path(tmp)):
                    return server.page_words(252)

    def test_page_size_from_bbox_output(self):
        # pdfinfo가 아니라 -bbox 출력의 값을 써야 한다 (서로 다를 수 있음)
        got = self._parse()
        self.assertAlmostEqual(got["pageWidth"], 637.2)
        self.assertAlmostEqual(got["pageHeight"], 843.8)

    def test_empty_and_blank_words_dropped(self):
        words = self._parse()["words"]
        self.assertEqual([w["t"] for w in words], ["Grover", "iteration"])

    def test_width_height_derived(self):
        w = self._parse()["words"][0]
        self.assertAlmostEqual(w["w"], 30.0)
        self.assertAlmostEqual(w["h"], 10.0)

    def test_result_is_cached(self):
        fake = mock.Mock(stdout=BBOX_XML)
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(server, "CACHE", Path(tmp)):
                with mock.patch.object(server.subprocess, "run", return_value=fake) as run:
                    server.page_words(252)
                    server.page_words(252)
                    self.assertEqual(run.call_count, 1, "두 번째 호출은 캐시를 써야 한다")


class TestHistoryAppend(unittest.TestCase):
    """history.md는 절대 덮어쓰지 않는다 (FR-6). audit.md 사고와 같은 실수를 막는다."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.qa = Path(self.tmp.name)
        (self.qa / "history.md").write_text("# 기존 노트\n\n지워지면 안 되는 내용\n")
        self.patch = mock.patch.object(server, "QA", self.qa)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.tmp.cleanup()

    def _write(self, question_text, summary):
        server.append_history(
            {"bookPage": 252, "question": question_text, "createdAt": "2026-08-26T10:00:00Z",
             "selectedText": "rotation", "cropPath": None},
            {"summary": summary, "bookPages": [252], "webLinks": []})

    def test_preserves_existing_content(self):
        self._write("Q1", "A1")
        text = (self.qa / "history.md").read_text()
        self.assertIn("지워지면 안 되는 내용", text)
        self.assertIn("Q1", text)

    def test_accumulates_across_calls(self):
        self._write("Q1", "A1")
        self._write("Q2", "A2")
        text = (self.qa / "history.md").read_text()
        for token in ("지워지면 안 되는 내용", "Q1", "Q2"):
            self.assertIn(token, text)
        self.assertLess(text.index("Q1"), text.index("Q2"), "시간순으로 쌓여야 한다")

    def test_records_page_and_selection(self):
        self._write("Q1", "A1")
        text = (self.qa / "history.md").read_text()
        self.assertIn("책 p.252", text)
        self.assertIn("rotation", text)


class TestDescribeTool(unittest.TestCase):
    """진행 표시 문구 (FR-10).

    이 함수는 PDF 페이지를 책 페이지로 되돌린다 — 오프셋 변환이 일어나는 두 번째 지점이다.
    첫 번째(to_pdf_page)는 이미 고정해 두었으므로 여기도 같은 기준점으로 묶는다.
    입력은 전부 실제 스트림에서 관측된 모양을 쓴다.
    """

    PDF = str(server.PDF)      # 설정에서 온다

    # --- Read: 페이지 이미지 판독 (오프셋 역변환)

    def test_read_pages_converts_back_to_book_page(self):
        for pdf_page, book_page in ((40, 6), (200, 166), (286, 252)):
            with self.subTest(pdf_page=pdf_page):
                got = server.describe_tool("Read", {"file_path": self.PDF, "pages": str(pdf_page)})
                self.assertEqual(got, f"책 p.{book_page} 원본 페이지 판독 중")

    def test_read_pages_roundtrips_with_to_pdf_page(self):
        """to_pdf_page 와 정확히 역관계여야 한다. 한쪽만 바뀌면 인용이 어긋난다."""
        for book_page in (-33, 1, 6, 166, 252, 676):
            label = server.describe_tool(
                "Read", {"file_path": self.PDF, "pages": server.to_pdf_page(book_page)})
            self.assertEqual(label, f"책 p.{book_page} 원본 페이지 판독 중")

    def test_read_pages_accepts_int(self):
        # 스트림에서 pages 가 정수로 오는 경우가 있다
        self.assertEqual(server.describe_tool("Read", {"file_path": self.PDF, "pages": 286}),
                         "책 p.252 원본 페이지 판독 중")

    def test_read_page_range_uses_first_page(self):
        self.assertEqual(server.describe_tool("Read", {"file_path": self.PDF, "pages": "286-288"}),
                         "책 p.252 원본 페이지 판독 중")

    def test_read_crop_image(self):
        got = server.describe_tool(
            "Read", {"file_path": "/tmp/proj/qa/crops/20260826-1.png"})
        self.assertEqual(got, "지목하신 영역 판독 중")

    def test_read_without_pages_falls_back_to_filename(self):
        got = server.describe_tool("Read", {"file_path": "/tmp/notes.txt"})
        self.assertEqual(got, "notes.txt 읽는 중")

    # --- Bash: nc.sh 호출

    def test_bash_find_quoted_stops_at_pipe(self):
        # 실제 관측된 형태: nc.sh find 'X' | head -3
        got = server.describe_tool("Bash", {
            "command": "/some/where/refs/nc.sh find 'Grover iteration' | head -3"})
        self.assertEqual(got, '책에서 "Grover iteration" 검색 중')

    def test_bash_find_unquoted(self):
        got = server.describe_tool("Bash", {"command": "refs/nc.sh find Schmidt | head -5"})
        self.assertEqual(got, '책에서 "Schmidt" 검색 중')

    def test_bash_page_and_layout(self):
        self.assertEqual(server.describe_tool("Bash", {"command": "refs/nc.sh page 252"}),
                         "책 p.252 텍스트 확인 중")
        self.assertEqual(server.describe_tool("Bash", {"command": "refs/nc.sh layout 252 254"}),
                         "책 p.252 텍스트 확인 중")

    def test_bash_negative_page(self):
        # 서문 영역은 책 페이지가 음수다
        self.assertEqual(server.describe_tool("Bash", {"command": "refs/nc.sh page -10"}),
                         "책 p.-10 텍스트 확인 중")

    def test_bash_other_command_is_generic(self):
        self.assertEqual(server.describe_tool("Bash", {"command": "ls -la"}), "책 자료 확인 중")

    # --- 웹 / 기타

    def test_web_search_with_query(self):
        self.assertEqual(server.describe_tool("WebSearch", {"query": "surface code threshold"}),
                         "웹 검색: surface code threshold")

    def test_web_search_truncates_long_query(self):
        got = server.describe_tool("WebSearch", {"query": "가" * 200})
        self.assertEqual(got, "웹 검색: " + "가" * 60)

    def test_web_fetch_uses_url(self):
        self.assertEqual(server.describe_tool("WebFetch", {"url": "https://example.com/x"}),
                         "웹 검색: https://example.com/x")

    def test_web_search_without_query(self):
        self.assertEqual(server.describe_tool("WebSearch", {}), "웹 검색 중")

    def test_structured_output(self):
        self.assertEqual(server.describe_tool("StructuredOutput", {}), "답변 정리 중")

    def test_unknown_tool_returns_none(self):
        """None 이어야 진행 목록에 쌓이지 않는다. 빈 문자열을 돌려주면 빈 줄이 생긴다."""
        self.assertIsNone(server.describe_tool("Edit", {"file_path": "/tmp/x"}))
        self.assertIsNone(server.describe_tool("", {}))

    def test_never_leaks_absolute_paths_for_known_tools(self):
        """화면에 내부 경로가 그대로 뜨면 안 된다."""
        for name, inp in (("Read", {"file_path": self.PDF, "pages": "286"}),
                          ("Read", {"file_path": "/some/where/qa/crops/a.png"}),
                          ("Bash", {"command": "/some/where/refs/nc.sh find 'x'"})):
            with self.subTest(name=name):
                self.assertNotIn("/some/where", server.describe_tool(name, inp))


class TestSearchBook(unittest.TestCase):
    """본문 검색 (FR-11). 실제 추출 텍스트를 그대로 쓴다."""

    def test_finds_known_section(self):
        hits = server.search_book("Schmidt decomposition")
        pages = [h["page"] for h in hits]
        self.assertIn(109, pages, "2.5 Schmidt decomposition 시작 지면이 잡혀야 한다")
        hit = next(h for h in hits if h["page"] == 109)
        self.assertIn("2.5", hit["section"])

    def test_results_carry_section_label(self):
        for h in server.search_book("Grover"):
            self.assertIsInstance(h["section"], str)

    def test_excludes_front_matter(self):
        """앞부분 목차 페이지가 검색어를 그대로 담고 있어 잡음이 된다."""
        for h in server.search_book("Schmidt decomposition"):
            self.assertGreaterEqual(h["page"], 1)

    def test_short_query_returns_nothing(self):
        self.assertEqual(server.search_book("a"), [])
        self.assertEqual(server.search_book("  "), [])

    def test_case_insensitive(self):
        self.assertTrue(server.search_book("GROVER ITERATION"))

    def test_invalid_regex_falls_back_to_literal(self):
        """사용자가 '(' 를 치면 정규식으로는 깨진다. 죽지 말고 문자 그대로 찾아야 한다."""
        try:
            server.search_book("f(x)")
        except Exception as exc:
            self.fail(f"raised {exc}")

    def test_respects_limit(self):
        self.assertLessEqual(len(server.search_book("the", limit=5)), 5)


class TestChapterSessions(unittest.TestCase):
    """장별 대화 세션 (2026-08-26 추가).

    절로 가르면 같은 논증 도중에 맥락이 끊긴다. 장이 맞는 단위다.
    """

    def test_chapter_key_from_page(self):
        self.assertEqual(server.chapter_key(252), "6")
        self.assertEqual(server.chapter_key(248), "6")
        self.assertEqual(server.chapter_key(500), "11")
        self.assertEqual(server.chapter_key(109), "2")

    def test_whole_chapter_shares_one_key(self):
        """6.1.1 과 6.7 은 같은 세션이어야 한다 — 후속 질문이 통해야 하므로."""
        keys = {server.chapter_key(p) for p in range(248, 277)}
        self.assertEqual(keys, {"6"})

    def test_different_chapters_differ(self):
        self.assertNotEqual(server.chapter_key(252), server.chapter_key(500))

    def test_appendix_is_its_own_chapter(self):
        self.assertTrue(server.chapter_key(611).startswith("Appendix"))

    def _tmp_state(self, tmp):
        (Path(tmp) / "state.json").write_text(json.dumps({"lastBookPage": 1}))
        return mock.patch.object(server, "QA", Path(tmp))

    def test_session_is_stable_per_chapter(self):
        with tempfile.TemporaryDirectory() as tmp, self._tmp_state(tmp):
            a1 = server.session_for("6")
            a2 = server.session_for("6")
            b1 = server.session_for("10")
            self.assertEqual(a1, a2, "같은 장은 같은 세션을 이어써야 한다")
            self.assertNotEqual(a1, b1, "다른 장은 갈라져야 한다")

    def test_session_persists_to_state(self):
        with tempfile.TemporaryDirectory() as tmp, self._tmp_state(tmp):
            sid = server.session_for("6")
            saved = json.loads((Path(tmp) / "state.json").read_text())
            self.assertEqual(saved["sessions"]["6"], sid)

    def test_question_records_its_chapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            qa = Path(tmp)
            (qa / "questions").mkdir(); (qa / "answers").mkdir()
            with mock.patch.object(server, "QA", qa), mock.patch.object(server, "enqueue"):
                qid = server.submit_question({"bookPage": 252, "question": "?"})
            saved = json.loads((qa / "questions" / f"{qid}.json").read_text())
        self.assertEqual(saved["chapter"], "6")


class TestQuestionIds(unittest.TestCase):
    def test_ids_are_unique_within_same_second(self):
        with tempfile.TemporaryDirectory() as tmp:
            qa = Path(tmp)
            (qa / "questions").mkdir()
            (qa / "answers").mkdir()
            (qa / "state.json").write_text(json.dumps({"lastBookPage": 1, "sessionId": "x"}))
            with mock.patch.object(server, "QA", qa), \
                 mock.patch.object(server, "enqueue"):
                ids = {server.submit_question({"bookPage": 252, "question": f"q{i}"})
                       for i in range(30)}
        self.assertEqual(len(ids), 30)

    def test_question_file_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            qa = Path(tmp)
            (qa / "questions").mkdir()
            (qa / "answers").mkdir()
            with mock.patch.object(server, "QA", qa), mock.patch.object(server, "enqueue"):
                qid = server.submit_question({"bookPage": 252, "question": "왜?"})
            saved = json.loads((qa / "questions" / f"{qid}.json").read_text())
        self.assertEqual(saved["bookPage"], 252)
        self.assertEqual(saved["question"], "왜?")
        self.assertIsNone(saved["cropPath"])


if __name__ == "__main__":
    unittest.main(verbosity=2)

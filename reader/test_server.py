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


class TestPartialJson(unittest.TestCase):
    """StructuredOutput 의 인자는 조금씩 흘러온다. 완성될 때까지 기다리지 않고
    지금까지 온 만큼 보여주기 위해 부분 JSON 에서 값을 꺼낸다."""

    FULL = {"summary": '수식 $|\\beta\\rangle$ 은 얽힘이다.\n두 번째 "줄"',
            "bookPages": [95]}

    def _text(self):
        return json.dumps(self.FULL, ensure_ascii=False)

    def test_any_cut_is_a_prefix_of_the_final_value(self):
        """어디서 잘려도 최종 값의 접두사여야 한다. 화면에 헛것이 뜨면 안 된다."""
        text = self._text()
        for cut in range(1, len(text) + 1):
            got = server.partial_string_field(text[:cut], "summary")
            self.assertTrue(self.FULL["summary"].startswith(got),
                            f"{cut}자에서 어긋남: {got!r}")

    def test_complete_json_matches_exactly(self):
        self.assertEqual(server.partial_string_field(self._text(), "summary"),
                         self.FULL["summary"])

    def test_missing_field(self):
        self.assertEqual(server.partial_string_field(self._text(), "detail"), "")
        self.assertEqual(server.partial_string_field('{"boo', "summary"), "")

    def test_truncated_escape_does_not_leak(self):
        """이스케이프가 반만 왔을 때 깨진 문자를 내보내면 안 된다."""
        self.assertEqual(server.partial_string_field('{"summary": "ab\\', "summary"), "ab")
        self.assertEqual(server.partial_string_field('{"summary": "ab\\u00', "summary"), "ab")

    def test_unicode_escape(self):
        self.assertEqual(server.partial_string_field('{"summary": "\\uac00\\uac01"', "summary"),
                         "가각")

    def test_does_not_run_past_the_closing_quote(self):
        got = server.partial_string_field('{"summary": "끝", "detail": "다른값"}', "summary")
        self.assertEqual(got, "끝")


class TestOrphanReaping(unittest.TestCase):
    """서버가 재시작되면 워커도 죽는데 answers/*.json 은 'running' 으로 남는다.
    화면에는 '33분째 조사 중' 으로 보이지만 실제로는 아무것도 돌지 않는다."""

    def _qa(self, tmp):
        qa = Path(tmp)
        (qa / "questions").mkdir(); (qa / "answers").mkdir()
        return qa

    def _pair(self, qa, qid, status):
        (qa / "questions" / f"{qid}.json").write_text(json.dumps({"id": qid, "bookPage": 1}))
        (qa / "answers" / f"{qid}.json").write_text(json.dumps(
            {"id": qid, "status": status, "activity": "생각 정리 중", "startedAt": "2026-01-01T00:00:00Z"}))

    def test_running_becomes_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            qa = self._qa(tmp)
            self._pair(qa, "a", "running")
            self._pair(qa, "b", "pending")
            with mock.patch.object(server, "QA", qa):
                self.assertEqual(server.reap_orphans(), 2)
            for qid in ("a", "b"):
                d = json.loads((qa / "answers" / f"{qid}.json").read_text())
                self.assertEqual(d["status"], "error")
                self.assertIn("다시 시작", d["error"])
                self.assertIsNone(d["activity"], "진행 표시도 지워야 한다")

    def test_finished_answers_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            qa = self._qa(tmp)
            self._pair(qa, "done", "summary_ready")
            with mock.patch.object(server, "QA", qa):
                self.assertEqual(server.reap_orphans(), 0)
            self.assertEqual(json.loads((qa / "answers" / "done.json").read_text())["status"],
                             "summary_ready")

    def test_answer_without_question_is_removed(self):
        """질문을 지운 뒤 워커가 답을 마치면 짝 없는 파일이 남는다."""
        with tempfile.TemporaryDirectory() as tmp:
            qa = self._qa(tmp)
            (qa / "answers" / "ghost.json").write_text('{"id":"ghost","status":"summary_ready"}')
            with mock.patch.object(server, "QA", qa):
                server.reap_orphans()
            self.assertFalse((qa / "answers" / "ghost.json").exists())

    def test_corrupt_answer_does_not_stop_reaping(self):
        with tempfile.TemporaryDirectory() as tmp:
            qa = self._qa(tmp)
            (qa / "questions" / "bad.json").write_text("{}")
            (qa / "answers" / "bad.json").write_text("{ not json")
            self._pair(qa, "good", "running")
            with mock.patch.object(server, "QA", qa):
                self.assertEqual(server.reap_orphans(), 1)


class TestHostBinding(unittest.TestCase):
    """이 도구는 이 컴퓨터에서도, 다른 기기에서도 쓴다.
    tailscale 을 골라도 로컬 접속을 막으면 안 된다."""

    def setUp(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import config
        self.config = config

    def test_default_is_local_only(self):
        hosts, _ = self.config.resolve_hosts("127.0.0.1")
        self.assertEqual(hosts, ["127.0.0.1"])

    def test_tailscale_keeps_localhost(self):
        """회귀 방지: 예전에는 tailnet 주소에만 묶여 맥에서 localhost 로 못 들어갔다."""
        with mock.patch.object(self.config, "_tailscale_ip", return_value="100.85.159.32"):
            hosts, note = self.config.resolve_hosts("tailscale")
        self.assertIn("127.0.0.1", hosts)
        self.assertIn("100.85.159.32", hosts)
        self.assertIn("이 컴퓨터", note)

    def test_tailscale_unavailable_still_starts_locally(self):
        """Tailscale 이 꺼져 있다고 서버를 못 띄울 이유는 없다."""
        with mock.patch.object(self.config, "_tailscale_ip", return_value=""):
            hosts, note = self.config.resolve_hosts("tailscale")
        self.assertEqual(hosts, ["127.0.0.1"])
        self.assertIn("Tailscale", note)

    def test_explicit_address_keeps_localhost(self):
        hosts, _ = self.config.resolve_hosts("192.168.0.9")
        self.assertEqual(hosts, ["127.0.0.1", "192.168.0.9"])

    def test_wildcard_warns_and_does_not_duplicate(self):
        hosts, note = self.config.resolve_hosts("0.0.0.0")
        self.assertEqual(hosts, ["0.0.0.0"])
        self.assertIn("인증이 없어", note)


class TestDeleteAndBookScope(unittest.TestCase):
    """삭제(휴지통)와 책 전체 질문 (FR-14)."""

    def _qa(self, tmp):
        qa = Path(tmp)
        for d in ("questions", "answers", "crops"):
            (qa / d).mkdir()
        return qa

    def test_delete_moves_to_trash_not_gone(self):
        """지우는 게 아니라 옮긴다. 답변 하나에 몇 분씩 걸린다."""
        with tempfile.TemporaryDirectory() as tmp:
            qa = self._qa(tmp)
            (qa / "questions" / "q1.json").write_text("{}")
            (qa / "answers" / "q1.json").write_text("{}")
            (qa / "crops" / "q1.png").write_bytes(b"x")
            with mock.patch.object(server, "QA", qa):
                res = server.delete_question("q1")
            self.assertEqual(len(res["movedTo"]), 3)
            for d in ("questions", "answers", "crops"):
                self.assertFalse((qa / d / "q1.json").exists() and d != "crops")
            self.assertEqual(len(list((qa / "trash").iterdir())), 3)

    def test_delete_is_reversible(self):
        with tempfile.TemporaryDirectory() as tmp:
            qa = self._qa(tmp)
            (qa / "questions" / "q1.json").write_text('{"id":"q1"}')
            with mock.patch.object(server, "QA", qa):
                server.delete_question("q1")
                moved = next((qa / "trash").iterdir())
                moved.replace(qa / "questions" / "q1.json")
            self.assertTrue((qa / "questions" / "q1.json").exists())

    def test_delete_rejects_bad_id(self):
        """경로 조작을 막는다."""
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(server, "QA", Path(tmp)):
                for bad in ("../secret", "a/b", "x" * 100, ""):
                    with self.subTest(bad=bad), self.assertRaises(ValueError):
                        server.delete_question(bad)

    def test_delete_missing_is_harmless(self):
        with tempfile.TemporaryDirectory() as tmp:
            qa = self._qa(tmp)
            with mock.patch.object(server, "QA", qa):
                self.assertEqual(server.delete_question("nope")["movedTo"], [])

    def test_region_coordinates_are_stored(self):
        """좌표를 남겨야 나중에 지목했던 자리로 돌아갈 수 있다."""
        with tempfile.TemporaryDirectory() as tmp:
            qa = self._qa(tmp)
            with mock.patch.object(server, "QA", qa), \
                 mock.patch.object(server, "enqueue"), \
                 mock.patch.object(server, "crop_region",
                                   return_value=Path(tmp, "crops", "x.png")):
                qid = server.submit_question({
                    "bookPage": 252, "question": "?",
                    "region": {"x": 250, "y": 1050, "w": 800, "h": 130}})
            q = json.loads((qa / "questions" / f"{qid}.json").read_text())
        self.assertEqual(q["region"], {"x": 250, "y": 1050, "w": 800, "h": 130})

    def test_no_region_key_when_not_selected(self):
        with tempfile.TemporaryDirectory() as tmp:
            qa = self._qa(tmp)
            with mock.patch.object(server, "QA", qa), mock.patch.object(server, "enqueue"):
                qid = server.submit_question({"bookPage": 252, "question": "?"})
            q = json.loads((qa / "questions" / f"{qid}.json").read_text())
        self.assertIsNone(q.get("region"))

    def test_book_scope_gets_its_own_chapter_key(self):
        """책 전체 질문이 서 있던 장에 묶이면 안 된다."""
        with tempfile.TemporaryDirectory() as tmp:
            qa = self._qa(tmp)
            with mock.patch.object(server, "QA", qa), mock.patch.object(server, "enqueue"):
                bid = server.submit_question({"bookPage": 252, "question": "?", "scope": "book"})
                pid = server.submit_question({"bookPage": 252, "question": "?"})
            b = json.loads((qa / "questions" / f"{bid}.json").read_text())
            n = json.loads((qa / "questions" / f"{pid}.json").read_text())
        self.assertEqual(b["scope"], "book")
        self.assertEqual(b["chapter"], server.BOOK_SCOPE)
        self.assertEqual(n["scope"], "page")
        self.assertEqual(n["chapter"], "6")
        self.assertNotEqual(b["chapter"], n["chapter"])

    def test_book_scope_session_is_separate(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / "state.json").write_text(json.dumps({"lastBookPage": 1}))
            with mock.patch.object(server, "QA", Path(tmp)):
                self.assertNotEqual(server.session_for(server.BOOK_SCOPE),
                                    server.session_for("6"))


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

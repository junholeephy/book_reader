"""목차 색인 테스트. 질문 앵커링(FR-13)의 정확도가 여기에 달려 있다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from toc import Toc, parse_toc  # noqa: E402

REAL = Toc.load(Path(__file__).resolve().parent.parent / "refs" / "toc-raw.txt")


class TestParsing(unittest.TestCase):
    def test_wrapped_title_is_joined(self):
        """실제 목차에 있는 형태 — 제목이 다음 줄로 넘어가고 거기에 페이지가 붙는다."""
        items = parse_toc("   5.4 General applications of the quantum Fourier\n"
                          "             transform                              234\n")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["number"], "5.4")
        self.assertEqual(items[0]["page"], 234)
        self.assertIn("transform", items[0]["title"])

    def test_appendix_forms(self):
        items = parse_toc("   Appendix 2: Group theory        610\n"
                          "    A2.1 Basic definitions          610\n"
                          "         A2.1.1 Generators          611\n")
        self.assertEqual([i["number"] for i in items], ["Appendix 2", "A2.1", "A2.1.1"])
        self.assertEqual([i["depth"] for i in items], [1, 2, 3])

    def test_unnumbered_top_level(self):
        items = parse_toc("Bibliography      649\nIndex      665\n")
        self.assertEqual([i["number"] for i in items], ["Bibliography", "Index"])
        self.assertTrue(all(i["depth"] == 1 for i in items))


class TestRealToc(unittest.TestCase):
    def test_all_twelve_chapters_present(self):
        chapters = {i["number"] for i in REAL.items if i["depth"] == 1}
        for n in range(1, 13):
            self.assertIn(str(n), chapters)

    def test_appendices_and_backmatter_present(self):
        top = {i["number"] for i in REAL.items if i["depth"] == 1}
        for n in range(1, 7):
            self.assertIn(f"Appendix {n}", top)
        self.assertIn("Bibliography", top)
        self.assertIn("Index", top)

    def test_pages_are_monotonic(self):
        pages = [i["page"] for i in REAL.items]
        self.assertEqual(pages, sorted(pages))

    def test_known_anchors(self):
        """육안으로 확인한 지면. 여기가 틀리면 질문이 엉뚱한 절에 묶인다."""
        self.assertEqual(REAL.label(252), "6.1.3 Geometric visualization")
        self.assertEqual(REAL.label(248), "6.1.1 The oracle")
        self.assertEqual(REAL.label(500), "11.1 Shannon entropy")

    def test_backmatter_not_swallowed_by_last_appendix(self):
        """p.649 이후가 마지막 부록으로 잘못 매핑되던 버그의 회귀 방지."""
        self.assertEqual(REAL.label(650), "Bibliography")
        self.assertEqual(REAL.label(670), "Index")

    def test_ancestors_form_a_chain(self):
        chain = REAL.ancestors(252)
        self.assertEqual([a["number"] for a in chain], ["6", "6.1", "6.1.3"])
        self.assertEqual([a["depth"] for a in chain], [1, 2, 3])

    def test_ancestors_depth_increases_monotonically(self):
        for page in (1, 100, 252, 400, 611, 650):
            depths = [a["depth"] for a in REAL.ancestors(page)]
            self.assertEqual(depths, sorted(set(depths)), f"page {page}: {depths}")

    def test_section_range_includes_its_subsections(self):
        """6.1 은 6.1.1~6.1.4 를 품어야 한다. 렌즈를 '이 절'로 넓혔을 때의 근거."""
        start, end = REAL.page_range("6.1")
        self.assertEqual(start, 248)
        self.assertGreaterEqual(end, 254)
        for sub in ("6.1.1", "6.1.2", "6.1.3", "6.1.4"):
            p = next(i["page"] for i in REAL.items if i["number"] == sub)
            self.assertTrue(start <= p <= end, f"{sub}(p.{p}) not in {start}-{end}")

    def test_chapter_range_covers_all_its_sections(self):
        start, end = REAL.page_range("6")
        for it in REAL.items:
            if it["number"].startswith("6.") and it["number"][1] == ".":
                self.assertTrue(start <= it["page"] <= end, it["number"])

    def test_every_content_page_resolves(self):
        for page in range(1, 677):
            self.assertIsNotNone(REAL.locate(page), f"page {page} unresolved")

    def test_page_before_book_start_returns_none(self):
        self.assertIsNone(REAL.locate(-20))


if __name__ == "__main__":
    unittest.main(verbosity=2)

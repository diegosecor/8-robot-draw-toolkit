"""Unit tests for the text cleaning and passage splitting in mcp_server/ingest.py.

These tests use only pure functions, so they need neither the model nor ChromaDB.
Run from the repository root:  .venv/Scripts/python.exe -m unittest discover -s tests -v
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp_server"))
import ingest  # noqa: E402


class PassageTests(unittest.TestCase):
    def split(self, n_words: int, pages_every: int = 1000):
        words = [f"w{i}" for i in range(n_words)]
        pages = [str(1 + i // pages_every) for i in range(n_words)]
        return words, ingest.make_passages(words, pages)

    def test_lengths_stay_in_range_and_cover_every_word(self):
        for n in (1, 50, 200, 230, 370, 371, 1000, 4321):
            words, passages = self.split(n)
            covered = set()
            for text, _, _ in passages:
                size = len(text.split())
                self.assertLessEqual(size, ingest.PASSAGE_WORDS + ingest.MIN_TAIL_WORDS, n)
                covered.update(text.split())
            self.assertEqual(covered, set(words), f"words lost for n={n}")
            if n >= ingest.PASSAGE_WORDS:
                self.assertTrue(all(len(t.split()) >= ingest.MIN_TAIL_WORDS for t, _, _ in passages))

    def test_consecutive_passages_overlap_by_configured_words(self):
        _, passages = self.split(1000)
        first, second = passages[0][0].split(), passages[1][0].split()
        self.assertEqual(first[-ingest.OVERLAP_WORDS:], second[:ingest.OVERLAP_WORDS])

    def test_page_labels_follow_first_and_last_word(self):
        _, passages = self.split(600, pages_every=100)
        text, first, last = passages[1]
        self.assertEqual((first, last), ("2", "4"))  # words 170..369 -> pages 2..4

    def test_pdf_units_can_span_pages_but_files_cannot(self):
        units = [("a", "x " * 90), ("b", "y " * 90)]
        across = ingest.source_passages(units, cross_pages=True)
        separate = ingest.source_passages(units, cross_pages=False)
        self.assertEqual(len(across), 1)
        self.assertEqual((across[0][1], across[0][2]), ("a", "b"))
        self.assertEqual([(p[1], p[2]) for p in separate], [("a", "a"), ("b", "b")])


class CleaningTests(unittest.TestCase):
    def test_running_header_footer_and_page_numbers_are_removed(self):
        pages = []
        for i in range(1, 11):
            topic = "ABCDEFGHIJ"[i - 1]
            body = [f"Intro about {topic}", f"MoveL detail {topic}", f"zonedata {topic}", f"Outro {topic}"]
            pages.append(["ABB Technical reference manual", *body, f"3HAC050917-001 Revision: N {i}", str(i)])
        cleaned = ingest.remove_repeated_lines(pages)
        self.assertEqual(cleaned[4], ["Intro about E", "MoveL detail E", "zonedata E", "Outro E"])

    def test_lines_that_repeat_only_in_the_middle_are_kept(self):
        pages = [[f"Title {i}"] + [f"line {i}-{j}" for j in range(9)] + ["Repeated body line"]
                 + [f"line {i}-{j}" for j in range(9, 18)] for i in range(10)]
        cleaned = ingest.remove_repeated_lines(pages)
        self.assertIn("Repeated body line", cleaned[0])

    def test_abb_style_footer_block_at_page_end_is_removed(self):
        # Real layout from abb_rapid_reference_rw6.pdf (page 878): pypdf puts footer + running
        # header after the body, as ~7 lines. v2 only checked 3 edge lines and missed it.
        # Line keys ignore digits, so synthetic lines must differ in letters, like real text does.
        sections = ["AccSet - Reduces the acceleration", "ActUnit - Activates a mechanical unit",
                    "MoveL - Moves the robot linearly", "MoveJ - Moves the robot by joint movement",
                    "SingArea - Defines interpolation around singular points"]
        words = "alpha bravo charlie delta echo foxtrot golf hotel india juliett kilo lima".split()
        pages = []
        for i in range(20):
            body = [f"{words[j]} {words[(i + j) % 12]} {words[(2 * i + j) % 12]}" for j in range(12)]
            block = [f"{800 + i} Technical reference manual - RAPID Instructions, Functions and Data types",
                     "3HAC050917-001 Revision: AC", "© Copyright 2004-2026 ABB. All rights reserved.",
                     "1 Instructions", f"1.{300 + i // 4} {sections[i // 4]}", "RobotWare Base", "Continued"]
            pages.append(body + block)
        cleaned = ingest.remove_repeated_lines(pages)
        self.assertEqual(cleaned[9], pages[9][:12] + ["1.302 MoveL - Moves the robot linearly"])
        self.assertFalse(any("Copyright" in line or "3HAC" in line for page in cleaned for line in page))

    def test_lone_surrogates_and_control_chars_are_removed(self):
        # Real case: pypdf returned 114 lone surrogates (U+DC43) for song2018_impedance_pen.pdf,
        # which made the tokenizer raise TypeError during the first full ingest run.
        dirty = "force\udc43 control\x00 ok\nnext\tline"
        self.assertEqual(ingest.sanitize(dirty), "force control ok\nnext\tline")

    def test_hyphenated_line_breaks_are_joined(self):
        self.assertEqual(ingest.join_lines(["the manipu-", "lator moves"]), "the manipulator moves")

    def test_markdown_front_matter_liquid_and_links_are_cleaned(self):
        raw = ("---\nlayout: default\ntitle: Robot Tool\n---\n\n# **{{page.title}}**\n\n"
               "See [Definition]({{ site.baseurl }}/docs/x) and ![img](a.png).\n| a | b |\n|---|---|\n")
        text, title = ingest.clean_markdown(raw)
        self.assertEqual(title, "Robot Tool")
        self.assertIn("Robot Tool", text)
        self.assertIn("Definition", text)
        for leftover in ("{{", "layout:", "](", "**", "|---|"):
            self.assertNotIn(leftover, text)


if __name__ == "__main__":
    unittest.main()

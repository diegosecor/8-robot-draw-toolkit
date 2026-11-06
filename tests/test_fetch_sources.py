"""Offline tests for mcp_server/fetch_sources.py (no network: downloads are mocked).

Run from the repository root:  .venv/Scripts/python.exe -m unittest discover -s tests -v
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp_server"))
import fetch_sources  # noqa: E402

ROWS = list(csv.DictReader(fetch_sources.SOURCES_CSV.open(encoding="utf-8")))
IDS = {row["id"] for row in ROWS}


class PlanTests(unittest.TestCase):
    def test_special_cases_name_real_sources(self):
        # A renamed or removed row in sources.csv must not leave a stale entry behind.
        for source_id in [*fetch_sources.PDF_URLS, *fetch_sources.MANUAL, fetch_sources.DOCS_ID]:
            self.assertIn(source_id, IDS)

    def test_every_automatic_source_has_a_pdf_link(self):
        for row in ROWS:
            if row["id"] in fetch_sources.MANUAL or row["id"] == fetch_sources.DOCS_ID:
                continue
            url = fetch_sources.pdf_url(row)
            self.assertTrue(url.startswith("https://"), url)
            self.assertNotIn("arxiv.org/abs/", url)
            self.assertTrue(url.endswith(".pdf") or "/pdf/" in url or "Download.aspx" in url, url)

    def test_arxiv_abstract_links_become_pdf_links(self):
        row = {"id": "x", "source_url": "https://arxiv.org/abs/2210.07592"}
        self.assertEqual(fetch_sources.pdf_url(row), "https://arxiv.org/pdf/2210.07592")


class DownloadTests(unittest.TestCase):
    row = {"id": "demo", "source_url": "https://example.org/demo.pdf"}

    def test_existing_pdfs_are_kept_without_downloading(self):
        with tempfile.TemporaryDirectory() as dest:
            (Path(dest) / "demo.pdf").write_bytes(b"%PDF-1.7 already here")
            with mock.patch.object(fetch_sources, "fetch", side_effect=AssertionError("no download expected")):
                self.assertEqual(fetch_sources.fetch_pdf(self.row, Path(dest)), "kept")

    def test_a_page_that_is_not_a_pdf_is_rejected_and_not_saved(self):
        with tempfile.TemporaryDirectory() as dest:
            with mock.patch.object(fetch_sources, "fetch", return_value=b"<html>sign in</html>"):
                with self.assertRaises(ValueError):
                    fetch_sources.fetch_pdf(self.row, Path(dest))
            self.assertEqual(list(Path(dest).iterdir()), [])


if __name__ == "__main__":
    unittest.main()

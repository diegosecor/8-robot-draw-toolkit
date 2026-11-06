"""Tests for mcp_server/server.py.

- Formatting helpers and the missing/empty-index messages need no built index.
- SearchTests call search_robot_papers directly against the real index in data/chroma_store.
- StdioTests start server.py as a subprocess and talk to it over stdio with the official
  MCP client, like Claude Code does.
- MinimalEnvironmentTests search from a child process that has almost no environment
  variables, like a client that passes only a few to the server.
The last three groups are skipped when the index has not been built (run ingest.py first).

Run from the repository root:  .venv/Scripts/python.exe -m unittest discover -s tests -v
"""
import asyncio
import contextlib
import io
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp_server"))
import ingest  # noqa: E402
import server  # noqa: E402

INDEX_BUILT = (ingest.STORE_DIR / "chroma.sqlite3").is_file()
PASSAGE_LINE = re.compile(r"^- \[#\d+, score -?\d\.\d{3}\] ", re.M)


class FormattingTests(unittest.TestCase):
    def test_docs_pages_get_their_own_site_link(self):
        meta = {"source_id": "robotcomponents_docs", "source_url": server.DOCS_SITE,
                "page": "Parameters/Actions/Zone Data"}
        self.assertEqual(server.passage_link(meta),
                         server.DOCS_SITE + "docs/Parameters/Actions/Zone%20Data/")

    def test_docs_index_pages_and_readmes(self):
        base = {"source_id": "robotcomponents_docs", "source_url": server.DOCS_SITE}
        self.assertEqual(server.passage_link({**base, "page": "Parameters/index"}),
                         server.DOCS_SITE + "docs/Parameters/")
        self.assertEqual(server.passage_link({**base, "page": "index"}), server.DOCS_SITE)
        self.assertEqual(server.passage_link({**base, "page": "RobotComponents README"}),
                         "https://github.com/RobotComponents/RobotComponents")

    def test_pdf_passages_keep_the_source_link(self):
        meta = {"source_id": "song2018_impedance_pen", "source_url": "https://example.org/a.pdf",
                "page": "5", "page_end": "6"}
        self.assertEqual(server.passage_link(meta), "https://example.org/a.pdf")
        self.assertEqual(server.location(meta), "pp. 5-6")
        self.assertEqual(server.location({**meta, "page_end": "5"}), "p. 5")

    def test_long_author_lists_are_shortened(self):
        self.assertEqual(server.short_authors("A; B; C"), "A, B, C")
        self.assertEqual(server.short_authors("A; B; C; D"), "A et al.")

    def test_trim_marks_cut_passages(self):
        self.assertEqual(server.trim("a b c", 5), "a b c")
        self.assertEqual(server.trim("a b c d", 2), "a b ...")


class UnavailableIndexTests(unittest.TestCase):
    def test_missing_index_returns_instructions_not_a_traceback(self):
        with tempfile.TemporaryDirectory() as empty, mock.patch.object(ingest, "STORE_DIR", Path(empty)):
            out = server.search_robot_papers("pen pressure")
        self.assertIn("not available", out)
        self.assertIn("ingest.py", out)
        self.assertNotIn("Traceback", out)

    def test_empty_collection_returns_instructions(self):
        import chromadb
        from chromadb.config import Settings

        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as store:  # Chroma keeps files open on Windows
            client = chromadb.PersistentClient(path=store, settings=Settings(anonymized_telemetry=False))
            client.create_collection(ingest.COLLECTION, embedding_function=None,
                                     metadata={"model": ingest.MODEL})
            with mock.patch.object(ingest, "STORE_DIR", Path(store)):
                out = server.search_robot_papers("pen pressure")
        self.assertIn("is empty", out)
        self.assertIn("ingest.py", out)

    def test_empty_query_is_rejected_politely(self):
        self.assertIn("Empty query", server.search_robot_papers("   "))

    def test_unexpected_errors_opening_the_index_are_reported_not_raised(self):
        # Real case: with only SYSTEMROOT in the environment, importing chromadb raised this
        # inside open_index, and the client only saw "Error executing tool search_robot_papers".
        error = RuntimeError("Could not determine home directory.")
        with mock.patch.object(server, "open_index", side_effect=error), \
                self.assertLogs(server.log, level="ERROR"):
            out = server.search_robot_papers("pen pressure")
        self.assertIn("Search failed: RuntimeError: Could not determine home directory.", out)


@unittest.skipUnless(INDEX_BUILT, "index not built: run mcp_server/ingest.py")
class SearchTests(unittest.TestCase):
    def test_results_are_grouped_by_source_with_citation_fields(self):
        out = server.search_robot_papers("keep constant pen pressure when drawing on a curved surface", k=5)
        self.assertEqual(len(PASSAGE_LINE.findall(out)), 5)
        titles = re.findall(r"^## (.+)$", out, re.M)
        self.assertTrue(titles)
        self.assertEqual(len(titles), len(set(titles)), "a source appears in more than one group")
        for field in ("Authors:", "Year:", "Link:"):
            self.assertEqual(out.count(field), len(titles), field)
        self.assertRegex(out, r"\] pp?\. \d+")

    def test_k_is_capped_at_ten(self):
        out = server.search_robot_papers("RAPID MoveL instruction", k=50)
        self.assertEqual(len(PASSAGE_LINE.findall(out)), server.MAX_K)
        self.assertIn("capped", out)

    def test_excerpts_are_trimmed(self):
        out = server.search_robot_papers("zonedata fine z10", k=3)
        for excerpt in re.findall(r'\] [^:]+: "(.*)"$', out, re.M):
            self.assertLessEqual(len(excerpt.split()), server.SNIPPET_WORDS + 1)

    def test_the_tool_never_writes_to_stdout(self):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            server.search_robot_papers("tool orientation from surface normals", k=2)
        self.assertEqual(captured.getvalue(), "")


@unittest.skipUnless(INDEX_BUILT, "index not built: run mcp_server/ingest.py")
class StdioTests(unittest.TestCase):
    def test_server_lists_one_tool_and_answers_over_stdio(self):
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(command=sys.executable, args=[str(ROOT / "mcp_server" / "server.py")])

        async def run(errlog):
            async with stdio_client(params, errlog=errlog) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    result = await session.call_tool("search_robot_papers",
                                                     {"query": "map a 2D drawing onto a bottle", "k": 3})
                    return tools, result

        with tempfile.TemporaryFile("w+", encoding="utf-8") as errlog:  # the server's stderr
            tools, result = asyncio.run(asyncio.wait_for(run(errlog), timeout=120))
            errlog.seek(0)
            server_log = errlog.read()
        self.assertEqual([tool.name for tool in tools.tools], ["search_robot_papers"], server_log)
        self.assertIn("Do NOT use it", tools.tools[0].description)
        self.assertFalse(result.is_error, server_log)  # mcp 2.x fields are snake_case (v1: isError)
        text = "".join(block.text for block in result.content if block.type == "text")
        self.assertEqual(len(PASSAGE_LINE.findall(text)), 3, text)
        self.assertIn("query 'map a 2D drawing onto a bottle'", server_log)  # logs reached stderr


@unittest.skipUnless(INDEX_BUILT, "index not built: run mcp_server/ingest.py")
class MinimalEnvironmentTests(unittest.TestCase):
    def test_search_works_without_a_home_directory(self):
        # Windows Python needs SYSTEMROOT to start at all; every other variable is left out,
        # so Path.home() fails in the child unless server.py provides a fallback.
        env = {name: os.environ[name] for name in ("SYSTEMROOT",) if name in os.environ}
        code = ("import sys; sys.stdout.reconfigure(encoding='utf-8'); sys.path.insert(0, sys.argv[1]); "
                "import server; print(server.search_robot_papers('zonedata fine z10', k=2))")
        proc = subprocess.run([sys.executable, "-c", code, str(ROOT / "mcp_server")], env=env,
                              cwd=tempfile.gettempdir(), capture_output=True, text=True,
                              encoding="utf-8", timeout=300)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(len(PASSAGE_LINE.findall(proc.stdout)), 2, proc.stdout + proc.stderr)
        if os.name == "nt":
            self.assertIn("no home directory in the environment", proc.stderr)


if __name__ == "__main__":
    unittest.main()

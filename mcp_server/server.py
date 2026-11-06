"""MCP server for the Robot Draw Toolkit, with one tool: search_robot_papers.

The tool runs a local semantic search over the passage index built by ingest.py:
papers on robotic drawing on curved surfaces, the Robot Components documentation and
the ABB IRB 120 / RAPID manuals. Everything runs offline: the encoder weights and the
ChromaDB store live in data/, and no API key is needed.

The transport is stdio, so stdout carries JSON-RPC messages only. This module never
prints; logs go to stderr through the logging module.

Normally the MCP client starts it. To run it by hand, from the repository root:
    .venv/Scripts/python.exe mcp_server/server.py
"""
from __future__ import annotations

import logging
import sys
import threading
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))  # ingest.py sits next to this file; the client may start us from any cwd

import ingest  # noqa: E402  (shared paths, encoder name and collection name)
from mcp.server import MCPServer  # noqa: E402  (FastMCP was renamed MCPServer in mcp 2.x)

logging.basicConfig(stream=sys.stderr, level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("robot-draw-toolkit")

MAX_K = 10           # most passages one call may return
SNIPPET_WORDS = 80   # passages are ~200 words; the encoder only reads the first ~74, so show those
INGEST_COMMAND = ".venv/Scripts/python.exe mcp_server/ingest.py"

# Per-page links for the Robot Components docs, checked against the site navigation on
# 2026-11-06 (106 of 106 pages match). The two READMEs are not on the site.
DOCS_SOURCE_ID = "robotcomponents_docs"
DOCS_SITE = "https://robotcomponents.github.io/RobotComponents-Documentation/"
README_LINKS = {
    "Documentation README": "https://github.com/RobotComponents/RobotComponents-Documentation",
    "RobotComponents README": "https://github.com/RobotComponents/RobotComponents",
}

server = MCPServer(
    "robot-draw-toolkit",
    instructions=("Local search over papers and manuals for drawing with an ABB IRB 120 on curved "
                  "surfaces (Robot Components, RAPID, RobotStudio). Call search_robot_papers and cite "
                  "the title, year and page it returns."),
)

_model = None
_model_lock = threading.Lock()  # sync tools run in worker threads; load the encoder only once


class IndexUnavailable(Exception):
    """The ChromaDB index is missing, empty or was built with another encoder."""


# ---------------------------------------------------------------- index and encoder

def open_index():
    """Return the passage collection, or raise IndexUnavailable without creating anything."""
    store = ingest.STORE_DIR
    if not (store / "chroma.sqlite3").is_file():
        raise IndexUnavailable(f"no index found in {store}")
    import chromadb
    from chromadb.config import Settings
    from chromadb.errors import NotFoundError

    client = chromadb.PersistentClient(path=str(store), settings=Settings(anonymized_telemetry=False))
    try:
        collection = client.get_collection(ingest.COLLECTION)
    except NotFoundError:
        raise IndexUnavailable(f"collection '{ingest.COLLECTION}' not found in {store}") from None
    if collection.count() == 0:
        raise IndexUnavailable(f"collection '{ingest.COLLECTION}' is empty")
    built_with = (collection.metadata or {}).get("model")
    if built_with != ingest.MODEL:
        raise IndexUnavailable(f"index was built with encoder '{built_with}', expected '{ingest.MODEL}' "
                               "(rebuild it with --rebuild)")
    return collection


def get_model():
    global _model
    with _model_lock:
        if _model is None:
            log.info("loading encoder %s", ingest.MODEL)
            _model = ingest.load_model()
    return _model


# ---------------------------------------------------------------- formatting

def short_authors(authors: str) -> str:
    names = [name.strip() for name in authors.split(";") if name.strip()]
    return f"{names[0]} et al." if len(names) > 3 else ", ".join(names)


def location(meta: dict) -> str:
    """'p. 5' / 'pp. 5-6' for PDF pages, the page path for documentation files."""
    first, last = str(meta["page"]), str(meta["page_end"])
    if first.isdigit():
        return f"p. {first}" if first == last else f"pp. {first}-{last}"
    return f"doc page '{first}'"


def passage_link(meta: dict) -> str:
    """Link to the exact documentation page when there is one, else the source link."""
    page = str(meta["page"])
    if meta["source_id"] != DOCS_SOURCE_ID or page.isdigit():
        return meta["source_url"]
    if page in README_LINKS:
        return README_LINKS[page]
    parts = page.split("/")
    if parts[-1] == "index":
        parts = parts[:-1]
    if not parts:
        return DOCS_SITE
    return DOCS_SITE + "docs/" + "/".join(urllib.parse.quote(part) for part in parts) + "/"


def trim(text: str, words: int = SNIPPET_WORDS) -> str:
    tokens = text.split()
    return " ".join(tokens[:words]) + (" ..." if len(tokens) > words else "")


def format_results(query: str, k: int, capped: bool, total: int, hits: list[tuple[float, dict, str]]) -> str:
    """Group hits (score, metadata, passage) by source, sources ordered by their best hit."""
    groups: dict[str, list[tuple[int, float, dict, str]]] = {}
    for rank, (score, meta, text) in enumerate(hits, start=1):
        groups.setdefault(meta["source_id"], []).append((rank, score, meta, text))

    lines = [f'Top {len(hits)} passages for "{query}", grouped by source '
             f"({len(groups)} sources; index holds {total} passages)."]
    if capped:
        lines.append(f"Note: k was capped at {MAX_K}.")
    for entries in groups.values():
        meta = entries[0][2]
        lines += ["", f"## {meta['title']}",
                  f"Authors: {short_authors(meta['authors'])} | Year: {meta['year']} | "
                  f"Type: {meta['type']} | Venue: {meta['venue']}",
                  f"Link: {meta['source_url']}"]
        for rank, score, meta, text in entries:
            lines.append(f"- [#{rank}, score {score:.3f}] {location(meta)}: \"{trim(text)}\"")
            link = passage_link(meta)
            if link != meta["source_url"]:
                lines.append(f"  Page link: {link}")
    lines += ["", "Scores are cosine similarity (higher is closer); compare them within this list only. "
              "Page numbers count pages of the PDF file and can differ from the printed page number. "
              "Cite the title, year and page."]
    return "\n".join(lines)


# ---------------------------------------------------------------- the tool

@server.tool()
def search_robot_papers(query: str, k: int = 5) -> str:
    """Search a local library of robotics papers and manuals for this robot-drawing project.

    The project: a team draws with a sharpie held by an ABB IRB 120 (Robot Components preset
    "IRB120-3") on a fixed, raised bottle or can, designing in Grasshopper with Robot Components,
    simulating in RobotStudio and running RAPID on the real robot.

    The index holds about 3,500 passages from 26 sources:
    - research papers on robotic drawing and painting on 3D and curved surfaces (pen pressure /
      impedance control, conformal 2D-to-3D mapping, decals and surface parameterization),
      stroke ordering, coverage paths, reachability maps, collision checking, sketch generation;
    - the Robot Components documentation (one entry per Grasshopper component);
    - the ABB IRB 120 product specification and the ABB RAPID technical reference manual
      (RobotWare 6), which is about two thirds of all passages.

    Use it for questions about: robotic drawing on curved surfaces, mapping a 2D drawing onto a
    3D surface, tool orientation from surface normals, pen pressure and compliant holders,
    reachability and workspace, RAPID instructions and data types (MoveL, speeddata, zonedata,
    tooldata, wobjdata...), Robot Components components, the IRB 120, RobotStudio.
    Do NOT use it for general programming questions (Python, C#, Grasshopper scripting basics),
    for the team's own files, or for topics outside robot drawing.

    Args:
        query: what to look for, in natural language (English or Spanish), e.g.
            "keep constant pen pressure on a curved surface" or "difference between fine and z10".
        k: number of passages to return, 1 to 10 (default 5).

    Returns:
        Plain text with the top-k passages grouped by source: title, authors, year, link,
        then for each passage its rank, score, page and a short excerpt (about 80 words).
        If the index has not been built, a message saying how to build it.
    """
    query = " ".join((query or "").split())
    if not query:
        return "Empty query: pass a question or keywords, e.g. 'orientation of the pen from surface normals'."
    capped = k > MAX_K
    k = max(1, min(int(k), MAX_K))
    try:
        collection = open_index()
    except IndexUnavailable as exc:
        log.warning("index unavailable: %s", exc)
        return (f"The paper index is not available: {exc}.\n"
                f"Build it from the repository root with:\n    {INGEST_COMMAND}\n"
                "then call search_robot_papers again.")
    try:
        vector = next(iter(get_model().embed([query]))).tolist()
        result = collection.query(query_embeddings=[vector], n_results=k,
                                  include=["metadatas", "documents", "distances"])
        hits = [(1.0 - distance, meta, text) for meta, text, distance
                in zip(result["metadatas"][0], result["documents"][0], result["distances"][0])]
        total = collection.count()
    except Exception as exc:  # noqa: BLE001 - report to the agent instead of failing the call
        log.exception("search failed for query %r", query)
        return f"Search failed: {type(exc).__name__}: {exc}. The server log (stderr) has the details."
    log.info("query %r -> %d passages", query, len(hits))
    return format_results(query, k, capped, total, hits)


if __name__ == "__main__":
    server.run(transport="stdio")

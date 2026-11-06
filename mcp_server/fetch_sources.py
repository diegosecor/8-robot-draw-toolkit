"""Download the sources listed in sources.csv into data/papers/, so ingest.py can build the index.

The papers and manuals are copyrighted, so they are not committed to the repository. Every link
in sources.csv points to an open-access copy (see its license_note column); this script fetches
them for your own local use. Files that already exist are kept, so it is safe to run it again.

The source_url column is the link used for citations. When it is a landing page, the PDF link is
derived from it (arXiv /abs/ becomes /pdf/) or taken from PDF_URLS below. Three sources have no
direct PDF link: the script prints where to get them, and ingest.py skips them if they are missing.
A publisher may also refuse scripted downloads; the script then prints the link to open in a browser.

Needs internet and only the Python standard library. From the repository root:
    .venv/Scripts/python.exe mcp_server/fetch_sources.py
    .venv/Scripts/python.exe mcp_server/fetch_sources.py --dest some/other/folder
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES_CSV = HERE / "sources.csv"
DEFAULT_DEST = HERE.parent / "data" / "papers"
USER_AGENT = "Mozilla/5.0 (compatible; robot-draw-toolkit-fetch/1.0)"
ARXIV_PAUSE_S = 3  # arXiv asks automated clients to space out their requests

# PDFs behind the landing pages in source_url.
PDF_URLS = {
    "haddadi2020_drawing_3d_object": "https://repositum.tuwien.at/bitstream/20.500.12708/16142/2/"
                                     "Haddadi%20Amin%20-%202020%20-%20Robotic%20drawing%20on%20a%203D%20object.pdf",
    "atkar2005_uniform_coverage": "https://www.ri.cmu.edu/pub_files/pub4/atkar_prasad_2005_1/atkar_prasad_2005_1.pdf",
}
# No direct PDF link: open source_url and save the PDF as data/papers/<id>.pdf by hand (optional).
MANUAL = {"levy2002_lscm", "braumann2011_parametric_robot_control", "garcia2019_robot_ex_machina"}

# Robot Components documentation (markdown, GPL-3.0), pinned to the commits the index was built from.
DOCS_ID = "robotcomponents_docs"
DOCS_REPO, DOCS_COMMIT = "RobotComponents/RobotComponents-Documentation", "adba3bdb718e103a9c9efa80afbe1aa3693f8072"
CODE_REPO, CODE_COMMIT = "RobotComponents/RobotComponents", "5776b1e07005361cf02c9f485dfa6ba07b7bb492"


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def save(path: Path, data: bytes) -> None:
    """Write through a temporary file so an interrupted download never looks complete."""
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    partial.write_bytes(data)
    partial.replace(path)


def pdf_url(row: dict) -> str:
    if row["id"] in PDF_URLS:
        return PDF_URLS[row["id"]]
    url = row["source_url"]
    if url.startswith("https://arxiv.org/abs/"):
        return url.replace("/abs/", "/pdf/", 1)
    return url  # already a direct link to the PDF


def fetch_pdf(row: dict, dest: Path) -> str:
    path = dest / f"{row['id']}.pdf"
    if path.is_file() and path.read_bytes()[:5] == b"%PDF-":
        return "kept"
    url = pdf_url(row)
    data = fetch(url)
    if not data.startswith(b"%PDF-"):
        raise ValueError(f"{url} did not return a PDF")
    save(path, data)
    if "arxiv.org" in url:
        time.sleep(ARXIV_PAUSE_S)
    return f"downloaded ({len(data) // 1024} KB)"


def docs_files() -> list[tuple[str, str]]:
    """(raw URL, path inside the docs folder) for every documentation page and the two READMEs."""
    raw = "https://raw.githubusercontent.com/{}/{}/{}"
    tree = json.loads(fetch(f"https://api.github.com/repos/{DOCS_REPO}/git/trees/{DOCS_COMMIT}?recursive=1"))
    if tree.get("truncated"):
        raise ValueError("GitHub returned a truncated file list")
    pages = sorted(item["path"] for item in tree["tree"]
                   if item["type"] == "blob" and item["path"].startswith("docs/") and item["path"].endswith(".md"))
    files = [(raw.format(DOCS_REPO, DOCS_COMMIT, urllib.parse.quote(page)), page[len("docs/"):]) for page in pages]
    files.append((raw.format(DOCS_REPO, DOCS_COMMIT, "README.md"), "Documentation README.md"))
    files.append((raw.format(CODE_REPO, CODE_COMMIT, "README.md"), "RobotComponents README.md"))
    return files


def fetch_docs(dest: Path) -> str:
    folder = dest / DOCS_ID
    files = docs_files()
    downloaded = 0
    for url, relative in files:
        path = folder / relative
        if not path.is_file():
            save(path, fetch(url))
            downloaded += 1
    return f"{len(files)} markdown files ({downloaded} downloaded, {len(files) - downloaded} kept)"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", type=Path, default=DEFAULT_DEST, help="folder to save into (default: data/papers)")
    dest = parser.parse_args().dest.resolve()
    rows = list(csv.DictReader(SOURCES_CSV.open(encoding="utf-8")))
    print(f"Saving {len(rows)} sources into {dest}")

    failed, manual = [], []
    for row in rows:
        source_id = row["id"]
        try:
            if source_id == DOCS_ID:
                status = fetch_docs(dest)
            elif source_id in MANUAL:
                if (dest / f"{source_id}.pdf").is_file():
                    status = "kept"
                else:
                    manual.append(source_id)
                    status = f"manual, optional: {row['source_url']}"
            else:
                status = fetch_pdf(row, dest)
        except Exception as exc:  # noqa: BLE001 - report every source, then fail at the end
            failed.append(source_id)
            status = f"FAILED: {type(exc).__name__}: {exc}"
        print(f"  {source_id:40} {status}")

    print(f"\n{len(rows) - len(failed) - len(manual)} ready, {len(manual)} manual, {len(failed)} failed.")
    if failed:
        # Some publishers refuse scripted downloads (IEEE answered HTTP 418 in testing). Do not work
        # around that: open the link in a browser instead.
        print("For each failed source, open its link in a browser and save the PDF as <dest>/<id>.pdf:")
        by_id = {row["id"]: row for row in rows}
        for source_id in failed:
            if source_id != DOCS_ID:
                print(f"  {source_id}.pdf  <-  {pdf_url(by_id[source_id])}")
        print("Or run the script again later; files already downloaded are kept.")
        return 1
    print("Next: .venv/Scripts/python.exe mcp_server/ingest.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())

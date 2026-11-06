"""Build the local vector index used by the search_robot_papers MCP tool.

Reads mcp_server/sources.csv and the matching files in data/papers/, extracts text
page by page, removes repeated headers and footers, splits the text into overlapping
passages and stores locally computed multilingual embeddings in a persistent
ChromaDB collection in data/chroma_store/.

File convention: each row of sources.csv with id X is read from data/papers/X.pdf,
X.md or X.txt, or from a folder data/papers/X/ containing .md/.txt files.

Adapted from HW6 (114-mscd-thesis-orbit, semantic.py): same encoder, a cosine
collection with explicit vectors (embedding_function=None) and fingerprints so
unchanged sources are not embedded again.

Usage, from the repository root:
    .venv/Scripts/python.exe mcp_server/ingest.py            # incremental, idempotent
    .venv/Scripts/python.exe mcp_server/ingest.py --rebuild  # drop the collection and rebuild
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOURCES_CSV = Path(__file__).resolve().parent / "sources.csv"
PAPERS_DIR = ROOT / "data" / "papers"
STORE_DIR = ROOT / "data" / "chroma_store"
MODEL_CACHE = ROOT / "data" / "model-cache"

MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
COLLECTION = "robot_draw_passages_v1"
PASSAGE_WORDS = 200    # target passage length in words
OVERLAP_WORDS = 30     # words shared by consecutive passages
MIN_TAIL_WORDS = 80    # a shorter final piece is merged into the previous passage
CLEANER_VERSION = "3"  # bump when text cleaning changes, so every source is re-embedded
TEXT_SUFFIXES = (".pdf", ".md", ".txt")

# ABB manuals put a ~7-line footer+header block at the end of each extracted page and the
# TU Wien thesis a 4-line notice at the top, so 3 edge lines were not enough (v2 bug).
EDGE_LINES = 8                                  # lines checked at the top and bottom of each page
REPEAT_SHARE = 0.4                              # an edge line on >= 40% of pages is a header/footer
MIN_REPEAT_PAGES = 3                            # ...and on at least this many pages
PAGE_NUMBER = re.compile(r"(page\s*)?\d{1,4}(\s*(/|of)\s*\d{1,4})?", re.I)
FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
# Lone UTF-16 surrogates (pypdf emits them for some embedded fonts) and control characters
# make the Rust tokenizer raise "TextEncodeInput must be Union[...]".
UNENCODABLE = re.compile(r"[\ud800-\udfff\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


# ---------------------------------------------------------------- text cleaning

def sanitize(text: str) -> str:
    """Remove characters the tokenizer cannot encode (lone surrogates, control characters)."""
    return UNENCODABLE.sub("", text)


def _line_key(line: str) -> str:
    """Normalize a line so running headers match across pages (page numbers vary)."""
    return re.sub(r"\d+", "#", " ".join(line.lower().split()))


def remove_repeated_lines(pages: list[list[str]]) -> list[list[str]]:
    """Drop running headers/footers and bare page numbers from the edges of each page.

    A line counts as a header/footer when its normalized form appears within the first
    or last EDGE_LINES lines of at least REPEAT_SHARE of the pages (and MIN_REPEAT_PAGES+).
    Lines in the middle of a page are never removed.
    """
    counts: Counter[str] = Counter()
    for lines in pages:
        edges = lines[:EDGE_LINES] + lines[-EDGE_LINES:]
        counts.update({_line_key(line) for line in edges if line.strip()})
    threshold = max(MIN_REPEAT_PAGES, round(REPEAT_SHARE * len(pages)))
    repeated = {key for key, count in counts.items() if count >= threshold}

    cleaned = []
    for lines in pages:
        last = len(lines) - EDGE_LINES
        kept = []
        for i, line in enumerate(lines):
            at_edge = i < EDGE_LINES or i >= last
            if at_edge and (_line_key(line) in repeated or PAGE_NUMBER.fullmatch(line.strip())):
                continue
            kept.append(line)
        cleaned.append(kept)
    return cleaned


def join_lines(lines: list[str]) -> str:
    """Join extracted lines, repairing words hyphenated across a line break."""
    text = "\n".join(line.rstrip() for line in lines)
    return re.sub(r"([a-z])-\n([a-z])", r"\1\2", text)


def clean_markdown(text: str) -> tuple[str, str | None]:
    """Strip Jekyll front matter, Liquid tags, links, images and markup; return (text, title)."""
    title = None
    match = FRONT_MATTER.match(text)
    if match:
        found = re.search(r"^title:\s*(.+)$", match.group(1), re.M)
        title = found.group(1).strip().strip("\"'") if found else None
        text = text[match.end():]
    if title:
        text = re.sub(r"\{\{\s*page\.title\s*\}\}", title, text)
    text = re.sub(r"\{%.*?%\}|\{\{.*?\}\}", " ", text, flags=re.S)  # remaining Liquid tags
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", " ", text)               # images
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)            # links -> link text
    text = re.sub(r"<[^>]+>", " ", text)                            # inline HTML
    text = re.sub(r"^\s*\|?[\s:|-]+\|[\s:|-]*$", " ", text, flags=re.M)  # table separator rows
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.M)                # heading marks
    text = re.sub(r"\*\*|__|`|\|", " ", text)                        # emphasis, code, table pipes
    return text, title


# ---------------------------------------------------------------- reading sources

def read_pdf(path: Path) -> list[tuple[str, str]]:
    """Return [(page label, cleaned text)] for a PDF, one entry per page."""
    from pypdf import PdfReader

    pages = []
    for page in PdfReader(path).pages:
        try:
            pages.append(sanitize(page.extract_text() or "").splitlines())
        except Exception:  # noqa: BLE001 - a broken page must not stop the whole source
            pages.append([])
    return [(str(number), join_lines(lines))
            for number, lines in enumerate(remove_repeated_lines(pages), start=1)]


def read_text_file(path: Path, label: str) -> tuple[str, str]:
    text = sanitize(path.read_text(encoding="utf-8", errors="replace"))
    if path.suffix.lower() == ".md":
        text, _ = clean_markdown(text)
    return label, text


def find_source_file(source_id: str) -> Path | None:
    """Locate data/papers/<id>.pdf|.md|.txt or the folder data/papers/<id>/."""
    folder = PAPERS_DIR / source_id
    if folder.is_dir():
        return folder
    for suffix in TEXT_SUFFIXES:
        candidate = PAPERS_DIR / f"{source_id}{suffix}"
        if candidate.is_file():
            return candidate
    return None


def read_source(path: Path) -> tuple[list[tuple[str, str]], bool]:
    """Return ([(page label, text)], cross_pages). PDF passages may span pages; files may not."""
    if path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.suffix.lower() in (".md", ".txt"))
        return [read_text_file(p, p.relative_to(path).with_suffix("").as_posix()) for p in files], False
    if path.suffix.lower() == ".pdf":
        return read_pdf(path), True
    return [read_text_file(path, "1")], False


def fingerprint(path: Path, row: dict) -> str:
    """Hash file contents, the CSV row and chunking settings; any change triggers re-embedding."""
    digest = hashlib.sha256()
    files = sorted(p for p in path.rglob("*") if p.is_file()) if path.is_dir() else [path]
    for file in files:
        digest.update(file.relative_to(path).as_posix().encode() if path.is_dir() else b"")
        digest.update(file.read_bytes())
    settings = [row, MODEL, PASSAGE_WORDS, OVERLAP_WORDS, MIN_TAIL_WORDS, CLEANER_VERSION]
    digest.update(json.dumps(settings, sort_keys=True, ensure_ascii=False).encode())
    return digest.hexdigest()


# ---------------------------------------------------------------- passages

def make_passages(words: list[str], pages: list[str]) -> list[tuple[str, str, str]]:
    """Split words into ~PASSAGE_WORDS windows overlapping by OVERLAP_WORDS.

    Returns [(text, first page, last page)]. A final piece shorter than MIN_TAIL_WORDS is
    merged into the previous passage, so passages stay between ~80 and ~250 words.
    """
    if not words:
        return []
    step = PASSAGE_WORDS - OVERLAP_WORDS
    starts = list(range(0, len(words), step))
    if len(starts) > 1 and len(words) - starts[-1] < MIN_TAIL_WORDS:
        starts.pop()
    passages = []
    for i, start in enumerate(starts):
        end = start + PASSAGE_WORDS if i < len(starts) - 1 else len(words)
        passages.append((" ".join(words[start:end]), pages[start], pages[end - 1]))
    return passages


def source_passages(units: list[tuple[str, str]], cross_pages: bool) -> list[tuple[str, str, str]]:
    """Build passages from (page label, text) units, letting PDF passages run across pages."""
    if cross_pages:
        words, pages = [], []
        for label, text in units:
            tokens = text.split()
            words.extend(tokens)
            pages.extend([label] * len(tokens))
        return make_passages(words, pages)
    passages = []
    for label, text in units:
        tokens = text.split()
        passages.extend(make_passages(tokens, [label] * len(tokens)))
    return passages


# ---------------------------------------------------------------- embedding and storage

def load_model():
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    from fastembed import TextEmbedding

    return TextEmbedding(MODEL, cache_dir=str(MODEL_CACHE), threads=4)


def embedded_words(model, texts: list[str]) -> list[int]:
    """Count how many words of each passage fit in the encoder's token window.

    The encoder truncates input (128 tokens for this model); words after the cut are
    stored and returned to the agent but do not influence the vector. Returns -1 if
    the tokenizer is not reachable through this fastembed version.
    """
    try:
        tokenizer = model.model.tokenizer
        limit = tokenizer.truncation["max_length"]
    except (AttributeError, KeyError, TypeError):
        return [-1] * len(texts)
    counts = []
    for text in texts:
        encoding = tokenizer.encode(text)
        if len(encoding.ids) < limit:
            counts.append(len(text.split()))
            continue
        # Offsets of the last real token (before the closing special token) mark the cut.
        cut = max(end for start, end in encoding.offsets if end > 0)
        counts.append(len(text[:cut].split()))
    return counts


def open_collection(rebuild: bool):
    import chromadb
    from chromadb.config import Settings

    client = chromadb.PersistentClient(path=str(STORE_DIR), settings=Settings(anonymized_telemetry=False))
    if rebuild and COLLECTION in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION)
    return client.get_or_create_collection(
        COLLECTION, embedding_function=None, configuration={"hnsw": {"space": "cosine"}},
        metadata={"model": MODEL, "passage_words": PASSAGE_WORDS, "overlap_words": OVERLAP_WORDS},
    )


def load_sources() -> list[dict]:
    with SOURCES_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rebuild", action="store_true", help="drop the collection and embed everything again")
    args = parser.parse_args(argv)
    logging.getLogger("pypdf").setLevel(logging.ERROR)  # malformed-PDF warnings are noise here

    rows = load_sources()
    collection = open_collection(args.rebuild)
    stored = collection.get(include=["metadatas"])
    stored_fps: dict[str, set[str]] = {}
    for meta in stored["metadatas"]:
        stored_fps.setdefault(meta["source_id"], set()).add(meta["fingerprint"])

    wanted = {row["id"] for row in rows}
    for stale in sorted(stored_fps.keys() - wanted):
        collection.delete(where={"source_id": stale})
        print(f"removed  {stale} (no longer in sources.csv)")
    known = wanted | {f"{row['id']}{s}" for row in rows for s in TEXT_SUFFIXES}
    for path in sorted(PAPERS_DIR.iterdir()):
        if path.name != ".gitkeep" and path.name not in known:
            print(f"ignored  data/papers/{path.name} (no row in sources.csv)")

    model = None
    missing, empty, embedded, unchanged = [], [], [], []
    for row in rows:
        source_id = row["id"]
        path = find_source_file(source_id)
        if path is None:
            missing.append(source_id)
            if source_id in stored_fps:
                collection.delete(where={"source_id": source_id})
            continue
        fp = fingerprint(path, row)
        if stored_fps.get(source_id) == {fp}:
            unchanged.append(source_id)
            continue

        started = time.time()
        units, cross_pages = read_source(path)
        passages = source_passages(units, cross_pages)
        collection.delete(where={"source_id": source_id})
        if not passages:
            empty.append(source_id)
            print(f"EMPTY    {source_id}: no extractable text")
            continue
        model = model or load_model()
        texts = [text for text, _, _ in passages]
        vectors = [vector.tolist() for vector in model.embed(texts, batch_size=16)]
        coverage = embedded_words(model, texts)
        base = {
            "source_id": source_id, "title": row["title"], "authors": row["authors"],
            "year": int(row["year"]), "venue": row["venue"], "source_url": row["source_url"],
            "type": row["type"], "fingerprint": fp,
        }
        metadatas = [{**base, "page": first, "page_end": last, "passage": i + 1, "embedded_words": words}
                     for i, ((_, first, last), words) in enumerate(zip(passages, coverage))]
        ids = [f"{source_id}:{i + 1:05d}" for i in range(len(passages))]
        for at in range(0, len(ids), 256):
            collection.add(ids=ids[at:at + 256], documents=texts[at:at + 256],
                           embeddings=vectors[at:at + 256], metadatas=metadatas[at:at + 256])
        embedded.append(source_id)
        print(f"embedded {source_id}: {len(units)} pages/files -> {len(passages)} passages "
              f"({time.time() - started:.0f}s)", flush=True)

    index = collection.get(include=["metadatas", "documents"])
    final = index["metadatas"]
    per_source = Counter(meta["source_id"] for meta in final)
    lengths = [len(doc.split()) for doc in index["documents"]]
    pairs = [(meta.get("embedded_words", -1), n) for meta, n in zip(final, lengths)]
    coverage = [(c, n) for c, n in pairs if c >= 0]

    print("\n=== Index summary ===")
    print(f"Sources in sources.csv : {len(rows)}")
    print(f"Indexed sources        : {len(per_source)} (embedded now: {len(embedded)}, unchanged: {len(unchanged)})")
    print(f"Passages in index      : {len(final)}")
    if lengths:
        print(f"Passage length (words) : min {min(lengths)}, mean {sum(lengths) / len(lengths):.0f}, max {max(lengths)}")
    if coverage:
        cut = sum(1 for c, n in coverage if c < n)
        print(f"Encoder coverage       : mean {sum(c for c, _ in coverage) / len(coverage):.0f} words embedded "
              f"per passage; {100 * cut / len(coverage):.0f}% of passages truncated by the 128-token window")
    print(f"Missing files          : {', '.join(missing) or 'none'}")
    print(f"No extractable text    : {', '.join(empty) or 'none'}")
    print("Passages per source    : " + ", ".join(f"{k}={v}" for k, v in per_source.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())

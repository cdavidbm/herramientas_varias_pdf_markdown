#!/usr/bin/env python3
"""
build_plan.py — Generate a plan.json for The Study Quran EPUB.

The book has 114 suras, some split across continuation files (Chapter_2.xhtml +
Chapter_2a.xhtml + Chapter_2b.xhtml, etc.). This script reads the EPUB's
nav.xhtml to pull the canonical sura titles, then assembles a plan that merges
continuation files into a single logical section per sura — plus the substantive
front/back matter.

Usage:
  python3 build_plan.py path/to/book.epub > plan.json
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup
from bs4.element import Tag


# Files to skip wholesale — dividers, covers, index, etc.
SKIP_FILES = {
    "9780062227621_Cover.xhtml",
    "9780062227621_Titlepage.xhtml",
    "nav.xhtml",
    "9780062227621_Part_1.xhtml",
    "9780062227621_Part_2.xhtml",
    "9780062227621_Ad_card.xhtml",
    "9780062227621_Copyright.xhtml",
    "About_the_Publisher.xhtml",
    "9780062227621_Footnote.xhtml",
    # Index and maps are not useful as RAG content
    "9780062227621_Backmatter_20.xhtml",
    "9780062227621_Backmatter_20a.xhtml",
    "9780062227621_Backmatter_21.xhtml",
}

# Short/fragmentary frontmatter to skip
SKIP_FRONTMATTER = {
    "9780062227621_Frontmatter_1.xhtml",   # Editorial Board — list of bios
    "9780062227621_Frontmatter_3.xhtml",   # Acknowledgments — funders
}


def build(epub: Path) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(epub) as z:
            z.extractall(tmp_path)
        text_root = next(p for p in tmp_path.rglob("text") if p.is_dir())
        nav_path = text_root / "nav.xhtml"
        nav_soup = BeautifulSoup(nav_path.read_text(encoding="utf-8"), "html.parser")
        existing = {p.name for p in text_root.iterdir() if p.is_file()}

    # Build href -> title map, preferring the first non-"Commentary", non-page-number link
    primary: dict[str, str] = {}
    for a in nav_soup.find_all("a"):
        if not isinstance(a, Tag):
            continue
        href = a.get("href") or ""
        if not isinstance(href, str):
            continue
        file_part = href.split("#", 1)[0]
        text = " ".join(a.get_text().split())
        if not text or text.isdigit() or text.lower() == "commentary":
            continue
        if file_part not in primary:
            primary[file_part] = text

    sections: list[dict] = []

    # Frontmatter in numeric order
    for i in range(1, 10):
        f = f"9780062227621_Frontmatter_{i}.xhtml"
        if f in SKIP_FRONTMATTER:
            continue
        title = primary.get(f, f"Frontmatter {i}")
        import unicodedata as _u
        slug_body = _u.normalize("NFKD", title).encode("ascii", "ignore").decode()
        slug_body = re.sub(r"[^\w]+", "_", slug_body).strip("_")[:60]
        sections.append({"title": title, "files": [f], "slug": f"fm_{i:02d}_{slug_body}"})

    # Suras 1..114, each may have continuation files (a, b, ...).
    for n in range(1, 115):
        base = f"9780062227621_Chapter_{n}.xhtml"
        title = primary.get(base, f"Sura {n}")
        files = [base]
        for suffix in ("a", "b", "c", "d"):
            cont = f"9780062227621_Chapter_{n}{suffix}.xhtml"
            if cont in existing:
                files.append(cont)
        sections.append({"title": title, "files": files, "slug": f"{n:03d}_{_slug_sura(title)}"})

    # Backmatter (essays + appendices); keep only substantive ones
    for i in range(1, 22):
        f = f"9780062227621_Backmatter_{i}.xhtml"
        if f in SKIP_FILES:
            continue
        title = primary.get(f, f"Backmatter {i}")
        files = [f]
        # Merge 17a into 17 (Ḥadīth Citations continuation)
        if i == 17:
            files.append("9780062227621_Backmatter_17a.xhtml")
        sections.append({
            "title": title,
            "files": files,
            "slug": _slug_backmatter(i, title),
        })

    return {
        "epub": epub.name,
        "output_dir": "markdown",
        "footnote_file": "9780062227621_Footnote.xhtml",
        "sections": sections,
    }


def _slug_sura(title: str) -> str:
    # "1 The Opening, al-Fātiḥah" -> "al-Fatihah"
    m = re.search(r",\s*(.+)$", title)
    tail = m.group(1) if m else title
    import unicodedata
    tail = unicodedata.normalize("NFKD", tail).encode("ascii", "ignore").decode()
    tail = re.sub(r"[^\w]+", "_", tail).strip("_")
    return tail or "sura"


def _slug_backmatter(i: int, title: str) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    t = re.sub(r"[^\w]+", "_", t).strip("_")
    return f"essay_{i:02d}_{t[:60]}"


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: build_plan.py path/to/book.epub > plan.json", file=sys.stderr)
        sys.exit(2)
    plan = build(Path(sys.argv[1]))
    print(json.dumps(plan, indent=2, ensure_ascii=False))

#!/usr/bin/env python3
"""
build_plan.py — Generate a plan.json for ANY EPUB, ready for epub_to_markdown.py.

Reads the EPUB's package document (.opf) for the canonical reading order
(spine) and its table of contents (EPUB3 `nav` or EPUB2 `.ncx`) for chapter
titles, then emits one section per logical chapter:

  * one section per spine document that the TOC names as a chapter;
  * spine documents that the TOC does NOT name (continuation files such as
    Chapter_2a.xhtml, or untitled spill-over pages) are merged into the
    preceding section — so a chapter split across several files comes out as
    one .md;
  * front/back-matter cruft (cover, title page, copyright, the TOC page
    itself, colophon, plain index pages) is skipped by spine-id / filename
    heuristics;
  * the footnote-pool file (Footnote.xhtml / notas*.xhtml / endnotes…) is
    auto-detected and written to `footnote_file` + `footnote_format`, so the
    converter can resolve `[^N]` bodies.

The companion converter (epub_to_markdown.py) is already general; this script
removes the last manual step (hand-writing the plan).

Usage:
  python3 build_plan.py book.epub > plan.json
  python3 build_plan.py book.epub --footnotes none > plan.json   # ignore notes
  python3 build_plan.py book.epub --footnotes some_file.xhtml > plan.json
  python3 build_plan.py book.epub --keep-frontmatter > plan.json # don't skip fm

Then eyeball plan.json and run:
  python3 epub_to_markdown.py plan.json --dry-run
  python3 epub_to_markdown.py plan.json
"""
from __future__ import annotations

import argparse
import json
import posixpath
import re
import sys
import tempfile
import unicodedata
import zipfile
from pathlib import Path

from bs4 import BeautifulSoup
from bs4.element import Tag

from forja_common import slugify


# Spine idrefs / filename stems that are almost never substantive content.
SKIP_ID_PATTERNS = re.compile(
    r"^(cover|cvi|titlepage|title[\-_]?page|title|tp|halftitle|copy(right)?|"
    r"cop|ded(ication)?|toc|contents|content|nav|landmark|colophon|"
    r"index\d*$|idx\d*$|advert|ad[\-_]?card|backcover|bcover|teaser|praise|"
    r"about([\-_]?(the[\-_]?)?(author|publisher))?|fm$)",
    re.IGNORECASE,
)
# Note: `index\d*$` (not bare `index`) so Calibre's content files named
# `index_split_NNN.html` are NOT mistaken for an actual index page.
SKIP_TITLE_PATTERNS = re.compile(
    r"^(cover|title\s*page|copyright|table\s+of\s+contents|contents|"
    r"index|colophon|dedication|about\s+the\s+(author|publisher)|"
    r"also\s+by|praise\s+for|"
    # Spanish front/back-matter cruft
    r"cubierta|portada|cr[eé]ditos|p[aá]gina\s+de\s+cr[eé]ditos|"
    r"[ií]ndice|tabla\s+de\s+contenidos?|sinopsis|colof[oó]n|"
    r"sobre\s+el\s+autor|acerca\s+del?\s+autor|otros?\s+t[ií]tulos?|"
    r"informaci[oó]n\s+adicional)\b",
    re.IGNORECASE,
)

# Leading ISBN / numeric-id prefix that some publishers (HarperCollins, etc.)
# bolt onto every filename and title; strip it before matching skip patterns.
_PREFIX = re.compile(r"^[\d\s_\-]+")

FOOTNOTE_NAME = re.compile(r"(footnote|endnote|\bnotas?\b|\bnotes?\b)", re.IGNORECASE)


def _norm(base_dir: str, href: str) -> str:
    """Resolve an href (relative to base_dir) to a posix path from the EPUB root,
    drop any #fragment, and normalise."""
    href = href.split("#", 1)[0]
    joined = posixpath.normpath(posixpath.join(base_dir, href))
    return joined.lstrip("./")


def find_opf(root: Path) -> Path:
    """Locate the package document via META-INF/container.xml, else first *.opf."""
    container = root / "META-INF" / "container.xml"
    if container.is_file():
        soup = BeautifulSoup(container.read_text(encoding="utf-8"), "xml")
        rootfile = soup.find("rootfile")
        if isinstance(rootfile, Tag):
            full = rootfile.get("full-path")
            if isinstance(full, str):
                p = root / full
                if p.is_file():
                    return p
    opfs = list(root.rglob("*.opf"))
    if not opfs:
        sys.exit("No .opf package document found in EPUB.")
    return opfs[0]


def parse_opf(opf: Path, epub_root: Path):
    """Return (opf_dir_rel, manifest, spine_hrefs, nav_href, ncx_href).

    manifest: id -> {"href": rel_to_root, "type": media_type, "props": str}
    spine_hrefs: ordered list of hrefs (rel_to_root) of spine content docs
    """
    soup = BeautifulSoup(opf.read_text(encoding="utf-8"), "xml")
    opf_dir = posixpath.dirname(opf.relative_to(epub_root).as_posix())

    manifest: dict[str, dict] = {}
    nav_href = None
    ncx_id_to_href: dict[str, str] = {}
    for item in soup.find_all("item"):
        if not isinstance(item, Tag):
            continue
        iid = item.get("id")
        href = item.get("href")
        mtype = item.get("media-type") or ""
        props = item.get("properties") or ""
        if not isinstance(iid, str) or not isinstance(href, str):
            continue
        rel = _norm(opf_dir, href)
        manifest[iid] = {"href": rel, "type": str(mtype), "props": str(props)}
        if "nav" in str(props).split():
            nav_href = rel
        if str(mtype) == "application/x-dtbncx+xml":
            ncx_id_to_href[iid] = rel

    spine_hrefs: list[str] = []
    spine = soup.find("spine")
    ncx_href = None
    if isinstance(spine, Tag):
        toc_attr = spine.get("toc")
        if isinstance(toc_attr, str):
            ncx_href = manifest.get(toc_attr, {}).get("href")
        for itemref in spine.find_all("itemref"):
            if not isinstance(itemref, Tag):
                continue
            idref = itemref.get("idref")
            if isinstance(idref, str) and idref in manifest:
                spine_hrefs.append(manifest[idref]["href"])
    if ncx_href is None and ncx_id_to_href:
        ncx_href = next(iter(ncx_id_to_href.values()))

    return opf_dir, manifest, spine_hrefs, nav_href, ncx_href


def titles_from_nav(nav_path: Path, nav_rel: str) -> dict[str, str]:
    """EPUB3 nav.xhtml: map content-file (rel_to_root) -> first TOC title.

    nav_rel is the nav file's path relative to the EPUB root (hrefs inside the
    nav are relative to the nav file's own directory).
    """
    soup = BeautifulSoup(nav_path.read_text(encoding="utf-8"), "html.parser")
    nav_dir = posixpath.dirname(nav_rel)
    out: dict[str, str] = {}
    # Prefer the <nav epub:type="toc">; fall back to any nav/ol.
    toc = None
    for nav in soup.find_all("nav"):
        if isinstance(nav, Tag) and "toc" in (nav.get("epub:type") or nav.get("type") or ""):
            toc = nav
            break
    scope = toc or soup
    for a in scope.find_all("a"):
        if not isinstance(a, Tag):
            continue
        href = a.get("href")
        if not isinstance(href, str) or not href:
            continue
        text = " ".join(a.get_text().split())
        if not text or text.isdigit():
            continue
        rel = _norm(nav_dir, href)
        out.setdefault(rel, text)
    return out


def titles_from_ncx(ncx_path: Path, ncx_rel: str) -> dict[str, str]:
    """EPUB2 toc.ncx: map content-file (rel_to_root) -> first navPoint title."""
    soup = BeautifulSoup(ncx_path.read_text(encoding="utf-8"), "xml")
    ncx_dir = posixpath.dirname(ncx_rel)
    out: dict[str, str] = {}
    for nav_point in soup.find_all("navPoint"):
        if not isinstance(nav_point, Tag):
            continue
        label = nav_point.find("navLabel")
        content = nav_point.find("content")
        if not isinstance(label, Tag) or not isinstance(content, Tag):
            continue
        text = " ".join(label.get_text().split())
        src = content.get("src")
        if not isinstance(src, str) or not text:
            continue
        rel = _norm(ncx_dir, src)
        out.setdefault(rel, text)
    return out


def detect_footnote_file(manifest: dict, epub_root: Path) -> tuple[str | None, str]:
    """Return (footnote_href, footnote_format) or (None, 'by_a_id').

    Heuristic: among content docs, pick one whose filename looks like a notes
    pool, preferring one that actually contains many <p class="footnote"> or
    id="...fn..." anchors. Guess format from its structure.
    """
    candidates = []
    for item in manifest.values():
        if "html" not in item["type"]:
            continue
        href = item["href"]
        name = posixpath.basename(href)
        if FOOTNOTE_NAME.search(name):
            candidates.append(href)
    best = None
    best_fmt = "by_a_id"
    best_score = -1
    for href in candidates:
        p = epub_root / href
        if not p.is_file():
            continue
        html = p.read_text(encoding="utf-8", errors="ignore")
        n_pclass = len(re.findall(r'class="[^"]*footnote', html))
        n_anchor = len(re.findall(r'id="[^"]*(fn|nt|note)\d', html, re.IGNORECASE))
        score = n_pclass * 2 + n_anchor
        if score <= best_score:
            continue
        best_score = score
        best = href
        # Format guess: <div class="nota"><p id="ntN"> => by_p_id; else by_a_id.
        if re.search(r'<p[^>]*id="[^"]*(nt|note)\d', html, re.IGNORECASE) and \
           not re.search(r'<p[^>]*class="[^"]*footnote', html):
            best_fmt = "by_p_id"
        else:
            best_fmt = "by_a_id"
    if best and best_score > 0:
        return best, best_fmt
    # Filename match but no strong signal: still offer the first candidate.
    if candidates:
        return candidates[0], "by_a_id"
    return None, "by_a_id"


def is_skippable(spine_idstem: str, title: str | None, href: str) -> bool:
    stem = posixpath.splitext(posixpath.basename(href))[0]
    # Strip a leading ISBN/numeric prefix so "9780062227621_Cover" -> "Cover".
    stem_clean = _PREFIX.sub("", stem) or stem
    if (SKIP_ID_PATTERNS.match(stem_clean) or SKIP_ID_PATTERNS.match(stem)
            or SKIP_ID_PATTERNS.match(spine_idstem)):
        return True
    if title:
        title_clean = _PREFIX.sub("", title) or title
        if SKIP_TITLE_PATTERNS.match(title_clean):
            return True
    return False


def build(epub: Path, footnotes: str, keep_frontmatter: bool) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with zipfile.ZipFile(epub) as z:
            z.extractall(root)

        opf = find_opf(root)
        opf_dir, manifest, spine_hrefs, nav_href, ncx_href = parse_opf(opf, root)

        # Build file -> title map from the TOC (nav preferred, else ncx).
        titles: dict[str, str] = {}
        if nav_href:
            nav_path = root / nav_href
            if nav_path.is_file():
                titles = titles_from_nav(nav_path, nav_href)
        if not titles and ncx_href:
            ncx_path = root / ncx_href
            if ncx_path.is_file():
                titles = titles_from_ncx(ncx_path, ncx_href)

        # Footnote pool.
        fn_href: str | None = None
        fn_fmt = "by_a_id"
        if footnotes == "auto":
            fn_href, fn_fmt = detect_footnote_file(manifest, root)
        elif footnotes != "none":
            fn_href = _norm(opf_dir, footnotes)

        # Files are expressed relative to text_dir (= opf_dir) so the converter's
        # `text_root / file` join works.
        def rel_to_textdir(href: str) -> str:
            return posixpath.relpath(href, opf_dir) if opf_dir else href

        # Content docs in spine order (the footnote pool is not a section).
        content = [h for h in spine_hrefs if h != fn_href]

        # Index of the first TOC-named, non-cruft doc — the first real chapter.
        # Untitled docs BEFORE it are front matter (cover/title/copyright pages
        # that carry no TOC entry); untitled docs AFTER a named chapter are
        # continuation files to be merged into it.
        first_named = None
        for i, href in enumerate(content):
            t = titles.get(href)
            if t is not None and not is_skippable(
                    posixpath.splitext(posixpath.basename(href))[0], t, href):
                first_named = i
                break

        sections: list[dict] = []
        skipped: list[str] = []
        for i, href in enumerate(content):
            title = titles.get(href)
            stem = posixpath.splitext(posixpath.basename(href))[0]

            # Hard cruft (cover/title/copyright/toc/nav/index/colophon) — always drop.
            if is_skippable(stem, title, href) and not keep_frontmatter:
                skipped.append(f"{rel_to_textdir(href)} ({title or stem})")
                continue

            # Untitled front matter before the first real chapter — drop by default.
            if (not keep_frontmatter and title is None
                    and first_named is not None and i < first_named):
                skipped.append(f"{rel_to_textdir(href)} ({stem}) [front matter]")
                continue

            if title is not None or first_named is None or not sections:
                # New section: TOC-named, or (no TOC at all) one section per doc,
                # or the very first kept doc. Provisional title from filename.
                sec_title = title or stem.replace("_", " ").replace("-", " ").strip().title()
                sections.append({"title": sec_title, "files": [rel_to_textdir(href)]})
            else:
                # Untitled continuation after a named chapter — merge.
                sections[-1]["files"].append(rel_to_textdir(href))

        # Assign slugs in final order.
        for i, sec in enumerate(sections, 1):
            sec["slug"] = f"{i:02d}_{slugify(sec['title'], 70)}"
            # Reorder keys: title, files, slug.
            sec_files = sec.pop("files")
            sec_slug = sec.pop("slug")
            sec["files"] = sec_files
            sec["slug"] = sec_slug

        plan: dict = {
            "epub": epub.name,
            "output_dir": "markdown",
        }
        if opf_dir:
            plan["text_dir"] = opf_dir
        if fn_href:
            plan["footnote_file"] = rel_to_textdir(fn_href)
            plan["footnote_format"] = fn_fmt
        plan["sections"] = sections

        # Diagnostics to stderr.
        print(f"info: OPF at {opf.relative_to(root).as_posix()}", file=sys.stderr)
        print(f"info: TOC source: {'nav' if nav_href and titles else ('ncx' if ncx_href else 'NONE — used filenames')}",
              file=sys.stderr)
        if fn_href:
            print(f"info: footnote pool: {rel_to_textdir(fn_href)} ({fn_fmt})", file=sys.stderr)
        else:
            print("info: no footnote pool detected", file=sys.stderr)
        print(f"info: {len(sections)} section(s); skipped {len(skipped)} cruft doc(s)",
              file=sys.stderr)
        for s in skipped:
            print(f"  skip: {s}", file=sys.stderr)

        return plan


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("epub", type=Path)
    ap.add_argument("--footnotes", default="auto",
                    help="'auto' (default), 'none', or an explicit pool filename")
    ap.add_argument("--keep-frontmatter", action="store_true",
                    help="don't drop front-matter cruft (keep everything but cover/nav)")
    args = ap.parse_args()

    if not args.epub.is_file():
        sys.exit(f"EPUB not found: {args.epub}")

    plan = build(args.epub, args.footnotes, args.keep_frontmatter)
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())

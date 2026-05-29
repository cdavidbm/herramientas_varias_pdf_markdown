#!/usr/bin/env python3
"""Attach Flew's per-chapter Notes from index_split_023.html to converted markdown files.

Flew's EPUB has a quirk: chapter `<sup>N</sup>` refs link to TOC anchors, not to
the Notes file. So the main converter can't auto-resolve them. This helper:

  1. Parses the Notes pool (`<p class="calibre_3">` chapter markers,
     `<p class="calibre_9">` per-note bodies with `<span>N.</span><span>body</span>`).
  2. For each section in the plan that has `_notes_key`, finds matching notes
     and appends them as a `## Notes` section to the corresponding md file.

Usage: python3 flew_attach_notes.py <plan.json> <epub_path>
"""
from __future__ import annotations
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path
from bs4 import BeautifulSoup


def parse_notes_pool(html: str) -> dict[str, list[tuple[str, str]]]:
    """Return {chapter_key: [(num_str, body_text), ...]}. Keys: 'PREFACE',
    'Chapter 1', ..., 'APPENDIX A'."""
    soup = BeautifulSoup(html, "html.parser")
    out: dict[str, list[tuple[str, str]]] = {}
    current: str | None = None
    for p in soup.find_all("p"):
        cls = p.get("class") or []
        if "calibre_3" in cls:
            text = p.get_text(" ", strip=True)
            # Normalize the key: keep the leading "Chapter N" or "PREFACE"/"APPENDIX X"
            m = re.match(r"(Chapter\s+\d+)\b", text)
            if m:
                current = m.group(1)
            elif text.upper().startswith("PREFACE"):
                current = "PREFACE"
            elif text.upper().startswith("APPENDIX"):
                ap = re.match(r"APPENDIX\s+([A-Z])", text.upper())
                current = f"APPENDIX {ap.group(1)}" if ap else "APPENDIX"
            else:
                current = text  # fallback
            out[current] = []
        elif "calibre_9" in cls and current:
            spans = p.find_all("span", recursive=False)
            if len(spans) >= 2:
                num = spans[0].get_text(" ", strip=True).rstrip(".")
                body = spans[1].get_text(" ", strip=True)
                # Normalize multi-space and italics within body
                # (re-render <i>/<em> as *...* if present in spans[1])
                body_md = ""
                for c in spans[1].descendants:
                    pass  # keep simple text for now
                body_md = body
                out[current].append((num, body_md))
            else:
                # Sometimes the structure differs; capture full text
                full = p.get_text(" ", strip=True)
                m = re.match(r"^(\d+)\.\s*(.+)$", full, re.DOTALL)
                if m:
                    out[current].append((m.group(1), m.group(2)))
    return out


def main() -> int:
    if len(sys.argv) != 3:
        sys.exit("usage: flew_attach_notes.py <plan.json> <epub_path>")
    plan_path = Path(sys.argv[1])
    epub_path = Path(sys.argv[2])
    plan = json.loads(plan_path.read_text(encoding="utf-8"))

    output_dir = Path(plan["output_dir"])
    if not output_dir.is_absolute():
        output_dir = (plan_path.parent / output_dir).resolve()

    notes_pool_file = plan.get("_notes_pool_file") or "index_split_023.html"

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(epub_path) as z:
            z.extractall(tmp_path)
        # Find the notes pool file (might be at any level)
        candidates = list(tmp_path.rglob(notes_pool_file))
        if not candidates:
            sys.exit(f"notes pool file not found: {notes_pool_file}")
        notes_html = candidates[0].read_text(encoding="utf-8")

    pool = parse_notes_pool(notes_html)
    print(f"parsed pool: {sum(len(v) for v in pool.values())} notes "
          f"across {len(pool)} chapter(s)")

    attached = 0
    for sec in plan["sections"]:
        key = sec.get("_notes_key")
        if not key:
            continue
        notes = pool.get(key)
        if not notes:
            print(f"  warning: no notes found for key {key!r} (section {sec['title']})")
            continue
        slug = sec.get("slug")
        if not slug:
            continue
        md_path = output_dir / f"{slug}.md"
        if not md_path.is_file():
            print(f"  warning: md file missing: {md_path.name}")
            continue

        body = md_path.read_text(encoding="utf-8")
        # Don't double-append
        if "\n## Notes\n" in body:
            print(f"  skip (already has Notes): {md_path.name}")
            continue
        notes_md = "\n\n---\n\n## Notes\n\n"
        for num, txt in notes:
            txt = re.sub(r"\s+", " ", txt).strip()
            notes_md += f"{num}. {txt}\n"
        md_path.write_text(body.rstrip() + notes_md, encoding="utf-8")
        attached += 1
        print(f"  appended {len(notes)} notes -> {md_path.name}")

    print(f"\nDone. {attached} file(s) updated.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

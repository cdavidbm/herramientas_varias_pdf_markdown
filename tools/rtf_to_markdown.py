#!/usr/bin/env python3
"""
rtf_to_markdown.py — Convert an RTF book into per-section markdown,
with footnote-pool resolution and clean paragraph/heading structure.

Targets ePubLibre/Titivillus-style RTFs and similar exports where:
  - Paragraphs are tab-indented (`' \\t...'`)
  - Sub-section headings are space-indented but NOT tab-indented
  - Notes live in a pool at the end (header line `Notas` or `Notes`),
    one note per `[N]` line followed by body lines, with trailing `<<`
    back-link to strip; numbering resets per chapter group

Plan format (JSON):
{
  "source": "book.rtf",
  "output_dir": "markdown",
  "notes_header": "Notas",                    // line that marks start of pool (default "Notas")
  "sections": [
    {
      "slug": "01_Presentacion",
      "title": "Presentación",
      "ranges": [[45, 67]],                    // 0-based line ranges (inclusive)
      "notes": []                              // no notes for this section
    },
    {
      "slug": "02_Cap_1",
      "title": "1. Judío de Galilea",
      "ranges": [[68, 213]],
      "notes": [1]                             // shorthand: use the entire 1st pool group
    },
    {
      "slug": "19_Anexos_2_y_4",
      "title": "Anexos 2 y 4. Criterios",
      "ranges": [[2593, 2635], [2695, 2729]],  // multi-range section (non-contiguous)
      "notes": [{"group": 17, "indices": [2]}] // pick specific notes from a pool group
    }
  ]
}

Section `notes` field (per section):
  - []                  → no notes for this section (pure prose)
  - [N]                 → use pool group N (1-indexed) entirely
  - [{"group":N,
      "indices":[a,b]}] → pick specific notes [a, b] from group N
                          (used when a single pool group's refs are scattered
                          across multiple sections, e.g. the trailing notes
                          shared by anexos)

Inline `[N]` references in body text become `[^N]` markdown footnote refs;
each output `.md` file ends with a `## Notas` (or `## Notes`) section
listing `[^N]: ...` definitions.

Usage:
  pip install --user --break-system-packages striprtf  # one-time
  python3 rtf_to_markdown.py plan.json
  python3 rtf_to_markdown.py plan.json --dry-run
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

try:
    from striprtf.striprtf import rtf_to_text
except ImportError:
    sys.exit("error: striprtf not installed. Run: pip install --user --break-system-packages striprtf")


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s\-]", "", text.strip(), flags=re.UNICODE)
    text = re.sub(r"\s+", "_", text)
    return text[:80] or "section"


def parse_notes_pool(lines: list[str], header_line: str) -> list[dict[int, str]]:
    """Parse the notes pool into a list of dicts {note_num: text}, one per chapter group."""
    start = None
    for i, line in enumerate(lines):
        if line.strip() == header_line:
            start = i + 1
            break
    if start is None:
        return []

    groups: list[dict[int, str]] = []
    current: dict[int, str] = {}
    prev_n = 0

    i = start
    while i < len(lines):
        s = lines[i].strip()
        m = re.fullmatch(r'\[(\d+)\]', s)
        if m:
            n = int(m.group(1))
            if n == 1 and prev_n != 0:
                groups.append(current)
                current = {}
            body_parts: list[str] = []
            j = i + 1
            while j < len(lines):
                ns = lines[j].strip()
                if re.fullmatch(r'\[\d+\]', ns):
                    break
                if ns:
                    body_parts.append(ns)
                j += 1
            text = ' '.join(body_parts).strip()
            text = re.sub(r'\s*<<\s*$', '', text).strip()
            current[n] = text
            prev_n = n
            i = j
        else:
            i += 1
    if current:
        groups.append(current)
    return groups


def render_body(lines: list[str], ranges: list[tuple[int, int]], section_title: str) -> str:
    """Walk RTF lines and produce clean paragraphs + sub-headings."""
    raw_lines: list[str] = []
    for start, end in ranges:
        raw_lines.extend(lines[start:end + 1])

    items: list[tuple[str, str]] = []
    skip_chapter_title = False
    for line in raw_lines:
        if not line.strip():
            continue
        # Body lines are tab-indented (any leading whitespace then a tab).
        is_para = '\t' in line[:6]
        text = line.strip()

        if is_para:
            skip_chapter_title = False
            items.append(('para', text))
            continue

        # Non-tab-indented short line — heading-shaped or chapter num/title.
        if re.fullmatch(r'\d{1,2}', text):
            skip_chapter_title = True
            continue
        if skip_chapter_title and text == text.upper() and re.search(r'[A-ZÁÉÍÓÚÑ]', text):
            skip_chapter_title = False
            continue
        skip_chapter_title = False

        if text == 'BIBLIOGRAFÍA':
            items.append(('sub', 'Bibliografía'))
            continue
        if text == 'BIBLIOGRAPHY':
            items.append(('sub', 'Bibliography'))
            continue
        if re.fullmatch(r'(PRESENTACIÓN|EPÍLOGO|PREFACE|EPILOGUE|INTRODUCTION)', text):
            continue
        if re.fullmatch(r'(ANEXO|APPENDIX|ANNEX)\s+\d+', text):
            continue

        # Drop a subtitle that duplicates the section H1 (e.g. "Breve perfil"
        # right after dropping "ANEXO 1" when the section title already says
        # "Anexo 1. Breve perfil…").
        if section_title and text.lower() in section_title.lower():
            continue
        items.append(('sub', text))

    blocks: list[str] = []
    for kind, text in items:
        blocks.append(f'## {text}' if kind == 'sub' else text)
    md = '\n\n'.join(blocks).strip()
    md = re.sub(r'\n{3,}', '\n\n', md)
    return md


def replace_inline_refs(text: str) -> str:
    return re.sub(r'\[(\d+)\]', lambda m: f'[^{m.group(1)}]', text)


def render_section(section: dict, lines: list[str], pool: list[dict[int, str]],
                   notes_heading: str) -> str:
    body = render_body(lines, section['ranges'], section['title'])

    notes_spec = section.get('notes') or []
    fn_lookup: dict[str, str] = {}

    if notes_spec and isinstance(notes_spec[0], int):
        group_idx = notes_spec[0]
        if group_idx - 1 < len(pool):
            for n, txt in sorted(pool[group_idx - 1].items()):
                fn_lookup[str(n)] = txt
        body = replace_inline_refs(body)
    elif notes_spec:
        for entry in notes_spec:
            group_idx = entry['group']
            indices = entry['indices']
            if group_idx - 1 < len(pool):
                group = pool[group_idx - 1]
                for n in indices:
                    if n in group:
                        fn_lookup[str(n)] = group[n]
        body = replace_inline_refs(body)

    out = [f"# {section['title']}", '', body]
    if fn_lookup:
        out.append('')
        out.append(f'## {notes_heading}')
        out.append('')
        for n_str in sorted(fn_lookup, key=int):
            out.append(f'[^{n_str}]: {fn_lookup[n_str]}')
    return '\n'.join(out) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('plan', type=Path, help='Path to plan JSON file')
    parser.add_argument('--out', type=Path, help='Output dir (overrides plan.output_dir)')
    parser.add_argument('--dry-run', action='store_true', help='Preview and exit')
    args = parser.parse_args()

    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    plan_dir = args.plan.parent.resolve()

    src = Path(plan['source'])
    if not src.is_absolute():
        src = (plan_dir / src).resolve()
    if not src.is_file():
        sys.exit(f"error: source RTF not found: {src}")

    output_dir = args.out or Path(plan.get('output_dir', 'markdown'))
    if not output_dir.is_absolute():
        output_dir = (plan_dir / output_dir).resolve()

    notes_header = plan.get('notes_header', 'Notas')
    notes_heading = 'Notes' if notes_header.lower() == 'notes' else 'Notas'

    sections = plan.get('sections', [])
    if not sections:
        sys.exit("error: plan has no 'sections'")

    print(f'Source  : {src}')
    print(f'Output  : {output_dir}')
    print(f'Sections: {len(sections)}')
    print()

    rtf = src.read_text(encoding='utf-8', errors='replace')
    text = rtf_to_text(rtf, errors='ignore')
    lines = text.splitlines()
    print(f'  RTF text: {len(lines)} lines, {len(text)} chars')

    pool = parse_notes_pool(lines, notes_header)
    print(f'  Notes pool: {len(pool)} groups, sizes: {[len(g) for g in pool]}')
    print()

    width = max(2, len(str(len(sections))))
    for i, sec in enumerate(sections):
        slug = sec.get('slug') or f'{str(i+1).zfill(width)}_{slugify(sec["title"])}'
        out_path = output_dir / f'{slug}.md'
        print(f"  [{i:02d}] {slug}")

    if args.dry_run:
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    print()
    for i, sec in enumerate(sections):
        slug = sec.get('slug') or f'{str(i+1).zfill(width)}_{slugify(sec["title"])}'
        md = render_section(sec, lines, pool, notes_heading)
        out_path = output_dir / f'{slug}.md'
        out_path.write_text(md, encoding='utf-8')
        wc = len(md.split())
        print(f'  wrote {out_path.name} ({wc} words, {len(md)} chars)')

    print(f'\nDone. {len(sections)} files written to {output_dir}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

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

The plan is OPTIONAL. Point the script at the RTF itself and it derives the
sections from the same layout signals described above (a lone number line
followed by an ALL-CAPS title = chapter; named front/back matter; the notes
pool ends the body). Hand-write a plan only when the auto-derived one is wrong
— use `--emit-plan` to get it as a starting point.

Usage:
  pip install --user --break-system-packages striprtf  # one-time
  python3 rtf_to_markdown.py book.rtf --dry-run        # preview auto-sections
  python3 rtf_to_markdown.py book.rtf                  # convert
  python3 rtf_to_markdown.py book.rtf --emit-plan plan.json   # tweak by hand
  python3 rtf_to_markdown.py plan.json                 # convert from a plan
"""
from __future__ import annotations
import argparse
import json
import re
import sys
from pathlib import Path

from forja_common import slugify

try:
    from striprtf.striprtf import rtf_to_text
except ImportError:
    sys.exit("error: striprtf not installed. Run: pip install --user --break-system-packages striprtf")


# Front/back matter that stands alone as a section heading.
NAMED_HEADING_RE = re.compile(
    r'PRESENTACIÓN|PRÓLOGO|PREFACIO|INTRODUCCIÓN|EPÍLOGO|CONCLUSIÓN|BIBLIOGRAFÍA'
    r'|PREFACE|PROLOGUE|INTRODUCTION|EPILOGUE|CONCLUSION|BIBLIOGRAPHY'
)
# Numbered back matter: `ANEXO 2`, `APPENDIX IV`.
NUMBERED_HEADING_RE = re.compile(
    r'(?:ANEXO|APÉNDICE|APPENDIX|ANNEX|CAPÍTULO|CHAPTER)\s+(?:\d{1,2}|[IVXLC]{1,6})'
)
# Kept lowercase inside a title: Spanish and English function words.
_MINOR_WORDS = {
    'de', 'del', 'la', 'las', 'el', 'los', 'lo', 'y', 'e', 'o', 'u', 'en', 'a',
    'al', 'con', 'por', 'para', 'un', 'una', 'sin', 'sobre', 'tras', 'que',
    'of', 'the', 'and', 'in', 'on', 'for', 'to', 'an', 'at', 'by', 'from',
}


def titlecase(text: str) -> str:
    """ALL-CAPS heading → readable title, keeping function words lowercase."""
    words = text.split()
    out: list[str] = []
    for i, w in enumerate(words):
        lw = w.lower()
        out.append(lw if i > 0 and lw in _MINOR_WORDS else lw[:1].upper() + lw[1:])
    return ' '.join(out)


def is_body_line(line: str) -> bool:
    """Body paragraphs are tab-indented; headings are not."""
    return '\t' in line[:6]


def find_pool_start(lines: list[str], header_line: str) -> int | None:
    for i, line in enumerate(lines):
        if line.strip() == header_line:
            return i
    return None


def derive_sections(lines: list[str], header_line: str,
                    pool: list[dict[int, str]]) -> list[dict]:
    """Derive a plan's `sections` from the RTF's own layout signals.

    Same signals `render_body` already trusts: a lone 1-2 digit line followed by
    an ALL-CAPS line is a chapter heading; named/numbered front- and back-matter
    stand alone. The notes pool terminates the body.
    """
    pool_start = find_pool_start(lines, header_line)
    end_limit = pool_start if pool_start is not None else len(lines)

    starts: list[tuple[int, str]] = []
    i = 0
    while i < end_limit:
        raw = lines[i]
        text = raw.strip()
        if not text or is_body_line(raw):
            i += 1
            continue

        # `12` on its own line, then the ALL-CAPS chapter title.
        if re.fullmatch(r'\d{1,2}', text):
            j = i + 1
            while j < end_limit and not lines[j].strip():
                j += 1
            if j < end_limit:
                nxt = lines[j].strip()
                if (not is_body_line(lines[j]) and nxt == nxt.upper()
                        and re.search(r'[A-ZÁÉÍÓÚÑ]', nxt)):
                    starts.append((i, f'{text}. {titlecase(nxt)}'))
                    i = j + 1
                    continue

        if NAMED_HEADING_RE.fullmatch(text) or NUMBERED_HEADING_RE.fullmatch(text):
            starts.append((i, titlecase(text)))
            i += 1
            continue
        i += 1

    if not starts:
        return []

    sections: list[dict] = []
    width = max(2, len(str(len(starts))))
    for n, (start, title) in enumerate(starts):
        end = starts[n + 1][0] - 1 if n + 1 < len(starts) else end_limit - 1
        sections.append({
            'slug': f'{str(n + 1).zfill(width)}_{slugify(title)}',
            'title': title,
            'ranges': [[start, end]],
            'notes': [],
        })

    # The pool resets at [1] once per chapter that HAS notes, in reading order —
    # so hand out groups sequentially to the sections that cite them.
    group = 0
    for sec in sections:
        if group >= len(pool):
            break
        start, end = sec['ranges'][0]
        body = '\n'.join(lines[start:end + 1])
        if re.search(r'\[\d{1,3}\](?![(:])', body):
            sec['notes'] = [group + 1]
            group += 1
    return sections


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
    # Solo 1-3 dígitos: un `[2024]` (año entre corchetes) o `[123456]` NO es un
    # marcador de nota. Y no delante de `(` o `:` para no romper enlaces markdown
    # `[1](url)` ni definiciones `[1]:` que ya vinieran en el texto.
    return re.sub(r'\[(\d{1,3})\](?![(:])', lambda m: f'[^{m.group(1)}]', text)


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
    parser.add_argument('input', type=Path,
                        help='The .rtf book (sections auto-derived) or a plan .json')
    parser.add_argument('--out', type=Path, help='Output dir (overrides plan.output_dir)')
    parser.add_argument('--dry-run', action='store_true', help='Preview and exit')
    parser.add_argument('--emit-plan', type=Path, metavar='PLAN.json',
                        help='Write the auto-derived plan for hand-editing, then exit')
    parser.add_argument('--notes-header', default=None, metavar='LINE',
                        help='Line that starts the notes pool (default: Notas)')
    args = parser.parse_args()

    auto = args.input.suffix.lower() != '.json'
    if not args.input.is_file():
        sys.exit(f"error: input not found: {args.input}")

    if auto:
        # Auto mode: the RTF is the source; the plan is derived below, once the
        # text is parsed (deriving sections needs the striprtf line numbers).
        plan = {}
        plan_dir = args.input.parent.resolve()
        src = args.input.resolve()
    else:
        plan = json.loads(args.input.read_text(encoding='utf-8'))
        plan_dir = args.input.parent.resolve()
        src = Path(plan['source'])
        if not src.is_absolute():
            src = (plan_dir / src).resolve()
        if not src.is_file():
            sys.exit(f"error: source RTF not found: {src}")

    output_dir = args.out or Path(plan.get('output_dir', 'markdown'))
    if not output_dir.is_absolute():
        output_dir = (plan_dir / output_dir).resolve()

    notes_header = args.notes_header or plan.get('notes_header', 'Notas')
    notes_heading = 'Notes' if notes_header.lower() == 'notes' else 'Notas'

    print(f'Source  : {src}')
    print(f'Output  : {output_dir}')

    rtf = src.read_text(encoding='utf-8', errors='replace')
    text = rtf_to_text(rtf, errors='ignore')
    lines = text.splitlines()
    print(f'  RTF text: {len(lines)} lines, {len(text)} chars')

    pool = parse_notes_pool(lines, notes_header)
    print(f'  Notes pool: {len(pool)} groups, sizes: {[len(g) for g in pool]}')

    if auto:
        sections = derive_sections(lines, notes_header, pool)
        if not sections:
            sys.exit(
                "error: no sections found in the RTF layout.\n"
                "  This RTF doesn't use the expected signals (lone number line +\n"
                "  ALL-CAPS title, or named front/back matter). Write a plan.json\n"
                "  by hand — see the module docstring for its shape."
            )
        print(f'  Auto-derived {len(sections)} sections from the RTF layout')
    else:
        sections = plan.get('sections', [])
        if not sections:
            sys.exit("error: plan has no 'sections'")

    if args.emit_plan:
        derived = {
            'source': src.name,
            'output_dir': str(output_dir.name),
            'notes_header': notes_header,
            'sections': sections,
        }
        args.emit_plan.write_text(
            json.dumps(derived, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(f'\nWrote plan: {args.emit_plan} ({len(sections)} sections). '
              f'Edit it, then run: python3 {Path(__file__).name} {args.emit_plan.name}')
        return 0

    print(f'Sections: {len(sections)}')
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

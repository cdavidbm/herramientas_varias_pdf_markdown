#!/usr/bin/env python3
"""
pdf_chapters_to_markdown.py — Convert one or more pre-split chapter PDFs
into per-chapter markdown, with proper handling of page-bottom footnotes.

Use this when the book is already provided as separate per-chapter PDFs
(common for academic books shared chapter-by-chapter), and the layout uses
classic page-bottom footnotes (`^N text...` at the foot of each page).

Plan format (JSON):
{
  "output_dir": "markdown",
  "running_heads": [                   // regex strings (case-insensitive),
    "A HISTORY OF WESTERN ASTROLOGY",  // matched as full-line; lines that
    "INTRODUCTION",                    // match are dropped page-by-page.
    "PREFACE"
  ],
  "sections": [
    {
      "slug": "01_Preface",
      "title": "Preface",
      "pdf": "1 Intro.pdf",            // path relative to plan file
      "pages": [9, 10]                 // [start, end] 1-based PDF pages,
                                       // both inclusive. `null` end = last
                                       // page of the PDF.
    },
    {
      "slug": "02_Introduction",
      "title": "I. Introduction",
      "pdf": "1 Intro.pdf",
      "pages": [11, null]
    },
    {
      "slug": "03_Chapter_2",
      "title": "II. Chapter 2",
      "pdf": "2 Chapter 2.pdf"         // omitted "pages" = entire PDF
    }
  ]
}

Usage:
  python3 pdf_chapters_to_markdown.py plan.json
  python3 pdf_chapters_to_markdown.py plan.json --dry-run
  python3 pdf_chapters_to_markdown.py plan.json --only Preface

Pipeline per page (`pdftotext -layout`):
  - drop running heads, page-number-only lines, lone Roman-numeral lines
  - footnote zone = lines after a blank line that starts with `^\\d+\\s+` —
    everything from that marker to end of page is footnote text
  - body paragraphs split on blank lines OR on indent transitions
    (lines with leading whitespace ≥ 3 start a new paragraph;
     pdftotext -layout doesn't blank-line-separate body paragraphs)
  - soft hyphens (U+00AD) and end-of-line `-` + lowercase undone at line
    breaks AND across paragraph joins
  - cross-page sentence join: when last paragraph of page N ends without
    terminal punctuation (.!?"”')) AND page N+1's first paragraph follows,
    merge them — captures sentences broken at page boundaries.
  - body paragraphs that look like leaked footnotes (`^N word...`) are dropped
  - inline-ref rewriting: `(non-digit)(1-3 digits)(?=\\W|$)` → `[^N]` if N is
    a footnote on the same page; second pass splits concatenated digit runs
    (`written1718two` → `written[^17][^18]two`) using same-page footnote nums

Each output `.md` file:
  # <title>
  <body paragraphs ...>
  ## Notes
  [^1]: ...
  [^2]: ...
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path


_PAGE_NUM = re.compile(r'^[\s•·\.]*(\d{1,3}|[ivxIVX]{1,5})[\s•·\.]*$')
_CHAPTER_HEADING = re.compile(r'^[IVX]+$')
_FN_LINE = re.compile(r'^(\d{1,3})\s+(\S.*)$')


def require_tool(name: str) -> None:
    if shutil.which(name) is None:
        sys.exit(f"error: required tool '{name}' is not installed (apt: poppler-utils)")


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s\-]", "", text.strip(), flags=re.UNICODE)
    text = re.sub(r"\s+", "_", text)
    return text[:80] or "section"


def extract_pages(pdf: Path) -> list[str]:
    result = subprocess.run(
        ['pdftotext', '-layout', str(pdf), '-'],
        check=True, capture_output=True, text=True,
    )
    pages = result.stdout.split('\f')
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def is_running_head(line: str, patterns: list[re.Pattern[str]]) -> bool:
    s = line.strip()
    if not s:
        return False
    return any(p.match(s) for p in patterns)


def is_page_number(line: str) -> bool:
    return bool(_PAGE_NUM.match(line))


def split_page(page: str, head_patterns: list[re.Pattern[str]]) -> tuple[list[str], dict[int, str]]:
    raw_lines = page.splitlines()
    cleaned: list[str] = []
    for line in raw_lines:
        s = line.strip()
        if not s:
            cleaned.append('')
            continue
        if is_running_head(s, head_patterns):
            continue
        if is_page_number(line):
            continue
        if _CHAPTER_HEADING.match(s):
            continue
        cleaned.append(line)
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    if not cleaned:
        return [], {}

    fn_zone_start: int | None = None
    for i in range(len(cleaned) - 1, -1, -1):
        if cleaned[i].strip() == '':
            j = i + 1
            while j < len(cleaned) and cleaned[j].strip() == '':
                j += 1
            if j < len(cleaned):
                m = _FN_LINE.match(cleaned[j].strip())
                if m and int(m.group(1)) <= 200:
                    fn_zone_start = j
                    break

    if fn_zone_start is not None:
        body_lines = cleaned[:fn_zone_start]
        fn_lines = cleaned[fn_zone_start:]
    else:
        body_lines = cleaned
        fn_lines = []

    notes: dict[int, str] = {}
    current_n: int | None = None
    current_parts: list[str] = []
    for line in fn_lines:
        s = line.strip()
        if not s:
            continue
        m = _FN_LINE.match(s)
        if m:
            if current_n is not None:
                notes[current_n] = ' '.join(current_parts).strip()
            current_n = int(m.group(1))
            current_parts = [m.group(2)]
        else:
            current_parts.append(s)
    if current_n is not None:
        notes[current_n] = ' '.join(current_parts).strip()

    paragraphs: list[str] = []
    current: list[str] = []
    for line in body_lines:
        s = line.rstrip()
        leading = len(line) - len(line.lstrip())
        if not s.strip():
            if current:
                paragraphs.append(_join_lines(current))
                current = []
            continue
        if leading >= 3 and current:
            paragraphs.append(_join_lines(current))
            current = []
        current.append(s.strip())
    if current:
        paragraphs.append(_join_lines(current))

    return paragraphs, notes


def _join_lines(lines: list[str]) -> str:
    if not lines:
        return ''
    out = lines[0]
    for nxt in lines[1:]:
        if out.endswith('­'):
            out = out[:-1] + nxt.lstrip()
            continue
        if out.endswith('-') and nxt[:1].isalpha() and nxt[:1].islower():
            out = out[:-1] + nxt.lstrip()
            continue
        out = out + ' ' + nxt
    out = re.sub(r'­\s+', '', out)
    return out


def join_paragraph_text(text: str) -> str:
    text = re.sub(r'(\w)­\n(\w)', r'\1\2', text)
    text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
    text = re.sub(r'\s*\n\s*', ' ', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.strip()


def render_section(
    title: str, pdf_path: Path, page_start: int, page_end: int | None,
    head_patterns: list[re.Pattern[str]],
) -> str:
    pages = extract_pages(pdf_path)
    if page_end is None:
        page_end = len(pages)
    selected = pages[page_start - 1:page_end]

    all_paragraphs: list[str] = []
    all_notes: dict[int, str] = {}
    note_counter = 0

    for page in selected:
        body_paras, page_notes = split_page(page, head_patterns)
        local_to_global: dict[int, int] = {}
        for local_n in sorted(page_notes):
            note_counter += 1
            local_to_global[local_n] = note_counter
        valid_locals = set(local_to_global)

        body_paras = [p for p in body_paras if not re.match(r'^\d{1,3}\s+\S', p.strip())]

        rewritten: list[str] = []
        for p in body_paras:
            p = join_paragraph_text(p)

            def repl(m: re.Match[str]) -> str:
                prefix = m.group(1)
                n = int(m.group(2))
                if n not in valid_locals:
                    return m.group(0)
                return f'{prefix}[^{local_to_global[n]}]'
            # (?<!\d): NO tocar cifras que continúan un número (decimales, fechas
            # «1970.01», «27.13°»): ahí el char previo al prefijo es un dígito. Sin
            # esta guarda, «1970.01» → «1970.[^1]» si la nota 1 existe (falso marcador).
            p = re.sub(r"(?<!\d)([^\s\d])(\d{1,3})(?=\W|$)", repl, p)

            def split_concat(m: re.Match[str]) -> str:
                prefix = m.group(1)
                digits = m.group(2)
                suffix = m.group(3)

                def try_split(d: str) -> list[int] | None:
                    if not d:
                        return []
                    for ln in (3, 2):
                        if len(d) >= ln:
                            n = int(d[:ln])
                            if n in valid_locals:
                                rest = try_split(d[ln:])
                                if rest is not None:
                                    return [n] + rest
                    return None
                parts = try_split(digits)
                if parts and len(parts) >= 2:
                    refs = ''.join(f'[^{local_to_global[n]}]' for n in parts)
                    return f'{prefix}{refs}{suffix}'
                return m.group(0)
            p = re.sub(r"([^\s\d])(\d{4,9})([A-Za-z])", split_concat, p)
            rewritten.append(p)

        if all_paragraphs and rewritten:
            tail = all_paragraphs[-1].rstrip()
            head = rewritten[0].lstrip()
            tail_end = tail[-1:] if tail else ''
            ends_open = tail_end not in '.!?"”\')'
            if ends_open:
                if tail.endswith('­') or tail.endswith('-'):
                    merged = tail[:-1] + head
                else:
                    merged = tail + ' ' + head
                all_paragraphs[-1] = merged
                rewritten = rewritten[1:]
        all_paragraphs.extend(rewritten)

        for local_n, text in page_notes.items():
            global_n = local_to_global[local_n]
            all_notes[global_n] = join_paragraph_text(text)

    norm_title = re.sub(r'\s+', ' ', title.lower())
    norm_title_short = re.sub(r'^(i{1,3}|iv|v|vi|vii|viii|ix|x{1,3})\.?\s*', '', norm_title)
    while all_paragraphs:
        first_short = re.sub(r'\s+', ' ', all_paragraphs[0].lower().strip())
        if first_short == norm_title.strip() or first_short == norm_title_short.strip():
            all_paragraphs.pop(0)
        else:
            break

    out = [f'# {title}', '', '\n\n'.join(all_paragraphs).strip()]
    if all_notes:
        out.append('')
        out.append('## Notes')
        out.append('')
        for n in sorted(all_notes):
            out.append(f'[^{n}]: {all_notes[n]}')
    return '\n'.join(out).rstrip() + '\n'


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('plan', type=Path, help='Path to plan JSON file')
    parser.add_argument('--out', type=Path, help='Output directory (overrides plan.output_dir)')
    parser.add_argument('--dry-run', action='store_true', help='Preview the plan and exit')
    parser.add_argument('--only', type=str, help='Process only sections whose title contains this substring')
    parser.add_argument('--verify', action='store_true',
                        help='After writing, run check_completeness.py per section to catch '
                             'DROPPED text (the footnote-zone/paragraph heuristics can silently '
                             'lose content on some layouts). Warns only; never modifies output.')
    args = parser.parse_args()

    require_tool('pdftotext')
    require_tool('pdfinfo')

    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    plan_dir = args.plan.parent.resolve()

    output_dir = args.out or Path(plan.get('output_dir', 'markdown'))
    if not output_dir.is_absolute():
        output_dir = (plan_dir / output_dir).resolve()

    head_patterns = [re.compile(p, re.IGNORECASE) for p in plan.get('running_heads', [])]

    sections = plan.get('sections', [])
    if not sections:
        sys.exit("error: plan has no 'sections'")

    print(f'Plan    : {args.plan}')
    print(f'Output  : {output_dir}')
    print(f'Sections: {len(sections)}')
    print()

    width = max(2, len(str(len(sections))))
    plans: list[tuple[Path, str, Path, int, int | None, str]] = []
    for i, sec in enumerate(sections):
        title = sec['title']
        if args.only and args.only.lower() not in title.lower():
            continue
        slug = sec.get('slug') or f'{str(i+1).zfill(width)}_{slugify(title)}'
        pdf_path = Path(sec['pdf'])
        if not pdf_path.is_absolute():
            pdf_path = (plan_dir / pdf_path).resolve()
        if not pdf_path.is_file():
            sys.exit(f"error: PDF not found: {pdf_path}")
        pages = sec.get('pages')
        if pages:
            p_start = pages[0]
            p_end = pages[1] if len(pages) > 1 else None
        else:
            p_start, p_end = 1, None
        out_path = output_dir / f'{slug}.md'
        plans.append((out_path, title, pdf_path, p_start, p_end, slug))
        end_str = str(p_end) if p_end is not None else 'end'
        print(f'  [{i:02d}] p.{p_start}-{end_str} {pdf_path.name} -> {out_path.name}')

    if args.dry_run:
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    print()
    for out_path, title, pdf_path, p_start, p_end, slug in plans:
        md = render_section(title, pdf_path, p_start, p_end, head_patterns)
        out_path.write_text(md, encoding='utf-8')
        wc = len(md.split())
        print(f'  wrote {out_path.name} ({wc} words, {len(md)} chars)')

    print(f'\nDone. {len(plans)} files written to {output_dir}')

    if args.verify:
        checker = Path(__file__).resolve().parent / 'check_completeness.py'
        print('\nVerificando completitud contra pdftotext -layout '
              '(texto perdido por la conversión)…')
        flagged = 0
        for out_path, title, pdf_path, p_start, p_end, slug in plans:
            cmd = ['python3', str(checker), str(pdf_path), str(out_path)]
            if p_end is not None or p_start != 1:
                cmd += ['--pages', f'{p_start}-{p_end if p_end is not None else ""}']
            r = subprocess.run(cmd, capture_output=True, text=True)
            first = (r.stdout.strip().splitlines() or [''])[0]
            print('  ' + first)
            if r.returncode == 1:
                flagged += 1
        if flagged:
            print(f'\n  ⚠️  {flagged} sección(es) con posible texto perdido. Revisa el '
                  f'detalle con:\n      python3 {checker.name} <pdf> <sección.md> [--pages A-B]\n'
                  f'      y repara con --repair (excluye falsos positivos de orden de lectura).')
        else:
            print('  ✅ todas las secciones completas.')
    return 0


if __name__ == '__main__':
    sys.exit(main())

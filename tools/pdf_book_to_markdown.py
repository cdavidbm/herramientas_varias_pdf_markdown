#!/usr/bin/env python3
"""
pdf_book_to_markdown.py — Convert a single PDF book (post-OCR or text-layer)
into per-section markdown files using a page-range plan.

Companion to `pdf_chapters_to_markdown.py`. Use this when the book is a
single PDF (not pre-split per chapter) and uses Harvard-style author-year
in-text citations rather than numbered page-bottom footnotes (i.e., no
footnote zone to detect at the bottom of each page).

Plan format (JSON):
{
  "source": "es_reocr.pdf",            // path relative to plan file
  "output_dir": "...",
  "running_heads": [                   // regex strings, case-insensitive,
    "Kocku\\s+von\\s+Stuckrad",        // matched as full-line on each
    "Astrolog[ií]a"                    // page; matching lines are dropped.
  ],
  "ocr_fixes": [                       // optional: literal/regex post-fixes
    ["Antig[uü]?[ií][eí]?dad", "Antigüedad"],
    ["\\b1[a0]\\b", "la"]
  ],
  "sections": [
    {"slug": "01_Prefacio", "title": "Prefacio", "pages": [15, 17]},
    {"slug": "02_Introduccion", "title": "I. Introducción", "pages": [18, 39]},
    ...
  ]
}

Pipeline per page (`pdftotext -layout`):
  - drop running heads (regex), page-number lines, lone Roman-numeral lines
  - body paragraphs split on blank lines OR on indent transitions
    (lines with leading whitespace ≥ 3 start a new paragraph)
  - soft hyphens (U+00AD) and end-of-line `-` + lowercase are undone at line
    breaks AND across paragraph joins
  - cross-page sentence join: when last paragraph of page N ends without
    terminal punctuation AND page N+1's first paragraph follows, merge them
  - optional OCR fix-up pass: list of (pattern, replacement) regex pairs
    applied per-paragraph after assembly

Each output `.md` file:
  # <title>
  <body paragraphs ...>
"""
from __future__ import annotations
import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from forja_common import slugify, require_tool


_PAGE_NUM = re.compile(r'^[\s•·\.\-]*(\d{1,3}|[ivxIVX]{1,5})[\s•·\.\-]*$')
_CHAPTER_HEADING = re.compile(r'^[IVX]+$')
_LEAD_PAGENUM = re.compile(r'^[\s\-]*\d{1,3}([A-ZÁÉÍÓÚÑa-záéíóúñ¡¿«¿])')


_SPANISH_STOPWORDS = {
    'de', 'la', 'el', 'en', 'que', 'y', 'a', 'los', 'las', 'un', 'una',
    'por', 'para', 'con', 'no', 'es', 'se', 'lo', 'su', 'al', 'del',
    'como', 'pero', 'si', 'mas', 'más', 'sus', 'también', 'este', 'esta',
    'fue', 'son', 'ya', 'sí', 'le', 'sin', 'ha', 'había', 'tiene',
    'sobre', 'entre', 'cuando', 'tras', 'porque', 'desde', 'hasta',
    'esto', 'eso', 'aquí', 'allí', 'donde', 'dos', 'tres', 'cuatro',
}

_ENGLISH_STOPWORDS = {
    'the', 'of', 'and', 'a', 'to', 'in', 'is', 'it', 'that', 'was', 'for',
    'on', 'are', 'with', 'as', 'his', 'they', 'at', 'be', 'this', 'have',
    'from', 'or', 'one', 'had', 'by', 'but', 'not', 'what', 'all', 'were',
    'when', 'we', 'there', 'can', 'an', 'your', 'which', 'their', 'if',
    'do', 'will', 'each', 'about', 'how', 'up', 'out', 'them', 'then',
    'she', 'so', 'these', 'has', 'her', 'two', 'see', 'time', 'could',
    'no', 'may', 'who', 'now', 'my', 'over', 'did', 'down', 'only', 'way',
    'use', 'our', 'me', 'too', 'any', 'day', 'same', 'also', 'come',
    'work', 'such', 'here', 'take', 'why', 'put', 'old', 'us', 'i', 'he',
    'you', 'are', 'its', 'than', 'into', 'been', 'more', 'some', 'like',
}

_STOPWORDS = _SPANISH_STOPWORDS | _ENGLISH_STOPWORDS


def looks_like_spanish(s: str) -> int:
    """Count stopword-like tokens in s (lowercase, 1-7 chars).

    Name kept for back-compat. Set now includes both Spanish and English
    stopwords so the same garbage heuristics apply to either language.
    """
    tokens = re.findall(r"\b[a-záéíóúüñ]{1,7}\b", s.lower())
    return sum(1 for t in tokens if t in _STOPWORDS)


def is_garbage_line(line: str) -> bool:
    """Detect OCR garbage from figures/captions: high ratio of non-letter chars
    or no recognizable word-like tokens."""
    s = line.strip()
    if len(s) < 6:
        return False
    letters = sum(1 for c in s if c.isalpha())
    if letters == 0:
        return True
    if letters / len(s) < 0.55:
        return True
    word_like = re.findall(r'[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]{3,}', s)
    if len(word_like) < 2 and len(s) > 12:
        return True
    longest_word = max((len(w) for w in word_like), default=0)
    if longest_word > 25:
        return True
    return False


def is_garbage_paragraph(p: str) -> bool:
    """Heuristic for an entire paragraph: figures/captions yield long words,
    very few Spanish stopwords, and unusual case patterns."""
    s = p.strip()
    if not s:
        return True
    letters = sum(1 for c in s if c.isalpha())
    if len(s) >= 4 and letters / max(len(s), 1) < 0.55:
        return True
    words = re.findall(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+", s)
    if not words:
        return True
    stopword_hits = looks_like_spanish(s)
    long_words = [w for w in words if len(w) > 18]
    avg_len = sum(len(w) for w in words) / len(words)
    # mixed-case mid-word (e.g. "DKoreaXcJSIaN") is unusual in Spanish prose
    weird_case = sum(
        1 for w in words
        if len(w) >= 4
        and any(c.isupper() for c in w[1:])
        and any(c.islower() for c in w[1:])
    )
    weird_ratio = weird_case / max(len(words), 1)
    # Tokens that contain bracket/pipe/digit-mixed characters (figure-caption noise)
    digit_letter_mix = sum(
        1 for tok in re.findall(r'\S+', s)
        if any(c.isalpha() for c in tok) and any(c.isdigit() for c in tok) and len(tok) >= 4
    )
    bracket_chars = sum(1 for c in s if c in '[]{}|<>~`^')
    if bracket_chars >= 2 or digit_letter_mix >= 2:
        return True
    # Very short fragments without any stopword anchor are likely OCR junk
    if len(s) < 40 and stopword_hits == 0 and weird_case == 0 and len(words) <= 3:
        # but allow short headings like "Hemerología" — long enough single words
        if len(words) == 1 and len(words[0]) >= 5 and not any(c.isdigit() for c in s):
            return False
        return True
    if stopword_hits == 0 and (long_words or avg_len > 9 or weird_ratio > 0.3):
        return True
    if stopword_hits <= 1 and (len(long_words) >= 2 or weird_ratio > 0.4):
        return True
    return False





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
    return any(p.search(s) for p in patterns)


def is_page_number(line: str) -> bool:
    return bool(_PAGE_NUM.match(line.strip()))


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


def page_to_paragraphs(page: str, head_patterns: list[re.Pattern[str]]) -> list[str]:
    raw = page.splitlines()
    cleaned: list[str] = []
    for line in raw:
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
        if is_garbage_line(s):
            continue
        cleaned.append(line)
    while cleaned and not cleaned[0].strip():
        cleaned.pop(0)
    while cleaned and not cleaned[-1].strip():
        cleaned.pop()
    if not cleaned:
        return []

    paragraphs: list[str] = []
    current: list[str] = []
    for line in cleaned:
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
    return paragraphs


def apply_ocr_fixes(text: str, fixes: list[tuple[re.Pattern[str], str]]) -> str:
    for pat, rep in fixes:
        text = pat.sub(rep, text)
    return text


def is_uppercase_heading(p: str) -> bool:
    """Detect a paragraph that is an ALL-CAPS subheading (CHAPTER, SECTION,
    etc.). Cap typography: short, mostly uppercase letters, no terminal `.` `!`
    `?` outside of `?` for question titles."""
    s = p.strip()
    if not (3 <= len(s) <= 90):
        return False
    letters = [c for c in s if c.isalpha()]
    if len(letters) < 3:
        return False
    upper = sum(1 for c in letters if c.isupper())
    if upper / len(letters) < 0.85:
        return False
    # Not a real sentence: shouldn't end with period (`.`) — `?` allowed for
    # question-form headings; punctuation otherwise mostly absent.
    if s.endswith('.') and not s.endswith('...'):
        return False
    if any(c in s for c in (':',)) and len(s) > 60:
        return False
    return True


def to_title_case_es(s: str) -> str:
    """Spanish-friendly title case (don't capitalize particles: de, la, y...)"""
    minor = {
        'de', 'del', 'la', 'el', 'los', 'las', 'y', 'o', 'u', 'a', 'al',
        'en', 'con', 'por', 'para', 'sin', 'sobre', 'que', 'se', 'su', 'sus',
    }
    words = s.split()
    out: list[str] = []
    for i, w in enumerate(words):
        wl = w.lower()
        if i > 0 and wl in minor:
            out.append(wl)
        else:
            # preserve trailing punct
            core = wl
            trail = ''
            while core and not core[-1].isalpha():
                trail = core[-1] + trail
                core = core[:-1]
            lead = ''
            while core and not core[0].isalpha():
                lead = lead + core[0]
                core = core[1:]
            out.append(lead + (core[:1].upper() + core[1:] if core else '') + trail)
    return ' '.join(out)


def merge_broken_paragraphs(paragraphs: list[str]) -> list[str]:
    """Re-fuse paragraphs that were artificially split by visual line breaks
    (epigraph layouts, narrow-column passages). Heuristic: if paragraph i
    ends without strong terminal punctuation AND paragraph i+1 starts with
    a lowercase letter, merge them. Also merge across soft hyphen `­` and
    end-of-line `-` + lowercase-start."""
    if not paragraphs:
        return paragraphs
    merged: list[str] = [paragraphs[0]]
    for p in paragraphs[1:]:
        if not merged:
            merged.append(p)
            continue
        prev = merged[-1].rstrip()
        nxt = p.lstrip()
        if not prev or not nxt:
            merged.append(p)
            continue
        # Don't merge into a heading-shaped previous paragraph
        if is_uppercase_heading(prev):
            merged.append(p)
            continue
        last = prev[-1]
        first = nxt[:1]
        terminal = '.!?"”\')»…'
        # Soft hyphen / hyphen at end → join without space
        if last in '­-' and first.islower():
            merged[-1] = prev[:-1] + nxt
            continue
        # No terminal punctuation, next starts lowercase → continuation
        if last not in terminal and first.islower():
            merged[-1] = prev + ' ' + nxt
            continue
        # Previous ends with comma/colon/semicolon and next starts lowercase
        if last in ',;:' and first.islower():
            merged[-1] = prev + ' ' + nxt
            continue
        merged.append(p)
    return merged


def promote_headings(paragraphs: list[str]) -> list[str]:
    """Convert ALL-CAPS short paragraphs (likely subheadings) to `## Title`."""
    out: list[str] = []
    for p in paragraphs:
        if is_uppercase_heading(p):
            title = to_title_case_es(p.strip().rstrip('.'))
            out.append(f'## {title}')
        else:
            out.append(p)
    return out


def fold_prefacio_suelto(paragraphs: list[str], section_title: str) -> list[str]:
    """If the first paragraph after the H1 is just 'Prefacio' or 'Introducción',
    drop it (it duplicates the section H1). Also fold a second occurrence
    later in the file into a `## Heading` if it's a real internal divider."""
    if not paragraphs:
        return paragraphs
    title_l = section_title.lower()
    drops = ('prefacio', 'introducción', 'introduccion', 'prólogo', 'prologo')
    while paragraphs:
        first = paragraphs[0].strip().lower().rstrip('.')
        if first in drops and any(d in title_l for d in drops):
            paragraphs.pop(0)
        else:
            break
    return paragraphs


_PAGE_STUCK_MID = re.compile(r'(\w+)-\s+\d{1,3}\.?\s+\d{0,3}\s+([a-záéíóúüñ])')
_PAGE_STUCK_MID_SIMPLE = re.compile(r'(\w+)-\s+\d{1,3}\s+([a-záéíóúüñ])')


def clean_inline_pagenums(p: str) -> str:
    """Remove page-number residue stuck inside a hyphenated word break.
    Patterns like `comen- 2. 26 la` → `comenza la` (we drop the digits and
    rejoin the broken word, keeping the digits-side hint as best-effort)."""
    # `word- N. M next` → `word-next` (drop the digits, rejoin hyphen)
    p = _PAGE_STUCK_MID.sub(r'\1\2', p)
    p = _PAGE_STUCK_MID_SIMPLE.sub(r'\1\2', p)
    return p


def render_section(
    title: str, page_start: int, page_end: int | None,
    head_patterns: list[re.Pattern[str]],
    ocr_fixes: list[tuple[re.Pattern[str], str]],
    pages_cache: list[str],
) -> str:
    if page_end is None:
        page_end = len(pages_cache)
    selected = pages_cache[page_start - 1:page_end]

    all_paragraphs: list[str] = []
    for page in selected:
        paras = page_to_paragraphs(page, head_patterns)
        paras = [join_paragraph_text(p) for p in paras]

        if all_paragraphs and paras:
            tail = all_paragraphs[-1].rstrip()
            head = paras[0].lstrip()
            tail_end = tail[-1:] if tail else ''
            ends_open = tail_end not in '.!?"”\')»'
            # Don't merge across an ALL-CAPS heading (chapter title pages)
            if (ends_open and tail and head
                and not is_uppercase_heading(tail)
                and not is_uppercase_heading(head)):
                if tail.endswith('­') or tail.endswith('-'):
                    merged = tail[:-1] + head
                else:
                    merged = tail + ' ' + head
                all_paragraphs[-1] = merged
                paras = paras[1:]
        all_paragraphs.extend(paras)

    norm_title = re.sub(r'\s+', ' ', title.lower())
    norm_title_short = re.sub(r'^(i{1,3}|iv|v|vi|vii|viii|ix|x{1,3})\.?\s*', '', norm_title)
    while all_paragraphs:
        first = re.sub(r'\s+', ' ', all_paragraphs[0].lower().strip())
        if first == norm_title.strip() or first == norm_title_short.strip():
            all_paragraphs.pop(0)
        else:
            break

    fixed: list[str] = []
    for p in all_paragraphs:
        if is_garbage_paragraph(p):
            continue
        m = _LEAD_PAGENUM.match(p)
        if m:
            p = p[m.start(1):]
        # Strip leading non-alpha junk (e.g. "* facilitó" residue)
        p = re.sub(r'^[\*\+\-•·\.\s]+(?=[A-ZÁÉÍÓÚÑa-záéíóúñ¡¿«])', '', p, count=1)
        p = clean_inline_pagenums(p)
        fixed.append(p)
    all_paragraphs = fixed

    if ocr_fixes:
        all_paragraphs = [apply_ocr_fixes(p, ocr_fixes) for p in all_paragraphs]

    all_paragraphs = fold_prefacio_suelto(all_paragraphs, title)
    all_paragraphs = merge_broken_paragraphs(all_paragraphs)

    # Second pass of OCR fixes after merge — captures patterns that span
    # previously-broken paragraph boundaries (e.g. running-head debris glued
    # to body text once the broken-paragraph merger runs).
    if ocr_fixes:
        all_paragraphs = [apply_ocr_fixes(p, ocr_fixes) for p in all_paragraphs]

    all_paragraphs = promote_headings(all_paragraphs)

    body = '\n\n'.join(p for p in all_paragraphs if p.strip())
    return f'# {title}\n\n{body}\n'


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('plan', type=Path, help='Path to plan JSON file')
    parser.add_argument('--pdf', type=Path, help='Override source PDF path')
    parser.add_argument('--out', type=Path, help='Output directory')
    parser.add_argument('--dry-run', action='store_true', help='Preview only')
    parser.add_argument('--only', type=str, help='Process only sections whose title contains this substring')
    args = parser.parse_args()

    require_tool('pdftotext')
    require_tool('pdfinfo')

    plan = json.loads(args.plan.read_text(encoding='utf-8'))
    plan_dir = args.plan.parent.resolve()

    pdf_path: Path
    if args.pdf:
        pdf_path = args.pdf
    elif 'source' in plan:
        pdf_path = Path(plan['source'])
        if not pdf_path.is_absolute():
            pdf_path = (plan_dir / pdf_path).resolve()
    else:
        sys.exit("error: plan must include 'source' or pass --pdf")
    if not pdf_path.is_file():
        sys.exit(f"error: PDF not found: {pdf_path}")

    output_dir = args.out or Path(plan.get('output_dir', 'markdown'))
    if not output_dir.is_absolute():
        output_dir = (plan_dir / output_dir).resolve()

    head_patterns = [re.compile(p, re.IGNORECASE) for p in plan.get('running_heads', [])]
    raw_fixes = plan.get('ocr_fixes', [])
    ocr_fixes: list[tuple[re.Pattern[str], str]] = []
    for entry in raw_fixes:
        if isinstance(entry, list) and len(entry) == 2:
            # case-sensitive by default; authors can prepend `(?i)` to a pattern
            # if they need case-insensitive matching for that fix.
            ocr_fixes.append((re.compile(entry[0]), entry[1]))

    sections = plan.get('sections', [])
    if not sections:
        sys.exit("error: plan has no 'sections'")

    print(f'Plan    : {args.plan}')
    print(f'PDF     : {pdf_path}')
    print(f'Output  : {output_dir}')
    print(f'Sections: {len(sections)}')
    print(f'Fixes   : {len(ocr_fixes)} OCR patterns')
    print()

    width = max(2, len(str(len(sections))))
    plans: list[tuple[Path, str, int, int | None]] = []
    for i, sec in enumerate(sections):
        title = sec['title']
        if args.only and args.only.lower() not in title.lower():
            continue
        slug = sec.get('slug') or f'{str(i+1).zfill(width)}_{slugify(title)}'
        pages = sec.get('pages')
        if pages:
            p_start = pages[0]
            p_end = pages[1] if len(pages) > 1 else None
        else:
            p_start, p_end = 1, None
        out_path = output_dir / f'{slug}.md'
        plans.append((out_path, title, p_start, p_end))
        end_str = str(p_end) if p_end is not None else 'end'
        print(f'  [{i:02d}] p.{p_start}-{end_str} -> {out_path.name}')

    if args.dry_run:
        return 0

    print('\nLoading PDF text…')
    pages_cache = extract_pages(pdf_path)
    print(f'  {len(pages_cache)} pages extracted')

    output_dir.mkdir(parents=True, exist_ok=True)
    print()
    for out_path, title, p_start, p_end in plans:
        md = render_section(title, p_start, p_end, head_patterns, ocr_fixes, pages_cache)
        out_path.write_text(md, encoding='utf-8')
        wc = len(md.split())
        print(f'  wrote {out_path.name} ({wc} words, {len(md)} chars)')

    print(f'\nDone. {len(plans)} files written to {output_dir}')
    return 0


if __name__ == '__main__':
    sys.exit(main())

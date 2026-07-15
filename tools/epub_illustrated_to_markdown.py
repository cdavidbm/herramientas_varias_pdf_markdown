#!/usr/bin/env python3
"""
epub_illustrated_to_markdown.py — convert an image-heavy EPUB (music theory,
science diagrams, etc.) to clean per-section markdown with figures EXPORTED
and EMBEDDED.

Built for books where:
  * block figures live in <div class="illustype_image_text"> with a sibling
    <div class="caption"> (rendered as ![caption](images/FILE)).
  * inline musical/symbol glyphs are tiny <span class="imageinline"><img
    alt="..._img_NNNN.gif"> images whose filename encodes a Unicode codepoint
    (NNNN decimal) — these are converted to the real Unicode character
    (img_9837 -> chr(9837) -> '♭').
  * headings carry classes like title-chapter / title-section1 / title-section2.

Reads spine order straight from the OPF. No plan.json needed.

Usage:
  python3 epub_illustrated_to_markdown.py <epub> <out_dir> [--combined]
"""
import sys, re, shutil, zipfile, tempfile, html
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Tag

from forja_common import slugify

# ---- heading class -> markdown level ----------------------------------------
H1 = {"title-chapter", "title-appendix", "title-glossary", "title-forewordPage",
      "title-acknowPage", "title-aboutAuthorPage", "title-toc"}
H2 = {"title-section1"}
H3 = {"title-section2"}
H4 = {"title-box", "subtitle-section1"}

SKIP_SPINE_KEYS = {"cov01", "cop01", "toc01", "toc", "tp01", "ftn01"}
# cover img, copyright, dup TOC, title-page image, standalone footnote pool
# (footnotes are resolved inline into each chapter's ## Notes)


def heading_level(classes):
    for c in classes:
        if c in H1: return 1
        if c in H2: return 2
        if c in H3: return 3
        if c in H4: return 4
    return None


class Converter:
    def __init__(self, src_root, img_out_dir, img_rel="images"):
        self.src_root = src_root          # OEBPS dir (where html + images/ live)
        self.img_out_dir = img_out_dir    # absolute dir to copy figures into
        self.img_rel = img_rel            # path prefix used in markdown
        self.exported = set()
        self.figmap = {}                  # not used yet

    # -- image helpers --------------------------------------------------------
    def _inline_glyph(self, img):
        """Return Unicode char for an inline glyph image, or None."""
        alt = img.get("alt", "") + " " + img.get("src", "")
        m = re.search(r"_img_(\d+)\.(?:gif|png|jpg)", alt)
        if m:
            try:
                return chr(int(m.group(1)))
            except ValueError:
                return None
        return None

    def _export_figure(self, img):
        """Copy a block figure image and return its markdown-relative path."""
        src = img.get("src", "")
        name = Path(src).name
        srcpath = (self.src_root / src).resolve()
        if not srcpath.exists():
            # try images/ dir
            srcpath = (self.src_root / "images" / name)
        if srcpath.exists() and name not in self.exported:
            shutil.copy2(srcpath, self.img_out_dir / name)
            self.exported.add(name)
        return f"{self.img_rel}/{name}"

    # -- inline (text-level) conversion --------------------------------------
    def inline(self, node):
        out = []
        for c in node.children:
            if isinstance(c, NavigableString):
                out.append(str(c))
            elif isinstance(c, Tag):
                if c.name == "img":
                    g = self._inline_glyph(c)
                    out.append(g if g is not None else "")
                elif c.name == "br":
                    out.append("  \n")
                elif c.name in ("span",):
                    cls = c.get("class", [])
                    if "imageinline" in cls:
                        img = c.find("img")
                        if img:
                            g = self._inline_glyph(img)
                            out.append(g if g is not None else "")
                        else:
                            out.append(self.inline(c))
                    elif "b" in cls or "bold" in cls:
                        inner = self.inline(c).strip()
                        out.append(f"**{inner}**" if inner else "")
                    elif "i" in cls or "italic" in cls:
                        inner = self.inline(c).strip()
                        out.append(f"*{inner}*" if inner else "")
                    else:
                        out.append(self.inline(c))
                elif c.name in ("b", "strong"):
                    inner = self.inline(c).strip()
                    out.append(f"**{inner}**" if inner else "")
                elif c.name in ("i", "em"):
                    inner = self.inline(c).strip()
                    out.append(f"*{inner}*" if inner else "")
                elif c.name == "sup":
                    a = c.find("a")
                    href = (a.get("href") if a else "") or ""
                    if "ftn01" in href:
                        out.append(f"[^{a.get_text(strip=True)}]")
                    else:
                        out.append(f"^{self.inline(c).strip()}")
                elif c.name == "a":
                    href = c.get("href", "")
                    if "ftn01" in href:
                        out.append(f"[^{c.get_text(strip=True)}]")
                    else:  # internal cross-ref -> plain text
                        out.append(self.inline(c))
                else:
                    out.append(self.inline(c))
        return "".join(out)

    # -- block-level conversion ----------------------------------------------
    def _figure(self, div):
        """Render an illustype_image_text block."""
        img = div.find("img")
        if not img:
            return ""
        path = self._export_figure(img)
        cap_div = div.find("div", class_="caption")
        caption = ""
        if cap_div:
            caption = self.inline(cap_div).strip()
        alt = caption or img.get("alt", "figure")
        line = f"![{alt}]({path})"
        if caption:
            line += f"\n\n*{caption}*"
        return line

    def _table(self, table):
        rows = table.find_all("tr")
        if not rows:
            return ""
        md = []
        ncols = 0
        grid = []
        for tr in rows:
            cells = tr.find_all(["td", "th"])
            row = []
            for cell in cells:
                txt = self._cell(cell)
                row.append(txt)
            ncols = max(ncols, len(row))
            grid.append(row)
        if ncols == 0:
            return ""
        for r in grid:
            r += [""] * (ncols - len(r))
        md.append("| " + " | ".join(grid[0]) + " |")
        md.append("| " + " | ".join(["---"] * ncols) + " |")
        for r in grid[1:]:
            md.append("| " + " | ".join(r) + " |")
        return "\n".join(md)

    def _cell(self, cell):
        parts = []
        for ch in cell.children:
            if isinstance(ch, Tag) and ch.name == "img" and "imageinline" not in (ch.parent.get("class", []) if ch.parent else []):
                g = self._inline_glyph(ch)
                if g is not None:
                    parts.append(g)
                else:
                    parts.append(f"![]({self._export_figure(ch)})")
            else:
                if isinstance(ch, Tag) and ch.find("img") and "illustype" in " ".join(ch.get("class", [])):
                    img = ch.find("img")
                    parts.append(f"![]({self._export_figure(img)})")
                else:
                    t = self.inline(ch) if isinstance(ch, Tag) else str(ch)
                    parts.append(t)
        txt = "".join(parts)
        txt = txt.replace("\n", " ").strip()
        txt = re.sub(r"\s+", " ", txt)
        return txt.replace("|", "\\|")

    def block(self, node, out):
        """Recurse over block-level structure, appending markdown strings."""
        for c in node.children:
            if isinstance(c, NavigableString):
                t = str(c).strip()
                if t:
                    out.append(t)
                continue
            if not isinstance(c, Tag):
                continue
            cls = c.get("class", [])
            clsname = " ".join(cls)

            # headings
            if c.name in ("h1", "h2", "h3", "h4", "h5", "h6"):
                lvl = heading_level(cls) or int(c.name[1])
                txt = self.inline(c).strip()
                txt = re.sub(r"\s+", " ", txt)
                txt = txt.replace("*", "").strip()  # no bold/italic inside ATX headings
                if txt:
                    out.append("#" * lvl + " " + txt)
                continue

            # figure block
            if "illustype_image_text" in cls or "illustype" in clsname:
                fig = self._figure(c)
                if fig:
                    out.append(fig)
                continue

            # caption that is standalone (handled inside figure normally) -> skip
            if "caption" in cls:
                continue

            # tables
            if c.name == "table":
                t = self._table(c)
                if t:
                    out.append(t)
                continue

            # lists
            if c.name in ("ul", "ol"):
                items = []
                for i, li in enumerate(c.find_all("li", recursive=False), 1):
                    bullet = "- " if c.name == "ul" else f"{i}. "
                    items.append(bullet + re.sub(r"\s+", " ", self.inline(li).strip()))
                if items:
                    out.append("\n".join(items))
                continue

            # paragraphs
            if c.name == "p":
                if "p-blanc" in clsname:   # spacer paragraphs
                    continue
                txt = self.inline(c).strip()
                txt = re.sub(r"[ \t]+\n", "\n", txt)
                txt = re.sub(r"[ \t]{2,}", " ", txt)
                if txt.strip():
                    out.append(txt)
                continue

            # block image not wrapped in illustype
            if c.name == "img":
                g = self._inline_glyph(c)
                if g is None:
                    out.append(f"![]({self._export_figure(c)})")
                continue

            # divs / sections -> recurse
            if c.name in ("div", "section", "blockquote", "body"):
                self.block(c, out)
                continue

            # fallthrough: recurse
            self.block(c, out)

    def convert_file(self, path):
        soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="replace"), "html.parser")
        body = soup.body or soup
        out = []
        self.block(body, out)
        # collapse, dedupe blanks
        md = "\n\n".join(s.strip() for s in out if s.strip())
        md = re.sub(r"\n{3,}", "\n\n", md)
        return md


def load_footnotes(src_root, conv):
    f = src_root / [p.name for p in src_root.glob("*ftn01.html")][0] if list(src_root.glob("*ftn01.html")) else None
    notes = {}
    if not f:
        return notes
    soup = BeautifulSoup(f.read_text(encoding="utf-8", errors="replace"), "html.parser")
    for div in soup.find_all("div", class_="footnote"):
        a = div.find("a")
        num = a.get_text(strip=True) if a else None
        p = div.find("p")
        body = conv.inline(p).strip() if p else ""
        if num:
            notes[num] = re.sub(r"\s+", " ", body)
    return notes


def main():
    if len(sys.argv) < 3:
        print(__doc__); sys.exit(1)
    epub = Path(sys.argv[1]).resolve()
    out_dir = Path(sys.argv[2]).resolve()
    combined = "--combined" in sys.argv[3:]

    tmp = Path(tempfile.mkdtemp(prefix="epub_ill_"))
    with zipfile.ZipFile(epub) as z:
        z.extractall(tmp)

    # locate OPF
    container = tmp / "META-INF" / "container.xml"
    opf_rel = re.search(r'full-path="([^"]+)"', container.read_text()).group(1)
    opf = tmp / opf_rel
    src_root = opf.parent
    opf_txt = opf.read_text(encoding="utf-8", errors="replace")

    # manifest id -> href
    manifest = dict(re.findall(r'<item[^>]*id="([^"]+)"[^>]*href="([^"]+)"', opf_txt))
    manifest2 = dict(re.findall(r'<item[^>]*href="([^"]+)"[^>]*id="([^"]+)"', opf_txt))
    for href, id_ in manifest2.items():
        manifest.setdefault(id_, href)
    spine = re.findall(r'<itemref[^>]*idref="([^"]+)"', opf_txt)

    out_dir.mkdir(parents=True, exist_ok=True)
    img_out = out_dir / "images"
    img_out.mkdir(exist_ok=True)

    conv = Converter(src_root, img_out)
    notes = load_footnotes(src_root, conv)

    combined_parts = []
    idx = 0
    for sid in spine:
        href = manifest.get(sid)
        if not href:
            continue
        key = re.sub(r".*_", "", Path(href).stem)
        if key in SKIP_SPINE_KEYS:
            continue
        path = (src_root / href)
        if not path.exists():
            continue
        md = conv.convert_file(path)
        if not md.strip():
            continue
        # attach footnotes used in this file
        used = sorted(set(re.findall(r"\[\^(\d+)\]", md)), key=int)
        if used:
            md += "\n\n## Notes\n\n" + "\n\n".join(
                f"[^{n}]: {notes.get(n,'')}" for n in used)
        # title for filename
        first_h = re.search(r"^#\s+(.+)$", md, re.M)
        title = first_h.group(1) if first_h else key
        title = re.sub(r"[*`]", "", title)
        fname = f"{idx:02d}_{slugify(title, 50, lower=True, fallback=key)}.md"
        (out_dir / fname).write_text(md + "\n", encoding="utf-8")
        combined_parts.append(md)
        print(f"  {fname}  ({len(md.split())} words)")
        idx += 1

    if combined:
        (out_dir / "modalogy_full.md").write_text(
            "\n\n---\n\n".join(combined_parts) + "\n", encoding="utf-8")
        print(f"  modalogy_full.md  (combined)")

    print(f"\nFigures exported: {len(conv.exported)}  ->  {img_out}")
    print(f"Output: {out_dir}")
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()

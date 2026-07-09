#!/usr/bin/env python3
"""
book_index.py — Índice de búsqueda full-text LOCAL sobre una carpeta de markdown.

Convierte una carpeta de libros convertidos (.md por capítulo) en algo
consultable al instante: recupera los pasajes más relevantes a una consulta,
con su ubicación (archivo › encabezado) y un fragmento. Así el agente lee SOLO
lo relevante en vez del libro entero — ahorra tokens SIN perder calidad.

Motor: SQLite FTS5 (viene con Python; sin instalar nada). Insensible a acentos.
El índice se guarda como `.forja_index.db` DENTRO de la carpeta indexada
(git-ignóralo). Se reconstruye solo si faltan archivos o cambian.

Uso:
    python3 book_index.py build  <carpeta> [--exts .md,.txt]
    python3 book_index.py query  <carpeta> "melancolía saturnina" [--top 8]
    python3 book_index.py status <carpeta>

`query` construye el índice automáticamente si no existe o está desactualizado.
"""
from __future__ import annotations
import argparse
import re
import sqlite3
import sys
from pathlib import Path

DB_NAME = ".forja_index.db"
HEADING = re.compile(r'^(#{1,6})\s+(.*)')


def db_path(folder: Path) -> Path:
    return folder / DB_NAME


def iter_files(folder: Path, exts: list[str]):
    for p in sorted(folder.rglob("*")):
        if p.is_file() and p.suffix.lower() in exts and p.name != DB_NAME:
            yield p


def passages(text: str):
    """Parte un markdown en (encabezado_actual, párrafo). Granularidad útil."""
    heading = ""
    buf: list[str] = []
    for line in text.splitlines():
        m = HEADING.match(line)
        if m:
            if buf:
                yield heading, "\n".join(buf).strip(); buf = []
            heading = m.group(2).strip()
            continue
        if not line.strip():
            if buf:
                yield heading, "\n".join(buf).strip(); buf = []
        else:
            buf.append(line)
    if buf:
        yield heading, "\n".join(buf).strip()


def fingerprint(folder: Path, exts: list[str]) -> str:
    """Huella de la carpeta (rutas + mtime + tamaño) para detectar cambios."""
    parts = [f"{p.relative_to(folder)}:{p.stat().st_mtime_ns}:{p.stat().st_size}"
             for p in iter_files(folder, exts)]
    return "|".join(parts)


def build(folder: Path, exts: list[str], quiet: bool = False) -> int:
    db = sqlite3.connect(db_path(folder))
    db.executescript("""
        DROP TABLE IF EXISTS docs;
        CREATE VIRTUAL TABLE docs USING fts5(
            path UNINDEXED, heading UNINDEXED, body,
            tokenize = 'unicode61 remove_diacritics 2'
        );
        CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
    """)
    n_files = n_pass = 0
    for f in iter_files(folder, exts):
        rel = str(f.relative_to(folder))
        text = f.read_text(encoding="utf-8", errors="replace")
        rows = [(rel, h, b) for h, b in passages(text) if len(b) > 15]
        db.executemany("INSERT INTO docs(path, heading, body) VALUES (?,?,?)", rows)
        n_files += 1; n_pass += len(rows)
    db.execute("INSERT OR REPLACE INTO meta VALUES ('fingerprint', ?)",
               (fingerprint(folder, exts),))
    db.execute("INSERT OR REPLACE INTO meta VALUES ('exts', ?)", (",".join(exts),))
    db.commit(); db.close()
    if not quiet:
        print(f"Índice construido: {n_files} archivo(s), {n_pass} pasaje(s) → {db_path(folder).name}")
    return n_pass


def is_fresh(folder: Path, exts: list[str]) -> bool:
    if not db_path(folder).is_file():
        return False
    try:
        db = sqlite3.connect(db_path(folder))
        cur = db.execute("SELECT v FROM meta WHERE k='fingerprint'").fetchone()
        db.close()
        return bool(cur) and cur[0] == fingerprint(folder, exts)
    except sqlite3.Error:
        return False


def query(folder: Path, terms: str, top: int, exts: list[str]) -> int:
    if not is_fresh(folder, exts):
        build(folder, exts, quiet=True)
    db = sqlite3.connect(db_path(folder))
    # Consulta FTS5: por defecto OR entre términos, ranking bm25.
    q = " OR ".join(re.findall(r'\w+', terms, flags=re.UNICODE)) or terms
    try:
        rows = db.execute(
            """SELECT path, heading,
                      snippet(docs, 2, '»', '«', '…', 12) AS snip,
                      bm25(docs) AS score
               FROM docs WHERE docs MATCH ?
               ORDER BY score LIMIT ?""",
            (q, top),
        ).fetchall()
    except sqlite3.OperationalError as e:
        db.close(); sys.exit(f"error de consulta FTS: {e}")
    db.close()

    print(f"== Índice de «{folder.name}» · consulta: {terms} · {len(rows)} resultado(s) ==\n")
    if not rows:
        print("   sin resultados — prueba sinónimos o términos más generales")
        return 0
    for path, heading, snip, _score in rows:
        loc = f"{path}" + (f" › {heading}" if heading else "")
        snip = re.sub(r'\s+', ' ', snip).strip()
        print(f"• {loc}\n    …{snip}…\n")
    print("(Lee los archivos citados para el contexto completo y sintetiza con la ubicación.)")
    return len(rows)


def status(folder: Path, exts: list[str]) -> int:
    fresh = is_fresh(folder, exts)
    exists = db_path(folder).is_file()
    print(f"Carpeta: {folder}")
    print(f"Índice:  {'existe' if exists else 'no existe'} | {'al día' if fresh else 'desactualizado/ausente'}")
    if exists:
        db = sqlite3.connect(db_path(folder))
        n = db.execute("SELECT count(*) FROM docs").fetchone()[0]
        db.close()
        print(f"Pasajes indexados: {n}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["build", "query", "status"])
    ap.add_argument("folder", type=Path)
    ap.add_argument("terms", nargs="?", default="")
    ap.add_argument("--exts", default=".md,.txt", help="extensiones a indexar (coma)")
    ap.add_argument("--top", type=int, default=8)
    args = ap.parse_args()

    exts = [e if e.startswith(".") else "." + e for e in args.exts.split(",")]
    if not args.folder.is_dir():
        sys.exit(f"error: no existe la carpeta {args.folder}")

    if args.cmd == "build":
        build(args.folder, exts)
    elif args.cmd == "status":
        status(args.folder, exts)
    else:
        if not args.terms:
            sys.exit("error: 'query' necesita términos de búsqueda")
        query(args.folder, args.terms, args.top, exts)
    return 0


if __name__ == "__main__":
    sys.exit(main())

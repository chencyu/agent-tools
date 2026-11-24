#!/usr/bin/env python3
"""spec-query engine — structured, multi-format spec extraction into a mirrored cache.

Design
------
- SOURCE OF TRUTH: read-only documents under references/source/, reached through the symlinks
  `add-source` creates to real spec roots. Never written to.
- CACHE (regenerable): references/cache/<rel dir under source/>/<doc-stem>/ holds all
  derived artifacts + a manifest.json. Safe to delete; rebuilt by `sync`.

Extraction per format (precision/correctness/coverage first, cost no object):
- .docx  -> pandoc html5 (structured.html: faithful merged/nested tables via rowspan/colspan)
          + pandoc gfm  (content.md: prose+tables for search & LLM reading)
          + --extract-media (media/: raw embedded figure files)
- .pdf   -> pymupdf4llm per-page (pages/NNNNN.md) + 200 DPI render (pages/NNNNN.jpg), the
          viewable source for diagrams/figures.
- .pptx/.xlsx -> markitdown (content.md).

Every manifest records source identity (path + sha256) so answers can cite the document's
OWN figure numbers (pre-ratification docx and ratified pdf may differ).

Subcommands: add-source | sync | extract | catalog | status   (see -h).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import functools
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPTS_DIR.parent
REF_DIR = SKILL_DIR / "references"
SRC_DIR = REF_DIR / "source"
CACHE_DIR = REF_DIR / "cache"
CONFIG_PATH = SCRIPTS_DIR / "specquery_config.json"

FIG_RE = re.compile(r"^\s*(Figure|Table)\s+([0-9]+[A-Za-z]?)\s*[:.\u2013-]?\s*(.*)$")

# Without Windows long-path support, Win32 rejects a file path of MAX_PATH characters or more
# and a directory path longer than MAX_PATH - 12. The failure surfaces differently in each
# library (FileNotFoundError, WinError 206, MuPDF's own errors), so paths are checked up front.
MAX_PATH = 260
MAX_PATH_EXIT = 3
max_path_blocked: list[str] = []

# Without Developer Mode (or administrator rights), Windows refuses to create symlinks.
ERROR_PRIVILEGE_NOT_HELD = 1314
DEVELOPER_MODE_EXIT = 4


def prompt_developer_setting(tag: str, setting: str, reason: str) -> None:
    """Open the Windows developer settings page and tell whoever runs the command what to turn on there."""
    os.startfile("ms-settings:developers")
    print(f"[{tag}] Opened the Windows developer settings page (ms-settings:developers) automatically;"
          f" turn on {setting} there, then rerun. {reason}")


@functools.cache  # Windows itself reads the setting once per process.
def long_paths_enabled() -> bool:
    if sys.platform != "win32":
        return True
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SYSTEM\CurrentControlSet\Control\FileSystem") as key:
            return winreg.QueryValueEx(key, "LongPathsEnabled")[0] == 1
    except OSError:
        return False


def exceeds_max_path(files: Iterable[Path], dirs: Iterable[Path] = ()) -> bool:
    if long_paths_enabled():
        return False
    return any(len(str(f)) >= MAX_PATH for f in files) or any(len(str(d)) > MAX_PATH - 12 for d in dirs)


def extraction_exceeds_max_path(src: Path, outdir: Path) -> bool:
    # No fixed artifact name is longer than these; media file names come from inside the docx.
    files = (src, outdir / "structured.html", outdir / "pages" / "00000.jpg")
    return exceeds_max_path(files, dirs=(outdir / "pages", outdir / "media"))


# ----------------------------- helpers -----------------------------------
def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        sys.exit(f"[FATAL] missing config: {CONFIG_PATH}")
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def sha256(path: Path, buf: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(buf), b""):
            h.update(chunk)
    return h.hexdigest()


def find_pandoc() -> str | None:
    exe = shutil.which("pandoc")
    if exe:
        return exe
    for c in (Path.home() / "scoop/shims/pandoc.exe", Path("C:/Program Files/Pandoc/pandoc.exe")):
        if c.exists():
            return str(c)
    return None


def ensure_pandoc() -> str | None:
    """Return pandoc's path, installing it through scoop first when scoop is available."""
    pandoc = find_pandoc()
    scoop = shutil.which("scoop")
    if not pandoc and scoop:
        print("[BOOTSTRAP] Installing pandoc via scoop...")
        subprocess.run([scoop, "install", "pandoc"], capture_output=True)
        pandoc = find_pandoc()
    if not pandoc:
        print("[WARN] pandoc not found; .docx will be skipped. Install it: https://pandoc.org/installing.html")
    return pandoc


def _pandoc_version(pandoc: str) -> str:
    try:
        out = subprocess.run([pandoc, "--version"], capture_output=True, text=True, timeout=30)
        return out.stdout.splitlines()[0].strip() if out.stdout else "pandoc"
    except Exception:
        return "pandoc"


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


# ----------------------------- docx parsing ------------------------------
def _soup(html: str):
    from bs4 import BeautifulSoup

    try:
        return BeautifulSoup(html, "lxml")
    except Exception:
        return BeautifulSoup(html, "html.parser")


def _fig_sortkey(f: dict):
    m = re.match(r"(\d+)(.*)", f.get("num", ""))
    return (int(m.group(1)) if m else 1 << 30, m.group(2) if m else f.get("num", ""))


def parse_structure(html_path: Path) -> dict:
    """Extract a figure/table catalog + heading outline from pandoc html5 output.

    Two caption sources (both matter for coverage):
      - TABLE figures: caption is the table's first header cell (e.g. 'Figure 91: ...'),
        tagged as='table' (has structured rowspan/colspan content in structured.html).
      - IMAGE/diagram figures: caption is a standalone <p> (e.g. 'Figure 11: ...'),
        tagged as='image' (viewed on the sibling PDF's page render).
    Table-of-Contents entries (a <p> containing an intra-doc <a href="#...">) are skipped.
    Headings become the section outline.
    """
    soup = _soup(html_path.read_text(encoding="utf-8", errors="replace"))
    figures: list[dict] = []
    seen: set[str] = set()

    def add(text: str, as_kind: str) -> None:
        m = FIG_RE.match(text)
        if not m:
            return
        key = f"{m.group(1)} {m.group(2)}"
        if key in seen:
            return
        seen.add(key)
        figures.append({"label": key, "kind": m.group(1), "num": m.group(2),
                        "title": m.group(3)[:200], "as": as_kind})

    # 1) table-figures (authoritative structured tables)
    for tbl in soup.find_all("table"):
        cell = tbl.find(["th", "td"])
        if cell:
            add(" ".join(cell.get_text(" ", strip=True).split()), "table")
    # 2) image/diagram figures (standalone captions; skip TOC links)
    for p in soup.find_all("p"):
        if p.find("a", href=True):
            continue
        add(" ".join(p.get_text(" ", strip=True).split()), "image")

    figures.sort(key=_fig_sortkey)
    headings = [{"level": int(h.name[1]), "text": " ".join(h.get_text(" ", strip=True).split())[:200]}
                for h in soup.find_all(re.compile(r"^h[1-6]$"))]
    return {
        "figures": figures,
        "headings": headings,
        "counts": {
            "tables": len(soup.find_all("table")),
            "rowspan": len(soup.find_all(attrs={"rowspan": True})),
            "colspan": len(soup.find_all(attrs={"colspan": True})),
            "fig_table": sum(1 for f in figures if f["as"] == "table"),
            "fig_image": sum(1 for f in figures if f["as"] == "image"),
        },
    }


# ----------------------------- extractors --------------------------------
def _finalize_media(outdir: Path) -> int:
    """Flatten pandoc's media subtree to <outdir>/media/ and return its file count.

    pandoc may nest images (e.g. media/media/imageN); collapse to a single level so
    refs are stable.
    """
    media = outdir / "media"
    if not media.exists():
        return 0
    for p in list(media.rglob("*")):
        if p.is_file() and p.parent != media:
            dest = media / p.name
            if not dest.exists():
                shutil.move(str(p), str(dest))
    for d in sorted((d for d in media.rglob("*") if d.is_dir()), key=lambda x: len(x.parts), reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass
    return sum(1 for p in media.glob("*") if p.is_file())


def extract_docx(src: Path, outdir: Path, pandoc: str) -> dict:
    outdir.mkdir(parents=True, exist_ok=True)
    html_out = outdir / "structured.html"
    md_out = outdir / "content.md"
    logs = []
    r1 = subprocess.run(
        [pandoc, str(src), "-f", "docx", "-t", "html5", f"--extract-media={outdir}", "-o", str(html_out)],
        capture_output=True, text=True,
    )
    if r1.returncode != 0:
        logs.append(f"pandoc html5 rc={r1.returncode}: {r1.stderr.strip()[:500]}")
    r2 = subprocess.run(
        [pandoc, str(src), "-f", "docx", "-t", "gfm", "-o", str(md_out)],
        capture_output=True, text=True,
    )
    if r2.returncode != 0:
        logs.append(f"pandoc gfm rc={r2.returncode}: {r2.stderr.strip()[:500]}")
    media_count = _finalize_media(outdir)
    struct = parse_structure(html_out) if html_out.exists() else {"figures": [], "headings": [], "counts": {}}
    return {
        "format": "docx",
        "tool": _pandoc_version(pandoc),
        "artifacts": {
            "content_md": "content.md" if md_out.exists() else None,
            "structured_html": "structured.html" if html_out.exists() else None,
            "media_dir": "media" if media_count else None,
            "pages_dir": None,
        },
        "figures": struct["figures"],
        "headings": struct["headings"],
        "counts": {**struct["counts"], "media": media_count, "figures": len(struct["figures"])},
        "logs": logs,
    }


def extract_pdf(src: Path, outdir: Path) -> dict:
    import pymupdf
    import pymupdf4llm

    pages_dir = outdir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    doc = pymupdf.open(str(src))
    try:
        chunks = pymupdf4llm.to_markdown(doc, page_chunks=True)
        for i, ch in enumerate(chunks, 1):
            (pages_dir / f"{i:05d}.md").write_text(ch.get("text", ""), encoding="utf-8")
        for i in range(len(doc)):
            doc[i].get_pixmap(dpi=200).save(str(pages_dir / f"{i + 1:05d}.jpg"))
        npages = len(doc)
    finally:
        doc.close()
    return {
        "format": "pdf",
        "tool": f"pymupdf4llm {getattr(pymupdf4llm, '__version__', '?')}",
        "artifacts": {"content_md": None, "structured_html": None, "media_dir": None, "pages_dir": "pages"},
        "figures": [],
        "headings": [],
        "counts": {"pages": npages},
        "logs": [],
    }


def extract_office(src: Path, outdir: Path) -> dict:
    from markitdown import MarkItDown

    outdir.mkdir(parents=True, exist_ok=True)
    md_out = outdir / "content.md"
    logs = []
    try:
        res = MarkItDown().convert(str(src))
        md_out.write_text(res.text_content, encoding="utf-8")
    except Exception as e:  # noqa: BLE001
        logs.append(f"markitdown error: {e!r}")
    return {
        "format": src.suffix.lstrip(".").lower(),
        "tool": "markitdown",
        "artifacts": {"content_md": "content.md" if md_out.exists() else None,
                      "structured_html": None, "media_dir": None, "pages_dir": None},
        "figures": [],
        "headings": [],
        "counts": {},
        "logs": logs,
    }


DISPATCH = {
    ".docx": "docx",
    ".pdf": "pdf",
    ".pptx": "office",
    ".xlsx": "office",
}


# The hash gate keys on the source alone, so a logged failure stays cached after its cause is fixed.
REUSED_FAILURE_HINT = ("^ reused from an earlier run because the source is unchanged; if the cause above is fixed"
                       " now (e.g. a missing tool or package was installed), rerun with --force")


def extract_one(src: Path, outdir: Path, rel: str, pandoc: str | None, force: bool) -> tuple[dict | None, bool]:
    """Return the document's manifest (None for an unsupported extension) and whether it was reused."""
    ext = src.suffix.lower()
    kind = DISPATCH.get(ext)
    if kind is None:
        return None, False
    manifest_path = outdir / "manifest.json"
    digest = sha256(src)
    if manifest_path.exists() and not force:
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
            if old.get("source", {}).get("sha256") == digest:
                return old, True
        except Exception:
            pass
    if kind == "docx":
        body = extract_docx(src, outdir, pandoc) if pandoc else {
            "format": "docx", "tool": None, "artifacts": {}, "figures": [], "headings": [],
            "counts": {}, "logs": ["pandoc not found; cannot extract docx"]}
    elif kind == "pdf":
        body = extract_pdf(src, outdir)
    else:
        body = extract_office(src, outdir)
    st = src.stat()
    manifest = {
        "source": {"path": str(src.resolve()), "rel": rel, "sha256": digest, "bytes": st.st_size,
                   "mtime": _dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")},
        "generated_at": _now(),
        **body,
    }
    write_json(manifest_path, manifest)
    return manifest, False


# ----------------------------- walking -----------------------------------
def iter_docs(base: Path, exts: set[str], skip_globs: list[str]):
    """Yield spec files anywhere under `base`, descending THROUGH symlinked source roots."""
    for dirpath, _dirs, files in os.walk(base, followlinks=True):
        for fn in files:
            p = Path(dirpath) / fn
            if p.suffix.lower() not in exts:
                continue
            if fn.startswith("~$") or any(p.match(g) for g in skip_globs):
                continue
            yield p


def cache_dir_for(f: Path) -> tuple[Path, str]:
    """Mirror <source>/<rel> -> <cache>/<rel-parent>/<stem>/ (rel is relative to source/)."""
    rel = f.relative_to(SRC_DIR)
    return CACHE_DIR / rel.parent / f.stem, str(rel).replace("\\", "/")


# ----------------------------- commands ----------------------------------
def build_catalog() -> dict:
    """Rebuild references/cache/catalog.json from every manifest under the cache."""
    docs = []
    # os.walk, not Path.rglob: rglob silently drops files whose path Win32 rejects for its length.
    manifests = sorted(Path(d) / "manifest.json" for d, _, files in os.walk(CACHE_DIR) if "manifest.json" in files)
    for mf in manifests:
        if exceeds_max_path([mf]):
            max_path_blocked.append(str(mf))
            continue
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue
        src = m.get("source", {})
        title = Path(src.get("rel") or mf.parent.name).stem
        docs.append({
            "rel": src.get("rel"),
            "cache": str(mf.parent.relative_to(CACHE_DIR)).replace("\\", "/"),
            "format": m.get("format"),
            "title": title,
            "figures": m.get("counts", {}).get("figures", len(m.get("figures", []))),
            "tables": m.get("counts", {}).get("tables"),
            "pages": m.get("counts", {}).get("pages"),
            "sha256": (src.get("sha256") or "")[:12],
        })
    catalog = {"generated_at": _now(), "count": len(docs), "documents": docs}
    write_json(CACHE_DIR / "catalog.json", catalog)
    return catalog


def cmd_sync(args) -> None:
    cfg = load_config()
    exts = {e.lower() for e in cfg["extract"]["extensions"]}
    skip = cfg["extract"].get("skip_glob", [])
    pandoc = ensure_pandoc() if ".docx" in exts else None
    base = SRC_DIR
    if args.path:
        p = Path(args.path)
        base = p if p.is_absolute() else SRC_DIR / args.path
    if not base.exists():
        sys.exit(f"[FATAL] path not found: {base}")
    if base != SRC_DIR and SRC_DIR not in base.parents:
        sys.exit("[FATAL] sync scans references/source/. Pass a subpath of it, or use `extract` for a one-off file.")
    files = list(iter_docs(base, exts, skip))
    if args.limit:
        files = files[: args.limit]
    print(f"[SYNC] {len(files)} document(s) under {base}")
    n_ok = n_err = 0
    for f in files:
        outdir, rel = cache_dir_for(f)
        if extraction_exceeds_max_path(f, outdir):
            max_path_blocked.append(str(f))
            continue
        try:
            m, reused = extract_one(f, outdir, rel, pandoc, args.force)
            if m is None:
                continue
            logs = m.get("logs") or []
            ok = not (logs and not any(m["artifacts"].values()))
            n_ok += ok
            n_err += not ok
            print(f"  [{'ok' if ok else 'err'}] {rel}"
                  + (f"  {m['counts']}" if m.get("counts") else "")
                  + (f"  !{logs[0][:120]}" if logs else ""))
            if reused and logs:
                print(f"      {REUSED_FAILURE_HINT}")
        except Exception as e:  # noqa: BLE001
            n_err += 1
            print(f"  [ERR] {rel}: {e!r}")
    cat = build_catalog()
    print(f"[DONE] ok={n_ok} err={n_err} | catalog: {cat['count']} docs -> {CACHE_DIR / 'catalog.json'}")


def cmd_extract(args) -> None:
    f = Path(os.path.abspath(args.file))  # Win32 measures the absolute path
    try:
        rel = f.relative_to(SRC_DIR)
        outdir, relstr = CACHE_DIR / rel.parent / f.stem, str(rel).replace("\\", "/")
    except ValueError:
        outdir, relstr = CACHE_DIR / "_adhoc" / f.stem, f.name
    # Checked first: a path Win32 rejects for its length also reads as nonexistent.
    if extraction_exceeds_max_path(f, outdir):
        max_path_blocked.append(str(f))
        return
    if not f.exists():
        sys.exit(f"[FATAL] not found: {f}")
    pandoc = ensure_pandoc() if f.suffix.lower() == ".docx" else None
    m, reused = extract_one(f, outdir, relstr, pandoc, args.force)
    print(json.dumps(m.get("counts", {}), ensure_ascii=False) if m else "[SKIP] unsupported extension")
    if m and reused and m.get("logs"):
        print(f"  !{m['logs'][0][:120]}\n  {REUSED_FAILURE_HINT}")
    build_catalog()


def cmd_catalog(_args) -> None:
    cat = build_catalog()
    print(f"[CATALOG] {cat['count']} docs -> {CACHE_DIR / 'catalog.json'}")


def cmd_add_source(args) -> None:
    target = Path(args.dir).resolve()
    if not target.is_dir():
        sys.exit(f"[FATAL] not a directory: {target}")
    link = SRC_DIR / (args.name or target.name)
    if os.path.lexists(link):
        if link.resolve() != target:
            sys.exit(f"[FATAL] {link} already links to {link.resolve()}; pass --name to choose another name")
        print(f"[SOURCE] {link.name} -> {target} (already added)")
        return
    SRC_DIR.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError as e:
        if getattr(e, "winerror", None) != ERROR_PRIVILEGE_NOT_HELD:
            raise
        prompt_developer_setting("DEVELOPER_MODE", "Developer Mode", "Creating the source symlink needs it.")
        sys.exit(DEVELOPER_MODE_EXIT)
    print(f"[SOURCE] {link.name} -> {target}")


def cmd_status(_args) -> None:
    sources = sorted(SRC_DIR.iterdir()) if SRC_DIR.exists() else []
    print(f"source/: {len(sources)} source(s)" + ("" if sources else " — register one with `add-source <dir>`"))
    for s in sources:
        print(f"  {s.name} -> {s.resolve()}")
    cat_path = CACHE_DIR / "catalog.json"
    if cat_path.exists():
        cat = json.loads(cat_path.read_text(encoding="utf-8"))
        fmts: dict[str, int] = {}
        for d in cat["documents"]:
            fmts[d["format"]] = fmts.get(d["format"], 0) + 1
        print(f"cache/: {cat['count']} docs {fmts}")
    else:
        print("cache/: no catalog yet — run `sync`")


def main() -> None:
    ap = argparse.ArgumentParser(
        prog="spec-query", description="Extract specs found under references/source/ into references/cache/.")
    sub = ap.add_subparsers(dest="cmd")

    pa = sub.add_parser("add-source", help="register a spec root by linking it under references/source/")
    pa.add_argument("dir", help="spec root directory")
    pa.add_argument("--name", help="link name under source/ (default: the directory's own name)")
    pa.set_defaults(fn=cmd_add_source)

    ps = sub.add_parser("sync", help="extract every spec under references/source/ into the cache (hash-gated) [default]")
    ps.add_argument("path", nargs="?", help="optional subpath of source/ (or an absolute path within it) to limit scope")
    ps.add_argument("--limit", type=int, help="cap number of documents (testing)")
    ps.add_argument("--force", action="store_true", help="re-extract even if unchanged")
    ps.set_defaults(fn=cmd_sync)

    pe = sub.add_parser("extract", help="extract a single file")
    pe.add_argument("file")
    pe.add_argument("--force", action="store_true")
    pe.set_defaults(fn=cmd_extract)

    sub.add_parser("catalog", help="rebuild references/cache/catalog.json").set_defaults(fn=cmd_catalog)
    sub.add_parser("status", help="show source + cache coverage").set_defaults(fn=cmd_status)

    argv = sys.argv[1:]
    if not argv or argv[0] not in {*sub.choices, "-h", "--help"}:
        argv = ["sync", *argv]  # sync is the default subcommand
    args = ap.parse_args(argv)
    args.fn(args)
    if max_path_blocked:
        prompt_developer_setting("MAX_PATH", "Enable long paths (needs administrator rights)",
                                 f"Skipped {len(max_path_blocked)} path(s) of {MAX_PATH}+ characters"
                                 " because long paths are off:")
        for p in max_path_blocked:
            print(f"  {p}")
        sys.exit(MAX_PATH_EXIT)


if __name__ == "__main__":
    main()

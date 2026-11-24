---
name: spec-query
description: "Must load when looking up content in specification documents. Do not look up spec content without this skill."
compatibility: "Requires Python 3.10+, PowerShell 7, pandoc, Windows."
---

# Spec Query

Answer spec questions from STRUCTURED sources. Parse the original `.docx` for authoritative
text and tables — pandoc keeps the merged/nested tables that PDF text extraction silently
corrupts — and use the ratified `.pdf` page images for visuals (diagrams/figures).

## Model

- **Sources** (read-only): spec root folders registered with
  `specquery.ps1 add-source "<abs dir>" [--name <name>]`; each appears as
  `references/source/<name>` (default name: the folder's own), and `specquery.ps1 status`
  lists them.
- **Cache** (regenerable): `references/cache/` mirrors the `source/` tree. Per document at
  `<cache>/…/<doc-stem>/`:
  - `.docx` → `content.md` (prose + tables, for search/reading), `structured.html`
    (authoritative tables — rowspan/colspan and nested tables survive here), `media/` (raw
    embedded figures), `manifest.json` (source identity + figure/heading catalog).
  - `.pdf` → `pages/NNNNN.md` + `pages/NNNNN.jpg` (200 DPI page renders).
  - `.pptx`/`.xlsx` → `content.md`.
  A single `references/cache/catalog.json` lists every extracted document.

## Workflow

### Step 0 — Identify target

`SKILL_DIR` is the folder holding this file; `specquery.ps1` below stands for
`pwsh -NoProfile -File "{{SKILL_DIR}}/scripts/specquery.ps1"`. Store `USER_PROMPT` verbatim.
From the question, identify the target spec (name + revision).

### Step 1 — Extract source → cache (idempotent, hash-gated)

If the target spec lies under none of the sources `specquery.ps1 status` lists, ask the user
for its root folder and register it with `add-source` first.

Extract everything under `source/`, or pass a plain subpath to limit scope (a large source
is slow on first run — every PDF is page-rendered):

```powershell
specquery.ps1 "{{SUBPATH}}"
```

`{{SUBPATH}}` is a path under `source/` (e.g. `ISAM\NVM Express\…\Base Specification`), or
omit it to extract all. The first run bootstraps the venv and Python deps, and installs pandoc
through `scoop` when it is available; without either, `.docx` files are skipped with a warning.
For a one-off file outside `source/`, use `specquery.ps1 extract "{{FILE}}"`.

Exit code 3 or 4 means a Windows setting is off: the script has opened its Settings page and
printed what to turn on. Relay that to the user and rerun the same command once they confirm.
- **3**: the listed paths reach Windows' 260-character limit and were skipped; **Enable long
  paths** needs administrator rights. If the user cannot or will not turn it on, continue
  without the listed documents and say they were skipped.
- **4** (`add-source`): creating the source symlink needs **Developer Mode**; the source was
  not added.

On any other nonzero exit code, stop and report.

### Step 2 — Discover (subagent, blocking)

Read `references/discover-prompt.md`, substitute placeholders, delegate to a **subagent**
that has shell access (not a read-only explore agent). It returns the target document's cache dir, its
sibling PDF `pages` dir (for visuals), and the relevant sections/figures. Store as `TARGET`,
`PAGES_DIR`, `FIGURES`, `SECTIONS`. If it returns `target-doc: NONE`, tell the user no
matching document was found and stop.

### Step 3 — Answer (subagent, blocking)

Read `references/answer-prompt.md`, substitute placeholders, delegate to a **subagent**
that has shell access and can view images (not a read-only explore agent). Present its response as the final answer.

For cross-spec questions, run Steps 1–3 per spec, then read `references/cross-spec-prompt.md`
and delegate synthesis to a **subagent**.

## Gotchas

- **Tables → docx**: read a table's exact structure from `structured.html` (merged/nested
  cells survive there; `content.md` may flatten them).
- **Visuals → PDF page image**: for a diagram/figure, view the spec's `.pdf` page render.
  Find the page by searching the sibling PDF's `pages/*.md` for the figure caption, then
  open that `pages/NNNNN.jpg` with a file-reading tool that displays images. `manifest.json.figures[]` tags each figure
  `as:"table"` or `as:"image"`.
- **Cite the document's own figure numbers + identity**: numbering differs between a
  pre-ratification docx and the ratified PDF (e.g. docx "Figure 28" == ratified PDF
  "Figure 142"). Name the source file/revision you answered from — `manifest.json.source`
  records it.
- **Paths contain spaces**, and the cache/skill dirs sit OUTSIDE the workspace: pass absolute
  paths to file-reading tools, and search with `Select-String` when your search tool cannot
  reach outside the workspace.
- Force re-extraction with `specquery.ps1 "<subpath>" --force` (or delete the doc's cache
  dir — it is regenerable).
- If your shell tool echoes or mangles multi-line input, run one-line commands or use a
  subagent.
- If the user reports a wrong or incomplete answer, read `references/diagnosis.md`.

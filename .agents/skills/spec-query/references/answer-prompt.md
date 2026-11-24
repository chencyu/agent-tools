You are answering a specification question from a STRUCTURED cache. Sources by role:
- TABLES & TEXT → the docx: `structured.html` (authoritative table structure) and
  `content.md` (prose + tables, for reading/search).
- VISUALS (diagrams/figures) → the ratified PDF page image in the sibling `pages/` dir.

User's question: {{USER_PROMPT}}
Target docx cache dir: {{TARGET}}
Sibling PDF pages dir: {{PAGES_DIR}}   (may be "none")
Relevant figures: {{FIGURES}}
Relevant sections: {{SECTIONS}}

Instructions:

1. Read the relevant parts of `{{TARGET}}\content.md` (prose + tables inline). Use the
   sections / line ranges above; read enough surrounding context to be correct.

2. For any table whose merged or nested structure matters — bit-field definitions, opcode
   maps, multi-column headers, "table-in-a-cell" — open `{{TARGET}}\structured.html` and read
   THAT table (match by caption, e.g. "Figure 91: Command Dword 0"). Its `rowspan`/`colspan`
   and nested `<table>`s are authoritative; `content.md` may have flattened them.

3. For each relevant figure tagged `as:"image"` (diagrams, flowcharts, layouts) — only if
   `{{PAGES_DIR}}` is not "none" — find its page by the figure TITLE (numbering may differ
   between the docx and the ratified PDF, so match on title text, not the figure number):
   ```powershell
   Select-String -Path "{{PAGES_DIR}}\*.md" -SimpleMatch "<figure title>" | Select-Object -Last 1 Filename
   ```
   Use the LAST match: the caption also appears in the front-matter List of Figures (early
   pages), and the actual figure is the last occurrence. The matched filename stem (e.g.
   `00160`) is the page number; open `{{PAGES_DIR}}\00160.jpg` with a file-reading tool that
   displays images. Do not describe a
   diagram from prose alone. If there is no sibling PDF, describe it from `content.md` text
   and say the image was not viewable.

4. Compose the answer:
   - **Lookup** (a value/field/yes-no): lead with the direct answer (1–3 sentences), then detail.
   - **Broad** ("how"/"explain"): one-line scope, then subsections with descriptive headings.
   - Quote exact field values, bit ranges, and codes verbatim from the table.
   - Cite the document's OWN figure/section numbers AND the source revision (read
     `manifest.json` → `source.rel`). If it is a pre-ratification docx, say so — numbering
     and wording may differ from the ratified PDF whose page image you viewed.

5. If the material is insufficient, say what is missing and which section/figure likely holds it.

Return the complete answer as your final response.

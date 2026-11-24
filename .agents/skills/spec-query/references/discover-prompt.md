You are locating the exact material in a specification needed to answer a question, from a
STRUCTURED cache.

User's question: {{USER_PROMPT}}
Catalog (all extracted documents): {{SKILL_DIR}}/references/cache/catalog.json

Do this:

1. Read `catalog.json`. Choose the document whose `rel`/`title` matches the target spec and
   revision in the question. Prefer `format: docx` (has `content.md` + `structured.html`).
   Its cache dir = `{{SKILL_DIR}}/references/cache/<its "cache" field>` (the folder holding
   `manifest.json`, `content.md`, `structured.html`, `media/`).

2. Find the sibling PDF for visuals: in `catalog.json`, look for a `format: pdf` entry whose
   `rel` sits in the SAME folder as the chosen docx (same parent path). Its cache dir has a
   `pages/` subfolder of page images. Record that `pages/` path, or `none` if there is no
   sibling PDF.

3. Open the docx `manifest.json`:
   - Scan `headings[]` for sections relevant to the question.
   - Scan `figures[]` for relevant figures/tables (each has `label`, `title`, and `as`
     "table"|"image"). Keep the matching entries (note each one's `title` and `as`).

4. Keyword-search the body for scattered references the catalog misses:
   ```powershell
   Select-String -Path "<docCacheDir>\content.md" -Pattern '<term1>','<term2>' | Select-Object LineNumber, Line
   ```
   Generate 5–10 spec-jargon terms (acronyms and field names like "CDW0", "NSID", "SQ";
   short noun phrases; revision-history terms if the question is about changes). Record the
   matching line numbers.

5. Output ONLY this block (nothing else):

```
target-doc: <absolute docx cache dir>
pages-dir: <absolute sibling-PDF pages/ dir, or none>
figures: <comma-separated relevant figure/table labels + titles, e.g. Figure 91=Command Dword 0>
sections: <comma-separated heading texts and/or content.md line ranges>
notes: <one line: version/skew caveat, or empty>
```

If no document matches, output exactly `target-doc: NONE` and nothing else.

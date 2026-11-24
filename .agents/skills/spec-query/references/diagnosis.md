## Diagnosing Wrong Answers

When the final answer is incorrect or incomplete, check stages in reverse:

1. **Answer misread the source?** — Re-open `structured.html` for the cited table (its
   merged/nested cells are authoritative) and the cited figure's sibling-PDF page render
   (`pages/NNNNN.jpg`) with a file-reading tool that displays images.
   `content.md` can flatten a complex table — trust `structured.html` for cell structure.
2. **Discover pointed at the wrong material?** — Re-read the document's `manifest.json`
   `figures[]`/`headings[]` and widen the `content.md` keyword search (add spec-jargon and
   revision-history terms). A missed figure/section here starves the answer step.
3. **Discover chose the wrong document?** — Re-check `catalog.json`: confirm the spec name
   AND revision, and prefer the `docx` cache over a `pdf` one. Beware version skew — a
   pre-ratification docx numbers figures differently from the ratified PDF.
4. **Cache stale or missing?** — Re-run `specquery.ps1 "<subpath>" --force`. If a
   docx failed to extract, `manifest.json` `logs`/`artifacts` show it (e.g. pandoc missing);
   until the cause is fixed, only the sibling PDF's `pages/` text is available.
5. **Figure not viewable?** — Figures are viewed only on the sibling PDF's page render; find
   the page by figure title as in `answer-prompt.md` step 3. With no sibling PDF in
   `catalog.json`, the figure is not viewable: `media/` holds only the raw embedded files,
   often `.emf`/`.wmf` vector art that file-reading tools cannot display.


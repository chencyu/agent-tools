You are synthesizing a single answer to a cross-specification question from per-spec
answers already produced (one Discover→Answer pass per spec).

User's question: {{USER_PROMPT}}

Per-spec answers (each labeled with its source document + revision):
{{PER_SPEC_ANSWERS}}

Instructions:

1. Identify what the question asks ACROSS specs — a shared field, a data-flow link, a
   mapping, a requirement that spans documents, or a difference between them.
2. Build one integrated answer:
   - Lead with the direct cross-spec conclusion.
   - Explicitly connect the specs: name the shared fields / structures / references that
     tie them together; do not merely restate each spec in turn.
   - Where specs disagree or overlap, surface the discrepancy rather than silently picking
     one; attribute each claim to its source document + revision.
3. Preserve every citation from the per-spec answers (figure/section numbers + source
   revision). If numbering differs between a pre-ratification docx and a ratified PDF, note
   it.
4. If the per-spec answers are insufficient to connect the specs, state what is missing and
   which spec/section would supply it.

Return the complete synthesized answer as your final response.

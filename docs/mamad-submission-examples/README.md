# Mamad submission examples (curated)

Put high-quality example PDFs/crops here (manually prepared from the original submission guide or real submissions).
These are used to calibrate preflight heuristics (PF-xx) and as human-reference examples.

## Naming convention

Use this format:

`EX-{PF_IDS}--{QUALITY}--{SHORT_DESC}--v{N}.pdf`

Where:
- `{PF_IDS}`: one or more PF IDs separated by `+` (e.g., `PF-01+PF-03`)
- `{QUALITY}`: `good` or `edge`
- `{SHORT_DESC}`: short slug in English or Hebrew (no spaces; use `-`)
- `{N}`: version number starting at 1

### Examples
- `EX-PF-01+PF-03--good--request-table-and-signatures--v1.pdf`
- `EX-PF-03--edge--signatures-hard-to-read--v1.pdf`

## Optional: add page notes

If the PDF contains multiple pages, add a small sidecar markdown file with the same name:

- `EX-PF-01+PF-03--good--request-table-and-signatures--v1.md`

Include:
- which pages are relevant for each PF
- what exact visual/text cues to look for (e.g., specific Hebrew labels)

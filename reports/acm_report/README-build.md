# ACM Report Build Notes

This directory contains a 3--4 page ACM-style report package.

## Artifacts

- `report.md`: canonical writing source (Markdown-first draft)
- `references.bib`: bibliography (5 key references)
- `figures/`: architecture + table export assets
- `figures/architecture_flow_tikz.tex`: Overleaf-compilable imported architecture diagram
- `report.tex`: ACM `acmart` sigconf-style LaTeX source (polished)
- `build.sh`: reproducible conversion/compile helper

## Prerequisites

Install locally (Ubuntu example):

```bash
sudo apt-get update
sudo apt-get install -y pandoc texlive-latex-extra texlive-fonts-recommended texlive-bibtex-extra latexmk
```

## Build Workflow

From repo root:

```bash
cd reports/acm_report
./build.sh
```

Expected output:

- `report.pdf`

## What `build.sh` does

1. Optionally converts Markdown to a review copy:
   - `report_from_md.tex` via Pandoc citation processing.
2. Compiles the polished ACM source:
   - preferred: `latexmk`
   - fallback: `pdflatex + bibtex`

## Notes

- `report.tex` is the authoritative ACM-layout source used for final page control.
- `report.md` remains the canonical narrative draft for easier editing.
- If page count exceeds 4 pages, trim prose in Background/Work Done before removing tables.

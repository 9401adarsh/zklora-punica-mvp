#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

if command -v pandoc >/dev/null 2>&1; then
  pandoc report.md \
    --from markdown \
    --to latex \
    --citeproc \
    --bibliography=references.bib \
    -o report_from_md.tex
  echo "[ok] generated report_from_md.tex"
else
  echo "[warn] pandoc not found; skipping Markdown->LaTeX conversion"
fi

if command -v latexmk >/dev/null 2>&1; then
  latexmk -pdf -interaction=nonstopmode -halt-on-error report.tex
elif command -v pdflatex >/dev/null 2>&1 && command -v bibtex >/dev/null 2>&1; then
  pdflatex -interaction=nonstopmode report.tex
  bibtex report
  pdflatex -interaction=nonstopmode report.tex
  pdflatex -interaction=nonstopmode report.tex
else
  echo "[error] No LaTeX build toolchain found (need latexmk or pdflatex+bibtex)."
  exit 1
fi

echo "[ok] built report.pdf"

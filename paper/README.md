# Paper (6-page IEEE conference)

Files: `main.tex` (IEEEtran, `conference` mode, scoped to **6 pages**), `refs.bib`.

## Build
- **Overleaf:** upload `main.tex` + `refs.bib`, compiler = pdfLaTeX. `IEEEtran.cls` is built in.
- **Local:** `pdflatex main && bibtex main && pdflatex main && pdflatex main`

## Workflow for real numbers
1. Run `../code/corgi_profile.py` → `../out/report.json`.
2. Paste values into **Table `tab:profile`** (the `\num{...}` placeholders, shown blue).
3. `\todo{...}` (red) marks prose still to write; `\num{...}` (blue) marks numbers to plug.
   Both macros are defined at the top of `main.tex` — delete the color before submission.

## Page budget (keep it to 6)
Intro 1 · DQ model 1.25 · CORGI system 1.5 (Fig 1) · Setup 0.75 · Results 1.5 (Fig 2 + 2 tables)
· Related 0.5 · Conclusion 0.25. Figures/tables eat space fast — if over, cut ablation prose first.

## Figures to produce
- **Fig 1** pipeline (profile→gate) — the screenshot figure.
- **Fig 2** dose–response curves (defect level → quality drop) — proves the causal claim C2.

## Word version (IEEE A4 template)
`CORGI_paper.docx` is the filled IEEE template (generated from `Conference-template-A4.doc`
via Word COM using the template's own named styles). Regenerate from the drafted content with:
```
cd ../code
python word_fill.py "../Conference-template-A4.doc" "../paper/CORGI_paper.docx"
```
`word_fill.py` opens the original `.doc` fresh each run (idempotent), so re-running overwrites
cleanly. `word_convert.py` just converts the `.doc` → `.docx` and dumps style names. The paper
content in `word_fill.py` (BODY list) mirrors `main.tex`/`manuscript_word.md` — keep them in sync,
or pick ONE as source of truth. **Still fill the author block manually** (left as template
placeholders). Requires MS Word + `pywin32`.

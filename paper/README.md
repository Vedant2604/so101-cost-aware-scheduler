# Paper: Practice Is Not Free

`practice_is_not_free.tex` is the master copy of the paper. It is one self-contained file: the figures are drawn in TikZ and the references are built in, so it compiles on its own with the Springer LNCS class (`llncs.cls`, available on Overleaf and most LaTeX tools).

## How we keep versions

- Edit only this file, then commit with a message that says what changed, for example `paper: reword loss-curve lesson`.
- When a version goes out (arXiv, a workshop, a conference), tag it: `git tag paper-v1-arxiv` then `git push --tags`.
- `git log -- paper/` shows every change to the paper; `git diff paper-v1-arxiv -- paper/` shows what changed since a tagged version.
- Every number in the results section comes from `runs/` and can be re-checked with `python analyze.py` from the repo root.

## Versions

| Tag | Date | What changed |
|---|---|---|
| (untagged) | 2026-10-19 | First version in the repo: title on one line, abstract leads with the A/B result, simulation section removed, loss-curve lesson reworded for narrow tasks, failure-clustering result added, long URLs wrap. |

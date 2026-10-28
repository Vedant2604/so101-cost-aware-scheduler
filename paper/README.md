# Paper: Practice Is Not Free

`practice_is_not_free.tex` is the master copy of the paper. Text, references and the attempt timeline (Figure 5) are in that one file. The other five figures are PDFs kept next to it, all rebuilt from `media/` and `runs/` by `python paper/make_figures.py` (run from the repo root):

- `fig1_teaser.pdf`: one unattended cycle and a call for help, with a QR to the videos
- `fig2_testbed.pdf`: the printed parts, and frames of one place and one retrieve
- `fig3_loop.pdf`: the practice loop, drawn with real camera frames and a real ledger row
- `fig4_ledger.pdf`: where the robot's time went, and what one success cost
- `fig6_analysis.pdf`: failures do not cluster; seconds per attempt

Upload the .tex and these five PDFs to the same folder; it compiles with the Springer LNCS class (`llncs.cls`). Each figure also accepts a .jpg of the same name, and a missing figure shows a labelled box instead of breaking the build.

## How we keep versions

- Edit only this file, then commit with a message that says what changed, for example `paper: reword loss-curve lesson`.
- When a version goes out (arXiv, a workshop, a conference), tag it: `git tag paper-v1-arxiv` then `git push --tags`.
- `git log -- paper/` shows every change to the paper; `git diff paper-v1-arxiv -- paper/` shows what changed since a tagged version.
- Every number in the results section comes from `runs/` and can be re-checked with `python analyze.py` from the repo root.

## Versions

| Tag | Date | What changed |
|---|---|---|
| (untagged) | 2026-10-28 | Dr. Sharma's review: GitHub link under the abstract; bigger testbed photos with step labels; Figure 3 redrawn with real camera frames, detector output and a real ledger row; every caption now opens with its finding; chart labels enlarged and annotated; em dashes and arrows removed; conclusion states the three findings; future work is one paragraph. Also corrected a claim that the best rule depends on the cost weights: rule B was worse in every currency. |
| (untagged) | 2026-10-22 | Shortened by about 30%: build lessons 8 to 4, pilot to two paragraphs, limitations to one paragraph, future work to five items, progress figure and two table rows dropped, Related Work and System tightened. Conclusion and Future Work split. Every disclosure kept: excluded sessions, the 2 s rule, the p-values, the wrist repair, the untested scheduler. |
| (untagged) | 2026-10-22 | Two new figures from the ledger: where the robot's time went (a quarter goes to homing and looking) and successes against robot minutes. Figure files renamed `fig1_`–`fig5_` so a stale upload cannot collide with a new one. |
| (untagged) | 2026-10-22 | Trimmed for length: pilot ledger table dropped (it is `runs/pilot.csv`), Limitations 9 bullets to 6, future work 8 items to 6, Results and Observations tightened. |
| (untagged) | 2026-10-22 | Teaser figure on page 1 (autonomous cycle, intervention, QR to the videos). Prose tightened. Pilot log extracted to `runs/pilot.csv` and cited in the table caption. Full reference re-check: OmniReset initial corrected to Zhang, Z.; LeRobot citation moved to the ICLR 2026 paper; ACT's 52M stated as our instance, not ACT's published ~80M. Pilot section rewritten; its table renumbered to match `runs/pilot.csv`. Session inventory re-checked: the paper uses the five clock-corrected sessions; `runs/pilot/` holds the pre-fix backups. Place-failure breakdown corrected (12 short, 6 at cap, 1 cut by session end). Sent to Dr. Sharma for review. |
| (untagged) | 2026-10-19 | Every reference checked against its primary page: OmniReset and LeRobot author lists corrected, Baranes volume/pages/DOI added, unverifiable Stout pages removed, PAINT arXiv ID added. New figures: testbed overview and A/B analysis. Video pointer in Availability. |
| (untagged) | 2026-10-19 | Ready for Dr. Sharma's review: FIND added to related work; "pre-register" softened to "stated in advance". |
| (untagged) | 2026-10-19 | Future work: long-horizon task chains with a task queue; simulated twin built from the demonstrations. |
| (untagged) | 2026-10-19 | First version in the repo: title on one line, abstract leads with the A/B result, simulation section removed, loss-curve lesson reworded for narrow tasks, failure-clustering result added, long URLs wrap. |

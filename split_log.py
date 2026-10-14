"""Separate two sessions that were logged into the same CSV.

The runner APPENDS to its log file, so running a session twice with the same
--log name puts both sessions in one file. Nothing is overwritten. This splits
them back apart at the point where the session clock restarts.

    python split_log.py runs\\SB_s02.csv

Result:
    runs\\SB_s02.csv                   the first (complete) session only
    runs\\pilot\\SB_s02_extra1.csv     the later session(s)
    runs\\pilot\\SB_s02_original.csv   untouched copy of the file as it was
"""
import csv
import os
import shutil
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: python split_log.py runs\\SB_s02.csv")
path = sys.argv[1]
rows = list(csv.reader(open(path, newline="")))
header, data = rows[0], rows[1:]
col = header.index("wallclock_min")

# a new session starts wherever the clock jumps backwards
parts, cur, last = [], [], -1.0
for r in data:
    t = float(r[col]) if r[col] else last
    if cur and t < last - 0.5:
        parts.append(cur)
        cur = []
    cur.append(r)
    last = t
if cur:
    parts.append(cur)


def describe(p):
    eps = [r for r in p if r[header.index("task")] in ("place", "retrieve")]
    ok = sum(int(r[header.index("success")]) for r in eps)
    return f"{len(eps)} attempts, {ok} successes, ends at {p[-1][col]} min"


for i, p in enumerate(parts):
    print(f"session {i + 1}: {describe(p)}")

if len(parts) == 1:
    raise SystemExit("only one session in this file - nothing to split")

stem = os.path.splitext(os.path.basename(path))[0]
pilot = os.path.join(os.path.dirname(path), "pilot")
os.makedirs(pilot, exist_ok=True)
shutil.copy(path, os.path.join(pilot, f"{stem}_original.csv"))

with open(path, "w", newline="") as f:
    csv.writer(f).writerows([header] + parts[0])
for i, p in enumerate(parts[1:], start=1):
    with open(os.path.join(pilot, f"{stem}_extra{i}.csv"), "w", newline="") as f:
        csv.writer(f).writerows([header] + p)

print(f"\nkept session 1 in {path}")
print(f"moved the rest to {pilot}  (original copy saved there too)")

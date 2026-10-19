"""A/B analysis for the cost-aware practice scheduler.

    python analyze.py                 (reads runs\\SA_s*.csv and runs\\SB_s*.csv)

Rules (fixed before looking at the comparison):
  * an attempt shorter than 2 s is invalid and dropped (the cube was still
    being moved by hand when the episode started)
  * robot time = the session clock, which pauses while a human is helping
  * intervention = any time the runner stopped and asked a person for help
"""
import csv, glob, math, os, statistics as st

MIN_S = 2.0

def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 2
    p = k / n; d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return c - h, c + h

def load(path):
    rows = list(csv.DictReader(open(path, newline="")))
    att = [r for r in rows if r["task"] in ("place", "retrieve")]
    valid = [r for r in att if float(r["seconds"]) >= MIN_S]
    ints = [r for r in rows if r["intervention"] == "1"]
    waits = [float(r["seconds"]) for r in rows if r["task"] == "human_wait"]
    robot_min = max(float(r["wallclock_min"]) for r in att)
    streak = best = 0
    for r in valid:
        streak = 0 if r["success"] == "1" else streak + 1
        best = max(best, streak)
    ok = lambda rs: sum(r["success"] == "1" for r in rs)
    sec = lambda rs: sum(float(r["seconds"]) for r in rs)
    jt = lambda rs: sum(float(r["joint_travel"]) for r in rs)
    fails = [r for r in valid if r["success"] != "1"]
    pl = [r for r in valid if r["task"] == "place"]
    rt = [r for r in valid if r["task"] == "retrieve"]
    return dict(name=os.path.basename(path)[:-4], n=len(valid), k=ok(valid),
                dropped=len(att) - len(valid), t=sec(valid), tf=sec(fails),
                jt=jt(valid), jtf=jt(fails), ints=len(ints),
                retry=sum(r["task"] == "retry_limit" for r in ints),
                human=sum(waits), robot=robot_min, streak=best,
                pk=ok(pl), pn=len(pl), rk=ok(rt), rn=len(rt))

def ms(xs):
    return f"{st.mean(xs):.2f} ± {st.stdev(xs):.2f}" if len(xs) > 1 else f"{xs[0]:.2f}"

sessions = {c: [load(p) for p in sorted(glob.glob(os.path.join("runs", f"S{c}_s*.csv")))]
            for c in "AB"}
names = {"A": "feasible rule", "B": "retry limit"}

print(f"{'session':8s} {'att':>3s} {'ok':>3s} {'rate':>5s} {'fail-time':>9s} "
      f"{'ok/min':>6s} {'int':>3s} {'stops':>5s} {'human s':>7s} {'streak':>6s} drop")
for c in "AB":
    for s in sessions[c]:
        print(f"{s['name']:8s} {s['n']:3d} {s['k']:3d} {s['k']/s['n']:5.0%} "
              f"{s['tf']/s['t']:9.1%} {s['k']/s['robot']:6.2f} {s['ints']:3d} "
              f"{s['retry']:5d} {s['human']:7.1f} {s['streak']:6d} {s['dropped']:4d}")

summary = {}
for c in "AB":
    ss = sessions[c]
    if not ss:
        continue
    g = lambda key: sum(s[key] for s in ss)
    n, k = g("n"), g("k")
    lo, hi = wilson(k, n)
    summary[c] = (k, n)
    print(f"\n== {c}: {names[c]}  ({len(ss)} sessions, {g('robot'):.1f} robot-min)")
    print(f"  success            {k}/{n} = {k/n:.1%}   95% CI {lo:.1%}-{hi:.1%}"
          f"   per session {ms([s['k']/s['n'] for s in ss])}")
    print(f"  place / retrieve   {g('pk')}/{g('pn')} = {g('pk')/g('pn'):.0%}   "
          f"{g('rk')}/{g('rn')} = {g('rk')/g('rn'):.0%}")
    print(f"  exec time on fails {g('tf'):.0f} of {g('t'):.0f} s = {g('tf')/g('t'):.1%}"
          f"   per session {ms([s['tf']/s['t'] for s in ss])}")
    print(f"  joint travel fails {g('jtf'):.0f} of {g('jt'):.0f} deg = {g('jtf')/g('jt'):.1%}")
    print(f"  successes / min    {k/g('robot'):.2f}   per session {ms([s['k']/s['robot'] for s in ss])}")
    print(f"  exec s / success   {g('t')/k:.1f}")
    print(f"  joint deg/success  {g('jt')/k:.0f}")
    print(f"  interventions      {g('ints')} ({g('ints')/k:.2f} per success), "
          f"of which retry-limit stops {g('retry')}")
    print(f"  human s / success  {g('human')/k:.1f}   (total {g('human'):.0f} s)")
    print(f"  longest streaks    {[s['streak'] for s in ss]}")
    print(f"  dropped (<{MIN_S:.0f} s)     {g('dropped')}")

if len(summary) == 2:
    try:
        from scipy.stats import fisher_exact, mannwhitneyu
        (ka, na), (kb, nb) = summary["A"], summary["B"]
        print("\nFisher exact, success A vs B: p =",
              round(fisher_exact([[ka, na - ka], [kb, nb - kb]]).pvalue, 3))
        fa = [s["tf"] / s["t"] for s in sessions["A"]]
        fb = [s["tf"] / s["t"] for s in sessions["B"]]
        print("Mann-Whitney, fail-time per session: p =",
              round(mannwhitneyu(fa, fb).pvalue, 3))
    except ImportError:
        print("\n(pip install scipy for the significance tests)")

# do failures cluster? success of a place that directly follows a failed place
after = [0, 0]
for c in "AB":
    for p in sorted(glob.glob(os.path.join("runs", f"S{c}_s*.csv"))):
        seq = [r for r in csv.DictReader(open(p, newline=""))
               if r["task"] in ("place", "retrieve") and float(r["seconds"]) >= MIN_S]
        for a, b in zip(seq, seq[1:]):
            if a["task"] == b["task"] == "place" and a["success"] != "1":
                after[0] += b["success"] == "1"; after[1] += 1
if after[1]:
    print(f"\nplace right after a failed place: {after[0]}/{after[1]} = "
          f"{after[0]/after[1]:.0%} succeeded")

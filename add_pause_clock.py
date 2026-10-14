"""Stop the 10-minute clock while a human is fixing the scene.

Before: the budget was wall-clock, so time spent waiting for a person
(e.g. the retry-limit key press) ate the robot's practice time. That
punishes condition B unfairly. After: both conditions get exactly the
same 10 minutes of ROBOT time, and human time is logged separately
(a row with task = "human_wait", seconds = how long the person took).

    python add_pause_clock.py          (run once, in E:\\Research\\SO-101)
"""
import shutil

SRC = "runner.py"
s = open(SRC, encoding="utf-8").read()

if "ledger.paused" in s:
    raise SystemExit("already applied - nothing to do")

edits = [
    # 1. ledger keeps track of paused time and total human time
    ("        self.t0 = time.time()\n",
     "        self.t0 = time.time()\n"
     "        self.paused = 0.0      # seconds the clock was stopped for a human\n"
     "        self.human_s = 0.0\n"),
    # 2. the budget only counts robot time
    ("        return (time.time() - self.t0) / 60.0\n",
     "        return (time.time() - self.t0 - self.paused) / 60.0\n"),
    # 3. summary shows human time too
    ('                f"{self.elapsed_min:.1f} min")\n',
     '                f"{self.elapsed_min:.1f} min robot | "\n'
     '                f"{self.human_s / 60:.1f} min human")\n'),
    # 4. start the stopwatch when the human is asked
    ("                stable = 0\n                while True:\n",
     "                _w0 = time.time()\n"
     "                stable = 0\n                while True:\n"),
    # 5. stop it when they are done, log it, don't charge it to the budget
    ("                if asked:\n                    sched.helped()\n                continue\n",
     "                waited = time.time() - _w0\n"
     "                ledger.paused += waited\n"
     "                ledger.human_s += waited\n"
     '                print(f"  human took {waited:.0f}s (clock paused)")\n'
     "                log.writerow([ledger.episodes, round(ledger.elapsed_min, 2),\n"
     '                              sched.name, "human_wait", "", "", "",\n'
     "                              round(waited, 1), \"\", 0, ledger.successes,\n"
     "                              ledger.interventions])\n"
     "                logf.flush()\n"
     "                if asked:\n                    sched.helped()\n                continue\n"),
    # 6. clearer instruction: the key press only works in the camera window
    ('"move it to a NEW spot in the same region, then press any key"',
     '"move it to a NEW spot in the same region, then CLICK the camera window and press any key"'),
]

for old, new in edits:
    n = s.count(old)
    if n != 1:
        raise SystemExit(f"could not find a unique spot for:\n{old}\n(found {n}) - runner.py unchanged")
    s = s.replace(old, new)

shutil.copy(SRC, "runner_before_pause.py")
open(SRC, "w", encoding="utf-8").write(s)
print("OK - clock now pauses during interventions (backup: runner_before_pause.py)")

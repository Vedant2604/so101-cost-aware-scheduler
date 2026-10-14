"""Add a retry-limit scheduler (condition B) to runner.py.

  python add_retry_limit.py

Backs up runner.py to runner_before_retry.py, then edits it in place.
Every edit is checked first; if any anchor is missing, nothing is changed.
New usage:
  python runner.py ... --scheduler retry --max-retries 2
After N consecutive failures the runner stops and asks you to move the cube
to a NEW spot and press any key. That counts as one intervention, logged with
task = "retry_limit".
"""
import shutil
import sys

PATH = "runner.py"
src = open(PATH, encoding="utf-8").read()

if "class RetryLimitScheduler" in src:
    sys.exit("runner.py already has the retry-limit scheduler, nothing to do.")

CLASS = '''class RetryLimitScheduler(FeasibleScheduler):
    """Feasible rule, plus a fixed retry limit: after N consecutive failures,
    stop and ask a human to reposition the cube (Leave No Trace's hard reset,
    with N fixed by hand). Condition B in the paper."""
    name = "retry"

    def __init__(self, n=2):
        self.n, self.streak, self.help = n, 0, False

    def feasible(self, ws):
        return [] if self.help else super().feasible(ws)

    def update(self, ws, task, outcome):
        self.streak = 0 if outcome["success"] else self.streak + 1
        self.help = self.streak >= self.n

    def helped(self):
        self.streak, self.help = 0, False


'''

edits = [
    # 1. the scheduler class and its registry entry
    ('SCHEDULERS = {"feasible": FeasibleScheduler, "random": RandomScheduler}',
     CLASS + 'SCHEDULERS = {"feasible": FeasibleScheduler, "random": RandomScheduler,\n'
             '              "retry": RetryLimitScheduler}'),
    # 2. the --max-retries flag
    ('ap.add_argument("--scheduler", default="feasible", choices=list(SCHEDULERS))',
     'ap.add_argument("--scheduler", default="feasible", choices=list(SCHEDULERS))\n'
     '    ap.add_argument("--max-retries", type=int, default=2,\n'
     '                    help="retry scheduler: consecutive failures before asking for help")'),
    # 3. build the scheduler with N
    ('sched = SCHEDULERS[args.scheduler]()',
     'sched = (RetryLimitScheduler(args.max_retries) if args.scheduler == "retry"\n'
     '             else SCHEDULERS[args.scheduler]())'),
    # 4. say why the intervention happened
    ('                ledger.interventions += 1\n'
     '                why = ws.region if ws else "no frame"',
     '                ledger.interventions += 1\n'
     '                asked = getattr(sched, "help", False)\n'
     '                why = "retry limit" if asked else (ws.region if ws else "no frame")'),
    ('if why == "table_edge" else "not usable")',
     'if why == "table_edge" else "not usable")\n'
     '                if asked:\n'
     '                    hint = "move it to a NEW spot in the same region, then press any key"'),
    # 5. log the reason in the (otherwise empty) task column
    ('sched.name, "", ws.region if ws else "", "", "",',
     'sched.name, "retry_limit" if asked else "", ws.region if ws else "", "", "",'),
    # 6. a retry-limit stop waits for a key press instead of auto-resuming
    ('if ws2.confident and ws2.region in VALID_REGIONS:',
     'if not asked and ws2.confident and ws2.region in VALID_REGIONS:'),
    # 7. clear the streak once the human has helped
    ('                    if k != -1:\n'
     '                        break\n'
     '                continue',
     '                    if k != -1:\n'
     '                        break\n'
     '                if asked:\n'
     '                    sched.helped()\n'
     '                continue'),
]

missing = [i + 1 for i, (old, _) in enumerate(edits) if src.count(old) != 1]
if missing:
    sys.exit(f"Anchor(s) {missing} not found exactly once; runner.py left unchanged. "
             "Send runner.py and the edit will be done by hand.")

shutil.copy(PATH, "runner_before_retry.py")
for old, new in edits:
    src = src.replace(old, new)
open(PATH, "w", encoding="utf-8").write(src)
print("runner.py updated (backup: runner_before_retry.py)")
print("check: python runner.py --help  ->  should list 'retry' and --max-retries")

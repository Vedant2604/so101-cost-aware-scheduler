

"""Autonomous multi-task practice session for the SO-101, with one policy per task.
 
Two single-task ACT policies are held in VRAM simultaneously; the scheduler picks
which task to attempt from the current world state and the matching policy runs
the episode. Episodes terminate on vision (the detector seeing the cube settled
in the goal region), not on the policy, because neither policy was ever shown a
terminal state.
 
  Dry run:   python runner2.py --place <ckpt> --retrieve <ckpt> --cams 0 1
  Live:      python runner2.py --place <ckpt> --retrieve <ckpt> --cams 0 1 --go --minutes 15
 
Example:
  python runner2.py ^
    --place outputs/act_pick3/checkpoints/100000/pretrained_model ^
    --retrieve outputs/act_retrieve_hub ^
    --cams 0 1 --go --minutes 15
"""
import argparse
import csv
import os
import time
from pathlib import Path
 
import cv2
import numpy as np
import torch
 
from detector import CubeDetector
from lerobot.policies.act.modeling_act import ACTPolicy
from lerobot.robots.so_follower import SO101Follower, SO101FollowerConfig
 
JOINTS = ["shoulder_pan", "shoulder_lift", "elbow_flex",
          "wrist_flex", "wrist_roll", "gripper"]
LIMITS = {"shoulder_pan": (-110, 110), "shoulder_lift": (-110, 110),
          "elbow_flex": (-110, 110), "wrist_flex": (-110, 110),
          "wrist_roll": (-160, 160), "gripper": (0, 100)}
 
# demo start pose — every recorded episode began here, and the policies are
# sensitive to it, so each practice episode is returned to it first
HOME = {"shoulder_pan": -6.0, "shoulder_lift": -104.0, "elbow_flex": 98.0,
        "wrist_flex": -18.0, "wrist_roll": -89.0, "gripper": 40.0}

HOME_MAX_DEG_PER_S = 25.0     # hard ceiling on homing speed, any joint

 
TASKS = {
    "place":    "pick up the cube and place it in the tray",
    "retrieve": "take the cube out of the tray and place it on the table",
}
# task -> (required start region, goal region)
# `place` needs the cube inside the taped work region — it was demonstrated only
# there and degrades at the edge. A cube at table_edge is feasible for neither
# task, so it is logged as an intervention rather than silently retried.
TASK_SPEC = {
    "place":    ("table_in", "tray"),
    "retrieve": ("tray", "table_in"),
}
VALID_REGIONS = ("tray", "table_in", "table_edge")
 
 
def reached_goal(region, goal):
    """A retrieve that lands at the edge still put the cube on the table."""
    return region == goal or (goal == "table_in" and region == "table_edge")
W, H = 320, 240
 
 
# --------------------------------------------------------------------------
# schedulers
# --------------------------------------------------------------------------
class FeasibleScheduler:
    """Hand-designed: run whichever task's precondition currently holds.
 
    The Gupta et al. (ICRA 2021) pattern — tasks reset each other and the
    sequencer is engineered. This is the baseline a learned scheduler must beat.
    """
    name = "feasible"
 
    def feasible(self, ws):
        return [t for t, (start, _) in TASK_SPEC.items() if ws.region == start]
 
    def select(self, ws, history):
        f = self.feasible(ws)
        return f[0] if f else None
 
    def update(self, *a, **kw):
        pass
 
 
class RandomScheduler:
    """Uniform over feasible tasks. Control for 'does the choice matter at all'."""
    name = "random"
 
    def __init__(self, seed=0):
        self.rng = np.random.default_rng(seed)
 
    def feasible(self, ws):
        return [t for t, (start, _) in TASK_SPEC.items() if ws.region == start]
 
    def select(self, ws, history):
        f = self.feasible(ws)
        return str(self.rng.choice(f)) if f else None
 
    def update(self, *a, **kw):
        pass
 
 
class RetryLimitScheduler(FeasibleScheduler):
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


SCHEDULERS = {"feasible": FeasibleScheduler, "random": RandomScheduler,
              "retry": RetryLimitScheduler}
 
 
# --------------------------------------------------------------------------
# cost ledger — time, wear, human attention
# --------------------------------------------------------------------------
class Ledger:
    def __init__(self):
        self.episodes = 0
        self.successes = 0
        self.interventions = 0
        self.seconds = 0.0
        self.joint_travel = 0.0
        self.per_task = {t: [0, 0] for t in TASKS}      # task -> [attempts, wins]
        self.t0 = time.time()
 
    def charge(self, o):
        self.episodes += 1
        self.successes += int(o["success"])
        self.seconds += o["seconds"]
        self.joint_travel += o["joint_travel"]
        self.per_task[o["task"]][0] += 1
        self.per_task[o["task"]][1] += int(o["success"])
 
    @property
    def elapsed_min(self):
        return (time.time() - self.t0) / 60.0
 
    def summary(self):
        rate = self.successes / max(self.episodes, 1)
        per_hr = self.interventions / max(self.elapsed_min / 60.0, 1e-6)
        by_task = "  ".join(
            f"{t}:{w}/{a}" for t, (a, w) in self.per_task.items() if a)
        return (f"{self.episodes} eps | {self.successes} ok ({rate:.0%}) | "
                f"{by_task} | {self.interventions} int ({per_hr:.1f}/hr) | "
                f"{self.elapsed_min:.1f} min")
 
 
# --------------------------------------------------------------------------
def load_policy(path, dev):
    """Load one ACT checkpoint plus its normalisation pipelines."""
    p = Path(path).resolve()
    policy = ACTPolicy.from_pretrained(p).to(dev).eval()
    pre = post = None
    try:
        from lerobot.processor import PolicyProcessorPipeline
        pre = PolicyProcessorPipeline.from_pretrained(
            p, config_filename="policy_preprocessor.json")
        post = PolicyProcessorPipeline.from_pretrained(
            p, config_filename="policy_postprocessor.json")
    except Exception as e:
        print(f"  no external processors for {p.name}:", type(e).__name__)
    return {"policy": policy, "pre": pre, "post": post, "path": str(p)}
 
 
def to_tensor(frame, dev):
    img = cv2.resize(frame, (W, H))
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    t = torch.from_numpy(rgb).permute(2, 0, 1).float() / 255.0
    return t.unsqueeze(0).to(dev)
 
 
def go_home(arm, args):
    """Ease the arm back to HOME over a fixed duration with a smooth ramp.

    Time-based rather than step-based: the move always takes at least
    --home-seconds, however far away the arm is, so no joint ever moves fast
    enough to brown out the servo bus.
    """
    start = {m: float(arm.get_observation()[f"{m}.pos"]) for m in JOINTS}
    dist = max(abs(HOME[m] - start[m]) for m in JOINTS)
    if dist < 1.0:
        return

    # duration scales with distance but never below the floor;
    # at most HOME_MAX_DEG_PER_S in any joint
    duration = max(args.home_seconds, dist / HOME_MAX_DEG_PER_S)
    rate = 20                                   # Hz — gentler on the bus than 30
    n = int(duration * rate)

    for i in range(1, n + 1):
        t = i / n
        s = 0.5 - 0.5 * np.cos(np.pi * t)       # cosine ease: slow start, slow end
        target = {m: start[m] + s * (HOME[m] - start[m]) for m in JOINTS}
        arm.send_action({f"{m}.pos": target[m] for m in JOINTS})
        time.sleep(1.0 / rate)

    arm.send_action({f"{m}.pos": HOME[m] for m in JOINTS})
    time.sleep(0.5)
 
 
import json as _json
RELEASE = _json.load(open("release.json")) if os.path.exists("release.json") else None
INFERRED_TRAY = [False]


def run_episode(task, bundle, arm, caps, det, args, dev):
    """One attempt. Ends on a settled cube in the goal region, the step cap,
    or a cube lost for too long."""
    policy, pre, post = bundle["policy"], bundle["pre"], bundle["post"]
    policy.reset()
    goal = TASK_SPEC[task][1]
 
    t_start = time.perf_counter()
    travel = 0.0
    lost_since = None
    settle_n, settle_xy = 0, None
    success = False
    step = 0
    min_grip, released_over_tray, stop_at = 1e9, False, None
 
    for step in range(args.max_steps):
        t0 = time.perf_counter()
        obs = arm.get_observation()
        cur = np.array([float(obs[f"{m}.pos"]) for m in JOINTS], dtype=np.float32)
        if task == "place" and RELEASE and not released_over_tray:
            min_grip = min(min_grip, float(cur[5]))
            if (min_grip <= RELEASE["grip_hold_max"]
                    and cur[5] > min_grip + RELEASE["open_by"]
                    and RELEASE["pan_min"] <= cur[0] <= RELEASE["pan_max"]):
                released_over_tray, stop_at = True, step + 45
                print("  released over the tray")
        if stop_at is not None and step >= stop_at:
            break
 
        frames = [c.read()[1] for c in caps]
        if any(f is None for f in frames):
            continue
 
        ws, dbg = det.find(frames[1], frames[0])
 
        # goal reached AND the cube has settled — a side-on camera projects a
        # carried cube into the tray region, so position alone is not enough
        if reached_goal(ws.region, goal) and ws.confident:
            if settle_xy is not None:
                moved = abs(ws.xy[0] - settle_xy[0]) + abs(ws.xy[1] - settle_xy[1])
                settle_n = settle_n + 1 if moved < args.settle_px else 0
            settle_xy = ws.xy
            if settle_n >= args.settle_frames:
                success = True
                break
        else:
            settle_n, settle_xy = 0, None
 
        # cube out of sight for too long (held is normal; gone is not)
        if ws.region == "lost":
            lost_since = lost_since or time.perf_counter()
            if time.perf_counter() - lost_since > args.lost_timeout:
                break
        else:
            lost_since = None
 
        batch = {
            "observation.state": torch.from_numpy(cur).unsqueeze(0).to(dev),
            "observation.images.wrist": to_tensor(frames[0], dev),
            "observation.images.scene": to_tensor(frames[1], dev),
            "task": TASKS[task],
        }
        if pre is not None:
            batch = pre(batch)
        with torch.inference_mode():
            out = policy.select_action(batch)
        if post is not None:
            out = post({"action": out})
            if isinstance(out, dict):
                out = out["action"]
 
        act = np.asarray(out.detach().cpu() if torch.is_tensor(out) else out,
                         dtype=np.float32).reshape(-1)[:6]
        act = np.clip(act, cur - args.max_delta, cur + args.max_delta)
        for i, m in enumerate(JOINTS):
            lo, hi = LIMITS[m]
            act[i] = float(np.clip(act[i], lo, hi))
 
        travel += float(np.abs(act - cur).sum())
 
        if args.go:
            arm.send_action({f"{m}.pos": float(act[i]) for i, m in enumerate(JOINTS)})
 
        cv2.putText(dbg, f"{task}  step {step}", (10, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
        cv2.imshow("session", dbg)
        if cv2.waitKey(1) == 27:
            raise KeyboardInterrupt
 
        time.sleep(max(1 / 30 - (time.perf_counter() - t0), 0))
 
    return {"task": task, "success": success, "steps": step + 1,
            "seconds": time.perf_counter() - t_start, "joint_travel": travel,
            "released_over_tray": released_over_tray}
 
 
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--place", required=True, help="checkpoint for the place task")
    ap.add_argument("--retrieve", required=True, help="checkpoint for the retrieve task")
    ap.add_argument("--cams", type=int, nargs=2, default=[0, 1],
                    help="wrist index, scene index")
    ap.add_argument("--scheduler", default="feasible", choices=list(SCHEDULERS))
    ap.add_argument("--max-retries", type=int, default=2,
                    help="retry scheduler: consecutive failures before asking for help")
    ap.add_argument("--go", action="store_true", help="actually move the arm")
    ap.add_argument("--minutes", type=float, default=0, help="0 = until Ctrl+C")
    ap.add_argument("--max-steps", type=int, default=800)
    ap.add_argument("--max-delta", type=float, default=8.0)
    ap.add_argument("--pause", type=float, default=3.0)
    ap.add_argument("--lost-timeout", type=float, default=25.0)
    ap.add_argument("--settle-frames", type=int, default=15)
    ap.add_argument("--settle-px", type=float, default=6.0)
    ap.add_argument("--home-seconds", type=float, default=4.0,
                    help="minimum duration of the return-to-home move")  
    ap.add_argument("--log", default="runs/session.csv")
    args = ap.parse_args()
 
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print("loading policies...")
    policies = {"place": load_policy(args.place, dev),
                "retrieve": load_policy(args.retrieve, dev)}
    for t, b in policies.items():
        print(f"  {t:9s} <- {b['path']}")
    if dev == "cuda":
        print(f"  VRAM: {torch.cuda.memory_allocated() / 1e9:.2f} GB")
 
    det = CubeDetector()
    sched = (RetryLimitScheduler(args.max_retries) if args.scheduler == "retry"
             else SCHEDULERS[args.scheduler]())
 
    caps = [cv2.VideoCapture(i, cv2.CAP_DSHOW) for i in args.cams]
    for c in caps:
        c.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        c.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
 
    arm = SO101Follower(SO101FollowerConfig(port="COM3", id="follower_arm",
                                            use_degrees=True))
    arm.connect()
    print(f"scheduler={sched.name} |",
          "LIVE — arm will move" if args.go else "DRY RUN — no motion")
 
    os.makedirs(os.path.dirname(args.log) or ".", exist_ok=True)
    new = not os.path.exists(args.log)
    logf = open(args.log, "a", newline="")
    log = csv.writer(logf)
    if new:
        log.writerow(["episode", "wallclock_min", "scheduler", "task",
                      "start_region", "success", "steps", "seconds",
                      "joint_travel", "intervention", "cum_successes",
                      "cum_interventions"])
 
    ledger = Ledger()
    history = []
 
    try:
        while True:
            if args.minutes and ledger.elapsed_min >= args.minutes:
                print("\ntime budget reached")
                break
 
            # return to the demo start pose (gripper open, so anything held
            # is released), let the scene settle, then look
            if args.go:
                go_home(arm, args)
            time.sleep(args.pause)
 
            okw, wrist = caps[0].read()
            oks, scene = caps[1].read()
            ws, dbg = det.find(scene, wrist if okw else None) if oks else (None, None)
            if ws is not None and ws.region in ("held", "lost") and INFERRED_TRAY[0]:
                ws.region, ws.confident = "tray", True
 
            if ws is None or not sched.feasible(ws):
                ledger.interventions += 1
                asked = getattr(sched, "help", False)
                why = "retry limit" if asked else (ws.region if ws else "no frame")
                hint = ("landed outside the work region"
                        if why == "table_edge" else "not usable")
                if asked:
                    hint = "move it to a NEW spot in the same region, then press any key"
                print(f"\n[INTERVENTION #{ledger.interventions}] cube {why} — "
                      f"{hint}. Move it inside the taped square or the tray.")
                log.writerow([ledger.episodes, round(ledger.elapsed_min, 2),
                              sched.name, "retry_limit" if asked else "", ws.region if ws else "", "", "",
                              "", "", 1, ledger.successes, ledger.interventions])
                logf.flush()
 
                stable = 0
                while True:
                    okw2, w2 = caps[0].read()
                    oks2, s2 = caps[1].read()
                    if oks2:
                        ws2, d2 = det.find(s2, w2 if okw2 else None)
                        cv2.putText(d2, "INTERVENTION - place the cube",
                                    (10, 90), cv2.FONT_HERSHEY_SIMPLEX,
                                    0.8, (0, 0, 255), 2)
                        cv2.imshow("session", d2)
                        if not asked and ws2.confident and ws2.region in VALID_REGIONS:
                            stable += 1
                            if stable > 45:
                                print("  scene recovered, resuming")
                                break
                        else:
                            stable = 0
                    k = cv2.waitKey(30)
                    if k == 27:
                        raise KeyboardInterrupt
                    if k != -1:
                        break
                if asked:
                    sched.helped()
                continue
 
            task = sched.select(ws, history)
            if task is None:
                continue
 
            print(f"\nep {ledger.episodes:3d} | cube {ws.region} -> {task}")
            outcome = run_episode(task, policies[task], arm, caps, det, args, dev)
 
            # the gripper occludes the cube at the moment of release, so an
            # in-episode miss is not conclusive — clear the arm and re-check
            if not outcome["success"]:
                if args.go:
                    go_home(arm, args)
                time.sleep(1.0)
                okw2, w2 = caps[0].read()
                oks2, s2 = caps[1].read()
                if oks2:
                    ws_after, _ = det.find(s2, w2 if okw2 else None)
                    if reached_goal(ws_after.region, TASK_SPEC[task][1]) \
                            and ws_after.confident:
                        outcome["success"] = True
                        print("  (success confirmed after homing)")
                    elif (outcome.get("released_over_tray")
                          and ws_after.region not in ("table_in", "table_edge")):
                        outcome["success"] = True
                        INFERRED_TRAY[0] = True
                        print("  (success: released over the tray, cube not on the table)")
 
            if task == "place" and outcome["success"]:
                INFERRED_TRAY[0] = True
            elif task != "place":
                INFERRED_TRAY[0] = False
            ledger.charge(outcome)
            history.append(outcome)
            sched.update(ws, task, outcome)
 
            print(f"  {'SUCCESS' if outcome['success'] else 'fail   '} "
                  f"{outcome['steps']} steps, {outcome['seconds']:.0f}s")
            print(f"  {ledger.summary()}")
 
            log.writerow([ledger.episodes, round(ledger.elapsed_min, 2),
                          sched.name, task, ws.region,
                          int(outcome["success"]), outcome["steps"],
                          round(outcome["seconds"], 1),
                          round(outcome["joint_travel"], 1), 0,
                          ledger.successes, ledger.interventions])
            logf.flush()
 
    except KeyboardInterrupt:
        print("\nstopped")
    finally:
        print("\nSESSION:", ledger.summary())
        logf.close()
        arm.disconnect()
        for c in caps:
            c.release()
        cv2.destroyAllWindows()
 
 
if __name__ == "__main__":
    main()
 

"""Detect a successful place even when the arm hides the tray from the camera.

  python add_tray_release.py

Uses the robot's own joints. A place counts as a success when:
  1. the gripper closed on something (holding), then
  2. opened while the base was turned over the tray (window from release.json), and
  3. after homing, the scene camera does NOT see the cube on the table.
The episode also ends ~1.5 s after the release instead of running to the cap.
The cube is then treated as 'in the tray' until the next episode runs.
Needs release.json from calibrate_release.py. Backup: runner_before_release.py
"""
import shutil
import sys

PATH = "runner.py"
src = open(PATH, encoding="utf-8").read()
if "released_over_tray" in src:
    sys.exit("runner.py already has tray-release detection, nothing to do.")

edits = [
    # 1. load release.json once
    ("def run_episode(",
     'import json as _json\n'
     'RELEASE = _json.load(open("release.json")) if os.path.exists("release.json") else None\n'
     'INFERRED_TRAY = [False]\n\n\n'
     'def run_episode('),
    # 2. per-episode tracking state
    ('    success = False\n'
     '    step = 0\n',
     '    success = False\n'
     '    step = 0\n'
     '    min_grip, released_over_tray, stop_at = 1e9, False, None\n'),
    # 3. watch the gripper and base every step
    ('        cur = np.array([float(obs[f"{m}.pos"]) for m in JOINTS], dtype=np.float32)\n',
     '        cur = np.array([float(obs[f"{m}.pos"]) for m in JOINTS], dtype=np.float32)\n'
     '        if task == "place" and RELEASE and not released_over_tray:\n'
     '            min_grip = min(min_grip, float(cur[5]))\n'
     '            if (min_grip <= RELEASE["grip_hold_max"]\n'
     '                    and cur[5] > min_grip + RELEASE["open_by"]\n'
     '                    and RELEASE["pan_min"] <= cur[0] <= RELEASE["pan_max"]):\n'
     '                released_over_tray, stop_at = True, step + 45\n'
     '                print("  released over the tray")\n'
     '        if stop_at is not None and step >= stop_at:\n'
     '            break\n'),
    # 4. report it
    ('            "seconds": time.perf_counter() - t_start, "joint_travel": travel}',
     '            "seconds": time.perf_counter() - t_start, "joint_travel": travel,\n'
     '            "released_over_tray": released_over_tray}'),
    # 5. after-episode decision: released over tray + not visible on the table = success
    ('                    if reached_goal(ws_after.region, TASK_SPEC[task][1]) \\\n'
     '                            and ws_after.confident:\n'
     '                        outcome["success"] = True\n'
     '                        print("  (success confirmed after homing)")\n',
     '                    if reached_goal(ws_after.region, TASK_SPEC[task][1]) \\\n'
     '                            and ws_after.confident:\n'
     '                        outcome["success"] = True\n'
     '                        print("  (success confirmed after homing)")\n'
     '                    elif (outcome.get("released_over_tray")\n'
     '                          and ws_after.region not in ("table_in", "table_edge")):\n'
     '                        outcome["success"] = True\n'
     '                        INFERRED_TRAY[0] = True\n'
     '                        print("  (success: released over the tray, cube not on the table)")\n'),
    # 6. a success seen directly also counts as 'cube in tray'
    ('            ledger.charge(outcome)\n',
     '            if task == "place" and outcome["success"]:\n'
     '                INFERRED_TRAY[0] = True\n'
     '            elif task != "place":\n'
     '                INFERRED_TRAY[0] = False\n'
     '            ledger.charge(outcome)\n'),
    # 7. at the top of the loop, a hidden cube after a place success is in the tray
    ('            ws, dbg = det.find(scene, wrist if okw else None) if oks else (None, None)\n',
     '            ws, dbg = det.find(scene, wrist if okw else None) if oks else (None, None)\n'
     '            if ws is not None and ws.region in ("held", "lost") and INFERRED_TRAY[0]:\n'
     '                ws.region, ws.confident = "tray", True\n'),
]
missing = [i + 1 for i, (old, _) in enumerate(edits) if src.count(old) != 1]
if missing:
    sys.exit(f"Anchor(s) {missing} not found exactly once; runner.py left unchanged. "
             "Send runner.py and it will be done by hand.")
shutil.copy(PATH, "runner_before_release.py")
for old, new in edits:
    src = src.replace(old, new)
open(PATH, "w", encoding="utf-8").write(src)
print("runner.py updated (backup: runner_before_release.py)")

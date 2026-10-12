"""Learn, from your own place demos, where the gripper lets go over the tray.

  python calibrate_release.py

For every place4 demo it finds the moment the gripper opens after holding the
cube, and records the base angle (shoulder_pan) at that moment and how closed
the gripper was while holding. Saves release.json for the runner.
"""
import glob
import json
import os

import numpy as np

FOLDER = os.path.join("demos", "place4")
OPEN_BY = 8.0          # degrees the gripper must open to count as letting go

pans, holds, grasp_pans = [], [], []
for f in sorted(glob.glob(os.path.join(FOLDER, "ep*", "traj.npz"))):
    s = np.load(f)["state"]
    pan, grip = s[:, 0], s[:, 5]
    k = int(np.argmin(grip))                       # most closed = holding the cube
    after = np.where(grip[k:] > grip[k] + OPEN_BY)[0]
    if not len(after):
        continue
    r = k + int(after[0])                          # first clear opening after that
    pans.append(float(pan[r]))
    holds.append(float(grip[k]))
    grasp_pans.append(float(pan[k]))

if not pans:
    raise SystemExit(f"no usable demos in {FOLDER}")

pans, holds, grasp_pans = map(np.array, (pans, holds, grasp_pans))
cfg = {
    "pan_min": round(float(pans.min() - 8), 1),
    "pan_max": round(float(pans.max() + 8), 1),
    "grip_hold_max": round(float(np.percentile(holds, 95) + 5), 1),
    "open_by": OPEN_BY,
}
json.dump(cfg, open("release.json", "w"), indent=2)

print(f"{len(pans)} demos")
print(f"  release pan     {pans.min():6.1f} .. {pans.max():6.1f}  -> tray window "
      f"{cfg['pan_min']} .. {cfg['pan_max']}")
print(f"  grasp pan       {grasp_pans.min():6.1f} .. {grasp_pans.max():6.1f}")
print(f"  holding gripper {holds.min():6.1f} .. {holds.max():6.1f}  -> hold max {cfg['grip_hold_max']}")
overlap = ((grasp_pans >= cfg["pan_min"]) & (grasp_pans <= cfg["pan_max"])).sum()
if overlap:
    print(f"  WARNING: {overlap} grasps happened inside the tray window - tell Claude")
else:
    print("  OK: no grasp happens inside the tray window")
print("saved release.json")

"""
Copy frames from assets/_frames/ to assets/cat_idle_XX.png and assets/cat_run_XX.png.
Frame ranges (1-indexed, inclusive):
  IDLE_RANGE = (1, 63)   → cat_idle_00 .. cat_idle_62
  RUN_RANGE  = (64, 97)  → cat_run_00  .. cat_run_33
"""
import shutil
from pathlib import Path

FRAMES_DIR = Path("assets/_frames")
OUTPUT_DIR = Path("assets")

IDLE_RANGE = (1, 63)    # frames 1-63 → idle
RUN_RANGE = (64, 97)    # frames 64-97 → run

def copy_frames(src_dir: Path, dst_dir: Path, range_start: int, range_end: int, prefix: str):
    dst_dir.mkdir(parents=True, exist_ok=True)
    idx = 0
    for i in range(range_start, range_end + 1):
        src = src_dir / f"frame_{i:03d}.png"
        dst = dst_dir / f"cat_{prefix}_{idx:02d}.png"
        if src.exists():
            shutil.copy2(src, dst)
            print(f"  {dst.name} ← {src.name}")
        else:
            print(f"  WARNING: {src.name} not found, skipping")
        idx += 1
    print(f"  Copied {idx} frames to cat_{prefix}_*.png\n")

if __name__ == "__main__":
    print(f"Idle frames ({IDLE_RANGE[0]}-{IDLE_RANGE[1]}):")
    copy_frames(FRAMES_DIR, OUTPUT_DIR, IDLE_RANGE[0], IDLE_RANGE[1], "idle")
    print(f"Run frames ({RUN_RANGE[0]}-{RUN_RANGE[1]}):")
    copy_frames(FRAMES_DIR, OUTPUT_DIR, RUN_RANGE[0], RUN_RANGE[1], "run")
    print("Done! cat_idle_*.png and cat_run_*.png updated.")

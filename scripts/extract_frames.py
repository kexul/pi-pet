"""
Extract all frames from video, remove background via flood fill + dilation,
output with magenta (#FF00FF) background to assets/_frames/.

Uses numpy/scipy for fast array operations.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, label, generate_binary_structure

VIDEO_PATH = Path("vid/jimeng-2026-05-02-4411-0-2秒，猫猫伸懒腰，蜷缩休息，2-4秒，猫猫奔跑。猫猫始终在镜头正中央。背景纯....mp4")
OUTPUT_DIR = Path("assets/_frames")
MAGENTA = (255, 0, 255)

TOLERANCE = 14          # tolerance for clean background
DILATE = 2              # eat anti-aliasing fringe
TARGET_SIZE = 128       # resize to this before background removal


def extract_all_frames(video_path: Path, output_dir: Path) -> list[Path]:
    """Use ffmpeg to extract all frames to output_dir."""
    output_dir.mkdir(parents=True, exist_ok=True)
    pattern = output_dir / "frame_%03d.png"

    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vsync", "0",
        str(pattern),
    ]
    result = subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    if result.returncode != 0:
        stderr_text = result.stderr.decode("utf-8", errors="replace") if result.stderr else ""
        print(f"ffmpeg error:\n{stderr_text}", file=sys.stderr)
        raise RuntimeError("ffmpeg failed")

    frames = sorted(output_dir.glob("frame_*.png"))
    print(f"Extracted {len(frames)} frames to {output_dir}")
    return frames


def remove_background(image_path: Path, target_size: int = None) -> Image.Image:
    """
    Remove background from image:
    1. Resize to target_size (optional)
    2. Sample bg reference from 4 corners
    3. Tolerance mask → edge-connected components → clean background
    4. Dilate mask to eat white anti-aliasing fringe
    5. Output RGBA with magenta background
    """
    img = Image.open(image_path).convert("RGB")

    # Resize before background removal to avoid magenta bleeding during interpolation
    if target_size:
        img = img.resize((target_size, target_size), Image.LANCZOS)

    img_arr = np.array(img)  # (h, w, 3)
    h, w = img_arr.shape[:2]

    # Sample background reference from 4 corners
    corners = np.array([
        img_arr[0, 0],
        img_arr[0, w - 1],
        img_arr[h - 1, 0],
        img_arr[h - 1, w - 1],
    ])
    bg_ref = corners.mean(axis=0).astype(img_arr.dtype)

    # ── Step 1: low-tolerance background mask ──
    diff = np.abs(img_arr.astype(np.int16) - bg_ref.astype(np.int16))
    bg_mask = (diff <= TOLERANCE).all(axis=2)  # (h, w) bool

    # Keep only regions connected to the edges (true background)
    # Label connected components in bg_mask
    structure = generate_binary_structure(2, 1)
    labeled, num_features = label(bg_mask, structure=structure)

    # Find which labels touch the edges
    edge_labels = set()
    edge_labels.update(labeled[0, :].ravel())
    edge_labels.update(labeled[-1, :].ravel())
    edge_labels.update(labeled[:, 0].ravel())
    edge_labels.update(labeled[:, -1].ravel())
    edge_labels.discard(0)  # 0 is background (non-mask)

    # Keep only edge-connected components
    edge_mask = np.isin(labeled, list(edge_labels))
    bg_before = int(edge_mask.sum())

    # ── Step 2: dilate to eat white anti-aliasing fringe ──
    if DILATE > 0:
        bg_mask_dilated = binary_dilation(edge_mask, iterations=DILATE)
    else:
        bg_mask_dilated = edge_mask.copy()

    # ── Step 3: Build output ──
    # ── Step 3: Build output ──
    final_mask = bg_mask_dilated
    bg_after = int(final_mask.sum())

    total = h * w
    print(f"  {image_path.name}: bg={bg_before}/{total} ({100*bg_before/total:.1f}%) "
          f"dilate=+{bg_after-bg_before} -> {100*bg_after/total:.1f}%")

    # Simple binary composite: cat pixels on magenta background
    out_arr = np.full((h, w, 4), MAGENTA + (255,), dtype=np.uint8)
    cat_mask = ~final_mask
    out_arr[cat_mask, 0:3] = img_arr[cat_mask]

    return Image.fromarray(out_arr, 'RGBA')


def process_video(video_path: Path, output_dir: Path, target_size: int = None, skip_extract: bool = False):
    """Extract frames, remove background, save to output_dir."""
    if skip_extract and list(output_dir.glob("frame_*.png")):
        raw_frames = sorted(output_dir.glob("frame_*.png"))
        print(f"Skipping extract, found {len(raw_frames)} existing frames")
    else:
        raw_frames = extract_all_frames(video_path, output_dir)

    for i, frame_path in enumerate(raw_frames):
        print(f"[{i+1}/{len(raw_frames)}] Processing {frame_path.name}...")
        result = remove_background(frame_path, target_size=target_size)
        result.save(frame_path)
        print(f"  saved")

    print(f"\nDone! {len(raw_frames)} frames in {output_dir}/")
    print("Next: manually sort frames into idle / run groups.")


if __name__ == "__main__":
    process_video(VIDEO_PATH, OUTPUT_DIR, target_size=TARGET_SIZE, skip_extract=False)

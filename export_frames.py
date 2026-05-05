"""
将 mp4 视频逐帧导出为 PNG 图片。
用法: uv run python export_frames.py
"""

import subprocess
import sys
import os
from pathlib import Path

# 修复 Windows 终端编码问题
if sys.platform == "win32":
    os.environ["PYTHONIOENCODING"] = "utf-8"

VIDEO = Path("C:/Users/kkk/projects/pet/vid/ji.mp4")
OUT_DIR = Path("C:/Users/kkk/projects/pet/vid/ji_frames")

# 创建输出目录
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ffmpeg 导出所有帧
cmd = [
    "ffmpeg",
    "-i", str(VIDEO),
    "-y",                          # 覆盖已有文件
    "-q:v", "1",                   # PNG 最高质量
    str(OUT_DIR / "frame_%04d.png"),
]

print(f"Source: {VIDEO}")
print(f"Output: {OUT_DIR}")
print(f"Cmd: {' '.join(cmd)}")

result = subprocess.run(cmd, capture_output=True, text=True)

if result.returncode != 0:
    print("[ERROR] Export failed:", file=sys.stderr)
    print(result.stderr, file=sys.stderr)
    sys.exit(1)

# 统计结果
pngs = sorted(OUT_DIR.glob("frame_*.png"))
print(f"\n[DONE] Exported {len(pngs)} frames")
for p in pngs:
    print(f"  {p.name}  ({p.stat().st_size / 1024:.1f} KB)")

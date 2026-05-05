# Plan: 视频转序列帧

## Context
将 `vid/` 中的猫猫视频（960×960, ~24fps, 4秒/97帧）提取为带透明背景的 PNG 序列帧，用于桌宠浮动窗口动画。视频分两段：0-2秒「伸懒腰/蜷缩休息」→ idle（~48帧）、2-4秒「奔跑」→ run（~49帧）。背景为近白色（~250,249,252），猫鼻子也是白色，简单色键抠图会伤到鼻子。同时将 app 状态从 idle/working/complete 简化为 idle/run。

## Approach

### 核心方案：边缘泛洪填充 (Flood Fill from Edges)
- 从图像四边出发做泛洪填充，识别相连的背景区域
- 猫鼻子虽然也是白色，但被猫身颜色包围，**不连通到边缘**，因此不会被误删
- 对每帧动态采样背景参考色（四角均值），以容差 14 做泛洪
- 将背景替换为品红色 `#FF00FF`（桌宠 app 已使用此色做透明 key）

已验证：样本帧中 84.9% 像素被识别为背景，3708 个白色像素（鼻子等）被正确保留。

### 帧提取
- 用 ffmpeg 导出全部 97 帧到临时目录（`assets/_frames/`）
- 不做时间段拆分，全部导出后由用户人工分拣哪些是 idle、哪些是 run
- 96×96 的方形视频，帧率约 24fps

## Files to modify / create

| 文件 | 操作 | 说明 |
|------|------|------|
| `scripts/extract_frames.py` | 新建 | 主脚本：调 ffmpeg 提取全部帧 + 泛洪填充去背景 |
| `assets/_frames/` | 新建 | 临时目录，全部 97 帧（品红背景），供人工分拣 |
| `assets/cat_idle_*.png` | 覆盖 | 分拣后 idle 序列帧 |
| `assets/cat_run_*.png` | 新建 | 分拣后 run 序列帧 |
| `pet_app.py` | 修改 | 状态简化为 idle/run，删 working/complete |

## Reuse
- `pet_app.py` 中 `FRAMES` 字典和 `load_frames()` — 新帧需匹配命名约定 `cat_{state}_{index:02d}.png`
- `assets/` 目录结构 — 已有 idle/working/complete 帧，保持兼容
- ffmpeg（已安装，scoop）— 视频帧提取

## Steps

- [ ] 1. 创建 `scripts/extract_frames.py`，实现：
  - [ ] 1a. `extract_all_frames(video_path, output_dir)` — 调 ffmpeg 导出全部帧到临时目录
  - [ ] 1b. `flood_fill_background(image_path)` — 边缘泛洪识别背景，替换为 #FF00FF
  - [ ] 1c. 批量处理：全部帧 → 去背景 → 输出到 `assets/_frames/`

- [ ] 2. 运行脚本，导出全部 97 帧（带品红背景）到 `assets/_frames/`

- [ ] 3. **人工分拣**：用户查看 `assets/_frames/`，将帧分为 idle 和 run 两组，告知分界点

- [ ] 4. 按分拣结果重命名输出：
  - [ ] 4a. idle 帧 → `assets/cat_idle_00.png` ~ `cat_idle_NN.png`
  - [ ] 4b. run 帧 → `assets/cat_run_00.png` ~ `cat_run_NN.png`

- [ ] 5. 修改 `pet_app.py`：状态从 idle/working/complete 改为 idle/run
  - [ ] 5a. `FRAMES` 字典：删 working/complete，加 run
  - [ ] 5b. `PetState._aggregate_state()`：状态优先级改为 run > idle
  - [ ] 5c. `PetState.tick()`：删 complete 超时逻辑

- [ ] 6. 手动抽查：确认白色鼻子未被擦除、品红背景均匀

## Verification
- 运行 `uv run python scripts/extract_frames.py`，检查 `assets/_frames/` 下 97 帧全部生成
- 随机打开几帧，确认：背景纯 `#FF00FF`，猫鼻子完整，无残留白边
- 用户分拣后，运行重命名步骤，确认 `assets/cat_idle_*.png` 和 `cat_run_*.png` 到位
- 运行 `pet_app.py`，确认浮动窗口播放 idle/run 动画正常

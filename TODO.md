# TODO

## Goal
对话完成时，在显示文字气泡的同时播报语音（edge-tts）。

## Tasks

### 1. 安装依赖
- [x] `uv pip install edge-tts`

### 2. 新增 voice_player.py 模块
- [x] 创建 `voice_player.py`，实现 `VoicePlayer` 类
- [x] `VoicePlayer.speak(text)` — 在后台线程中：用 `edge_tts.Communicate` 生成临时 MP3 → Win32 MCI 播放 → 删除临时文件
- [x] 使用 `threading.Thread` 避免阻塞 tkinter 主循环
- [x] 默认语音 `zh-CN-XiaoxiaoNeural`

### 3. 集成到 pet_app.py
- [x] 在 `FloatingPet.__init__` 中创建 `VoicePlayer` 实例
- [x] 在 `_poll_status` 中，当有 message 时，在显示气泡的同时调用 `voice_player.speak(message)`
- [x] 处理快速连续消息：新消息到达时停止当前播放

### 4. 验证
- [x] 语法检查通过
- [x] 手动测试：触发 complete 状态，确认语音播报正常，气泡同步显示

## Notes
- 语音与气泡同时出现，不互相替代
- 音频即时生成、播完即删
- 播放走后台线程，不阻塞动画和 UI

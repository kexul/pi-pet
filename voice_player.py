"""
Voice playback via Microsoft Edge TTS (edge-tts).
Generates MP3 to a temp file, plays via Win32 MCI, then cleans up.
Runs in a background thread so the tkinter UI is never blocked.
"""
import ctypes
import ctypes.wintypes as wintypes
import os
import re
import sys
import tempfile
import threading
import uuid

import edge_tts

DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"

# ── Win32 MCI helpers ───────────────────────────────────────
def _get_short_path(long_name: str) -> str:
    """Get the DOS-safe 8.3 short path for MCI (which can choke on Unicode)."""
    buf_size = 0
    while True:
        buf = ctypes.create_unicode_buffer(buf_size)
        needed = ctypes.windll.kernel32.GetShortPathNameW(long_name, buf, buf_size)
        if buf_size >= needed:
            return buf.value
        buf_size = needed


def _mci_send(cmd: str) -> int:
    """Send an MCI command string. Returns 0 on success."""
    return ctypes.windll.winmm.mciSendStringW(cmd, 0, 0, 0)


# ── VoicePlayer ─────────────────────────────────────────────
class VoicePlayer:
    """Non-blocking TTS player. Call `speak(text)` from any thread."""

    def __init__(self, voice: str = DEFAULT_VOICE):
        self._voice = voice
        self._lock = threading.Lock()
        self._current_alias: str | None = None
        self._stop_requested = False

    def speak(self, text: str) -> None:
        """Speak `text` asynchronously. Cancels any in-progress playback first."""
        text = _strip_markdown(text)
        if not text:
            return
        self.stop()
        alias = f"pi_pet_{uuid.uuid4().hex[:8]}"
        t = threading.Thread(
            target=self._speak_thread, args=(text, alias), daemon=True
        )
        with self._lock:
            self._current_alias = alias
            self._stop_requested = False
        t.start()

    def stop(self) -> None:
        """Stop current playback (if any) and clean up."""
        with self._lock:
            if self._current_alias is not None:
                self._stop_requested = True
                _mci_send(f"Stop {self._current_alias}")
                _mci_send(f"Close {self._current_alias}")
                self._current_alias = None

    def _speak_thread(self, text: str, alias: str) -> None:
        mp3_path = None
        try:
            # ── 1. Generate TTS audio ──
            with tempfile.NamedTemporaryFile(
                suffix=".mp3", delete=False
            ) as tmp:
                mp3_path = tmp.name

            if self._stop_requested:
                return

            communicate = edge_tts.Communicate(text, self._voice)
            communicate.save_sync(mp3_path)

            if self._stop_requested:
                return

            # ── 2. Play via Win32 MCI ──
            mp3_short = _get_short_path(mp3_path)
            rc = _mci_send(f'Open "{mp3_short}" Type MPEGVideo Alias {alias}')
            if rc != 0:
                print(f"[voice] MCI Open failed (rc={rc})", flush=True)
                return

            try:
                if not self._stop_requested:
                    _mci_send(f"Play {alias} Wait")
            finally:
                _mci_send(f"Close {alias}")

        except Exception as exc:
            print(f"[voice] ERROR: {exc}", flush=True)

        finally:
            # ── 3. Clean up temp file ──
            if mp3_path and os.path.exists(mp3_path):
                try:
                    os.unlink(mp3_path)
                except OSError:
                    pass

            # Clear alias if we still hold it
            with self._lock:
                if self._current_alias == alias:
                    self._current_alias = None


def _strip_markdown(text: str) -> str:
    """Remove common markdown formatting so TTS reads naturally."""
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'\[([^\]]*)\]\([^\)]*\)', r'\1', text)
    text = re.sub(r'\*\*\*([^*]+)\*\*\*', r'\1', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    text = re.sub(r'`([^`]+)`', r'\1', text)
    text = re.sub(r'```[\s\S]*?```', '', text)
    text = re.sub(r'~~([^~]+)~~', r'\1', text)
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ── quick smoke-test ────────────────────────────────────────
if __name__ == "__main__":
    vp = VoicePlayer()
    vp.speak("你好，任务完成了！")
    # Keep main thread alive long enough for playback
    import time
    time.sleep(5)
    print("Done.")

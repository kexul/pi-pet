"""
Tray Pet - Animated system tray cat.
Reacts to pi agent state changes from the pi extension.

System tray: animated cat icon with right-click menu (Exit).
"""
import json
import os
import re
import sys
import time
import threading
from pathlib import Path

from PIL import Image, ImageDraw
import pystray

from voice_player import VoicePlayer

# ── config ──────────────────────────────────────────────────
ASSETS_DIR = Path(__file__).parent / "assets"
STATUS_DIR = Path(os.environ.get("TEMP", "/tmp")) / "pi-pet"
STALE_TTL = 60.0  # seconds before a status file is considered stale
POLL_INTERVAL_MS = 100         # status file poll (milliseconds)
ANIM_FPS = 24                  # animation frame rate (matches source video)
TRAY_ICON_SIZE = 64            # icon image size passed to pystray
TRAY_TIP_MAX_CHARS = 127       # Windows tray tooltip limit
TRAY_NOTIFY_MAX_CHARS = 255    # Windows notification body limit
TRAY_TITLE_MAX_CHARS = 63      # Windows notification title limit
TTS_MAX_CHARS = 40             # keep spoken completion messages short
TRAY_FRAME_CACHE = {}          # id(PIL frame) -> prepared tray icon


# ── load frames ─────────────────────────────────────────────
def load_frames(name: str, count: int) -> list[Image.Image]:
    frames = []
    for i in range(count):
        path = ASSETS_DIR / f"cat_{name}_{i:02d}.png"
        if path.exists():
            frames.append(Image.open(path))
        else:
            print(f"WARNING: missing frame {path}")
    return frames


def _magenta_to_transparent(img: Image.Image) -> Image.Image:
    """Convert magenta-background image to transparent RGBA."""
    img = img.convert("RGBA")
    data = img.getdata()
    new_data = []
    for r, g, b, a in data:
        if r == 255 and g == 0 and b == 255:
            new_data.append((0, 0, 0, 0))
        else:
            new_data.append((r, g, b, 255))
    img.putdata(new_data)
    return img


def _prepare_tray_frame(img: Image.Image, size: int = TRAY_ICON_SIZE) -> Image.Image:
    """Convert an animation frame into a transparent tray icon."""
    img = _magenta_to_transparent(img)
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
    img.thumbnail((size, size), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    x = (size - img.width) // 2
    y = (size - img.height) // 2
    canvas.alpha_composite(img, (x, y))
    return canvas


def _draw_tray_icon(size: int = TRAY_ICON_SIZE) -> Image.Image:
    """Draw a simple cat icon for the system tray using PIL ImageDraw.

    The icon is a cat face with ears, eyes, nose, and whiskers on a
    transparent background, rendered at `size`×`size`.
    """
    from PIL import ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size  # shorthand

    # Colors
    cat_orange = (255, 165, 79, 255)    # warm orange cat
    cat_dark = (200, 120, 50, 255)      # darker orange for ears
    white = (255, 255, 255, 255)
    black = (30, 30, 30, 255)
    nose_pink = (255, 150, 150, 255)

    # ── ears (triangles above the head) ──
    # left ear
    draw.polygon([
        (s * 0.18, s * 0.35),
        (s * 0.28, s * 0.05),
        (s * 0.38, s * 0.28),
    ], fill=cat_dark)
    # inner left ear
    draw.polygon([
        (s * 0.22, s * 0.32),
        (s * 0.28, s * 0.12),
        (s * 0.35, s * 0.30),
    ], fill=cat_orange)

    # right ear
    draw.polygon([
        (s * 0.62, s * 0.28),
        (s * 0.72, s * 0.05),
        (s * 0.82, s * 0.35),
    ], fill=cat_dark)
    # inner right ear
    draw.polygon([
        (s * 0.65, s * 0.30),
        (s * 0.72, s * 0.12),
        (s * 0.78, s * 0.32),
    ], fill=cat_orange)

    # ── face (rounded ellipse) ──
    face_margin = s * 0.10
    draw.ellipse(
        (face_margin, s * 0.22, s - face_margin, s * 0.90),
        fill=cat_orange,
    )

    # ── eyes ──
    eye_w = s * 0.10
    eye_h = s * 0.13
    # left eye
    draw.ellipse(
        (s * 0.32 - eye_w / 2, s * 0.48 - eye_h / 2,
         s * 0.32 + eye_w / 2, s * 0.48 + eye_h / 2),
        fill=white,
    )
    draw.ellipse(
        (s * 0.33 - eye_w / 4, s * 0.48 - eye_h / 4,
         s * 0.33 + eye_w / 4, s * 0.48 + eye_h / 4),
        fill=black,
    )
    # right eye
    draw.ellipse(
        (s * 0.68 - eye_w / 2, s * 0.48 - eye_h / 2,
         s * 0.68 + eye_w / 2, s * 0.48 + eye_h / 2),
        fill=white,
    )
    draw.ellipse(
        (s * 0.67 - eye_w / 4, s * 0.48 - eye_h / 4,
         s * 0.67 + eye_w / 4, s * 0.48 + eye_h / 4),
        fill=black,
    )

    # ── nose ──
    draw.ellipse(
        (s * 0.46, s * 0.58, s * 0.54, s * 0.63),
        fill=nose_pink,
    )

    # ── mouth (two small arcs connecting below nose) ──
    draw.arc(
        (s * 0.38, s * 0.58, s * 0.50, s * 0.68),
        start=0, end=90, fill=black, width=max(1, int(s * 0.02)),
    )
    draw.arc(
        (s * 0.50, s * 0.58, s * 0.62, s * 0.68),
        start=90, end=180, fill=black, width=max(1, int(s * 0.02)),
    )

    # ── whiskers ──
    w_thick = max(1, int(s * 0.015))
    # left whiskers
    draw.line((s * 0.08, s * 0.55, s * 0.32, s * 0.60), fill=black, width=w_thick)
    draw.line((s * 0.10, s * 0.63, s * 0.32, s * 0.65), fill=black, width=w_thick)
    # right whiskers
    draw.line((s * 0.92, s * 0.55, s * 0.68, s * 0.60), fill=black, width=w_thick)
    draw.line((s * 0.90, s * 0.63, s * 0.68, s * 0.65), fill=black, width=w_thick)

    return img


# Load RGB frames (magenta background)
FRAMES = {
    "idle":     load_frames("idle", 63),
    "run":      load_frames("run", 34),
}

# Idle animation: ping-pong 0↔62 (stretch → curl → sleep → stretch → ...)
# When switching idle→run from stretched zone (frame < IDLE_CURLED_START),
# fast-forward to curled zone first for a smoother transition.
IDLE_CURLED_START = 38   # first frame where cat is fully curled
IDLE_FAST_SPEED = 5       # frames per tick during fast-forward
IDLE_CURL_HOLD_TICKS = 1440  # stay curled for 60s @ 24fps before uncurling

# Run animation: 0-7 settle (curl→run), 8-27 loop (running cycles)
RUN_LOOP_START = 8        # first loop frame
RUN_LOOP_END = 28         # last loop frame (exclusive: frames 8-27)

# ── state machine ───────────────────────────────────────────
class PetState:
    def __init__(self):
        self.current = "idle"
        self.frame_idx = 0
        self._idle_dir = 1           # 1 = forward, -1 = backward
        self._pending_run = False    # fast-forward idle → curl → switch to run
        self._curl_hold = 0            # ticks remaining at curled end before reversing
        self.lock = threading.Lock()

    def _aggregate_state(self) -> tuple[str | None, str | None]:
        """Scan status files, return (state, message).
        Simple: any file with working/complete → run, otherwise idle.
        Files older than STALE_TTL are ignored (dead pi).
        """
        if not STATUS_DIR.exists():
            return "idle", None
        now = time.time()
        has_active = False
        latest_message = None
        latest_ts = 0
        for f in STATUS_DIR.glob("status-*.json"):
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                ts = data.get("timestamp", 0) / 1000.0
                # Skip files older than STALE_TTL (pi likely dead)
                if now - ts > STALE_TTL:
                    try:
                        f.unlink()
                    except OSError:
                        pass
                    continue
                raw_state = data.get("state", "idle")
                if raw_state == "working":
                    has_active = True
                if raw_state == "complete" and ts > latest_ts:
                    msg = data.get("message", "").strip()
                    if msg:
                        latest_ts = ts
                        latest_message = msg
            except Exception:
                try:
                    f.unlink()
                except OSError:
                    pass
        if has_active:
            return "run", latest_message
        return "idle", latest_message

    def update_from_file(self) -> str | None:
        """Scan status files, update state. Returns message for notification."""
        new_state, new_message = self._aggregate_state()
        with self.lock:
            # Check for new message (even if state unchanged)
            result_message = None
            if new_message and new_message != getattr(self, '_last_message', None):
                self._last_message = new_message
                result_message = new_message

            if new_state == self.current:
                return result_message

            old = self.current

            # Guard: don't interrupt an in-progress smooth transition
            if self._pending_run and old == "idle":
                return result_message  # fast-forward still in progress

            # idle → run while in stretched zone: fast-forward to curl first
            if old == "idle" and new_state == "run" and self.frame_idx < IDLE_CURLED_START:
                self._pending_run = True
                self._idle_dir = 1  # force forward toward curled zone
                print(f"[pet] idle → run (fast-forward)", flush=True)
                return result_message

            # run → idle: direct switch
            # Direct transition
            self.current = new_state
            self.frame_idx = 0
            self._idle_dir = 1
            self._pending_run = False
            print(f"[pet] {old} → {new_state}", flush=True)
            return result_message

    def tick(self) -> Image.Image | None:
        """Advance animation, return current frame."""
        with self.lock:
            state = self.current
            if state == "idle":
                return self._tick_idle()
            else:
                return self._tick_run()

    def _tick_run(self) -> Image.Image | None:
        """Run: play 0→7 settle once, then loop 8→27."""
        frames = FRAMES.get("run")
        if not frames:
            return None

        # Normal run animation
        frame = frames[self.frame_idx]
        self.frame_idx += 1
        if self.frame_idx < RUN_LOOP_START:
            return frame
        if self.frame_idx >= RUN_LOOP_END:
            self.frame_idx = RUN_LOOP_START
        return frame

    def _tick_idle(self) -> Image.Image | None:
        """Ping-pong idle: 0 → 62 → 0 → ...
        If _pending_run, fast-forward to curled zone then switch to run."""
        frames = FRAMES.get("idle")
        if not frames:
            return None
        n = len(frames)

        # Fast-forward: idle → run transition
        if self._pending_run:
            self.frame_idx += IDLE_FAST_SPEED
            if self.frame_idx >= IDLE_CURLED_START:
                self.current = "run"
                self.frame_idx = 0
                self._idle_dir = 1
                self._pending_run = False
                print("[pet] fast-forward done → run", flush=True)
                run_frames = FRAMES.get("run")
                return run_frames[0] if run_frames else frames[self.frame_idx]
            if self.frame_idx >= n:
                self.frame_idx = n - 1
            return frames[self.frame_idx]

        # Normal ping-pong idle
        frame = frames[self.frame_idx]
        self.frame_idx += self._idle_dir
        if self.frame_idx >= n:
            if self._curl_hold < IDLE_CURL_HOLD_TICKS:
                self._curl_hold += 1
                self.frame_idx = n - 1  # stay at curled end
            else:
                self._curl_hold = 0
                self.frame_idx = n - 2
                self._idle_dir = -1
        elif self.frame_idx < 0:
            self.frame_idx = 1
            self._idle_dir = 1
        return frame

    def get_current_frame(self) -> Image.Image | None:
        """Get current frame without advancing."""
        with self.lock:
            state = self.current
            frames = FRAMES.get(state, FRAMES["idle"])
            if frames:
                return frames[self.frame_idx % len(frames)]
            return None


# ── application ─────────────────────────────────────────────
class PetApp:
    def __init__(self):
        self.state = PetState()
        self.icon = None
        self.voice_player = VoicePlayer()
        self._running = False
        self._last_tooltip = "pi pet cat"

    def _on_quit(self, icon, item):
        self._running = False
        self.voice_player.stop()
        icon.stop()

    def _tray_setup(self, icon):
        icon.visible = True
        next_poll = 0.0
        while self._running:
            now = time.monotonic()
            if now >= next_poll:
                self._poll_status()
                next_poll = now + POLL_INTERVAL_MS / 1000
            self._animate_tray_icon()
            time.sleep(1 / ANIM_FPS)

    def _poll_status(self):
        message = self.state.update_from_file()
        if not message:
            return
        message = _strip_markdown(message)
        self.voice_player.speak(_tts_summary(message))

    def _show_complete_notification(self, message: str):
        title = _truncate_text("pi 完成啦", TRAY_TITLE_MAX_CHARS)
        body = _truncate_text(message, TRAY_NOTIFY_MAX_CHARS)
        tooltip = _truncate_text(f"{title}: {body}", TRAY_TIP_MAX_CHARS)
        self._last_tooltip = tooltip
        if self.icon is None:
            return
        self.icon.title = tooltip
        try:
            self.icon.notify(body, title)
        except NotImplementedError:
            pass

    def _animate_tray_icon(self):
        frame = self.state.tick()
        if frame is None or self.icon is None:
            return
        key = id(frame)
        tray_frame = TRAY_FRAME_CACHE.get(key)
        if tray_frame is None:
            tray_frame = _prepare_tray_frame(frame)
            TRAY_FRAME_CACHE[key] = tray_frame
        self.icon.icon = tray_frame

    def _run_tray(self):
        initial_frame = self.state.get_current_frame()
        if initial_frame:
            tray_icon_img = _prepare_tray_frame(initial_frame)
        else:
            tray_icon_img = _draw_tray_icon()

        menu = pystray.Menu(pystray.MenuItem("Exit", self._on_quit))

        self.icon = pystray.Icon(
            "pi-pet",
            tray_icon_img,
            self._last_tooltip,
            menu,
        )
        self.icon.run(self._tray_setup)

    def run(self):
        print("[pet] Cat pet started!", flush=True)
        print("[pet]   Tray icon: animated, right-click for menu", flush=True)
        print(f"[pet]   Watching: {STATUS_DIR}/status-*.json", flush=True)
        self._running = True
        self._run_tray()
        print("[pet] Goodbye!", flush=True)


def _truncate_text(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 1] + "…"


def _tts_summary(text: str) -> str:
    first_line = text.splitlines()[0].strip() if text.strip() else ""
    if not first_line:
        return "pi 完成啦"
    return _truncate_text(first_line, TTS_MAX_CHARS)


def _strip_markdown(text: str) -> str:
    """Remove common markdown formatting so TTS / notifications read naturally."""
    # images
    text = re.sub(r'!\[.*?\]\(.*?\)', '', text)
    # links → keep text only
    text = re.sub(r'\[([^\]]*)\]\([^\)]*\)', r'\1', text)
    # bold + italic
    text = re.sub(r'\*\*\*([^*]+)\*\*\*', r'\1', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
    text = re.sub(r'__([^_]+)__', r'\1', text)
    text = re.sub(r'\*([^*]+)\*', r'\1', text)
    text = re.sub(r'_([^_]+)_', r'\1', text)
    # inline code
    text = re.sub(r'`([^`]+)`', r'\1', text)
    # code blocks
    text = re.sub(r'```[\s\S]*?```', '', text)
    # strikethrough
    text = re.sub(r'~~([^~]+)~~', r'\1', text)
    # headings
    text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)
    # list markers
    text = re.sub(r'^[\s]*[-*+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^[\s]*\d+\.\s+', '', text, flags=re.MULTILINE)
    # horizontal rules
    text = re.sub(r'^[-*_]{3,}\s*$', '', text, flags=re.MULTILINE)
    # collapse whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def main():
    if not any(ASSETS_DIR.iterdir()):
        print(f"ERROR: No frames found in {ASSETS_DIR}", flush=True)
        return 1

    try:
        app = PetApp()
        app.run()
    except Exception as e:
        print(f"[pet] FATAL: {e}", flush=True)
        import traceback
        traceback.print_exc()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

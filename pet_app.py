"""
Desktop Pet - Floating window cat + system tray icon.
Reacts to pi agent state changes from the pi extension.

Floating window: 128x128, always-on-top, magenta-key transparency, click-through by default.
System tray: static icon for right-click menu (Move Pet / Exit).
"""
import ctypes
import ctypes.wintypes as wintypes
import json
import os
import sys
import time
import threading
from pathlib import Path

from PIL import Image, ImageTk
import tkinter as tk
import pystray

# ── config ──────────────────────────────────────────────────
ASSETS_DIR = Path(__file__).parent / "assets"
STATUS_DIR = Path(os.environ.get("TEMP", "/tmp")) / "pi-pet"
STALE_TTL = 60.0  # seconds before a status file is considered stale
PID_CHECK_INTERVAL = 5.0  # seconds between PID liveness checks
POSITION_FILE = Path(os.environ.get("TEMP", "/tmp")) / "pi-pet-position.json"
POLL_INTERVAL_MS = 100         # status file poll (milliseconds)
ANIM_FPS = 24                  # animation frame rate (matches source video)
WIN_SIZE = 128                 # floating window size (pixels)
COLOR_KEY = "#FF00FF"          # magenta = transparent

# ── Win32 helpers (click-through only) ──────────────────────
GWL_EXSTYLE = -20
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_FRAMECHANGED = 0x0020

user32 = ctypes.windll.user32


def _set_click_through(hwnd: int, enable: bool):
    """Toggle WS_EX_TRANSPARENT on a window (mouse pass-through)."""
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    if enable:
        style |= WS_EX_TRANSPARENT
    else:
        style &= ~WS_EX_TRANSPARENT
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
    user32.SetWindowPos(
        wintypes.HWND(hwnd), 0, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
    )


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


def _draw_tray_icon(size: int = 64) -> Image.Image:
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
        """Scan status files, update state. Returns message for speech bubble."""
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


# ── speech bubble ──────────────────────────────────────────
class SpeechBubble:
    """A simple fixed-size speech bubble above the pet."""

    BUBBLE_BG = "#FFF8DC"
    BUBBLE_FG = "#333333"
    FONT = ("Microsoft YaHei", 11)
    DISMISS_MS = 4000

    def __init__(self):
        self._window: tk.Toplevel | None = None
        self._dismiss_id: str | None = None
        self._last_message: str | None = None

    def show(self, message: str, anchor_x: int, anchor_y: int, anchor_size: int):
        """Show a simple completion notification."""
        if message == self._last_message:
            return
        self._last_message = message
        self.dismiss()

        # Just a brief notification, not the full message
        text = "\u2714 pi \u5b8c\u6210\u5566!"  # ✓ pi 完成啦!

        self._window = tk.Toplevel()
        self._window.overrideredirect(True)
        self._window.attributes("-topmost", True)
        self._window.configure(bg=self.BUBBLE_BG)

        hwnd = self._window.winfo_id()
        self._window.update_idletasks()
        style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        style |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)

        label = tk.Label(
            self._window, text=text, bg=self.BUBBLE_BG, fg=self.BUBBLE_FG,
            font=(self.FONT[0], self.FONT[1], "bold"),
            padx=20, pady=12,
        )
        label.pack()

        x = anchor_x + (anchor_size - 160) // 2
        y = anchor_y - 50 - 12
        sw = self._window.winfo_screenwidth()
        sh = self._window.winfo_screenheight()
        if x < 8:
            x = 8
        if y < 8:
            y = anchor_y + anchor_size + 12

        self._window.geometry(f"+{x}+{y}")
        self._dismiss_id = self._window.after(self.DISMISS_MS, self.dismiss)
        print(f"[pet] Bubble: done", flush=True)

    def dismiss(self):
        """Close the speech bubble."""
        if self._window is not None:
            try:
                self._window.destroy()
            except Exception:
                pass
            self._window = None
            self._dismiss_id = None
            print("[pet] Bubble dismissed", flush=True)


# ── floating pet window ─────────────────────────────────────
class FloatingPet:
    """A borderless, always-on-top window with magenta-key transparency."""

    def __init__(self, state: PetState):
        self.state = state
        self._interactive_until = 0.0
        self._dragging = False
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._drag_win_x = 0
        self._drag_win_y = 0
        self._drag_moved = False
        self.bubble = SpeechBubble()

        # Create tkinter window
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=COLOR_KEY)
        self.root.wm_attributes("-transparentcolor", COLOR_KEY)

        # Load position
        x, y = self._load_position()
        self.root.geometry(f"{WIN_SIZE}x{WIN_SIZE}+{x}+{y}")

        # Force window realization
        self.root.update_idletasks()
        self.hwnd = self.root.winfo_id()

        # Set extended styles: tool window (no taskbar) + no activate
        style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
        style |= WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
        user32.SetWindowLongW(self.hwnd, GWL_EXSTYLE, style)
        user32.SetWindowPos(
            wintypes.HWND(self.hwnd), 0, 0, 0, 0, 0,
            SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED,
        )

        # Default: click-through
        _set_click_through(self.hwnd, True)
        print(f"[pet] Click-through enabled", flush=True)

        # Label that shows the cat frame
        self._label = tk.Label(
            self.root, bg=COLOR_KEY, bd=0, highlightthickness=0,
        )
        self._label.pack(fill=tk.BOTH, expand=True)

        # Show initial frame
        self._show_frame(self.state.get_current_frame())

        # Mouse bindings (only active when click-through is off)
        self._label.bind("<Button-1>", self._on_mouse_down)
        self._label.bind("<B1-Motion>", self._on_mouse_move)
        self._label.bind("<ButtonRelease-1>", self._on_mouse_up)

        print(f"[pet] Window ready at ({x},{y})", flush=True)

    def _show_frame(self, pil_image: Image.Image | None):
        """Display a frame on the label."""
        if pil_image is None:
            return
        # Use PhotoImage from cache or convert on-the-fly
        tk_img = ImageTk.PhotoImage(pil_image)
        self._label.configure(image=tk_img)
        self._label.image = tk_img  # prevent GC

    # ── position persistence ────────────────────────────
    def _load_position(self) -> tuple[int, int]:
        try:
            if POSITION_FILE.exists():
                data = json.loads(POSITION_FILE.read_text())
                return data["x"], data["y"]
        except (json.JSONDecodeError, OSError, KeyError):
            pass
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        return sw - WIN_SIZE - 16, sh - WIN_SIZE - 80

    def _save_position(self):
        try:
            POSITION_FILE.write_text(json.dumps({
                "x": self.root.winfo_x(),
                "y": self.root.winfo_y(),
            }))
        except OSError:
            pass

    # ── interactivity ───────────────────────────────────
    def enable_interactive(self):
        """Temporarily disable click-through for dragging / clicking."""
        _set_click_through(self.hwnd, False)
        self._interactive_until = time.time() + 3.0
        self.root.after(3000, self._check_interactive_timeout)
        print("[pet] Interactive mode ON (3s)", flush=True)

    def _check_interactive_timeout(self):
        if time.time() >= self._interactive_until and not self._dragging:
            _set_click_through(self.hwnd, True)
            print("[pet] Interactive mode OFF", flush=True)

    def _reset_interactive_timer(self):
        self._interactive_until = time.time() + 3.0

    # ── drag handling ───────────────────────────────────
    def _on_mouse_down(self, event):
        self._dragging = True
        self._drag_moved = False
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        self._drag_win_x = self.root.winfo_x()
        self._drag_win_y = self.root.winfo_y()

    def _on_mouse_move(self, event):
        if not self._dragging:
            return
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y
        if abs(dx) > 2 or abs(dy) > 2:
            self._drag_moved = True
        new_x = self._drag_win_x + dx
        new_y = self._drag_win_y + dy
        self.root.geometry(f"+{new_x}+{new_y}")

    def _on_mouse_up(self, event):
        if self._dragging:
            self._dragging = False
            if self._drag_moved:
                self._save_position()
                self._reset_interactive_timer()
            else:
                self._on_click_feedback()
                self._reset_interactive_timer()

    def _on_click_feedback(self):
        """Brief bounce reaction when clicked."""
        orig_x = self.root.winfo_x()
        orig_y = self.root.winfo_y()

        def _bounce(step):
            offsets = [0, -8, 0, -4, 0]
            if step >= len(offsets):
                return
            self.root.geometry(f"+{orig_x}+{orig_y + offsets[step]}")
            self.root.after(40, lambda: _bounce(step + 1))

        _bounce(0)

    # ── main loop ───────────────────────────────────────
    def start(self):
        self._poll_status()
        self._animate()
        self.root.mainloop()

    def stop(self):
        try:
            self.root.destroy()
        except Exception:
            pass

    def _poll_status(self):
        message = self.state.update_from_file()
        # Show speech bubble if there's a new complete message
        if message:
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            self.bubble.show(message, x, y, WIN_SIZE)
        self.root.after(POLL_INTERVAL_MS, self._poll_status)

    def _animate(self):
        frame = self.state.tick()
        if frame:
            self._show_frame(frame)
        self.root.after(int(1000 / ANIM_FPS), self._animate)


# ── application ─────────────────────────────────────────────
class PetApp:
    def __init__(self):
        self.state = PetState()
        self.floating = FloatingPet(self.state)
        self.icon = None

    def _on_move(self, icon, item):
        self.floating.root.after(0, self.floating.enable_interactive)

    def _on_quit(self, icon, item):
        icon.stop()
        self.floating.root.after(0, self.floating.stop)

    def _run_tray(self):
        initial_frame = FRAMES["idle"][0] if FRAMES["idle"] else None
        if not initial_frame:
            print("ERROR: no tray icon")
            return

        # Draw a dedicated cat icon for tray visibility
        tray_icon_img = _draw_tray_icon()

        menu = pystray.Menu(
            pystray.MenuItem("Move Pet", self._on_move),
            pystray.MenuItem("Exit", self._on_quit),
        )

        self.icon = pystray.Icon(
            "pi-pet",
            tray_icon_img,
            "pi pet cat",
            menu,
        )
        self.icon.run()

    def run(self):
        tray_thread = threading.Thread(target=self._run_tray, daemon=True)
        tray_thread.start()

        print("[pet] Cat pet started!", flush=True)
        print(f"[pet]   Floating window: {WIN_SIZE}x{WIN_SIZE}", flush=True)
        print(f"[pet]   Tray icon: right-click for menu", flush=True)
        print(f"[pet]   Watching: {STATUS_DIR}/status-*.json", flush=True)

        self.floating.start()
        print("[pet] Goodbye!", flush=True)


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

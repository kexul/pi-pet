# pi-pet 🐱

Animated system tray cat that reacts to [pi](https://pi.dev) coding agent state changes.

- **idle** — stretches and curls
- **working** — runs when pi is processing
- **complete** — speaks the message

## Setup

```bash
# Install deps
uv pip install pillow pystray

# Run the pet
uv run python pet_app.py
```

## pi Extension

Copy `.pi/extensions/pet-watcher.ts` to `~/.pi/agent/extensions/` for global use.

The extension writes status files to `%TEMP%/pi-pet/` which the pet app watches.

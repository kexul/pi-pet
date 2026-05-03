/**
 * pi-pet Extension: Notifies the desktop pet app about agent state changes.
 *
 * Each pi instance writes its own status file under %TEMP%/pi-pet/status-{PID}.json.
 * The Python pet app scans all files and aggregates: working > complete > idle.
 */
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { writeFileSync, existsSync, mkdirSync, unlinkSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const STATUS_DIR = join(tmpdir(), "pi-pet");
const STATUS_FILE = join(STATUS_DIR, `status-${process.pid}.json`);

type PetState = "idle" | "working" | "complete";

interface StatusPayload {
  state: PetState;
  timestamp: number;
  pid: number;
  message?: string;
}

function writeState(state: PetState, message?: string) {
  try {
    if (!existsSync(STATUS_DIR)) {
      mkdirSync(STATUS_DIR, { recursive: true });
    }
    const payload: StatusPayload = { state, timestamp: Date.now(), pid: process.pid };
    if (message) {
      payload.message = message;
    }
    writeFileSync(STATUS_FILE, JSON.stringify(payload) + "\n");
  } catch {
    // Silently ignore write errors (pet app may not be running)
  }
}

function cleanup() {
  try {
    if (existsSync(STATUS_FILE)) {
      unlinkSync(STATUS_FILE);
    }
  } catch {
    // Silently ignore cleanup errors
  }
}

export default function (pi: ExtensionAPI) {
  // Initialize to idle
  writeState("idle");

  // Current state tracker for heartbeat
  let currentState: PetState = "idle";

  // Heartbeat: refresh timestamp every 15s so STALE_TTL doesn't trigger
  const heartbeat = setInterval(() => {
    writeState(currentState);
  }, 15000);

  // Agent starts working
  pi.on("agent_start", async () => {
    currentState = "working";
    writeState("working");
  });

  // Agent finishes - celebrate with last message!
  pi.on("agent_end", async (event) => {
    // Extract text from the last assistant message
    let lastText: string | undefined;
    const messages = event.messages;
    if (messages && messages.length > 0) {
      // Find the last assistant message (walk backwards)
      for (let i = messages.length - 1; i >= 0; i--) {
        const msg = messages[i];
        if (msg.role === "assistant" && msg.content) {
          // Collect all text blocks
          const texts: string[] = [];
          for (const block of msg.content) {
            if (block.type === "text" && (block as any).text) {
              texts.push((block as any).text);
            }
          }
          if (texts.length > 0) {
            lastText = texts.join("\n");
            break;
          }
        }
      }
    }
    currentState = "complete";
    writeState("complete", lastText);

    // Auto-transition back to idle after celebration period
    setTimeout(() => {
      currentState = "idle";
      writeState("idle");
    }, 4000);
  });

  // Clean up on shutdown
  pi.on("session_shutdown", async () => {
    clearInterval(heartbeat);
    cleanup();
  });

  // Also clean up on process exit (graceful and crash)
  process.on("exit", () => { clearInterval(heartbeat); cleanup(); });
  process.on("SIGINT", () => { clearInterval(heartbeat); cleanup(); process.exit(); });
  process.on("SIGTERM", () => { clearInterval(heartbeat); cleanup(); process.exit(); });
}

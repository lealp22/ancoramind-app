"""Idle eval container. Starting it is never permission to execute a campaign."""

from __future__ import annotations

import json
import signal
import sys
import threading
from pathlib import Path
from types import FrameType

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval_source import source_identity  # noqa: E402


def main() -> int:
    try:
        identity = source_identity(ROOT)
        if identity["worktree"] != "clean":
            raise ValueError("eval_clean_image_required")
    except (ValueError, OSError):
        print(json.dumps({"status": "eval_service_blocked", "inference_started": False}),
              flush=True)
        return 1
    stopped = threading.Event()

    def stop(signum: int, frame: FrameType | None) -> None:
        stopped.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    print(json.dumps({"status": "idle_manual_only", "inference_started": False, **identity}),
          flush=True)
    stopped.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

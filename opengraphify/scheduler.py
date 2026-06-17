"""Daemon mode: run the graph-update pipeline on a fixed interval."""
from __future__ import annotations

import signal
import sys
import time
from datetime import datetime
from pathlib import Path

from opengraphify.config import Config
from opengraphify.runner import run


def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def watch(root: Path, config: Config, *, force_first: bool = False) -> None:
    """Run the pipeline every config.interval_minutes minutes until interrupted.

    - First run is incremental unless force_first=True.
    - SIGTERM and KeyboardInterrupt both trigger a clean shutdown.
    - Errors in a single pass are logged but do not stop the loop.
    """
    interval_secs = config.interval_minutes * 60
    shutdown_requested = False

    def _handle_signal(signum: int, frame: object) -> None:
        nonlocal shutdown_requested
        print(f"\n[opengraphify] received signal {signum}, shutting down after current pass...", flush=True)
        shutdown_requested = True

    signal.signal(signal.SIGTERM, _handle_signal)
    # SIGINT is handled via KeyboardInterrupt in the except block below.

    print(
        f"[opengraphify] starting watch mode on {root} "
        f"(interval: {config.interval_minutes} min, backend: {config.provider}/{config.model})"
    )

    first_run = True
    while not shutdown_requested:
        print(f"\n[opengraphify] [{_timestamp()}] running pass...", flush=True)
        try:
            run(root, config, force=force_first and first_run)
        except Exception as exc:
            print(f"[opengraphify] ERROR during pass: {exc}", file=sys.stderr)
        first_run = False

        if shutdown_requested:
            break

        print(
            f"[opengraphify] [{_timestamp()}] next run in {config.interval_minutes} min "
            f"(Ctrl+C to stop)",
            flush=True,
        )

        # Sleep in short increments so SIGTERM / KeyboardInterrupt wake us quickly.
        deadline = time.monotonic() + interval_secs
        try:
            while time.monotonic() < deadline and not shutdown_requested:
                time.sleep(min(5.0, deadline - time.monotonic()))
        except KeyboardInterrupt:
            print("\n[opengraphify] interrupted, stopping watch.", flush=True)
            break

    print(f"[opengraphify] [{_timestamp()}] watch stopped.", flush=True)

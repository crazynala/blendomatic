#!/usr/bin/env python3
"""Blendomatic worker daemon that polls run bundles and executes jobs."""
from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import shutil
import signal
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # Optional but recommended so remote workers get credentials.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional dependency
    load_dotenv = None  # type: ignore

if load_dotenv is not None:
    try:
        load_dotenv(Path(__file__).parent / ".env", override=False)
    except Exception:  # pragma: no cover - best effort
        pass

from path_utils import RUNS_DIR  # noqa: E402  (loaded after dotenv)
from worker_registry import (  # noqa: E402
    get_worker_id,
    get_worker_mode,
    record_heartbeat,
)
from blender_tui_bridge import _run_job  # noqa: E402

try:
    import boto3  # type: ignore
    from botocore.exceptions import ClientError  # type: ignore
#!/usr/bin/env python3
"""CLI entry point for the Blendomatic worker runner."""
from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
from pathlib import Path
from typing import Iterable, Optional

try:  # Optional but useful when running from source checkouts.
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - dotenv optional
    load_dotenv = None  # type: ignore

if load_dotenv is not None:
    try:
        load_dotenv(Path(__file__).parent / ".env", override=False)
    except Exception:  # pragma: no cover - best effort
        pass

from worker.runner import WorkerRunner, build_run_store  # noqa: E402

LOGGER = logging.getLogger("worker")


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Blendomatic worker daemon")
    parser.add_argument(
        "--blender",
        dest="blender",
        default=os.environ.get("BLENDER_PATH", "blender"),
        help="Path to Blender executable",
    )
    parser.add_argument(
        "--interval",
        dest="interval",
        type=float,
        default=15.0,
        help="Poll interval in seconds",
    )
    parser.add_argument(
        "--run",
        dest="run_id",
        help="Process only a single run id",
        default=None,
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process at most one job then exit",
    )
    parser.add_argument(
        "--log-level",
        dest="log_level",
        default="INFO",
        help="Python logging level",
    )
    parser.add_argument(
        "--store",
        dest="store",
        default=None,
        help="Override run store URI (falls back to env vars)",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=getattr(logging, args.log_level.upper(), logging.INFO))

    try:
        store = build_run_store(args.store)
    except Exception as exc:
        LOGGER.error("Failed to initialize run store: %s", exc)
        return 2

    runner = WorkerRunner(
        store,
        blender_executable=args.blender,
        poll_interval=args.interval,
        once=args.once,
        preferred_run=args.run_id,
    )

    def _handle_signal(signum, _frame):
        LOGGER.info("Received signal %s, shutting down", signum)
        runner.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        runner.run()
    except KeyboardInterrupt:
        runner.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
    @staticmethod

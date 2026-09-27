"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from collections.abc import Sequence

from . import __version__
from .config import AppConfig, ConfigError
from .service import run


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read a Netz NÖ encrypted P1 smart meter")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--check-config", action="store_true", help="validate environment configuration and exit"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        config = AppConfig.from_env()
    except ConfigError as exc:
        print(f"configuration error: {exc}", file=sys.stderr)
        return 2

    logging.basicConfig(
        level=getattr(logging, config.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.check_config:
        logging.getLogger(__name__).info("Configuration is valid")
        return 0

    stop_event = threading.Event()

    def request_stop(signum: int, _frame: object) -> None:
        logging.getLogger(__name__).info("Received signal %d; stopping", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    try:
        run(config, stop_event)
    except KeyboardInterrupt:
        stop_event.set()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

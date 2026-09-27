"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
from collections.abc import Sequence

from . import __version__
from .config import AppConfig, ConfigError, SerialConfig
from .serial_reader import SerialCheckError, check_serial_port
from .service import run


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read a Netz NÖ encrypted P1 smart meter")
    parser.add_argument("--version", action="version", version=__version__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument(
        "--check-config", action="store_true", help="validate environment configuration and exit"
    )
    actions.add_argument(
        "--check-serial",
        action="store_true",
        help="wait for a valid M-Bus frame without using GUEK or MQTT",
    )
    parser.add_argument(
        "--check-serial-seconds",
        type=float,
        default=15.0,
        metavar="SECONDS",
        help="maximum wait for --check-serial (default: 15)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.check_serial:
        try:
            serial_config = SerialConfig.from_env()
            result = check_serial_port(serial_config, args.check_serial_seconds)
        except KeyboardInterrupt:
            print("serial check interrupted", file=sys.stderr)
            return 130
        except (ConfigError, SerialCheckError, ValueError) as exc:
            print(f"serial check failed: {exc}", file=sys.stderr)
            return 1
        print(
            f"serial check passed: valid {result.frame_length}-byte M-Bus frame "
            f"received on {serial_config.port}"
        )
        return 0

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

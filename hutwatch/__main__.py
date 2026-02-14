"""Entry point for HutWatch: python -m hutwatch."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from .app import HutWatchApp


def setup_logging(verbose: bool, quiet: bool = False) -> None:
    """Configure logging."""
    if quiet:
        # TUI mode: suppress all log output to avoid corrupting the display
        logging.basicConfig(level=logging.CRITICAL + 1)
        return

    level = logging.DEBUG if verbose else logging.INFO
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Reduce noise from libraries
    logging.getLogger("bleak").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    try:
        import telegram  # noqa: F401

        logging.getLogger("telegram").setLevel(logging.WARNING)
    except ImportError:
        pass


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="hutwatch",
        description="BLE temperature monitoring with Telegram bot",
    )

    parser.add_argument(
        "-c", "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to configuration file (default: config.yaml)",
    )

    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "-o", "--console",
        nargs="?",
        const=0,
        type=int,
        default=None,
        metavar="INTERVAL",
        help=(
            "Force console output mode (skip Telegram). "
            "--console alone = keypress mode (Enter to print), "
            "--console 60 = print every 60 seconds"
        ),
    )

    parser.add_argument(
        "-t", "--tui",
        action="store_true",
        help="Launch ASCII TUI dashboard (skip Telegram)",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    setup_logging(args.verbose, quiet=args.tui)

    logger = logging.getLogger(__name__)

    # Check configuration file
    config_path = args.config.resolve()
    if not config_path.exists():
        logger.error("Configuration file not found: %s", config_path)
        logger.error("Copy config.example.yaml to config.yaml and edit it")
        return 1

    # Run the application
    try:
        app = HutWatchApp(config_path, console_interval=args.console, use_tui=args.tui)
        asyncio.run(app.run())
        return 0
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        return 0
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())

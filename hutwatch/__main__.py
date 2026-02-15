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

    parser.add_argument(
        "--lang",
        choices=["fi", "en"],
        default=None,
        help="UI language: fi (Finnish, default) or en (English)",
    )

    parser.add_argument(
        "--api-port",
        type=int,
        default=None,
        metavar="PORT",
        help="Start API server on this port for remote site sharing",
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Launch TUI with fake demo data (no config/BLE/network needed)",
    )

    return parser.parse_args()


def main() -> int:
    """Main entry point."""
    args = parse_args()
    setup_logging(args.verbose, quiet=args.tui or args.demo)

    logger = logging.getLogger(__name__)

    # Demo mode: bypass config, BLE, network — launch TUI with fake data
    if args.demo:
        from .i18n import init_lang
        init_lang(args.lang or "fi")

        from .demo import run_demo
        try:
            asyncio.run(run_demo())
            return 0
        except KeyboardInterrupt:
            return 0

    # Check configuration file
    config_path = args.config.resolve()
    if not config_path.exists():
        logger.error("Configuration file not found: %s", config_path)
        logger.error("Copy config.example.yaml to config.yaml and edit it")
        return 1

    # Determine language: CLI --lang overrides config file
    import yaml

    with open(config_path, "r", encoding="utf-8") as f:
        raw_config = yaml.safe_load(f) or {}
    lang = args.lang or raw_config.get("language", "fi")

    from .i18n import init_lang

    init_lang(lang)

    # Run the application
    try:
        app = HutWatchApp(config_path, console_interval=args.console, use_tui=args.tui, api_port=args.api_port)
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

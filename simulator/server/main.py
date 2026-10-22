"""Standalone simulator skeleton. No network or match logic is implemented."""

import argparse
import logging
import time
from collections.abc import Sequence


LOGGER = logging.getLogger("rm27.simulator")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="RM27 standalone simulator skeleton")
    parser.add_argument(
        "--check",
        action="store_true",
        help="check the entry point and exit without waiting",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    LOGGER.info("Simulator skeleton started; no network or match logic is enabled")
    try:
        if args.check:
            LOGGER.info("Entry point check passed")
            return 0

        LOGGER.info("Waiting; press Ctrl+C to exit")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            return 0
    finally:
        LOGGER.info("Simulator skeleton stopped")


if __name__ == "__main__":
    raise SystemExit(main())

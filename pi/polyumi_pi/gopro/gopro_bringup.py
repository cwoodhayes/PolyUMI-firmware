"""BLE bring-up test for connecting to a GoPro by name suffix."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from typing import Optional

from bleak import BleakScanner
from bleak.backends.device import BLEDevice
from open_gopro import GoPro
from open_gopro.util import setup_logging

logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line args."""
    parser = argparse.ArgumentParser(description='Connect to GoPro over BLE.')
    parser.add_argument(
        '--name-suffix',
        type=str,
        default='1112',
        help='Target BLE device name suffix (default: 1112).',
    )
    parser.add_argument(
        '--scan-timeout',
        type=float,
        default=6.0,
        help='BLE scan timeout in seconds for each attempt.',
    )
    parser.add_argument(
        '--scan-retries',
        type=int,
        default=4,
        help='Number of BLE scan attempts before giving up.',
    )
    return parser.parse_args()


def discover_device(
    name_suffix: str, timeout: float, retries: int
) -> Optional[BLEDevice]:
    """Discover BLE devices and return one whose name ends with name_suffix."""
    target_suffix = name_suffix.upper()
    for attempt in range(1, retries + 1):
        logger.info('BLE scan attempt %s/%s (%.1fs)', attempt, retries, timeout)
        devices = asyncio.run(BleakScanner.discover(timeout=timeout))

        visible = [d for d in devices if d.name]
        if visible:
            logger.info('Visible BLE devices:')
            for d in visible:
                logger.info('  - %s (%s)', d.name, d.address)
        else:
            logger.info('No named BLE devices found in this scan.')

        for d in visible:
            if d.name.upper().endswith(target_suffix):
                logger.info('Selected target device: %s (%s)', d.name, d.address)
                return d

    return None


def main() -> int:
    """Discover and connect to GoPro over BLE."""
    args = parse_args()

    global logger
    logger = setup_logging(logger)

    try:
        device = discover_device(
            name_suffix=args.name_suffix,
            timeout=args.scan_timeout,
            retries=args.scan_retries,
        )
        if device is None:
            logger.error(
                'Could not find a BLE device ending with suffix "%s".',
                args.name_suffix,
            )
            return 1

        # TURNS OUT. the gopro renaming used in the app doesn't change the BLE Name, so
        # we can just look for the default name ie "GoPro XXXX"
        with GoPro(device, enable_wifi=False) as gopro:
            logger.info('CONNECTED over BLE to GoPro: %s', gopro.identifier)
            return 0
    except KeyboardInterrupt:
        logger.warning('Interrupted by user.')
        return 130
    except Exception as exc:  # pragma: no cover - hardware-dependent
        logger.exception('BLE bringup failed: %s', exc)
        return 1


if __name__ == '__main__':
    sys.exit(main())

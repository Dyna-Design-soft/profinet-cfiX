"""Run the CFIX gateway: python -m cfix_api.gateway.cli --config config/gateway.example.json"""

from __future__ import annotations

import argparse
import logging
import sys

from .config import GatewayConfig
from .server import GatewayRunner


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Hilscher CIFX PROFINET <-> LabVIEW TCP/UDP gateway")
    parser.add_argument("--config", required=True, help="path to gateway config JSON file")
    args = parser.parse_args(argv)

    config = GatewayConfig.load(args.config)
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    runner = GatewayRunner(config)
    runner.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())

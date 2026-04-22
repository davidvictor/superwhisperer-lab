#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from common import DEFAULT_CONFIG_PATH, load_mode_config, render_mode_json, write_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write Superwhisper mode JSON files from a local declarative config."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to mode_specs.json.",
    )
    parser.add_argument(
        "--mode-key",
        action="append",
        default=[],
        help="Optional specific mode key(s) to sync.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned writes without changing files.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = load_mode_config(args.config.expanduser())
    selected_keys = set(args.mode_key)

    for mode in config["modes"]:
        if selected_keys and mode["key"] not in selected_keys:
            continue
        payload = render_mode_json(config["defaults"], mode)
        output_path = mode["output_path"]

        if args.dry_run:
            print(f"would_write {output_path}")
            continue

        write_json(output_path, payload)
        print(f"wrote {output_path}")


if __name__ == "__main__":
    main()

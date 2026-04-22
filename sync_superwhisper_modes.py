#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from common import (
    DEFAULT_CONFIG_PATH,
    load_json,
    load_mode_config,
    render_mode_json,
    render_settings_json,
    write_json,
)


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
    selected_modes = [
        mode for mode in config["modes"] if not selected_keys or mode["key"] in selected_keys
    ]

    for mode in selected_modes:
        payload = render_mode_json(config["defaults"], mode)
        output_path = mode["output_path"]

        if args.dry_run:
            print(f"would_write {output_path}")
            continue

        write_json(output_path, payload)
        print(f"wrote {output_path}")

    settings_path = config["superwhisper_settings_path"]
    existing_settings = load_json(settings_path) if settings_path.exists() else {}
    settings_payload = render_settings_json(
        existing_settings=existing_settings,
        built_in_mode_keys=config["built_in_mode_keys"],
        custom_mode_keys=[mode["key"] for mode in selected_modes],
    )

    if args.dry_run:
        print(f"would_update {settings_path}")
        print(f"modeKeys={settings_payload['modeKeys']}")
        return

    write_json(settings_path, settings_payload)
    print(f"updated {settings_path}")


if __name__ == "__main__":
    main()

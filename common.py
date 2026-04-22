#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import random
import re
from pathlib import Path
from typing import Any


LAB_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = LAB_DIR / "mode_specs.json"
DEFAULT_RUNS_DIR = LAB_DIR / "runs"
DEFAULT_COMPARISONS_DIR = LAB_DIR / "comparisons"

DEFAULT_RECORDINGS_CANDIDATES = [
    Path(
        os.environ.get(
            "SUPERWHISPER_RECORDINGS_DIR",
            str(Path.home() / "Documents" / "superwhisper" / "recordings"),
        )
    ),
    Path.home() / "Library" / "Application Support" / "superwhisper" / "recordings",
]

DEFAULT_EXPORT_ROOT = Path(
    os.environ.get(
        "SUPERWHISPER_EXPORT_ROOT",
        str(Path.home() / "Documents" / "superwhisper_exports"),
    )
)

DEFAULT_MODES_DIR = Path(
    os.environ.get(
        "SUPERWHISPER_MODES_DIR",
        str(Path.home() / "Documents" / "superwhisper" / "modes"),
    )
)

DEFAULT_SETTINGS_PATH = Path(
    os.environ.get(
        "SUPERWHISPER_SETTINGS_PATH",
        str(Path.home() / "Documents" / "superwhisper" / "settings" / "settings.json"),
    )
)

DEFAULT_BUILT_IN_MODE_KEYS = [
    "default",
    "message",
    "mail",
    "super",
]


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def choose_default_recordings_dir() -> Path:
    for candidate in DEFAULT_RECORDINGS_CANDIDATES:
        if candidate.exists():
            return candidate
    return DEFAULT_RECORDINGS_CANDIDATES[0]


def latest_export_jsonl(export_root: Path = DEFAULT_EXPORT_ROOT) -> Path:
    candidates = sorted(
        [
            path / "transcripts.jsonl"
            for path in export_root.glob("export-*")
            if (path / "transcripts.jsonl").exists()
        ]
    )
    if not candidates:
        raise FileNotFoundError(f"No export transcripts.jsonl found under {export_root}")
    return candidates[-1]


def extract_prompt_from_markdown(path: Path) -> str:
    text = path.read_text(encoding="utf-8")

    prompt_section = text
    marker = "## Prompt"
    if marker in text:
        prompt_section = text.split(marker, 1)[1]

    fence_match = re.search(r"```(?:text)?\n(.*?)```", prompt_section, re.DOTALL)
    if fence_match:
        return fence_match.group(1).strip()

    return prompt_section.strip()


def load_mode_config(config_path: Path) -> dict[str, Any]:
    config = load_json(config_path)
    config_dir = config_path.parent

    modes_dir = Path(config.get("superwhisper_modes_dir", DEFAULT_MODES_DIR)).expanduser()
    settings_path = Path(
        config.get("superwhisper_settings_path", DEFAULT_SETTINGS_PATH)
    ).expanduser()
    built_in_mode_keys = list(config.get("built_in_mode_keys", DEFAULT_BUILT_IN_MODE_KEYS))
    defaults = dict(config.get("defaults", {}))
    modes = []

    for mode in config.get("modes", []):
        resolved = dict(mode)
        prompt_markdown = config_dir / mode["prompt_markdown"]
        resolved["prompt_markdown_path"] = prompt_markdown
        resolved["prompt_text"] = extract_prompt_from_markdown(prompt_markdown)
        resolved["output_path"] = modes_dir / mode["file_name"]
        modes.append(resolved)

    return {
        "config_path": config_path,
        "config_dir": config_dir,
        "superwhisper_modes_dir": modes_dir,
        "superwhisper_settings_path": settings_path,
        "built_in_mode_keys": built_in_mode_keys,
        "defaults": defaults,
        "modes": modes,
    }


def render_mode_json(defaults: dict[str, Any], mode: dict[str, Any]) -> dict[str, Any]:
    payload = dict(defaults)
    payload.update(
        {
            "description": mode.get("description", ""),
            "key": mode["key"],
            "language": mode.get("language", payload.get("language", "en")),
            "languageModelID": mode.get("languageModelID", ""),
            "name": mode["name"],
            "prompt": mode["prompt_text"],
            "type": mode.get("type", "custom"),
            "version": mode.get("version", 1),
            "voiceModelID": mode.get("voiceModelID", payload.get("voiceModelID", "")),
        }
    )

    optional_fields = [
        "activationApps",
        "activationSites",
        "autocapitalizeInsert",
        "contextFromActiveApplication",
        "contextFromClipboard",
        "contextFromSelection",
        "contextTemplate",
        "diarize",
        "iconName",
        "literalPunctuation",
        "promptExamples",
        "realtimeOutput",
        "script",
        "scriptEnabled",
        "translateToEnglish",
        "useSystemAudio",
    ]

    for field in optional_fields:
        if field in mode:
            payload[field] = mode[field]

    return payload


def select_source_records(
    records: list[dict[str, Any]],
    sample_mode: str,
    limit: int | None,
    random_seed: int,
) -> list[dict[str, Any]]:
    selected = list(records)

    if sample_mode == "recent":
        selected = sorted(selected, key=lambda item: normalize_text(item.get("datetime")), reverse=True)
    elif sample_mode == "oldest":
        selected = sorted(selected, key=lambda item: normalize_text(item.get("datetime")))
    elif sample_mode == "random":
        rng = random.Random(random_seed)
        rng.shuffle(selected)
    else:
        raise ValueError(f"Unsupported sample mode: {sample_mode}")

    if limit is not None:
        selected = selected[:limit]

    return selected


def sanitize_filename(value: str) -> str:
    safe = []
    for char in value:
        if char.isalnum() or char in {"-", "_"}:
            safe.append(char)
        else:
            safe.append("-")
    collapsed = "".join(safe).strip("-")
    return collapsed or "item"


def unique_preserving_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def render_settings_json(
    existing_settings: dict[str, Any],
    built_in_mode_keys: list[str],
    custom_mode_keys: list[str],
) -> dict[str, Any]:
    payload = dict(existing_settings)
    existing_mode_keys = list(payload.get("modeKeys", []))
    payload["modeKeys"] = unique_preserving_order(
        existing_mode_keys + built_in_mode_keys + custom_mode_keys
    )
    return payload

#!/usr/bin/env python3

from __future__ import annotations

import json
import hashlib
import os
import random
import re
from pathlib import Path
from typing import Any


LAB_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = LAB_DIR / "mode_specs.json"
DEFAULT_RUNS_DIR = LAB_DIR / "runs"
DEFAULT_COMPARISONS_DIR = LAB_DIR / "comparisons"
DEFAULT_CORPORA_DIR = LAB_DIR / "corpora"
DEFAULT_JUDGE_RUNS_DIR = LAB_DIR / "judge_runs"

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


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_hash(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def text_hash(value: Any) -> str:
    return stable_hash(normalize_text(value))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


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
    deprecated_custom_mode_keys = list(config.get("deprecated_custom_mode_keys", []))
    deprecated_custom_modes = list(config.get("deprecated_custom_modes", []))
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
        "deprecated_custom_modes": deprecated_custom_modes,
        "deprecated_custom_mode_keys": deprecated_custom_mode_keys,
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


PRODUCT_BUILDER_NAMES = {
    "Product Engineering Translator",
    "Product Builder",
}


def is_product_builder_name(value: Any) -> bool:
    return normalize_text(value) in PRODUCT_BUILDER_NAMES


def context_surface_from_app_info(app_info: Any) -> str:
    if not isinstance(app_info, dict):
        return "unknown"
    text_input_format = normalize_text(app_info.get("textInputFormat"))
    if text_input_format == "code":
        return "code_editor"
    if text_input_format == "chat_message":
        return "ai_chat"
    if text_input_format == "url":
        return "browser_url"
    return "unknown"


def text_length_bucket(text: Any) -> str:
    length = len(normalize_text(text))
    if length == 0:
        return "empty"
    if length <= 80:
        return "short"
    if length <= 500:
        return "medium"
    if length <= 1200:
        return "long"
    return "very_long"


def extract_prompt_context(meta: dict[str, Any]) -> dict[str, Any]:
    prompt_context = meta.get("promptContext")
    return prompt_context if isinstance(prompt_context, dict) else {}


def summarize_prompt_context(prompt_context: dict[str, Any]) -> dict[str, Any]:
    app_context = prompt_context.get("applicationContext")
    if not isinstance(app_context, dict):
        app_context = {}

    app_info = app_context.get("appInfo")
    if not isinstance(app_info, dict):
        app_info = {}

    nouns = app_context.get("nouns")
    if not isinstance(nouns, list):
        nouns = []

    focused_content = normalize_text(app_context.get("focusedElementContent"))
    focused_description = normalize_text(app_context.get("focusedElementDescription"))
    selected_text = normalize_text(app_context.get("selectedText"))
    url = normalize_text(app_context.get("url"))
    active_app = normalize_text(app_context.get("name")) or "unknown"

    return {
        "active_app": active_app,
        "app_category": normalize_text(app_info.get("category")) or "unknown",
        "text_input_format": normalize_text(app_info.get("textInputFormat")) or "unknown",
        "context_surface": context_surface_from_app_info(app_info),
        "include_in_prompt": app_context.get("includeInPrompt"),
        "has_application_context": bool(app_context),
        "has_app_info": bool(app_info),
        "focused_element_content_length": len(focused_content),
        "focused_element_description_length": len(focused_description),
        "has_focused_element_content": bool(focused_content),
        "has_focused_element_description": bool(focused_description),
        "selected_text_length": len(selected_text),
        "has_selected_text": bool(selected_text),
        "url": url,
        "has_url": bool(url),
        "nouns_count": len(nouns),
        "has_nouns": bool(nouns),
    }


def build_record_hashes(meta: dict[str, Any]) -> dict[str, str]:
    prompt_context = extract_prompt_context(meta)
    return {
        "raw_result_hash": text_hash(meta.get("rawResult")),
        "llm_result_hash": text_hash(meta.get("llmResult")),
        "result_hash": text_hash(meta.get("result")),
        "prompt_hash": text_hash(meta.get("prompt")),
        "prompt_context_hash": stable_hash(prompt_context),
    }


def render_settings_json(
    existing_settings: dict[str, Any],
    built_in_mode_keys: list[str],
    custom_mode_keys: list[str],
    deprecated_mode_keys: list[str] | None = None,
) -> dict[str, Any]:
    payload = dict(existing_settings)
    deprecated = set(deprecated_mode_keys or [])
    existing_mode_keys = [
        mode_key for mode_key in payload.get("modeKeys", []) if mode_key not in deprecated
    ]
    payload["modeKeys"] = unique_preserving_order(
        existing_mode_keys + built_in_mode_keys + custom_mode_keys
    )
    return payload

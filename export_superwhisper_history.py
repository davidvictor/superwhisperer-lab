#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any


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


def choose_default_recordings_dir() -> Path:
    for candidate in DEFAULT_RECORDINGS_CANDIDATES:
        if candidate.exists():
            return candidate
    return DEFAULT_RECORDINGS_CANDIDATES[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export local Superwhisper transcript history into eval-ready files."
    )
    parser.add_argument(
        "--recordings-dir",
        type=Path,
        default=choose_default_recordings_dir(),
        help="Path to the Superwhisper recordings folder.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_EXPORT_ROOT,
        help="Directory where timestamped exports should be written.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap for quick test exports.",
    )
    return parser.parse_args()


def sanitize_filename(value: str) -> str:
    safe = []
    for char in value:
        if char.isalnum() or char in {"-", "_"}:
            safe.append(char)
        else:
            safe.append("-")
    collapsed = "".join(safe).strip("-")
    return collapsed or "recording"


def normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def load_meta(meta_path: Path) -> dict[str, Any] | None:
    try:
        with meta_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return None


def iso_sort_key(record: dict[str, Any]) -> str:
    return normalize_text(record.get("datetime"))


def build_record(folder: Path, meta: dict[str, Any]) -> dict[str, Any]:
    raw_result = normalize_text(meta.get("rawResult"))
    llm_result = normalize_text(meta.get("llmResult"))
    result = normalize_text(meta.get("result"))
    dt = normalize_text(meta.get("datetime"))

    return {
        "recording_id": folder.name,
        "datetime": dt,
        "duration_seconds": meta.get("duration"),
        "mode_name": normalize_text(meta.get("modeName")),
        "voice_model_key": normalize_text(meta.get("modelKey")),
        "voice_model_name": normalize_text(meta.get("modelName")),
        "language_model_key": normalize_text(meta.get("languageModelKey")),
        "language_model_name": normalize_text(meta.get("languageModelName")),
        "language": normalize_text(meta.get("languageSelected")),
        "recording_device": normalize_text(meta.get("recordingDevice")),
        "system_audio_enabled": bool(meta.get("systemAudioEnabled", False)),
        "separate_speakers_enabled": bool(meta.get("separateSpeakersEnabled", False)),
        "raw_result": raw_result,
        "llm_result": llm_result,
        "result": result,
        "recording_folder": str(folder),
        "audio_path": str(folder / "output.wav"),
        "meta_path": str(folder / "meta.json"),
    }


def write_jsonl(records: list[dict[str, Any]], output_path: Path) -> None:
    with output_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def write_csv(records: list[dict[str, Any]], output_path: Path) -> None:
    fieldnames = list(records[0].keys()) if records else []
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


def write_markdown(records: list[dict[str, Any]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        dt = record["datetime"] or "unknown-datetime"
        dt_slug = sanitize_filename(dt.replace(" ", "__").replace(":", "-").replace(".", "-"))
        mode_slug = sanitize_filename(record["mode_name"] or "unknown-mode")
        filename = f"{dt_slug}__{record['recording_id']}__{mode_slug}.md"
        body = "\n".join(
            [
                f"# Recording {record['recording_id']}",
                "",
                f"- Datetime: {record['datetime']}",
                f"- Mode: {record['mode_name']}",
                f"- Voice model: {record['voice_model_name']} ({record['voice_model_key']})",
                f"- Language model: {record['language_model_name']} ({record['language_model_key']})",
                f"- Duration seconds: {record['duration_seconds']}",
                f"- Recording device: {record['recording_device']}",
                "",
                "## Raw Transcript",
                "",
                record["raw_result"] or "_empty_",
                "",
                "## AI Result",
                "",
                record["llm_result"] or "_empty_",
                "",
                "## Final Result",
                "",
                record["result"] or "_empty_",
                "",
                "## Paths",
                "",
                f"- Meta: `{record['meta_path']}`",
                f"- Audio: `{record['audio_path']}`",
            ]
        )
        (output_dir / filename).write_text(body + "\n", encoding="utf-8")


def write_summary(records: list[dict[str, Any]], output_path: Path) -> None:
    mode_counts = Counter(record["mode_name"] or "Unknown" for record in records)
    language_model_counts = Counter(
        record["language_model_name"] or "None" for record in records
    )

    summary = {
        "recordings": len(records),
        "first_recording": records[0]["datetime"] if records else None,
        "last_recording": records[-1]["datetime"] if records else None,
        "mode_counts": dict(mode_counts),
        "language_model_counts": dict(language_model_counts),
    }
    output_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    args = parse_args()
    recordings_dir: Path = args.recordings_dir.expanduser()
    output_root: Path = args.output_root.expanduser()

    if not recordings_dir.exists():
        raise SystemExit(f"Recordings directory not found: {recordings_dir}")

    folders = sorted(
        [
            path
            for path in recordings_dir.iterdir()
            if path.is_dir() and (path / "meta.json").exists()
        ],
        key=lambda path: path.name,
    )

    if args.limit is not None:
        folders = folders[: args.limit]

    records: list[dict[str, Any]] = []
    for folder in folders:
        meta = load_meta(folder / "meta.json")
        if meta is None:
            continue
        records.append(build_record(folder, meta))

    records.sort(key=iso_sort_key)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    export_dir = output_root / f"export-{timestamp}"
    export_dir.mkdir(parents=True, exist_ok=True)

    write_summary(records, export_dir / "summary.json")
    write_jsonl(records, export_dir / "transcripts.jsonl")
    write_csv(records, export_dir / "transcripts.csv")
    write_markdown(records, export_dir / "transcripts_markdown")

    print(str(export_dir))


if __name__ == "__main__":
    main()

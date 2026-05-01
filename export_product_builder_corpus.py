#!/usr/bin/env python3

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from common import (
    DEFAULT_CORPORA_DIR,
    build_record_hashes,
    choose_default_recordings_dir,
    extract_prompt_context,
    is_product_builder_name,
    load_json,
    normalize_text,
    stable_hash,
    summarize_prompt_context,
    text_length_bucket,
    write_json,
    write_jsonl,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a context-rich Product Builder corpus from live Superwhisper history."
    )
    parser.add_argument(
        "--recordings-dir",
        type=Path,
        default=choose_default_recordings_dir(),
        help="Path to the live Superwhisper recordings folder.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory. Defaults to corpora/product-builder-YYYYMMDD-HHMMSS.",
    )
    parser.add_argument(
        "--corpora-root",
        type=Path,
        default=DEFAULT_CORPORA_DIR,
        help="Parent directory for generated corpora.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional cap for quick inspection exports.",
    )
    return parser.parse_args()


def list_meta_paths(recordings_dir: Path) -> list[Path]:
    return sorted(
        [
            path / "meta.json"
            for path in recordings_dir.iterdir()
            if path.is_dir() and (path / "meta.json").exists()
        ],
        key=lambda path: path.parent.name,
    )


def load_meta(meta_path: Path) -> dict[str, Any] | None:
    try:
        return load_json(meta_path)
    except Exception:
        return None


def build_product_builder_record(meta_path: Path, meta: dict[str, Any]) -> dict[str, Any]:
    folder = meta_path.parent
    raw_result = normalize_text(meta.get("rawResult"))
    llm_result = normalize_text(meta.get("llmResult"))
    result = normalize_text(meta.get("result"))
    prompt = normalize_text(meta.get("prompt"))
    prompt_context = extract_prompt_context(meta)
    context_summary = summarize_prompt_context(prompt_context)
    hashes = build_record_hashes(meta)

    record = {
        "recording_id": folder.name,
        "datetime": normalize_text(meta.get("datetime")),
        "mode_name": normalize_text(meta.get("modeName")),
        "duration_seconds": meta.get("duration"),
        "app_version": normalize_text(meta.get("appVersion")),
        "voice_model_key": normalize_text(meta.get("modelKey")),
        "voice_model_name": normalize_text(meta.get("modelName")),
        "language_model_key": normalize_text(meta.get("languageModelKey")),
        "language_model_name": normalize_text(meta.get("languageModelName")),
        "language": normalize_text(meta.get("languageSelected")),
        "recording_device": normalize_text(meta.get("recordingDevice")),
        "system_audio_enabled": bool(meta.get("systemAudioEnabled", False)),
        "separate_speakers_enabled": bool(meta.get("separateSpeakersEnabled", False)),
        "application_context_enabled": meta.get("applicationContextEnabled"),
        "literal_punctuation_enabled": meta.get("literalPunctuationEnabled"),
        "realtime_enabled": meta.get("realtimeEnabled"),
        "translation_enabled": meta.get("translationEnabled"),
        "processing_time": meta.get("processingTime"),
        "language_model_processing_time": meta.get("languageModelProcessingTime"),
        "prompt": prompt,
        "context_raw": prompt_context,
        "prompt_context": prompt_context,
        "context_summary": context_summary,
        "raw_result": raw_result,
        "llm_result": llm_result,
        "result": result,
        "raw_result_length_bucket": text_length_bucket(raw_result),
        "judgeable": bool(raw_result and llm_result),
        "recording_folder": str(folder),
        "audio_path": str(folder / "output.wav"),
        "meta_path": str(meta_path),
        **hashes,
    }
    record["candidate_hash"] = hashes["llm_result_hash"]
    record["context_hash"] = hashes["prompt_context_hash"]
    record["record_hash"] = stable_hash(
        {
            "recording_id": record["recording_id"],
            "raw_result_hash": record["raw_result_hash"],
            "candidate_hash": record["candidate_hash"],
            "prompt_hash": record["prompt_hash"],
            "context_hash": record["context_hash"],
        }
    )
    return record


def select_product_builder_records(meta_paths: list[Path]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for meta_path in meta_paths:
        meta = load_meta(meta_path)
        if meta is None:
            continue
        if not is_product_builder_name(meta.get("modeName")):
            continue
        records.append(build_product_builder_record(meta_path, meta))
    return sorted(records, key=lambda record: (record["datetime"], record["recording_id"]))


def summarize_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    app_counts = Counter(record["context_summary"]["active_app"] for record in records)
    surface_counts = Counter(record["context_summary"]["context_surface"] for record in records)
    length_counts = Counter(record["raw_result_length_bucket"] for record in records)
    mode_counts = Counter(record["mode_name"] for record in records)
    return {
        "record_count": len(records),
        "judgeable_count": sum(1 for record in records if record["judgeable"]),
        "first_recording": records[0]["datetime"] if records else None,
        "last_recording": records[-1]["datetime"] if records else None,
        "mode_counts": dict(mode_counts),
        "active_app_counts": dict(app_counts),
        "context_surface_counts": dict(surface_counts),
        "length_bucket_counts": dict(length_counts),
    }


def create_output_dir(corpora_root: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return corpora_root / f"product-builder-{timestamp}"


def export_corpus(recordings_dir: Path, output_dir: Path, limit: int | None = None) -> dict[str, Any]:
    meta_paths = list_meta_paths(recordings_dir)
    records = select_product_builder_records(meta_paths)
    if limit is not None:
        records = records[:limit]

    output_dir.mkdir(parents=True, exist_ok=True)
    corpus_path = output_dir / "product_builder_corpus.jsonl"
    manifest_path = output_dir / "manifest.json"
    summary_path = output_dir / "summary.json"

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "recordings_dir": str(recordings_dir),
        "corpus_path": str(corpus_path),
        "current_name": "Product Builder",
        "legacy_names": ["Product Engineering Translator"],
        "limit": limit,
        **summarize_records(records),
    }

    write_jsonl(corpus_path, records)
    write_json(manifest_path, manifest)
    write_json(summary_path, summarize_records(records))
    return manifest


def main() -> None:
    args = parse_args()
    recordings_dir = args.recordings_dir.expanduser()
    output_dir = (
        args.output_dir.expanduser()
        if args.output_dir
        else create_output_dir(args.corpora_root.expanduser())
    )
    manifest = export_corpus(recordings_dir, output_dir, args.limit)
    print(manifest["corpus_path"])


if __name__ == "__main__":
    main()

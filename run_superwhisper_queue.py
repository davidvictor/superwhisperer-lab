#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from common import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_RUNS_DIR,
    append_jsonl,
    choose_default_recordings_dir,
    latest_export_jsonl,
    load_json,
    load_jsonl,
    load_mode_config,
    normalize_text,
    render_mode_json,
    sanitize_filename,
    select_source_records,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a lightweight one-at-a-time Superwhisper batch queue over existing recordings."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG_PATH,
        help="Path to mode_specs.json.",
    )
    parser.add_argument(
        "--source-jsonl",
        type=Path,
        default=None,
        help="Source transcripts.jsonl export. Defaults to the latest export.",
    )
    parser.add_argument(
        "--recordings-dir",
        type=Path,
        default=choose_default_recordings_dir(),
        help="Path to the live Superwhisper recordings folder.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Optional existing or new run directory. If omitted, a new timestamped run is created.",
    )
    parser.add_argument(
        "--runs-root",
        type=Path,
        default=DEFAULT_RUNS_DIR,
        help="Parent directory for timestamped run folders.",
    )
    parser.add_argument(
        "--mode-key",
        action="append",
        default=[],
        help="Mode key(s) to run. Defaults to all configured modes.",
    )
    parser.add_argument(
        "--sample-mode",
        choices=["recent", "oldest", "random"],
        default="recent",
        help="How to pick source recordings from the export corpus.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=3,
        help="How many source recordings to select for the run.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=7,
        help="Seed used when sample mode is random.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=180.0,
        help="Maximum wait per queued transcription.",
    )
    parser.add_argument(
        "--poll-interval-seconds",
        type=float,
        default=2.0,
        help="Polling interval while waiting for new History items.",
    )
    parser.add_argument(
        "--mode-settle-seconds",
        type=float,
        default=2.0,
        help="Pause after switching mode before opening the audio file.",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Do not rewrite Superwhisper mode JSON files before the run.",
    )
    return parser.parse_args()


def list_recording_dirs(recordings_dir: Path) -> list[Path]:
    return sorted(
        [
            path
            for path in recordings_dir.iterdir()
            if path.is_dir() and path.name.isdigit() and (path / "meta.json").exists()
        ],
        key=lambda path: int(path.name),
    )


def load_meta(path: Path) -> dict[str, Any] | None:
    try:
        return load_json(path)
    except Exception:
        return None


def build_task(source_record: dict[str, Any], mode: dict[str, Any]) -> dict[str, Any]:
    task_id = f"{source_record['recording_id']}__{mode['key']}"
    return {
        "task_id": task_id,
        "source_recording_id": source_record["recording_id"],
        "source_datetime": source_record.get("datetime"),
        "source_audio_path": source_record["audio_path"],
        "source_meta_path": source_record["meta_path"],
        "source_mode_name": source_record.get("mode_name"),
        "source_raw_result": source_record.get("raw_result", ""),
        "source_result": source_record.get("result", ""),
        "source_duration_seconds": source_record.get("duration_seconds"),
        "mode_key": mode["key"],
        "mode_name": mode["name"],
        "mode_file_name": mode["file_name"],
        "prompt_markdown_path": str(mode["prompt_markdown_path"]),
        "language_model_id": mode.get("languageModelID", ""),
        "voice_model_id": mode.get("voiceModelID", ""),
    }


def sync_modes(config: dict[str, Any], selected_mode_keys: set[str]) -> None:
    for mode in config["modes"]:
        if selected_mode_keys and mode["key"] not in selected_mode_keys:
            continue
        payload = render_mode_json(config["defaults"], mode)
        write_json(mode["output_path"], payload)


def switch_mode(mode_key: str) -> None:
    subprocess.run(["open", f"superwhisper://mode?key={mode_key}"], check=True)


def submit_audio(audio_path: str) -> None:
    subprocess.run(["open", audio_path, "-a", "superwhisper"], check=True)


def match_new_recording(
    recordings_dir: Path,
    baseline_folder_num: int,
    source_task: dict[str, Any],
    expected_mode_name: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
) -> dict[str, Any] | None:
    deadline = time.time() + timeout_seconds
    source_raw = normalize_text(source_task.get("source_raw_result"))
    source_duration = source_task.get("source_duration_seconds")

    while time.time() < deadline:
        candidates: list[dict[str, Any]] = []
        for folder in list_recording_dirs(recordings_dir):
            folder_num = int(folder.name)
            if folder_num <= baseline_folder_num:
                continue

            meta = load_meta(folder / "meta.json")
            if meta is None:
                continue

            mode_name = normalize_text(meta.get("modeName"))
            if mode_name != expected_mode_name:
                continue

            raw_result = normalize_text(meta.get("rawResult"))
            duration = meta.get("duration")
            duration_match = False
            if source_duration is not None and duration is not None:
                try:
                    duration_match = abs(float(source_duration) - float(duration)) <= 0.75
                except (TypeError, ValueError):
                    duration_match = False

            candidate = {
                "output_recording_id": folder.name,
                "output_recording_folder": str(folder),
                "output_meta_path": str(folder / "meta.json"),
                "output_audio_path": str(folder / "output.wav"),
                "output_datetime": normalize_text(meta.get("datetime")),
                "output_mode_name": mode_name,
                "output_model_name": normalize_text(meta.get("modelName")),
                "output_language_model_name": normalize_text(meta.get("languageModelName")),
                "output_raw_result": raw_result,
                "output_llm_result": normalize_text(meta.get("llmResult")),
                "output_result": normalize_text(meta.get("result")),
                "output_duration_seconds": duration,
                "raw_text_exact_match": raw_result == source_raw,
                "duration_match": duration_match,
            }

            if candidate["raw_text_exact_match"]:
                return candidate
            candidates.append(candidate)

        duration_candidates = [item for item in candidates if item["duration_match"]]
        if len(duration_candidates) == 1:
            return duration_candidates[0]

        time.sleep(poll_interval_seconds)

    return None


def load_completed_task_ids(results_path: Path) -> set[str]:
    if not results_path.exists():
        return set()
    return {record["task_id"] for record in load_jsonl(results_path) if record.get("status") == "completed"}


def write_output_markdown(run_dir: Path, result: dict[str, Any]) -> None:
    outputs_dir = run_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    mode_slug = sanitize_filename(result["mode_name"])
    filename = f"{result['source_recording_id']}__{mode_slug}.md"
    candidate_text = result.get("output_llm_result") or result.get("output_result") or "_empty_"
    body = "\n".join(
        [
            f"# {result['task_id']}",
            "",
            f"- Source recording: {result['source_recording_id']}",
            f"- Source mode: {result['source_mode_name']}",
            f"- Test mode: {result['mode_name']}",
            f"- Status: {result['status']}",
            f"- Output recording: {result.get('output_recording_id', '')}",
            "",
            "## Source Raw Transcript",
            "",
            result.get("source_raw_result", "") or "_empty_",
            "",
            "## Candidate Output",
            "",
            candidate_text,
            "",
            "## Candidate Raw Transcript",
            "",
            result.get("output_raw_result", "") or "_empty_",
        ]
    )
    (outputs_dir / filename).write_text(body + "\n", encoding="utf-8")


def create_new_run_dir(runs_root: Path) -> Path:
    run_id = datetime.now().strftime("run-%Y%m%d-%H%M%S")
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir


def main() -> None:
    args = parse_args()
    config = load_mode_config(args.config.expanduser())
    recordings_dir = args.recordings_dir.expanduser()
    runs_root = args.runs_root.expanduser()
    run_dir = args.run_dir.expanduser() if args.run_dir else create_new_run_dir(runs_root)
    run_dir.mkdir(parents=True, exist_ok=True)

    source_jsonl = args.source_jsonl.expanduser() if args.source_jsonl else latest_export_jsonl()
    source_records = load_jsonl(source_jsonl)

    selected_mode_keys = set(args.mode_key)
    selected_modes = [
        mode for mode in config["modes"] if not selected_mode_keys or mode["key"] in selected_mode_keys
    ]
    if not selected_modes:
        raise SystemExit("No modes selected.")

    if not args.skip_sync:
        sync_modes(config, {mode["key"] for mode in selected_modes})

    selected_source_records = select_source_records(
        source_records,
        sample_mode=args.sample_mode,
        limit=args.limit,
        random_seed=args.random_seed,
    )

    tasks = [
        build_task(source_record, mode)
        for source_record in selected_source_records
        for mode in selected_modes
    ]

    queue_path = run_dir / "queue.jsonl"
    results_path = run_dir / "results.jsonl"
    manifest_path = run_dir / "manifest.json"

    if not queue_path.exists():
        for task in tasks:
            append_jsonl(queue_path, task)

    manifest = {
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source_jsonl": str(source_jsonl),
        "recordings_dir": str(recordings_dir),
        "mode_keys": [mode["key"] for mode in selected_modes],
        "sample_mode": args.sample_mode,
        "limit": args.limit,
        "task_count": len(tasks),
        "timeout_seconds": args.timeout_seconds,
        "poll_interval_seconds": args.poll_interval_seconds,
    }
    write_json(manifest_path, manifest)

    completed_task_ids = load_completed_task_ids(results_path)
    completed = 0
    failed = 0

    for task in tasks:
        if task["task_id"] in completed_task_ids:
            continue

        baseline_dirs = list_recording_dirs(recordings_dir)
        baseline_folder_num = int(baseline_dirs[-1].name) if baseline_dirs else 0

        started_at = datetime.now().isoformat(timespec="seconds")
        switch_mode(task["mode_key"])
        time.sleep(args.mode_settle_seconds)
        submit_audio(task["source_audio_path"])

        candidate = match_new_recording(
            recordings_dir=recordings_dir,
            baseline_folder_num=baseline_folder_num,
            source_task=task,
            expected_mode_name=task["mode_name"],
            timeout_seconds=args.timeout_seconds,
            poll_interval_seconds=args.poll_interval_seconds,
        )

        result = dict(task)
        result["started_at"] = started_at
        result["finished_at"] = datetime.now().isoformat(timespec="seconds")

        if candidate is None:
            result["status"] = "timeout"
            append_jsonl(results_path, result)
            write_output_markdown(run_dir, result)
            failed += 1
            continue

        result.update(candidate)
        result["status"] = "completed"
        append_jsonl(results_path, result)
        write_output_markdown(run_dir, result)
        completed += 1

    summary = {
        "completed": completed,
        "failed": failed,
        "results_path": str(results_path),
    }
    write_json(run_dir / "summary.json", summary)
    print(str(run_dir))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from common import (
    DEFAULT_CORPORA_DIR,
    DEFAULT_JUDGE_RUNS_DIR,
    LAB_DIR,
    append_jsonl,
    canonical_json,
    load_jsonl,
    normalize_text,
    stable_hash,
    write_json,
)


RUBRIC_VERSION = "product-builder-judge-v1"
JUDGE_PROMPT_VERSION = "product-builder-codex-judge-v1"
DEFAULT_SCHEMA_PATH = LAB_DIR / "schemas" / "product_builder_judge_response.schema.json"

SCORE_DIMENSIONS = [
    "intent_fidelity",
    "technical_specificity",
    "design_product_fidelity",
    "context_usefulness",
    "actionability",
    "noise_removal",
    "non_invention",
]

SCORE_WEIGHTS = {
    "intent_fidelity": 0.20,
    "technical_specificity": 0.18,
    "design_product_fidelity": 0.14,
    "context_usefulness": 0.12,
    "actionability": 0.16,
    "noise_removal": 0.10,
    "non_invention": 0.10,
}

RECOMMENDATION_CATEGORIES = {
    "no_change",
    "prompt_candidate",
    "manual_review",
    "exclude_from_eval",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Judge a context-rich Product Builder corpus with Codex CLI."
    )
    parser.add_argument(
        "--corpus-jsonl",
        type=Path,
        default=None,
        help="Path to product_builder_corpus.jsonl. Defaults to latest corpus.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Optional judge run directory. Defaults to judge_runs/product-builder-YYYYMMDD-HHMMSS.",
    )
    parser.add_argument(
        "--judge-runs-root",
        type=Path,
        default=DEFAULT_JUDGE_RUNS_DIR,
        help="Parent directory for generated judge runs.",
    )
    parser.add_argument("--chunk-size", type=int, default=25, help="Maximum records to judge.")
    parser.add_argument("--max-records", type=int, default=None, help="Optional cap before chunking.")
    parser.add_argument("--codex-bin", default="codex", help="Codex CLI executable.")
    parser.add_argument(
        "--judge-model",
        default="gpt-5.4",
        help="Codex model to use for judging.",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help="JSON schema for Codex final output.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=240.0,
        help="Timeout for each Codex judge invocation.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan the chunk and write no judge scores.",
    )
    return parser.parse_args()


def latest_corpus_jsonl(corpora_root: Path = DEFAULT_CORPORA_DIR) -> Path:
    candidates = sorted(corpora_root.glob("product-builder-*/product_builder_corpus.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"No product_builder_corpus.jsonl found under {corpora_root}")
    return candidates[-1]


def create_run_dir(judge_runs_root: Path) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return judge_runs_root / f"product-builder-{timestamp}"


def judge_prompt_hash() -> str:
    return stable_hash(
        {
            "rubric_version": RUBRIC_VERSION,
            "judge_prompt_version": JUDGE_PROMPT_VERSION,
            "dimensions": SCORE_DIMENSIONS,
            "weights": SCORE_WEIGHTS,
        }
    )


def record_judge_fingerprint(record: dict[str, Any]) -> str:
    return stable_hash(
        {
            "recording_id": record.get("recording_id"),
            "candidate_hash": record.get("candidate_hash") or record.get("llm_result_hash"),
            "context_hash": record.get("context_hash") or record.get("prompt_context_hash"),
            "prompt_hash": record.get("prompt_hash"),
            "rubric_version": RUBRIC_VERSION,
            "judge_prompt_hash": judge_prompt_hash(),
        }
    )


def load_completed_fingerprints(scores_path: Path) -> set[str]:
    if not scores_path.exists():
        return set()
    fingerprints: set[str] = set()
    for record in load_jsonl(scores_path):
        fingerprint = normalize_text(record.get("judge_fingerprint"))
        if fingerprint:
            fingerprints.add(fingerprint)
    return fingerprints


def select_pending_records(
    records: list[dict[str, Any]],
    completed_fingerprints: set[str],
    chunk_size: int,
    max_records: int | None = None,
) -> list[dict[str, Any]]:
    ordered = sorted(records, key=lambda record: (record.get("datetime") or "", record.get("recording_id") or ""))
    if max_records is not None:
        ordered = ordered[:max_records]

    pending: list[dict[str, Any]] = []
    for record in ordered:
        if record_judge_fingerprint(record) in completed_fingerprints:
            continue
        pending.append(record)
        if len(pending) >= chunk_size:
            break
    return pending


def weighted_score(scores: dict[str, Any]) -> float:
    total = 0.0
    for dimension, weight in SCORE_WEIGHTS.items():
        total += float(scores[dimension]) * weight
    return round(total, 4)


def validate_judge_response(payload: dict[str, Any]) -> None:
    scores = payload.get("scores")
    if not isinstance(scores, dict):
        raise ValueError("Judge response missing scores object.")
    for dimension in SCORE_DIMENSIONS:
        value = scores.get(dimension)
        if not isinstance(value, int) or value < 1 or value > 5:
            raise ValueError(f"Invalid score for {dimension}: {value!r}")

    confidence = payload.get("confidence")
    if not isinstance(confidence, (int, float)) or confidence < 0 or confidence > 1:
        raise ValueError(f"Invalid confidence: {confidence!r}")

    failure_tags = payload.get("failure_tags")
    if not isinstance(failure_tags, list) or not all(isinstance(tag, str) for tag in failure_tags):
        raise ValueError("failure_tags must be a list of strings.")

    if not isinstance(payload.get("rationale"), str) or not payload["rationale"].strip():
        raise ValueError("rationale must be a non-empty string.")

    category = payload.get("recommendation_category")
    if category not in RECOMMENDATION_CATEGORIES:
        raise ValueError(f"Invalid recommendation_category: {category!r}")

    if not isinstance(payload.get("prompt_recommendation"), str):
        raise ValueError("prompt_recommendation must be a string.")


def compact_record_for_judge(record: dict[str, Any]) -> dict[str, Any]:
    context_summary = record.get("context_summary")
    if not isinstance(context_summary, dict):
        context_summary = {}
    return {
        "recording_id": record.get("recording_id"),
        "datetime": record.get("datetime"),
        "mode_name": record.get("mode_name"),
        "active_app": context_summary.get("active_app"),
        "context_summary": context_summary,
        "prompt": record.get("prompt", ""),
        "prompt_context": record.get("context_raw") or record.get("prompt_context") or {},
        "raw_transcript": record.get("raw_result", ""),
        "candidate_output": record.get("llm_result", ""),
        "final_result": record.get("result", ""),
        "model_metadata": {
            "language_model_key": record.get("language_model_key"),
            "language_model_name": record.get("language_model_name"),
            "voice_model_key": record.get("voice_model_key"),
            "voice_model_name": record.get("voice_model_name"),
            "app_version": record.get("app_version"),
        },
        "hashes": {
            "raw_result_hash": record.get("raw_result_hash"),
            "llm_result_hash": record.get("llm_result_hash"),
            "prompt_hash": record.get("prompt_hash"),
            "prompt_context_hash": record.get("prompt_context_hash"),
        },
    }


def build_codex_prompt(record: dict[str, Any]) -> str:
    payload = compact_record_for_judge(record)
    return "\n".join(
        [
            "You are judging one Superwhisper Product Builder output.",
            "",
            "Product Builder contract:",
            "- The mode translates spoken product-building intent into precise technical language.",
            "- It should preserve software engineering, product design, and product thinking as dictated.",
            "- It should preserve code-level intent, constraints, implementation direction, design decisions, and imperative wording.",
            "- It may use Superwhisper app/focused context only to disambiguate references.",
            "- It must not invent requirements, code, fixes, metrics, designs, or decisions.",
            "- It must not route to another mode or judge based on speech content classification.",
            "- Use an empty prompt_recommendation string when no prompt change is recommended.",
            "",
            "Score each dimension from 1 to 5:",
            "- intent_fidelity: captures the speaker's actual intended instruction or note.",
            "- technical_specificity: preserves identifiers, APIs, files, commands, constraints, and code-level detail.",
            "- design_product_fidelity: preserves UX/product/design decisions when present without fabricating absent ones.",
            "- context_usefulness: uses app/focused context appropriately for disambiguation without summarizing unrelated context.",
            "- actionability: output is ready to paste into Codex/Claude or use as builder notes.",
            "- noise_removal: removes filler and false starts without erasing stance, caveats, or imperative force.",
            "- non_invention: avoids adding unsupported facts, decisions, requirements, or false certainty.",
            "",
            "Return only JSON matching the provided schema.",
            "",
            "Record:",
            canonical_json(payload),
        ]
    )


def run_codex_judge(
    record: dict[str, Any],
    run_dir: Path,
    codex_bin: str,
    schema_path: Path,
    judge_model: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    prompt = build_codex_prompt(record)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=run_dir, prefix="codex-judge-", suffix=".json", delete=False
    ) as output_handle:
        output_path = Path(output_handle.name)

    cmd = [
        codex_bin,
        "exec",
        "--json",
        "--ephemeral",
        "--sandbox",
        "read-only",
        "--output-schema",
        str(schema_path),
        "-o",
        str(output_path),
    ]
    if judge_model:
        cmd.extend(["--model", judge_model])
    cmd.append("-")

    completed = subprocess.run(
        cmd,
        input=prompt,
        text=True,
        capture_output=True,
        timeout=timeout_seconds,
        cwd=LAB_DIR,
        check=False,
    )
    if completed.returncode != 0:
        try:
            output_path.unlink()
        except OSError:
            pass
        raise RuntimeError(
            json.dumps(
                {
                    "returncode": completed.returncode,
                    "stderr": completed.stderr[-4000:],
                    "stdout": completed.stdout[-4000:],
                },
                ensure_ascii=False,
            )
        )

    try:
        payload = json.loads(output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Codex output was not valid JSON: {exc}") from exc
    finally:
        try:
            output_path.unlink()
        except OSError:
            pass

    validate_judge_response(payload)
    return payload


def skipped_score_record(record: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "status": reason,
        "recording_id": record.get("recording_id"),
        "datetime": record.get("datetime"),
        "judge_fingerprint": record_judge_fingerprint(record),
        "rubric_version": RUBRIC_VERSION,
        "judge_prompt_hash": judge_prompt_hash(),
        "candidate_hash": record.get("candidate_hash") or record.get("llm_result_hash"),
        "context_hash": record.get("context_hash") or record.get("prompt_context_hash"),
        "context_summary": record.get("context_summary", {}),
        "raw_result_length_bucket": record.get("raw_result_length_bucket"),
    }


def scored_record(record: dict[str, Any], judge_payload: dict[str, Any]) -> dict[str, Any]:
    scores = judge_payload["scores"]
    return {
        "status": "judged",
        "recording_id": record.get("recording_id"),
        "datetime": record.get("datetime"),
        "mode_name": record.get("mode_name"),
        "judge_fingerprint": record_judge_fingerprint(record),
        "rubric_version": RUBRIC_VERSION,
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
        "judge_prompt_hash": judge_prompt_hash(),
        "candidate_hash": record.get("candidate_hash") or record.get("llm_result_hash"),
        "context_hash": record.get("context_hash") or record.get("prompt_context_hash"),
        "prompt_hash": record.get("prompt_hash"),
        "context_summary": record.get("context_summary", {}),
        "raw_result_length_bucket": record.get("raw_result_length_bucket"),
        "scores": scores,
        "weighted_score": weighted_score(scores),
        "confidence": judge_payload["confidence"],
        "failure_tags": judge_payload["failure_tags"],
        "rationale": judge_payload["rationale"],
        "recommendation_category": judge_payload["recommendation_category"],
        "prompt_recommendation": judge_payload.get("prompt_recommendation", ""),
    }


def error_record(record: dict[str, Any], error: Exception) -> dict[str, Any]:
    return {
        "recording_id": record.get("recording_id"),
        "datetime": record.get("datetime"),
        "judge_fingerprint": record_judge_fingerprint(record),
        "candidate_hash": record.get("candidate_hash") or record.get("llm_result_hash"),
        "context_hash": record.get("context_hash") or record.get("prompt_context_hash"),
        "error_type": type(error).__name__,
        "error": str(error),
    }


def summarize_scores(score_records: list[dict[str, Any]]) -> dict[str, Any]:
    judged = [record for record in score_records if record.get("status") == "judged"]
    skipped = [record for record in score_records if record.get("status") != "judged"]
    failure_tags = Counter(tag for record in judged for tag in record.get("failure_tags", []))
    recommendation_counts = Counter(record.get("recommendation_category") for record in judged)

    def average(records: list[dict[str, Any]]) -> float | None:
        if not records:
            return None
        return round(sum(float(record["weighted_score"]) for record in records) / len(records), 4)

    segments: dict[str, dict[str, dict[str, Any]]] = {
        "active_app": {},
        "context_surface": {},
        "length_bucket": {},
    }
    segment_values: dict[str, defaultdict[str, list[dict[str, Any]]]] = {
        "active_app": defaultdict(list),
        "context_surface": defaultdict(list),
        "length_bucket": defaultdict(list),
    }

    for record in judged:
        context_summary = record.get("context_summary")
        if not isinstance(context_summary, dict):
            context_summary = {}
        segment_values["active_app"][context_summary.get("active_app") or "unknown"].append(record)
        segment_values["context_surface"][context_summary.get("context_surface") or "unknown"].append(record)
        segment_values["length_bucket"][record.get("raw_result_length_bucket") or "unknown"].append(record)

    for segment_name, values in segment_values.items():
        for value, records in values.items():
            segments[segment_name][value] = {
                "count": len(records),
                "average_weighted_score": average(records),
            }

    return {
        "rubric_version": RUBRIC_VERSION,
        "judge_prompt_hash": judge_prompt_hash(),
        "judged_count": len(judged),
        "skipped_count": len(skipped),
        "average_weighted_score": average(judged),
        "failure_tag_counts": dict(failure_tags),
        "recommendation_counts": dict(recommendation_counts),
        "segments": segments,
    }


def write_failure_patterns(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# Product Builder Failure Patterns",
        "",
        f"- Rubric version: `{summary['rubric_version']}`",
        f"- Judged records: {summary['judged_count']}",
        f"- Average weighted score: {summary['average_weighted_score']}",
        "",
        "## Failure Tags",
        "",
    ]
    tag_counts = summary.get("failure_tag_counts", {})
    if tag_counts:
        for tag, count in sorted(tag_counts.items(), key=lambda item: (-item[1], item[0])):
            lines.append(f"- `{tag}`: {count}")
    else:
        lines.append("- None recorded.")

    lines.extend(["", "## Recommendations", ""])
    recommendation_counts = summary.get("recommendation_counts", {})
    if recommendation_counts:
        for category, count in sorted(recommendation_counts.items()):
            lines.append(f"- `{category}`: {count}")
    else:
        lines.append("- None recorded.")

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_prompt_recommendations(path: Path, score_records: list[dict[str, Any]]) -> None:
    judged = [record for record in score_records if record.get("status") == "judged"]
    candidates = [
        record
        for record in judged
        if record.get("recommendation_category") in {"prompt_candidate", "manual_review"}
        and normalize_text(record.get("prompt_recommendation"))
    ]
    lines = [
        "# Product Builder Prompt Recommendations",
        "",
        f"- Rubric version: `{RUBRIC_VERSION}`",
        f"- Candidate recommendations: {len(candidates)}",
        "",
    ]
    if not candidates:
        lines.append("No prompt recommendations recorded in this chunk.")
    else:
        for record in candidates:
            lines.extend(
                [
                    f"## Recording {record.get('recording_id')}",
                    "",
                    f"- Category: `{record.get('recommendation_category')}`",
                    f"- Weighted score: {record.get('weighted_score')}",
                    f"- Failure tags: {', '.join(record.get('failure_tags', [])) or 'none'}",
                    "",
                    normalize_text(record.get("prompt_recommendation")),
                    "",
                ]
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_state(path: Path, run_dir: Path, corpus_jsonl: Path, pending: list[dict[str, Any]]) -> None:
    write_json(
        path,
        {
            "updated_at": datetime.now().isoformat(timespec="seconds"),
            "run_dir": str(run_dir),
            "corpus_jsonl": str(corpus_jsonl),
            "rubric_version": RUBRIC_VERSION,
            "judge_prompt_hash": judge_prompt_hash(),
            "pending_recording_ids": [record.get("recording_id") for record in pending],
        },
    )


def run_judge(args: argparse.Namespace) -> Path:
    corpus_jsonl = args.corpus_jsonl.expanduser() if args.corpus_jsonl else latest_corpus_jsonl()
    run_dir = (
        args.run_dir.expanduser()
        if args.run_dir
        else create_run_dir(args.judge_runs_root.expanduser())
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    records = load_jsonl(corpus_jsonl)
    scores_path = run_dir / "judge_scores.jsonl"
    errors_path = run_dir / "judge_errors.jsonl"
    completed_fingerprints = load_completed_fingerprints(scores_path)
    pending = select_pending_records(records, completed_fingerprints, args.chunk_size, args.max_records)
    write_state(run_dir / "judge_state.json", run_dir, corpus_jsonl, pending)

    if args.dry_run:
        print(str(run_dir))
        return run_dir

    attempted_judge_count = 0
    successful_judge_count = 0
    error_count = 0
    for record in pending:
        try:
            if not record.get("judgeable", True):
                append_jsonl(scores_path, skipped_score_record(record, "skipped_empty"))
                continue
            attempted_judge_count += 1
            judge_payload = run_codex_judge(
                record=record,
                run_dir=run_dir,
                codex_bin=args.codex_bin,
                schema_path=args.schema.expanduser(),
                judge_model=args.judge_model,
                timeout_seconds=args.timeout_seconds,
            )
            append_jsonl(scores_path, scored_record(record, judge_payload))
            successful_judge_count += 1
        except Exception as exc:
            error_count += 1
            append_jsonl(errors_path, error_record(record, exc))

    score_records = load_jsonl(scores_path) if scores_path.exists() else []
    summary = summarize_scores(score_records)
    write_json(run_dir / "judge_summary.json", summary)
    write_failure_patterns(run_dir / "failure_patterns.md", summary)
    write_prompt_recommendations(run_dir / "prompt_recommendations.md", score_records)
    if attempted_judge_count and error_count == attempted_judge_count and successful_judge_count == 0:
        raise RuntimeError(
            f"All {attempted_judge_count} judge invocation(s) failed. See {errors_path}."
        )
    print(str(run_dir))
    return run_dir


def main() -> None:
    run_judge(parse_args())


if __name__ == "__main__":
    main()

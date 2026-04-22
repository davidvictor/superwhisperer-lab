#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import html
import json
from datetime import datetime
import re
from collections import defaultdict
from pathlib import Path

from common import (
    DEFAULT_COMPARISONS_DIR,
    load_json,
    load_jsonl,
    normalize_text,
    sanitize_filename,
    write_json,
)


STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "has",
    "have",
    "i",
    "if",
    "in",
    "into",
    "is",
    "it",
    "its",
    "just",
    "me",
    "of",
    "on",
    "or",
    "our",
    "so",
    "that",
    "the",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "to",
    "up",
    "use",
    "want",
    "we",
    "with",
    "you",
    "your",
}

FILLER_WORDS = {
    "actually",
    "basically",
    "kind",
    "kinda",
    "like",
    "literally",
    "maybe",
    "probably",
    "really",
    "sort",
    "stuff",
    "thing",
    "things",
    "uh",
    "uhh",
    "um",
    "umm",
    "you know",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score a Superwhisper batch run with a simple deterministic heuristic."
    )
    parser.add_argument(
        "run_dirs",
        nargs="+",
        type=Path,
        help="One or more run directories from run_superwhisper_queue.py",
    )
    return parser.parse_args()


def tokenize_words(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9_./:-]+", text.lower())


def content_words(text: str) -> set[str]:
    return {word for word in tokenize_words(text) if len(word) >= 4 and word not in STOPWORDS}


def extract_special_tokens(text: str) -> set[str]:
    patterns = [
        r"https?://\S+",
        r"\b[A-Z][A-Z0-9_]{2,}\b",
        r"\b[A-Za-z0-9_./:-]*[./:_-][A-Za-z0-9_./:-]+\b",
        r"\b--[A-Za-z0-9_-]+\b",
        r"\b[A-Za-z_][A-Za-z0-9_]*\([A-Za-z0-9_, ]*\)",
    ]
    tokens: set[str] = set()
    for pattern in patterns:
        for match in re.findall(pattern, text):
            tokens.add(match.lower())
    return tokens


def safe_divide(numerator: float, denominator: float) -> float:
    if not denominator:
        return 0.0
    return numerator / denominator


def clip01(value: float) -> float:
    return max(0.0, min(1.0, value))


def ideal_length_bounds(mode_name: str) -> tuple[float, float]:
    normalized = mode_name.lower()
    if "email" in normalized:
        return 0.45, 1.05
    if "engineering" in normalized:
        return 0.60, 1.25
    if "product" in normalized:
        return 0.65, 1.35
    return 0.55, 1.25


def length_ratio_score(source_text: str, candidate_text: str, mode_name: str) -> float:
    source_len = max(1, len(source_text))
    ratio = len(candidate_text) / source_len
    lower, upper = ideal_length_bounds(mode_name)
    if lower <= ratio <= upper:
        return 1.0
    if ratio < lower:
        return clip01(1.0 - ((lower - ratio) / max(lower, 0.01)))
    return clip01(1.0 - ((ratio - upper) / max(upper, 0.01)))


def structure_score(text: str) -> float:
    if not text.strip():
        return 0.0
    score = 0.0
    stripped = text.strip()
    if stripped[0].isupper():
        score += 0.3
    if stripped.endswith((".", "!", "?", ":", "`")):
        score += 0.2
    if "  " not in stripped:
        score += 0.2
    if "\n\n" in stripped or "\n- " in stripped or "\n1." in stripped:
        score += 0.2
    if len(re.findall(r"[.!?]", stripped)) >= 1:
        score += 0.1
    return clip01(score)


def filler_rate(text: str) -> float:
    words = tokenize_words(text)
    if not words:
        return 0.0
    filler_hits = sum(1 for word in words if word in FILLER_WORDS)
    return filler_hits / len(words)


def repetition_penalty(text: str) -> float:
    words = tokenize_words(text)
    if len(words) < 2:
        return 0.0
    repeats = 0
    for first, second in zip(words, words[1:]):
        if first == second:
            repeats += 1
    return safe_divide(repeats, len(words) - 1)


def score_record(record: dict[str, str]) -> dict[str, float | str]:
    source_text = normalize_text(record.get("source_raw_result")) or normalize_text(record.get("source_result"))
    candidate_text = normalize_text(record.get("output_llm_result")) or normalize_text(record.get("output_result"))
    mode_name = normalize_text(record.get("mode_name"))

    source_content = content_words(source_text)
    candidate_content = content_words(candidate_text)
    content_recall = safe_divide(len(source_content & candidate_content), len(source_content))

    source_special = extract_special_tokens(source_text)
    candidate_special = extract_special_tokens(candidate_text)
    special_recall = safe_divide(len(source_special & candidate_special), len(source_special))
    if not source_special:
        special_recall = 1.0

    source_filler = filler_rate(source_text)
    candidate_filler = filler_rate(candidate_text)
    filler_cleanup = clip01(0.5 + (source_filler - candidate_filler) * 8.0)

    repetition = repetition_penalty(candidate_text)
    repetition_score = clip01(1.0 - repetition * 6.0)

    length_score = length_ratio_score(source_text, candidate_text, mode_name)
    formatting_score = structure_score(candidate_text)
    semantic_proxy = clip01((content_recall * 0.7) + (special_recall * 0.3))

    overall = (
        semantic_proxy * 0.38
        + special_recall * 0.18
        + length_score * 0.14
        + formatting_score * 0.14
        + filler_cleanup * 0.08
        + repetition_score * 0.08
    )

    return {
        "run_name": record.get("run_name", ""),
        "task_id": record["task_id"],
        "source_recording_id": record["source_recording_id"],
        "mode_name": mode_name,
        "candidate_length": len(candidate_text),
        "source_length": len(source_text),
        "content_recall": round(content_recall, 4),
        "special_token_recall": round(special_recall, 4),
        "semantic_proxy": round(semantic_proxy, 4),
        "length_score": round(length_score, 4),
        "formatting_score": round(formatting_score, 4),
        "filler_cleanup_score": round(filler_cleanup, 4),
        "repetition_score": round(repetition_score, 4),
        "overall_score": round(overall * 100, 2),
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def refresh_record_from_meta(record: dict[str, object]) -> dict[str, object]:
    refreshed = dict(record)

    output_meta_path = record.get("output_meta_path")
    if output_meta_path:
        path = Path(str(output_meta_path))
        if path.exists():
            meta = load_json(path)
            refreshed["output_raw_result"] = normalize_text(meta.get("rawResult"))
            refreshed["output_llm_result"] = normalize_text(meta.get("llmResult"))
            refreshed["output_result"] = normalize_text(meta.get("result"))
            refreshed["output_mode_name"] = normalize_text(meta.get("modeName"))
            refreshed["output_datetime"] = normalize_text(meta.get("datetime"))
            refreshed["output_model_name"] = normalize_text(meta.get("modelName"))
            refreshed["output_language_model_name"] = normalize_text(meta.get("languageModelName"))
            refreshed["output_duration_seconds"] = meta.get("duration")

    source_meta_path = record.get("source_meta_path")
    if source_meta_path:
        path = Path(str(source_meta_path))
        if path.exists():
            meta = load_json(path)
            refreshed["source_raw_result"] = normalize_text(meta.get("rawResult"))
            refreshed["source_result"] = normalize_text(meta.get("result"))
            refreshed["source_datetime"] = normalize_text(meta.get("datetime"))
            refreshed["source_duration_seconds"] = meta.get("duration")

    return refreshed


def build_side_by_side_rows(
    records: list[dict[str, object]],
    scores_by_task_id: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}

    for record in records:
        source_recording_id = str(record["source_recording_id"])
        group = grouped.setdefault(
            source_recording_id,
            {
                "source_datetime": record.get("source_datetime", ""),
                "source_recording_id": source_recording_id,
                "source_mode_name": record.get("source_mode_name", ""),
                "source_raw_result": record.get("source_raw_result", ""),
                "source_result": record.get("source_result", ""),
            },
        )
        mode_name = str(record.get("mode_name", ""))
        task_id = str(record.get("task_id", ""))
        score_row = scores_by_task_id.get(task_id, {})
        group[f"{mode_name} output"] = normalize_text(record.get("output_llm_result")) or normalize_text(
            record.get("output_result")
        )
        group[f"{mode_name} score"] = score_row.get("overall_score", "")
        group[f"{mode_name} run"] = record.get("run_name", "")

    rows = list(grouped.values())
    rows.sort(key=lambda row: normalize_text(row.get("source_datetime")), reverse=True)
    return rows


def write_side_by_side_html(path: Path, rows: list[dict[str, object]], mode_names: list[str]) -> None:
    headers = [
        "source_datetime",
        "source_recording_id",
        "source_mode_name",
        "source_raw_result",
    ]
    for mode_name in mode_names:
        headers.extend([f"{mode_name} score", f"{mode_name} output"])

    def render_cell(value: object, css_class: str = "") -> str:
        text = html.escape(str(value or ""))
        class_attr = f' class="{css_class}"' if css_class else ""
        return f"<td{class_attr}>{text}</td>"

    header_html = "".join(f"<th>{html.escape(column)}</th>" for column in headers)
    body_rows = []
    for row in rows:
        cells = [
            render_cell(row.get("source_datetime", ""), "meta"),
            render_cell(row.get("source_recording_id", ""), "meta"),
            render_cell(row.get("source_mode_name", ""), "meta"),
            render_cell(row.get("source_raw_result", ""), "text"),
        ]
        for mode_name in mode_names:
            cells.append(render_cell(row.get(f"{mode_name} score", ""), "score"))
            cells.append(render_cell(row.get(f"{mode_name} output", ""), "text"))
        body_rows.append("<tr>" + "".join(cells) + "</tr>")

    html_text = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Superwhisper Side by Side</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      margin: 0;
      background: #f7f7f8;
      color: #111;
    }}
    .wrap {{
      padding: 20px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 20px;
    }}
    p {{
      margin: 0 0 16px;
      color: #555;
    }}
    .table-wrap {{
      overflow: auto;
      border: 1px solid #ddd;
      background: white;
    }}
    table {{
      border-collapse: collapse;
      width: 100%;
      min-width: 1600px;
    }}
    th, td {{
      border: 1px solid #e5e5e5;
      padding: 10px;
      vertical-align: top;
      text-align: left;
      white-space: pre-wrap;
      line-height: 1.35;
    }}
    th {{
      position: sticky;
      top: 0;
      background: #fafafa;
      z-index: 1;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    td.meta {{
      min-width: 120px;
      font-size: 12px;
    }}
    td.score {{
      min-width: 70px;
      font-weight: 600;
      text-align: center;
    }}
    td.text {{
      min-width: 260px;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>Superwhisper Side by Side</h1>
    <p>Source transcript plus candidate outputs for each mode.</p>
    <div class="table-wrap">
      <table>
        <thead>
          <tr>{header_html}</tr>
        </thead>
        <tbody>
          {''.join(body_rows)}
        </tbody>
      </table>
    </div>
  </div>
</body>
</html>
"""
    path.write_text(html_text, encoding="utf-8")


def main() -> None:
    args = parse_args()
    all_results = []
    run_names = []
    for run_dir_arg in args.run_dirs:
        run_dir = run_dir_arg.expanduser()
        run_name = run_dir.name
        run_names.append(run_name)
        results_path = run_dir / "results.jsonl"
        results = [record for record in load_jsonl(results_path) if record.get("status") == "completed"]
        for record in results:
            enriched = refresh_record_from_meta(record)
            enriched["run_name"] = run_name
            all_results.append(enriched)

    scored_rows = [score_record(record) for record in all_results]
    scored_rows.sort(key=lambda row: (-float(row["overall_score"]), row["task_id"]))
    scores_by_task_id = {str(row["task_id"]): row for row in scored_rows}

    per_mode: dict[str, list[float]] = defaultdict(list)
    per_run: dict[str, list[float]] = defaultdict(list)
    for row in scored_rows:
        per_mode[str(row["mode_name"])].append(float(row["overall_score"]))
        per_run[str(row["run_name"])].append(float(row["overall_score"]))

    summary = {
        "completed_results": len(scored_rows),
        "runs": run_names,
        "mode_averages": {
            mode_name: round(sum(scores) / max(1, len(scores)), 2)
            for mode_name, scores in sorted(per_mode.items())
        },
        "run_averages": {
            run_name: round(sum(scores) / max(1, len(scores)), 2)
            for run_name, scores in sorted(per_run.items())
        },
    }

    if len(args.run_dirs) == 1:
        output_dir = args.run_dirs[0].expanduser()
    else:
        compare_id = datetime.now().strftime("compare-%Y%m%d-%H%M%S")
        suffix = sanitize_filename("-".join(run_names))
        output_dir = DEFAULT_COMPARISONS_DIR / f"{compare_id}__{suffix}"
        output_dir.mkdir(parents=True, exist_ok=True)

    write_csv(output_dir / "heuristic_scores.csv", scored_rows)
    write_json(output_dir / "heuristic_summary.json", summary)
    side_by_side_rows = build_side_by_side_rows(all_results, scores_by_task_id)
    write_csv(output_dir / "side_by_side.csv", side_by_side_rows)
    mode_names = sorted({str(record.get("mode_name", "")) for record in all_results})
    write_side_by_side_html(output_dir / "side_by_side.html", side_by_side_rows, mode_names)
    print(json.dumps(summary, indent=2))
    print(str(output_dir))


if __name__ == "__main__":
    main()

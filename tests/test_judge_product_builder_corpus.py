import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from judge_product_builder_corpus import (
    SCORE_DIMENSIONS,
    record_judge_fingerprint,
    select_pending_records,
    summarize_scores,
    validate_judge_response,
    weighted_score,
)


def valid_payload() -> dict:
    return {
        "scores": {dimension: 4 for dimension in SCORE_DIMENSIONS},
        "confidence": 0.8,
        "failure_tags": ["too_generic"],
        "rationale": "The output is mostly faithful but loses one specific constraint.",
        "recommendation_category": "prompt_candidate",
        "prompt_recommendation": "Emphasize preserving constraints.",
    }


def corpus_record(recording_id: str, app: str = "Codex", surface: str = "code_editor") -> dict:
    return {
        "recording_id": recording_id,
        "datetime": f"2026-04-30T12:00:0{recording_id}",
        "candidate_hash": f"candidate-{recording_id}",
        "context_hash": f"context-{recording_id}",
        "prompt_hash": f"prompt-{recording_id}",
        "judgeable": True,
        "context_summary": {
            "active_app": app,
            "context_surface": surface,
        },
        "raw_result_length_bucket": "medium",
    }


class TestJudgeProductBuilderCorpus(unittest.TestCase):
    def test_weighted_score_all_fives(self):
        scores = {dimension: 5 for dimension in SCORE_DIMENSIONS}
        self.assertEqual(weighted_score(scores), 5.0)

    def test_validate_judge_response_accepts_valid_payload(self):
        validate_judge_response(valid_payload())

    def test_validate_judge_response_rejects_bad_score(self):
        payload = valid_payload()
        payload["scores"]["intent_fidelity"] = 6
        with self.assertRaises(ValueError):
            validate_judge_response(payload)

    def test_validate_judge_response_requires_prompt_recommendation(self):
        payload = valid_payload()
        del payload["prompt_recommendation"]
        with self.assertRaises(ValueError):
            validate_judge_response(payload)

    def test_select_pending_records_skips_completed_fingerprints(self):
        first = corpus_record("1")
        second = corpus_record("2")
        completed = {record_judge_fingerprint(first)}

        pending = select_pending_records([first, second], completed, chunk_size=25)

        self.assertEqual([record["recording_id"] for record in pending], ["2"])

    def test_select_pending_records_respects_chunk_size(self):
        records = [corpus_record("1"), corpus_record("2")]

        pending = select_pending_records(records, set(), chunk_size=1)

        self.assertEqual(len(pending), 1)

    def test_summarize_scores_groups_by_deterministic_context(self):
        score_records = [
            {
                "status": "judged",
                "weighted_score": 4.0,
                "failure_tags": ["too_generic"],
                "recommendation_category": "manual_review",
                "context_summary": {
                    "active_app": "Codex",
                    "context_surface": "code_editor",
                },
                "raw_result_length_bucket": "medium",
            },
            {
                "status": "judged",
                "weighted_score": 2.0,
                "failure_tags": [],
                "recommendation_category": "no_change",
                "context_summary": {
                    "active_app": "Claude",
                    "context_surface": "ai_chat",
                },
                "raw_result_length_bucket": "short",
            },
        ]

        summary = summarize_scores(score_records)

        self.assertEqual(summary["judged_count"], 2)
        self.assertEqual(summary["average_weighted_score"], 3.0)
        self.assertEqual(summary["failure_tag_counts"]["too_generic"], 1)
        self.assertEqual(summary["segments"]["active_app"]["Codex"]["count"], 1)
        self.assertEqual(summary["segments"]["context_surface"]["ai_chat"]["count"], 1)


if __name__ == "__main__":
    unittest.main()

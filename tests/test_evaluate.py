import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluate_superwhisper_run import (
    content_words,
    filler_rate,
    length_ratio_score,
    repetition_penalty,
    score_record,
    structure_score,
    tokenize_words,
)


class TestTokenizeWords(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(tokenize_words("hello world"), ["hello", "world"])

    def test_empty(self):
        self.assertEqual(tokenize_words(""), [])

    def test_punctuation_stripped(self):
        # The regex includes '.' to preserve file paths and URLs, so "bar." stays intact.
        # Commas are stripped, so "foo" is clean.
        tokens = tokenize_words("foo, bar.")
        self.assertIn("foo", tokens)
        self.assertTrue(any("bar" in t for t in tokens))


class TestFillerRate(unittest.TestCase):
    def test_high_filler(self):
        rate = filler_rate("um uh like basically um")
        self.assertGreater(rate, 0.5)

    def test_no_filler(self):
        rate = filler_rate("the quick brown fox jumps")
        self.assertEqual(rate, 0.0)

    def test_empty(self):
        self.assertEqual(filler_rate(""), 0.0)


class TestRepetitionPenalty(unittest.TestCase):
    def test_no_repeats(self):
        self.assertEqual(repetition_penalty("the quick fox"), 0.0)

    def test_all_repeats(self):
        penalty = repetition_penalty("uh uh uh uh")
        self.assertGreater(penalty, 0.5)

    def test_single_word(self):
        self.assertEqual(repetition_penalty("hello"), 0.0)


class TestStructureScore(unittest.TestCase):
    def test_empty_scores_zero(self):
        self.assertEqual(structure_score(""), 0.0)

    def test_well_formed_prose(self):
        score = structure_score("The system processes audio files and writes results to disk.")
        self.assertGreater(score, 0.3)

    def test_score_bounded(self):
        score = structure_score("Hello world.")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


class TestLengthRatioScore(unittest.TestCase):
    def test_same_length_scores_one(self):
        source = "a" * 100
        candidate = "a" * 100
        score = length_ratio_score(source, candidate, "engineering")
        self.assertEqual(score, 1.0)

    def test_empty_candidate_scores_low(self):
        score = length_ratio_score("some text here", "", "engineering")
        self.assertLess(score, 0.5)

    def test_score_bounded(self):
        score = length_ratio_score("hello world", "hello world this is much longer text", "email")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


class TestScoreRecord(unittest.TestCase):
    BASE = {
        "task_id": "rec123__engineering",
        "source_recording_id": "rec123",
        "mode_name": "Engineering",
        "source_raw_result": "um so basically I want to add a retry loop to the worker process",
        "source_result": "",
        "output_llm_result": "Add a retry loop to the worker process.",
        "output_result": "",
    }

    def test_returns_expected_keys(self):
        result = score_record(self.BASE)
        for key in ["overall_score", "content_recall", "filler_cleanup_score", "repetition_score"]:
            self.assertIn(key, result)

    def test_score_bounded_0_100(self):
        result = score_record(self.BASE)
        self.assertGreaterEqual(result["overall_score"], 0.0)
        self.assertLessEqual(result["overall_score"], 100.0)

    def test_empty_candidate_scores_below_non_empty(self):
        empty_record = dict(self.BASE)
        empty_record["output_llm_result"] = ""
        empty_record["output_result"] = ""
        empty_score = score_record(empty_record)["overall_score"]
        full_score = score_record(self.BASE)["overall_score"]
        self.assertLess(empty_score, full_score)

    def test_filler_removed_improves_cleanup_score(self):
        clean_record = dict(self.BASE)
        dirty_record = dict(self.BASE)
        dirty_record["output_llm_result"] = "um uh basically like add um a retry loop basically"
        clean = score_record(clean_record)
        dirty = score_record(dirty_record)
        self.assertGreater(clean["filler_cleanup_score"], dirty["filler_cleanup_score"])


if __name__ == "__main__":
    unittest.main()

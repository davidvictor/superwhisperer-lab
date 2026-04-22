import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import (
    normalize_text,
    sanitize_filename,
    select_source_records,
    unique_preserving_order,
    render_settings_json,
)


class TestNormalizeText(unittest.TestCase):
    def test_strips_whitespace(self):
        self.assertEqual(normalize_text("  hello  "), "hello")

    def test_none_returns_empty(self):
        self.assertEqual(normalize_text(None), "")

    def test_non_string_coerced(self):
        self.assertEqual(normalize_text(42), "42")


class TestSanitizeFilename(unittest.TestCase):
    def test_replaces_spaces(self):
        result = sanitize_filename("hello world")
        self.assertNotIn(" ", result)

    def test_keeps_alphanumeric_and_dash_underscore(self):
        self.assertEqual(sanitize_filename("foo-bar_baz123"), "foo-bar_baz123")

    def test_empty_fallback(self):
        self.assertEqual(sanitize_filename("!!!"), "item")


class TestUniquePreservingOrder(unittest.TestCase):
    def test_removes_duplicates(self):
        self.assertEqual(unique_preserving_order(["a", "b", "a", "c"]), ["a", "b", "c"])

    def test_preserves_order(self):
        self.assertEqual(unique_preserving_order(["c", "a", "b"]), ["c", "a", "b"])

    def test_empty(self):
        self.assertEqual(unique_preserving_order([]), [])


class TestRenderSettingsJson(unittest.TestCase):
    def test_merges_mode_keys(self):
        result = render_settings_json(
            existing_settings={"modeKeys": ["default"]},
            built_in_mode_keys=["default", "mail"],
            custom_mode_keys=["engineering"],
        )
        self.assertIn("engineering", result["modeKeys"])
        self.assertIn("default", result["modeKeys"])
        self.assertIn("mail", result["modeKeys"])

    def test_no_duplicates(self):
        result = render_settings_json(
            existing_settings={"modeKeys": ["default", "engineering"]},
            built_in_mode_keys=["default"],
            custom_mode_keys=["engineering"],
        )
        self.assertEqual(result["modeKeys"].count("default"), 1)
        self.assertEqual(result["modeKeys"].count("engineering"), 1)

    def test_preserves_other_settings(self):
        result = render_settings_json(
            existing_settings={"modeKeys": [], "someOtherKey": "value"},
            built_in_mode_keys=[],
            custom_mode_keys=[],
        )
        self.assertEqual(result["someOtherKey"], "value")


class TestSelectSourceRecords(unittest.TestCase):
    RECORDS = [
        {"datetime": "2024-01-01T10:00:00", "id": "a"},
        {"datetime": "2024-01-03T10:00:00", "id": "b"},
        {"datetime": "2024-01-02T10:00:00", "id": "c"},
    ]

    def test_recent_ordering(self):
        result = select_source_records(self.RECORDS, sample_mode="recent", limit=None, random_seed=0)
        self.assertEqual(result[0]["id"], "b")

    def test_oldest_ordering(self):
        result = select_source_records(self.RECORDS, sample_mode="oldest", limit=None, random_seed=0)
        self.assertEqual(result[0]["id"], "a")

    def test_limit_applied(self):
        result = select_source_records(self.RECORDS, sample_mode="recent", limit=2, random_seed=0)
        self.assertEqual(len(result), 2)

    def test_invalid_sample_mode_raises(self):
        with self.assertRaises(ValueError):
            select_source_records(self.RECORDS, sample_mode="bogus", limit=None, random_seed=0)


if __name__ == "__main__":
    unittest.main()

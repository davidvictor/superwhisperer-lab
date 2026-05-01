import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common import stable_hash
from export_superwhisper_history import build_record as build_history_record
from export_product_builder_corpus import (
    build_product_builder_record,
    export_corpus,
    select_product_builder_records,
)


def write_meta(root: Path, folder_name: str, payload: dict) -> Path:
    folder = root / folder_name
    folder.mkdir(parents=True)
    meta_path = folder / "meta.json"
    meta_path.write_text(json.dumps(payload), encoding="utf-8")
    return meta_path


def sample_meta(mode_name: str = "Product Builder") -> dict:
    return {
        "datetime": "2026-04-30T12:00:00",
        "duration": 1000,
        "modeName": mode_name,
        "modelKey": "sw-ultra-cloud-v1-east",
        "modelName": "Ultra (Cloud)",
        "languageModelKey": "gpt-5.3-chat-latest",
        "languageModelName": "GPT-5.3 Instant",
        "languageSelected": "en",
        "recordingDevice": "mic",
        "rawResult": "Update the card component to preserve the existing hover style.",
        "llmResult": "Update the card component and preserve the existing hover style.",
        "result": "Update the card component to preserve the existing hover style.",
        "prompt": "Product Builder prompt",
        "promptContext": {
            "applicationContext": {
                "name": "Codex",
                "includeInPrompt": True,
                "focusedElementDescription": "editor",
                "focusedElementContent": "components/card.tsx",
                "selectedText": "Card",
                "nouns": ["Card", "hover"],
                "appInfo": {
                    "name": "Codex",
                    "category": "Text Editor (Code)",
                    "textInputFormat": "code",
                },
            },
            "systemContext": {"language": "en"},
            "userContext": {},
            "modeContext": {"type": "custom"},
        },
    }


class TestProductBuilderCorpus(unittest.TestCase):
    def test_build_record_preserves_full_prompt_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta = sample_meta()
            meta_path = write_meta(root, "1", meta)

            record = build_product_builder_record(meta_path, meta)

            self.assertEqual(record["context_raw"], meta["promptContext"])
            self.assertEqual(record["prompt_context"], meta["promptContext"])
            self.assertEqual(record["context_summary"]["active_app"], "Codex")
            self.assertEqual(record["context_summary"]["context_surface"], "code_editor")
            self.assertEqual(record["prompt_context_hash"], stable_hash(meta["promptContext"]))
            self.assertTrue(record["judgeable"])

    def test_general_history_export_preserves_prompt_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            meta = sample_meta()
            meta_path = write_meta(root, "1", meta)

            record = build_history_record(meta_path.parent, meta)

            self.assertEqual(record["prompt_context"], meta["promptContext"])
            self.assertEqual(record["context_raw"], meta["promptContext"])
            self.assertEqual(record["context_summary"]["active_app"], "Codex")
            self.assertEqual(record["prompt_context_hash"], stable_hash(meta["promptContext"]))

    def test_select_product_builder_records_includes_legacy_and_current_names_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            old_path = write_meta(root, "1", sample_meta("Product Engineering Translator"))
            new_path = write_meta(root, "2", sample_meta("Product Builder"))
            excluded_path = write_meta(root, "3", sample_meta("Engineering"))

            records = select_product_builder_records([excluded_path, new_path, old_path])

            self.assertEqual([record["recording_id"] for record in records], ["1", "2"])

    def test_export_corpus_writes_manifest_and_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            recordings_dir = root / "recordings"
            output_dir = root / "corpus"
            write_meta(recordings_dir, "1", sample_meta())

            manifest = export_corpus(recordings_dir, output_dir)

            self.assertEqual(manifest["record_count"], 1)
            self.assertTrue((output_dir / "product_builder_corpus.jsonl").exists())
            self.assertTrue((output_dir / "manifest.json").exists())


if __name__ == "__main__":
    unittest.main()

# Product Builder Eval Memory

## Current Contract

- Active Superwhisper mode key: `productbuilder`.
- Display name: `Product Builder`.
- Legacy mode key/name: `productengineeringtranslator` / `Product Engineering Translator`.
- Corpus source: live Superwhisper `meta.json` records where `modeName` is `Product Builder` or the legacy `Product Engineering Translator`.
- Candidate output for judging: `llmResult`.
- The judge must receive the full recorded `promptContext` exactly as Superwhisper stored it.

## Rubric

- Rubric version: `product-builder-judge-v1`.
- Dimensions: `intent_fidelity`, `technical_specificity`, `design_product_fidelity`, `context_usefulness`, `actionability`, `noise_removal`, `non_invention`.
- Routing and intent labels must come from deterministic Superwhisper context, not transcript classification.

## Corpus Rules

- Keep generated corpora in `corpora/`; do not commit them.
- Keep judge runs in `judge_runs/`; do not commit them.
- Records with empty source transcript or empty `llmResult` remain in the corpus but are marked non-judgeable and skipped by the judge.
- Preserve app context, focused element context, selected text, URL, nouns, prompt, model metadata, hashes, and file paths.

## Verified Smoke State

- `python3 -m unittest discover -s tests -v` passes.
- `python3 -m py_compile ...` passes for the repo scripts.
- `python3 export_product_builder_corpus.py --limit 5` writes an ignored five-record corpus.
- `python3 judge_product_builder_corpus.py --corpus-jsonl <corpus> --chunk-size 2 --dry-run` writes ignored judge state.
- Judge runs default to `gpt-5.4` because this local Codex CLI rejects its own `gpt-5.5` default.
- A real smoke judge run against a five-record corpus judged one record, skipped one empty record, and wrote no errors.
- `python3 sync_superwhisper_modes.py --mode-key productbuilder` writes `productbuilder.json`, removes the deprecated `productengineeringtranslator.json` file, and removes `productengineeringtranslator` from Superwhisper settings.

## Prompt Hypotheses

- The current prompt should prioritize outcome-based framing over process-based descriptions.
- The current prompt should route from deterministic Superwhisper context rather than spoken-content classification.

## Next Chunk

- Inspect the first larger chunk's `judge_errors.jsonl`, `judge_scores.jsonl`, `judge_summary.json`, and `failure_patterns.md` before increasing chunk size again.
- If all attempted judge calls fail, fix the invocation before increasing chunk size.

# Product Builder Evaluation Plan

## Scope

Evaluate Product Builder using real local Superwhisper recording metadata, full prompt context, and a resumable Codex judge workflow.

The active mode is `Product Builder`. The current repo mode key is `productbuilder`. Historical recordings may still use the legacy mode name `Product Engineering Translator`; those records remain valid corpus inputs so earlier evidence is not lost.

## Source Of Truth

- Editable prompt: `prompts/product-builder.md`
- Mode declaration: `mode_specs.json`
- Generated live mode target: `~/Documents/superwhisper/modes/productbuilder.json`
- Deprecated live mode key removed by sync: `productengineeringtranslator`
- Corpus exporter: `export_product_builder_corpus.py`
- Judge runner: `judge_product_builder_corpus.py`
- Judge schema: `schemas/product_builder_judge_response.schema.json`

## Corpus Workflow

1. Read live Superwhisper `meta.json` files from the configured recordings directory.
2. Select records whose `modeName` is `Product Builder` or the legacy `Product Engineering Translator`.
3. Preserve the raw transcript, `llmResult`, final result, prompt, full `promptContext`, model metadata, context summaries, file paths, and stable hashes.
4. Write generated corpus artifacts under `corpora/`, which must stay out of git.

Useful command:

```bash
python3 export_product_builder_corpus.py
```

## Judge Workflow

1. Load the latest Product Builder corpus, or pass `--corpus-jsonl`.
2. Skip records already judged in the target run directory by fingerprint.
3. Send each pending judgeable record to Codex CLI with the strict JSON schema.
4. Append scores to `judge_scores.jsonl`, errors to `judge_errors.jsonl`, and write summaries under `judge_runs/`, which must stay out of git.

Useful commands:

```bash
python3 judge_product_builder_corpus.py --chunk-size 25
python3 judge_product_builder_corpus.py --corpus-jsonl corpora/<run>/product_builder_corpus.jsonl --chunk-size 2 --dry-run
```

## Readiness Checks

Before committing Product Builder evaluation changes:

- Run `python3 -m unittest discover -s tests -v`.
- Run `python3 -m py_compile common.py export_superwhisper_history.py export_product_builder_corpus.py judge_product_builder_corpus.py run_superwhisper_queue.py sync_superwhisper_modes.py evaluate_superwhisper_run.py`.
- Run a small corpus export with `python3 export_product_builder_corpus.py --limit 5`.
- Run a judge dry run against that corpus.
- Run one real one-record judge pass when changing judge invocation, schema, or prompt assembly.
- Treat a run where every attempted judge invocation fails as not ready; the runner exits nonzero after writing the error log and summaries.

# Superwhisperer Lab

Superwhisperer Lab is a private utility repo for working with local Superwhisper history as a prompt-and-mode evaluation system.

It does four main things:

- exports local Superwhisper transcript history into eval-friendly files
- syncs Superwhisper custom modes from editable markdown prompts
- runs one-mode-at-a-time batch reprocessing through the real Superwhisper app
- compares outputs side by side across multiple mode runs

## Repo Layout

- `common.py`
  Shared path, config, and JSON helpers.
- `export_superwhisper_history.py`
  Exports local history into JSONL, CSV, and markdown bundles.
- `sync_superwhisper_modes.py`
  Writes live Superwhisper mode JSON files from `mode_specs.json` and the prompt markdown files.
- `run_superwhisper_queue.py`
  Drives the real Superwhisper app one mode at a time over a chosen transcript set.
- `evaluate_superwhisper_run.py`
  Rehydrates finished outputs from live `meta.json` files, scores them heuristically, and generates a side-by-side HTML compare view.
- `mode_specs.json`
  Declarative local mode configuration.
- `prompts/`
  Prompt text for the current mode set.

## Working Model

The safest operating mode is:

1. export a clean source corpus
2. run one mode per batch
3. compare multiple run folders together

This avoids the fragility of trying to switch modes repeatedly inside one long mixed-mode batch.

## Quick Start

Sync modes:

```bash
python3 sync_superwhisper_modes.py
```

Export local history:

```bash
python3 export_superwhisper_history.py
```

Run a single mode over the latest exported corpus:

```bash
python3 run_superwhisper_queue.py --sample-mode recent --limit 25 --mode-key engineering
```

Compare multiple runs:

```bash
python3 evaluate_superwhisper_run.py \
  /path/to/run-engineering \
  /path/to/run-productdesign \
  /path/to/run-emailcommunication
```

The compare command writes:

- `heuristic_summary.json`
- `heuristic_scores.csv`
- `side_by_side.csv`
- `side_by_side.html`

## Local Configuration

This repo is intentionally private and machine-local in spirit.

`mode_specs.json` can contain personal filesystem paths for:

- Superwhisper mode files
- prompt locations

The scripts also use the local default Superwhisper paths in `common.py` unless you override them.

## Current Guidance

- Treat `llmResult` as the primary rewritten output when present.
- Treat `result` as the fallback when `llmResult` is empty.
- Refresh compare output from live `meta.json` before judging a run.
- Keep generated run artifacts out of git.

## Status

This repo was spun out from a local exploratory lab under the default workspace and packaged as a standalone private repo candidate.

```
                           _   _                    _     _   
 ___ _ _ ___ ___ ___ _ _ _| |_|_|___ ___ ___ ___   | |___| |_ 
|_ -| | | . | -_|  _| | | |   | |_ -| . | -_|  _|  | | .'| . |
|___|___|  _|___|_| |_____|_|_|_|___|  _|___|_|    |_|__,|___|
        |_|                         |_|                       
```

# superwhisper-lab

> A CLI toolkit for anyone taking Superwhisper custom modes seriously: export your real recording history, replay prompts through the live app, score the results, and compare outputs side by side.

## The Problem

[Superwhisper](https://superwhisper.com/) lets you define custom modes: different LLM prompts that rewrite your dictation for different contexts — engineering notes, product thinking, email drafts. Writing a prompt is easy. Knowing whether it's actually working is not.

The feedback loop is broken. You dictate, glance at the output, and move on. You might notice a mode feels better, or worse, but you have no systematic way to verify that impression across a real corpus of your own speech. Tweaking a prompt feels like adjusting in the dark.

## Why I Built This

The insight behind this repo is simple: you already have the eval corpus. Every recording you've ever made is sitting in Superwhisper's local history, with the raw transcript, the rewritten output, the mode name, and the audio file. That's a real-world eval corpus built from your actual voice patterns.

Instead of testing prompt changes against synthetic examples, this tooling replays your real recordings through the Superwhisper app itself, one mode at a time, then scores the outputs using a deterministic heuristic that measures content recall, filler removal, length appropriateness, and structural quality. The score isn't a substitute for reading the output — it's a signal that tells you where to look in the side-by-side comparison.

That makes the workflow useful beyond this repo: anyone taking Superwhisper modes seriously can use their own history to evaluate whether a mode is improving, not just whether it feels better in the moment.

## What It Does

Four scripts, each with a distinct job:

- **`export_superwhisper_history.py`** — Walks Superwhisper's local recordings folder and exports your history to JSONL, CSV, and per-recording Markdown files. Produces a timestamped export bundle you can use as a stable eval corpus.

- **`sync_superwhisper_modes.py`** — Reads `mode_specs.json` and prompt Markdown, writes live Superwhisper mode JSON files, and keeps local mode settings aligned.

- **`run_superwhisper_queue.py`** — Drives the real Superwhisper desktop app to reprocess audio files one mode at a time. Matches output recordings by duration and raw transcript fingerprint. Writes a JSONL results log and per-task Markdown outputs.

- **`evaluate_superwhisper_run.py`** — Rehydrates results from live `meta.json` files, scores each output against the source transcript on six heuristic dimensions, and generates a side-by-side HTML comparison across all modes in a run.

## How It Works

The evaluation is deterministic and dependency-free. For each source/output pair, the scorer measures:

- **Content recall** — what fraction of the source's content words appear in the output
- **Special token recall** — how well URLs, identifiers, CLI flags, and capitalized terms survive the rewrite
- **Filler cleanup** — how much dictation noise (um, uh, basically, like) was removed
- **Length ratio** — whether the output is appropriately compressed or expanded for the mode type
- **Structure score** — capitalization, sentence endings, paragraph breaks
- **Repetition penalty** — consecutive repeated words in the output

The overall score (0–100) is a weighted composite. It's not a truth oracle — it's a fast signal to prioritize which rows in the side-by-side HTML are worth reading carefully.

## Quick Start

**1. Configure your paths**

Copy the example env file and set paths if your Superwhisper data isn't in the default location:

```bash
cp env.example .env
# edit .env if needed — defaults point to ~/Documents/superwhisper/
```

**2. Sync your modes**

```bash
python3 sync_superwhisper_modes.py
```

This writes the live mode JSON files from editable prompt sources. Restart Superwhisper if changes do not appear immediately.

**3. Export your recording history**

```bash
python3 export_superwhisper_history.py
```

Writes a timestamped bundle to `~/Documents/superwhisper_exports/export-YYYYMMDD-HHMMSS/`.

**4. Run a mode over recent recordings**

```bash
python3 run_superwhisper_queue.py --sample-mode recent --limit 25 --mode-key engineering
```

Run once per mode. Each mode gets its own run folder under `runs/`.

Warning: live replay runs drive the real Superwhisper desktop app through the macOS UI. While a batch is running, the machine is largely unusable for normal work.

**5. Compare runs**

```bash
python3 evaluate_superwhisper_run.py \
  runs/run-engineering \
  runs/run-productdesign \
  runs/run-emailcommunication
```

Writes to `comparisons/compare-YYYYMMDD-HHMMSS__<run-names>/`:

- `side_by_side.html` — full comparison table, one row per source recording
- `heuristic_summary.json` — per-mode and per-run average scores
- `heuristic_scores.csv` — raw scores for every task
- `side_by_side.csv` — flat export of the comparison table

## Usage

**Sync only specific modes:**

```bash
python3 sync_superwhisper_modes.py --mode-key engineering --mode-key emailcommunication
```

**Dry run (preview writes without touching files):**

```bash
python3 sync_superwhisper_modes.py --dry-run
```

**Run a random sample:**

```bash
python3 run_superwhisper_queue.py --sample-mode random --limit 20 --mode-key productdesign
```

**Evaluate a single run in place:**

```bash
python3 evaluate_superwhisper_run.py runs/run-engineering
```

## Configuration

**Environment variables** (all optional — see `env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `SUPERWHISPER_RECORDINGS_DIR` | `~/Documents/superwhisper/recordings` | Superwhisper's recordings folder |
| `SUPERWHISPER_EXPORT_ROOT` | `~/Documents/superwhisper_exports` | Where export bundles are written |
| `SUPERWHISPER_MODES_DIR` | `~/Documents/superwhisper/modes` | Superwhisper's live modes directory |
| `SUPERWHISPER_SETTINGS_PATH` | `~/Documents/superwhisper/settings/settings.json` | Superwhisper's settings file |

**`mode_specs.json`** — declarative mode configuration. Defines each custom mode's key, name, prompt file, language model, and voice model. Edit `prompts/*.md` files to change prompt text; run `sync_superwhisper_modes.py` to deploy.

For machine-specific path overrides without touching `mode_specs.json`, create `mode_specs.local.json` (gitignored) with your local paths — or use env vars.

## Requirements

- Python 3.11+ (standard library only, no pip installs required)
- macOS with [Superwhisper](https://superwhisper.com/) installed
- Superwhisper must be running during `run_superwhisper_queue.py` — the script drives the live app via `open` URL handlers

This repo does **not** require Codex or Codex Computer Use to function. The runtime dependency is just Python plus the local Superwhisper app on macOS.

## Limitations

- macOS + local Superwhisper only. Live replay uses the installed Superwhisper app and `superwhisper://` URL handlers.
- Live replay occupies the desktop. `run_superwhisper_queue.py` switches modes and submits audio through the app, so expect the machine to be tied up while a batch is running.
- Replay depends on app responsiveness. The runner watches the recordings folder for new results and can time out if Superwhisper or the LLM rewrite is slow; adjust `--timeout-seconds` for longer jobs.
- Scores are triage signals, not judgments. The heuristic measures recall, cleanup, length, structure, and repetition; use `side_by_side.html` for final evaluation.
- Path assumptions track Superwhisper's current local folder layout. If the app changes its storage format, `common.py` and the default paths may need updates.
- Runs and comparisons can get large. They are intentionally gitignored.

## Running Unit Tests

```bash
python3 -m unittest discover -s tests -v
```

These are pure-Python unit tests. They do **not** drive the Superwhisper UI and they do **not** take over the desktop.

## Running Live Replay Batches

Commands like the following are operational replay runs, not unit tests:

```bash
python3 run_superwhisper_queue.py --sample-mode recent --limit 25 --mode-key engineering
```

## License

MIT

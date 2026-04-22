```
                                    _     _                       _       _     
 ___ _   _ _ __   ___ _ ____      _| |__ (_)___ _ __   ___ _ __  | | __ _| |__  
/ __| | | | '_ \ / _ \ '__\ \ /\ / / '_ \| / __| '_ \ / _ \ '__| | |/ _` | '_ \ 
\__ \ |_| | |_) |  __/ |   \ V  V /| | | | \__ \ |_) |  __/ |    | | (_| | |_) |
|___/\__,_| .__/ \___|_|    \_/\_/ |_| |_|_|___/ .__/ \___|_|    |_|\__,_|_.__/ 
          |_|                                  |_|                              
```

# superwhisper-lab

> A CLI toolkit for benchmarking Superwhisper custom modes against your own voice recording history — export, replay, score, and compare prompt outputs side by side.

## The Problem

[Superwhisper](https://superwhisper.com/) lets you define custom modes: different LLM prompts that rewrite your dictation for different contexts — engineering notes, product thinking, email drafts. Writing a prompt is easy. Knowing whether it's actually working is not.

The feedback loop is broken. You dictate, glance at the output, and move on. You might notice a mode feels better, or worse, but you have no systematic way to verify that impression across a real corpus of your own speech. Tweaking a prompt feels like adjusting in the dark.

The second problem is operational: Superwhisper's mode deployment has two steps — write the mode JSON file, then register the mode key in `settings.json`. Miss the second step and your mode silently disappears from the UI. There's no built-in way to manage this from editable source files.

## Why I Built This

The insight behind this repo is simple: you already have the eval corpus. Every recording you've ever made is sitting in Superwhisper's local history, with the raw transcript, the rewritten output, the mode name, and the audio file. That's a ground-truth dataset of your actual voice patterns.

Instead of testing prompt changes against synthetic examples, this tooling replays your real recordings through the Superwhisper app itself, one mode at a time, then scores the outputs using a deterministic heuristic that measures content recall, filler removal, length appropriateness, and structural quality. The score isn't a substitute for reading the output — it's a signal that tells you where to look in the side-by-side comparison.

The longer goal is a periodic self-improvement loop: export a fresh slice of recent recordings, run them through your current mode set, score and compare, tune the prompts, repeat. Each iteration tightens alignment between how you actually speak and how your modes render it.

Built during a focused lab sprint using Codex, published because the workflow generalizes to anyone running custom Superwhisper modes seriously.

## What It Does

Four scripts, each with a distinct job:

- **`export_superwhisper_history.py`** — Walks Superwhisper's local recordings folder and exports your history to JSONL, CSV, and per-recording Markdown files. Produces a timestamped export bundle you can use as a stable eval corpus.

- **`sync_superwhisper_modes.py`** — Reads `mode_specs.json` and the prompt Markdown files, writes the live Superwhisper mode JSON files, and updates `settings.json` `modeKeys` so modes appear in the UI. Handles both steps atomically.

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

This writes the mode JSON files and registers them in `settings.json`. If Superwhisper is open, quit and reopen it after syncing.

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

Writes to `comparisons/compare-YYYYMMDD-HHMMSS__*/`:

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

- macOS only. The queue runner uses `open superwhisper://` URL schemes and the Superwhisper app itself.
- `run_superwhisper_queue.py` requires Superwhisper to be open and responsive. It polls for new recordings by watching the recordings folder — if the app is slow or the LLM rewrite takes longer than `--timeout-seconds`, tasks will time out.
- Live replay runs interact with the desktop UI only. They switch modes and submit audio through the app itself, so the computer is largely unusable while a batch is in progress.
- The heuristic scorer is a proxy, not a judge. It measures recall and structure, not semantic quality. Read the side-by-side HTML; don't just sort by score.
- End-to-end live replay runs have only been tested from the Codex desktop app on macOS. The repository itself is not Codex-specific, but other automation environments have not been validated to the same degree.
- Tested with Superwhisper's current folder layout. If Superwhisper changes its internal storage structure, the path assumptions in `common.py` may need updating.
- Run folders and comparison outputs are excluded from git. They can get large quickly if you run many modes over large corpora.

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

These runs drive the live Superwhisper app through the macOS UI. Expect the desktop to be effectively occupied until the batch finishes.

## License

MIT

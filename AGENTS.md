# Superwhisperer Lab

## Purpose

This repo packages the Superwhisper evaluation tooling as a standalone private utility repository.

It is a machine-local, operator-focused repo for:

- exporting Superwhisper history
- syncing prompt-defined modes into the live app
- batch-running one mode at a time through the real Superwhisper desktop app
- comparing outputs side by side

## Working Rules

- Prefer single-mode runs over mixed-mode runs. The app is more reliable when one mode is run across a whole batch before switching.
- When evaluating outputs, re-read the live `meta.json` files before rendering or scoring. Do not trust stale snapshots if `llmResult` may still be populating.
- Keep generated artifacts out of git. That includes:
  - run folders
  - comparison folders
  - caches
  - ad hoc exports
- Preserve prompt markdown as the editable source of truth. The live Superwhisper mode JSON files are a generated deployment target.
- Keep the tool standard-library-only unless there is a strong reason to add a dependency.

## Layout

- Root Python scripts are the main entrypoints.
- `prompts/` holds editable prompt text.
- `mode_specs.json` is the local mode declaration.

## Scope

This file applies to this repository and everything under it.

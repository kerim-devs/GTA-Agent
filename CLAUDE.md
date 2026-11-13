# GTA agent

An AI plays GTA on a real PS5 for a live stream. `PLAN.md` is the current plan and says how the work is done and where the limits are; read its sections "How the work is done" and "Limits" before anything else. Decisions and measurements are logged in `docs/LOG.md`, task cards live in `docs/tasks/`, finished cards leave a report in `docs/reports/`. A decision that is not in the log has not been made, so write it there on the day it falls.

## The console is real

The bridge daemon on `http://127.0.0.1:9395` sends inputs to Kerim's console. Only the planning session talks to it, and only after looking at the picture and reading `/pad`, as `PLAN.md` describes. A worker on a card never talks to the daemon, never runs `ps5rp` and never sets `PS5_HOST`; the full rules for workers are in `docs/tasks/README.md`. Tests and the gate always run with `env -u PS5_HOST`, because the variable switches on the hardware tests.

While a run is live on the console, nothing heavy runs on this Mac beside it. Tests, evaluations and replays slow the text recognition down until the pilot reads too late.

## Worktrees and branches

Every card is built in a worktree of its own under `../gta-worktrees/`, on a branch cut from the integration branch `feat/pilot`. A fresh worktree cannot run the gate until three things are in place: `lab/minimap/data/crops.npy` linked from the main checkout (367 MB, ignored by git), `pilot/models/yolox_l.onnx` copied from there (216 MB, ignored by git), and `uv sync` run in `pilot/`.

The gate is `env -u PS5_HOST .venv/bin/python tools/gate.py` from `pilot/`; `--full` adds the slow tests and has to be green before `feat/pilot` goes to `main`. A reviewed card is merged into `feat/pilot` locally. Pull requests go from `feat/pilot` to `main`. Nothing is force pushed, and work in progress in other worktrees is left alone.

## Who does what

The planning session plans, writes the cards and reviews; it does not build cards itself. Workers that build run on Sonnet. Opus is taken only when a card needs judgement on measurements, and the reason is said when the worker is started. Reading and searching goes to the `reader` agent.

## Boundaries

Work stays inside this repository, its worktrees and `/Users/kerim/recordings/`. Nothing is deleted except recordings of the game that are no longer needed, and those are named first. Everything written into the repository or to GitHub is English prose.

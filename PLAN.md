# Plan

An AI plays the story of GTA VI on a PS5 in a live stream from 19 November 2026, with an AI commentator who reads the chat. GTA V is the practice ground: rehearsal on 15 November, pilot stream on 16 November. The measure of success is not flawless play. The agent may hit a lamp post, but it has to free itself within about ten seconds and carry on, and it must never hold an input that the picture no longer justifies.

This file is the current plan. It replaces the two handoff notes, which now sit in `archive/`. Measurements and decisions are logged in `docs/LOG.md`, task cards live in `docs/tasks/`, and every finished task leaves a report in `docs/reports/`.

## How the agent is built

Three layers share the work. The reflexes are a local loop at 30 Hz without any language model: it reads the minimap from the picture and sets steering, throttle and brake. Skills are small behaviours built on the reflexes, such as following the GPS route, getting unstuck, walking to a blip, entering a vehicle or shooting with aim assist. The head is a strong model that is asked only on events (a new objective, a failed mission, a menu, being lost) and picks the skill. It runs through the local Codex CLI, where one call takes about seven seconds today, so nothing that has to happen within a second may depend on it. A commentator process later reads what the head and the reflexes are doing and turns it into speech for the stream.

The picture comes from Remote Play over a wired connection, and the inputs go back the same way through the bridge in `remoteplay/`. A capture card arrives on 11 November. It feeds OBS, and it replaces Remote Play as the agent's eyes only if a measurement shows a clear gain.

Every run is recorded. The bridge writes video, frame times and controller states, and the pilot adds one log line per tick with what it read and what it commanded. From 23 November a stronger machine is available, and these recordings, including every moment where Kerim had to take over, are the material for training a model of our own.

## Where things stand on 10 November

The bridge works and has 120 passing tests. Over the wired connection, with the game in performance mode, the time from an input to the changed picture is 120 to 156 ms at 60 fps, stable from sample to sample, and the stream is almost free of damaged frames. Over Wi-Fi it was 600 to 1160 ms with roughly a third of the frames damaged.

A minimap reader exists in `lab/minimap/impl_trace`. On the held-out sheets it reports no route where there is none, finds all 11 routes, is off by 5 degrees in the median on the near bearing and takes about 1 ms per crop. It is not packaged, has no tests and was built on Wi-Fi recordings.

Nothing drives yet: there is no controller, no loop, no recovery, no head and no stream setup.

## Work packages

Phase 1, 10 and 11 November, is driving. Four packages run in parallel, each with a task card: P1 closes two gaps on the path that sends inputs to the console, P2 packages the reader with tests and adds a motion estimate from the minimap, P3 builds the driver and a small simulator to test it against the measured delay, and P4 builds the runtime that connects bridge, reader and driver, records every run and can replay recordings offline. The phase ends with two live sessions together with Kerim: first he drives a route himself while the pilot runs in shadow mode and only logs what it would do, then the pilot drives to a waypoint on an empty road.

Phase 2, 12 and 13 November, is the head and the remaining skills: reading the instruction text on screen with the text recognition built into macOS, a persistent Codex process as the head, a notebook of lessons it reads before each mission, and the skills for walking to a blip, entering a vehicle, shooting with aim assist, skipping cutscenes and retrying after a failure.

Phase 3, 14 to 16 November, is the stream: OBS with the capture card, an overlay that shows the current goal and the route the pilot reads, the commentator with a voice and the chat, a two hour rehearsal on the 15th with a list of every failure, and the pilot stream on the 16th.

Phase 4, 17 to 19 November, prepares GTA VI. The HUD of the new game is unknown, so the reader has to be adapted on launch day: Kerim plays the first hour himself with the recorder running, the labelling and reader workflow in `lab/minimap/workflow.js` runs on that recording, and the pilot takes over the driving afterwards. The head carries over unchanged.

Phase 5 starts on 23 November with the new machine: training on the collected recordings, and a local vision model as a fast layer between reflexes and head if the measurements justify it.

P5, hardening the recorder, is specified in `docs/tasks/P5-recorder-robustness.md` and waits until the first kilometre has been driven.

## How the work is done

Claude plans, writes the task cards and reviews. Codex implements each card in its own worktree on a branch of its own. Nothing is merged into the integration branch `feat/pilot` before the gate of the package is green and the diff has been read. Changes on the path that sends inputs to the console get a second review whose only job is to break them. Pull requests go from `feat/pilot` to `main`, and `main` only moves when Kerim has accepted the change.

Measure first, then build. Several assumptions in this project turned out wrong once they were measured, so a number without a measurement is marked as an estimate in the log.

## Limits

The files `profiles.json` and `console.json` under `~/.config/ps5-remoteplay-mcp/` hold credentials and are never read; only `daemon.log` there may be. Inputs go to the real console only while Kerim is present. Reading status and frames is always fine. System and privacy settings of macOS are changed by Kerim, not by an agent. His email address and project details go to no outside service. Automated tests never run with `PS5_HOST` set, because that switches on the hardware tests.

## Open decisions

Whether the Codex quota carries a two hour stream with a head call every 20 seconds next to the build work is unknown until a long test run; an API key is the fallback. Also open: the platform, the voice and role of the commentator, preloading GTA VI, and the risk from the rules of PSN and Rockstar.

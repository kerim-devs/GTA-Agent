# Plan

An AI plays the story of GTA VI on a PS5 in a live stream from 19 November 2026, with an AI commentator who reads the chat. GTA V is the practice ground: rehearsal on 15 November, pilot stream on 16 November. The measure of success is not flawless play. The agent may hit a lamp post, but it has to free itself within about ten seconds and carry on, and it must never hold an input that the picture no longer justifies.

This file is the current plan. It replaces the two handoff notes, which now sit in `archive/`. Measurements and decisions are logged in `docs/LOG.md`, task cards live in `docs/tasks/`, and every finished task leaves a report in `docs/reports/`.

## How the agent is built

Three layers share the work. The reflexes are a local loop at 30 Hz without any language model: it reads the minimap from the picture and sets steering, throttle and brake. Skills are small behaviours built on the reflexes, such as following the GPS route, getting unstuck, walking to a blip, entering a vehicle or shooting with aim assist. The head is a strong model that is asked only on events (a new objective, a failed mission, a menu, being lost) and picks the skill. It runs through the local Codex CLI, where one call takes about seven seconds today, so nothing that has to happen within a second may depend on it. A commentator process later reads what the head and the reflexes are doing and turns it into speech for the stream.

The picture comes from Remote Play over a wired connection, and the inputs go back the same way through the bridge in `remoteplay/`. A capture card arrives on 11 November. It feeds OBS, and it replaces Remote Play as the agent's eyes only if a measurement shows a clear gain.

Every run is recorded. The bridge writes video, frame times and controller states, and the pilot adds one log line per tick with what it read and what it commanded. From 23 November a stronger machine is available, and these recordings, including every moment where Kerim had to take over, are the material for training a model of our own.

## Where things stand on the morning of 11 November

The bridge works. Over the wired connection, with the game in performance mode, the time from an input to the changed picture is 120 to 156 ms at 60 fps, stable from sample to sample, and the stream is almost free of damaged frames. Over Wi-Fi it was 600 to 1160 ms with roughly a third of the frames damaged. The bridge repeats the whole input state several times a second, so a lost release cannot leave a button held. On the morning of 11 November the console is in standby on another network and the bridge is stopped.

The pilot is a package with a gate. It reads the minimap in about 1 ms: map class, route colour, the route as a path of points, the player arrow and the coloured blips. It reads the distance to the destination that the game prints on the vehicle map and takes the car's speed from it. It reads health, armour and which screen the game shows, the German help, objective and banner texts, and it finds vehicles and people in the frame with a detector that runs beside the loop. The driver aims at the route close to the arrow, plans its speed before a bend, bridges damaged frames, backs out when it is stuck and gives up after repeated failures; in a simulator with a zooming map and a faulty distance readout it reaches every goal within 5 m of the route.

The conductor runs a session. It asks the head on events and ahead of the end of a plan, over a Codex process that stays up and answers in about five and a half seconds, and carries the answer out as a plan of up to five skills from a registry: follow the route, wait, press, walk, look, shoot, walk to a blip, face a blip, set a waypoint on the pause map, get into a vehicle, fight red blips with a gun or without, punch a person. A reflex beside it deals with the screens that wait for a button: it closes a menu nobody asked for, presses the retry after a failed mission, waits while the game loads and tells the head afterwards. The commentator follows a session's logs, speaks the head's sentences and the events, and answers the chat through a writer of its own within four to fifteen seconds. `pilot calibrate` measures the console's timings and dead zones in about a minute.

What has run on the console is little: on the night of 10 November the pilot walked the character around for four minutes with the first six skills. Everything built since then has been judged on recordings and simulated games only, and the reviews of that night found one fault after another that only real pictures show. The car has still not been driven by the pilot. The wanted level is not read yet. Nothing of the stream setup beyond the overlay page and the commentator exists.

## Work packages

Phase 1 is driving, and its building is done: P1 closed two gaps on the path that sends inputs to the console, P2 packaged the reader and added the motion check, P3 and P4 built the first driver, the simulator and the runtime, P6 stopped the driver cancelling its own steering, P8 moved it onto the route path, P9 gave it a real speed. What remains are the two live sessions together with Kerim: first he drives a route himself over the cable while the pilot runs in shadow mode and only logs what it would do, which is also the first clean recording to judge the readers and the speed on; then the pilot drives to a waypoint on an empty road at 4 m/s.

Phase 2, 11 to 13 November, is the head and the remaining skills. Reading the screen text and detecting events is done (P7). P10 builds the conductor that runs a whole session, asks the Codex CLI in the background on events and carries its answer out with small skills: following the route, waiting, pressing a button, walking, looking, shooting with aim assist. After that come a notebook of lessons the head reads, walking to a blip instead of walking blind, and retrying after a failure.

The second wave runs since the night of 10 November, seven cards in parallel and two more later that night, each a module of its own that the reviewer wires in: P13 keeps the character moving while the head thinks, asks the head ahead of time over a Codex process that stays up, and turns the skills into a registry; P14 detects vehicles and people in the frame; P15 reads health, armour and which screen the game shows; P16 gets into the nearest vehicle; P17 drives along the road without a route; P18 fights; P19 sets a waypoint on the pause map. Two more were added the same night: P20 builds the commentator's core, with the platform, the voice and the character left as settings, and P21 gets the pilot past the screens that wait for a button, such as the retry after a failed mission. All of these are merged except P17, which waits on its branch for clean footage of a drive without a route; P22 wired the readers, the reflex and the conductor together, P23 added the punch, P24 the command that measures the console. Running since the morning of 11 November: P25 reads the wanted level and the death screen, for which the long recording turned out to hold footage after all, and P20c gives the commentator the state of the game. Still to be written: the arrest screen, which no recording shows, and the loop that walks into a mission marker, retries after a failure and goes on to the next mission.

Phase 3, 14 to 16 November, is the stream: OBS with the capture card, an overlay that shows the current goal and the route the pilot reads, the commentator with a voice and the chat, a two hour rehearsal on the 15th with a list of every failure, and the pilot stream on the 16th.

Phase 4, 17 to 19 November, prepares GTA VI. The HUD of the new game is unknown, so the reader has to be adapted on launch day: Kerim plays the first hour himself with the recorder running, the labelling and reader workflow in `lab/minimap/workflow.js` runs on that recording, and the pilot takes over the driving afterwards. The head carries over unchanged.

Phase 5 starts on 23 November with the new machine: training on the collected recordings, and a local vision model as a fast layer between reflexes and head if the measurements justify it.

P5, hardening the recorder, is specified in `docs/tasks/P5-recorder-robustness.md` and waits until the first kilometre has been driven.

## How the work is done

Claude plans, writes the task cards and reviews. Codex implements each card in its own worktree on a branch of its own. Nothing is merged into the integration branch `feat/pilot` before the gate of the package is green and the diff has been read. Changes on the path that sends inputs to the console get a second review whose only job is to break them. Pull requests go from `feat/pilot` to `main`, and `main` only moves when Kerim has accepted the change.

Measure first, then build. Several assumptions in this project turned out wrong once they were measured, so a number without a measurement is marked as an estimate in the log.

## Limits

The files `profiles.json` and `console.json` under `~/.config/ps5-remoteplay-mcp/` hold credentials and are never read; only `daemon.log` there may be. Inputs go to the real console only while Kerim is present, and he starts every such run himself. No sound is played while he sleeps next to the machine; the commentator is rehearsed with `--mute`. Reading status and frames is always fine. System and privacy settings of macOS are changed by Kerim, not by an agent. His email address and project details go to no outside service. Automated tests never run with `PS5_HOST` set, because that switches on the hardware tests.

## Open decisions

Whether the Codex quota carries a two hour stream with a head call every 20 seconds next to the build work is unknown until a long test run; an API key is the fallback. Also open: the platform, the voice and role of the commentator, preloading GTA VI, and the risk from the rules of PSN and Rockstar.

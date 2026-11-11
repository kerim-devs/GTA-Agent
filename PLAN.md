# Plan

An AI plays the story of GTA VI on a PS5 in a live stream from 19 November 2026, with an AI commentator who reads the chat. GTA V is the practice ground: rehearsal on 15 November, pilot stream on 16 November. The measure of success is not flawless play. The agent may hit a lamp post, but it has to free itself within about ten seconds and carry on, and it must never hold an input that the picture no longer justifies.

This file is the current plan. It replaces the two handoff notes, which now sit in `archive/`. Measurements and decisions are logged in `docs/LOG.md`, task cards live in `docs/tasks/`, and every finished task leaves a report in `docs/reports/`.

## How the agent is built

Three layers share the work. The reflexes are a local loop at 30 Hz without any language model: it reads the minimap from the picture and sets steering, throttle and brake. Skills are small behaviours built on the reflexes, such as following the GPS route, getting unstuck, walking to a blip, entering a vehicle or shooting with aim assist. The head is a strong model that is asked only on events (a new objective, a failed mission, a menu, being lost) and picks the skill. It runs through the local Codex CLI, where one call takes about seven seconds today, so nothing that has to happen within a second may depend on it. A commentator process later reads what the head and the reflexes are doing and turns it into speech for the stream.

The picture comes from Remote Play over a wired connection, and the inputs go back the same way through the bridge in `remoteplay/`. A capture card arrives on 11 November. It feeds OBS, and it replaces Remote Play as the agent's eyes only if a measurement shows a clear gain.

Every run is recorded. The bridge writes video, frame times and controller states, and the pilot adds one log line per tick with what it read and what it commanded. From 23 November a stronger machine is available, and these recordings, including every moment where Kerim had to take over, are the material for training a model of our own.

## Where things stand on the evening of 10 November

The bridge works. Over the wired connection, with the game in performance mode, the time from an input to the changed picture is 120 to 156 ms at 60 fps, stable from sample to sample, and the stream is almost free of damaged frames. Over Wi-Fi it was 600 to 1160 ms with roughly a third of the frames damaged. The bridge repeats the whole input state several times a second, so a lost release cannot leave a button held.

The pilot is a package with a gate. It reads the minimap in about 1 ms: map class, route colour, the route as a path of points from 11 pixels outward, and the player arrow, with no false route and every route found on the labelled crops. It reads the distance to the destination and the turn arrow that the game prints on the vehicle map, and takes the car's speed in metres per second from that distance, because the map zooms with speed and its motion says nothing about how fast the car is. The driver aims at the route close to the arrow, plans its speed before a bend, bridges damaged frames briefly, backs out when it is stuck and gives up after repeated failures. In a simulator with a zooming map, a late and faulty distance readout and a range of unknown cars it reaches every goal within 5 m of the route. A runtime connects bridge, reader and driver under fixed safety rules, records every run and replays recordings offline. A second reader returns the German help, objective and banner texts of the screen, and a detector turns changes of the HUD, the map, the route and those texts into events.

The conductor, the head and the first skills exist and have played live. On the night of 10 November the pilot walked the character around for four minutes on its own: 26.5 ticks a second, every input accepted, ten plans from the Codex head. It stood still for more than a third of that time, because every answer of the head takes 7 to 12 s and the next one was only asked for when the plan had run out. The reader also reports the coloured blips of the map, and two skills walk to one and turn the camera to one; they have not been tried live.

The car has still not been driven by the pilot, and the speed estimate is still only measured on Wi-Fi recordings. Nothing of the stream setup beyond the overlay page exists.

## Work packages

Phase 1 is driving, and its building is done: P1 closed two gaps on the path that sends inputs to the console, P2 packaged the reader and added the motion check, P3 and P4 built the first driver, the simulator and the runtime, P6 stopped the driver cancelling its own steering, P8 moved it onto the route path, P9 gave it a real speed. What remains are the two live sessions together with Kerim: first he drives a route himself over the cable while the pilot runs in shadow mode and only logs what it would do, which is also the first clean recording to judge the readers and the speed on; then the pilot drives to a waypoint on an empty road at 4 m/s.

Phase 2, 11 to 13 November, is the head and the remaining skills. Reading the screen text and detecting events is done (P7). P10 builds the conductor that runs a whole session, asks the Codex CLI in the background on events and carries its answer out with small skills: following the route, waiting, pressing a button, walking, looking, shooting with aim assist. After that come a notebook of lessons the head reads, walking to a blip instead of walking blind, and retrying after a failure.

The second wave runs since the night of 10 November, seven cards in parallel and two more later that night, each a module of its own that the reviewer wires in: P13 keeps the character moving while the head thinks, asks the head ahead of time over a Codex process that stays up, and turns the skills into a registry; P14 detects vehicles and people in the frame; P15 reads health, armour and which screen the game shows; P16 gets into the nearest vehicle; P17 drives along the road without a route; P18 fights; P19 sets a waypoint on the pause map. Two more were added the same night: P20 builds the commentator's core, with the platform, the voice and the character left as settings, and P21 gets the pilot past the screens that wait for a button, such as the retry after a failed mission. Still to be written, because they need footage that does not exist yet or build on these: the wanted level and getting away from the police, the wasted and busted screens, and the loop that starts a mission, retries it after a failure and goes on to the next one.

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

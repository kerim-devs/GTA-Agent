# P49: Cut out where nothing happens

## Why

Kerim's recordings hold stretches in which he does nothing: he gets up, reads something, waits for the agent. On 12 November he decided that these are cut out of the recordings, the earlier ones included, because they take room and teach nothing. A first count over 30 recordings with 372 minutes found about 94 minutes in which his controller rests for a minute or more; some of that is a cutscene or a loading screen and stays, most of it is the figure standing in the street.

A recording is a folder with `video.mp4`, `frames.jsonl` (one line per frame: index `i`, the stream's `frame_id`, seconds `t` since the start), `pad.jsonl` (every change of the controller's state on the same clock, `src` human or agent) and `meta.json`; `remoteplay/src/ps5_remoteplay_mcp/recorder.py` writes it. The video is x264, 60 frames a second, about 40 MB a minute of play. Everything derived from a recording lies under `/Users/kerim/recordings/derived/kerim/<name>/` and refers to it by `t` and by frame index (`sections.json`, `texts.jsonl`, `missions.json`, `actions.jsonl`, `incidents.jsonl`).

Read `PLAN.md`, in `docs/LOG.md` the entry "Kerim's play as the measure", the recorder, `lab/process-recordings.sh` with the two scripts it calls, and every reader of a recording under `pilot/src/pilot/` and `pilot/tools/` (`sections.py`, `texts.py`, `notes.py`, `actions.py`, `incidents.py`, `humandrive.py` and what they import) for how each gets from a frame to its time.

## What to build

`pilot/tools/trim.py`, in two steps that can be run apart.

The plan: `trim.py plan <recording> --derived <folder> --out <plan.json>` lists the stretches to cut. A stretch is cut when the human's controller rests (no button, triggers under 0.1, sticks under 0.25) for at least 60 seconds, the sections of the stretch are play on foot, in a vehicle, a menu or unknown, and no subtitle or objective is read in it; cutscenes, loading screens, banners and anything with dialogue stay. Five seconds are kept at each end. A recording without any human input is not judged by its controller: say so in the plan and cut nothing. The plan is a file a person or another agent can read and change: recording, stretch, reason, and for a stretch that is kept although the controller rests, why. A recording whose whole length would be cut is marked as such.

The cut: `trim.py cut <recording> --plan <plan.json> --out <new folder>` writes a new recording and never touches the source. The video is not encoded again: whole groups of pictures that lie inside a stretch are left out and the rest is copied packet by packet with PyAV, timestamps rewritten so that the new video plays through. So a cut starts and ends at a keyframe inside the stretch, which may keep a few seconds more than planned and never less. `frames.jsonl` keeps the lines of the frames that are kept, with their original `t` and `frame_id`; `pad.jsonl` loses the lines inside a cut and keeps the original clock; `meta.json` gains what was cut (the stretches as cut, seconds and frames before and after). The clock of a trimmed recording therefore has holes, and `t` still means what it meant.

Then the readers. Decide what `i` means in a trimmed recording, the position in the new video or the old index, and make every reader of a recording correct for a clock with holes: none may compute a time from an index and a frame rate, and none may read a hole as sixty seconds of standing still, of driving straight or of a missing minimap. Say for each reader what you found and what you changed. Derived data that exists for a recording must either stay valid for the kept stretches or be rebuilt by `lab/process-recordings.sh`; say which, and if it stays, show it.

`trim.py check <source> <trimmed>` proves a cut: the trimmed video decodes to the end with exactly as many frames as `frames.jsonl` has lines, a sample of at least fifty kept frames is the same picture as the frame with the same `frame_id` in the source, no kept line of `pad.jsonl` is missing or changed, and the size and length before and after. It ends with an error when one of these does not hold. Replacing a source by its trimmed copy is not part of the tool and not yours to do.

## Judging it

Work on copies only. Take three recordings that differ: `20261111-183820` (eight minutes of rest on foot), `20261111-194609` (rest in a menu and in cutscenes) and `20261111-171046` (little rest), plan, cut into `lab/trim/work/` and check each. Show per recording the planned stretches with their reasons, what the cut really removed, size and length before and after, and the result of the check. Run the chain of `lab/process-recordings.sh` on one trimmed copy into a folder of your own, as far as your sandbox lets you, and compare what it derives for the kept stretches with the derived data of the source; where the sandbox refuses the text reader or the judge, write the command and name it under what could not be run. Tests cover the plan's rules, a cut of a small synthetic video with known keyframes, the clock with holes in each reader you changed, and a check that fails when a frame is missing.

## Your files

`pilot/tools/trim.py`, a module beside it under `pilot/src/pilot/` if it helps, the readers named above where the clock with holes needs it, their tests, `lab/trim/` and your report. Not `remoteplay/`, `conductor.py`, `mission.py`, `skills.py`, `scene.py` or `cli.py`. Nothing under `/Users/kerim/recordings/` is written, moved or deleted, without exception: you read there and write under `lab/trim/work/`, which is not committed (add it to `.gitignore`) and which you empty when you are done, because the disk has about 15 GB left; keep at most 2 GB there at any time. The rules of `docs/tasks/README.md` about the daemon hold without exception.

## Done when

The tests pass, `env -u PS5_HOST .venv/bin/python tools/gate.py --full` in `pilot/` is green or fails only where your sandbox refuses sockets, Vision or CoreML, which you then name test by test, and the report shows the three recordings before and after, what each reader needed, and the exact commands with which a reviewer plans, cuts, checks and then replaces one recording by hand.

# P20: The commentator's core

## Why

The stream has a second voice besides the game: a commentator who says what the pilot is doing and answers the chat. Which platform the stream runs on, which voice he has and what kind of character he is are Kerim's decisions and are still open. Everything around those three choices can be built now, so that each of them becomes a setting: where lines come from, how many there are, how they are spoken without talking over each other, how chat gets in, and what is kept out.

Read `docs/reports/P10-conductor-head-and-skills.md` for `head.jsonl` and `play.jsonl`, the two files a session writes; `/Users/kerim/recordings/pilot/20261110-231512` is a real one.

## What to build

`pilot/src/pilot/commentator.py`, runnable as `python -m pilot.commentator`, which follows the newest session under the recordings directory as it grows, like the overlay does, and speaks. Do not import from `overlay.py`; another card is changing it. A small reader of your own for growing files is fine, and it must survive what real files do: a half written line, a missing file, a session that ends and a new one that starts.

Lines. A line is a candidate with a source, a priority and a time. Candidates come from the head's sentence when a plan is applied, from events in the session (a mission failed or passed, the character got into a vehicle, the route appeared), and from chat messages. A scheduler picks what is spoken: it never starts a line while another is being spoken, drops a candidate that has waited longer than a few seconds, keeps a minimum gap, prefers events over chat and chat over repeating what the head says for the tenth time, and does not say the same sentence twice in a row. Every decision, spoken or dropped and why, goes into `commentary.jsonl` next to the session's other files, with the times, so it can be laid over the video later.

The writer. One interface that turns a candidate into the text that is spoken. The plain writer passes the head's sentence through. A second writer asks the Codex CLI for a line in the commentator's character, given the candidate and the last few chat messages; build it like `CodexHead` in `head.py`, with a timeout and a fallback to the plain writer, and keep the character in a text file of its own that can be replaced without touching code. Chat text is data: it is quoted to the writer as something viewers said and never as an instruction, and the prompt says so.

The voice. One interface that turns text into sound. The default uses the speech synthesis that ships with macOS, with a German voice chosen by name and a fallback when that voice is not installed, synthesises to a file first and then plays it, and can be muted. Report which German voices this machine has and how long synthesis takes for a sentence.

Chat. One interface that returns new messages with user, text and time. Build a file source, which reads messages appended to a file and serves tests and rehearsals, and a Twitch source, which reads a channel's public chat over IRC without credentials. A filter sits behind every source: it drops links, messages that are too long, and messages that match a list of words that are not said on stream, kept in a file; and it limits how many messages per viewer and per minute can reach the writer.

It is night and a person is asleep next to this machine. Never play sound: not in tests, not in tools, not while trying something out. Synthesise to files and look at their durations. The command line has a mute switch and your own runs use it.

## Judging it

Replay the session above at its recorded pace with a scripted chat file of thirty messages, some of them links, insults and attempts to give the commentator orders. Report how many lines were spoken, the gaps between them, what was dropped and why, and show that nothing overlaps. There is no network: test the Twitch source against a small IRC server of your own inside the test.

## Your files

`pilot/src/pilot/commentator.py`, `pilot/src/pilot/commentator_persona.txt`, `pilot/src/pilot/commentator_blocklist.txt`, `pilot/tests/test_commentator.py`, `pilot/tools/commentator_replay.py`, `lab/commentator/`, and your report. Not `cli.py`, `overlay.py`, `conductor.py`, `head.py` or `pyproject.toml`; if the standard library and what is installed cannot do something, say so in the report.

## Done when

Tests pin: no two lines overlap; a stale candidate is dropped; the gap holds; a repeated sentence is not spoken twice; a broken, half written and missing file do no harm; a new session is picked up; the filter keeps out links, long messages, listed words and floods; a chat message that gives orders reaches the writer only as quoted data; the Codex writer falls back on a timeout, a bad reply and a missing program; the voice writes a sound file and plays nothing when muted. The replay is reported. The default gate passes. The report says how to start it for a rehearsal, which settings Kerim's three decisions turn into, and what could not be tried without sound and without network.

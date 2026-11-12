# P11: The overlay for the stream

## Why

The stream is interesting when viewers can see what the agent is thinking. The conductor already writes that down: `head.jsonl` has every question to the head and every answer with a German sentence for the audience, `play.jsonl` has every tick with the skill that runs, the map reading and the speed. Nothing shows it. OBS can lay a web page over the game picture as a browser source; this card builds that page and the small local server behind it. Read `docs/reports/P10-conductor-head-and-skills.md` for the two log files; their fields are the contract you build on.

## What to build

`pilot overlay` as a new subcommand: a server on `127.0.0.1` (port as an option, default 9396) that serves one page and a stream of updates. It watches a root directory of sessions (default: the play recordings directory of `conductor.py`), follows the newest session's `head.jsonl` and `play.jsonl` as they grow, and switches by itself when a new session starts. It reads only; it never touches the bridge and never writes into a session.

The page, for a 1920x1080 browser source with a transparent background:

- what the agent says: the sentence of the last applied decision, large enough to read on a compressed stream, and a quiet "thinking" state while a request is waiting for its answer
- what it is doing: the skill that runs, in plain German words rather than identifiers, and its plan when there is more than one step
- what the game asked for: the objective and help text of the last request, when there is one
- how it is going: speed in km/h and the remaining distance when the map prints one, and a small sign when a person has taken the controller or the run is in shadow mode

Nothing may come from the network: no CDN, no web font, no framework to download. Plain HTML, CSS and JavaScript shipped inside the package. Colours, type sizes and panel positions are variables at the top of the stylesheet, because the look will be decided later by Kerim and must be easy to change; build a restrained default with dark translucent panels, high contrast and no decoration. Text that is too long is shortened, never allowed to overflow its panel. All visible words are German.

A demo mode that plays a finished session back in real time (`pilot overlay --demo <session dir>`), so the page can be designed and checked without a console.

The server must survive what real files do: a line that is half written, a file that does not exist yet, a session that ends, a new one that starts, a malformed line, a browser that reconnects. None of these may stop it or show an error on the stream; a broken line is skipped.

## Your files

`pilot/src/pilot/overlay.py`, the page's files in a directory inside the package, the subcommand in `cli.py`, `pilot/pyproject.toml` if the page's files need to be declared as package data, tests, and your report. Nothing else. No new dependency unless the standard library and what is installed truly cannot do it; say why if you add one.

There is no browser in your sandbox. Test the server and the update stream with the HTTP client that is installed, test the tailing against files you grow, truncate and swap in the test, and keep the page's script simple enough to be read and checked by eye. For the demo, a session can be produced offline with `tools/conductor_replay.py` on `/Users/kerim/Documents/ChatGPT/gta/recordings/20261110-093238` (read-only for you).

## Done when

Tests show that a growing log reaches a connected client within a second, that a half-written and a malformed line do no harm, that a new session is picked up, that the demo plays a session at its recorded pace, and that the server binds to localhost only. The page works from the package without any network. The gate passes. The report says how to add the page to OBS, what each panel shows from which field, what you could not check without a browser, and which variables change the look.

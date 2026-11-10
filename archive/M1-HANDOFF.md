# GTA Agent Handoff

The PS5 runs GTA. The M1 runs the Remote Play daemon, the game viewer, Codex, the controller loop and OBS. The M5 can leave the setup after the cutover. This folder contains a local Git clone in `remoteplay/` with the profile save and combined button/stick fixes through `de06f7a`. The earlier PS5 pairing and input tests ran on the M5. Pairing, sustained control and streaming still need verification on the M1.

## Bring up the M1

Open Terminal in this folder on the M1. Install `uv` if it is missing and connect the M1 and PS5 to the same local network. Check the current PS5 IP under **Einstellungen → Netzwerk → Verbindungsstatus**. The last known address was `192.168.178.40`.

```bash
cd remoteplay
uv sync --locked --python 3.12
export PS5_HOST=192.168.178.40  # Replace if the PS5 has a different address.
export PS5_CONFIG_DIR="$HOME/.config/ps5-remoteplay-mcp"
.venv/bin/ps5rp setup
```

Complete Sony sign-in on the M1. On the PS5, open **Einstellungen → System → Remote Play → Gerät verknüpfen**. Enter the eight-digit code in the M1 setup window. Allow local network access if macOS prompts. Pair the DualSense with the M1 and check that manual control takes priority before giving the agent control.

Once the M1 install is ready, close the old PS5 chat and any PS5 viewer on the M5, then run `/private/tmp/gta-ps5-mcp-check-venv/bin/ps5rp stop` there to release the Remote Play session. On the M1, from the same terminal and working directory:

```bash
.venv/bin/ps5rp status
.venv/bin/ps5rp view
```

Start GTA V in Story Mode and verify that the viewer shows the current mission. If the console is asleep, wake it with the controller first. Check `session_up: True` and fresh frames before testing agent input.

Sign in to Codex on the M1. If the Codex CLI is installed, run the following from `remoteplay/`, then restart Codex. In desktop settings the equivalent is a STDIO MCP server named `gta-ps5` using the same executable path and environment variables. [OpenAI MCP setup](https://learn.chatgpt.com/docs/extend/mcp#configure-with-the-cli)

```bash
codex mcp add gta-ps5 --env "PS5_HOST=$PS5_HOST" \
  --env "PS5_CONFIG_DIR=$PS5_CONFIG_DIR" -- "$PWD/.venv/bin/ps5-remoteplay-mcp"
```

Open the folder containing this file as a Codex project. Start with: “Lies M1-HANDOFF.md, prüfe den MCP-Status und nimm einen Screenshot. Erkenne die aktuelle Mission und den nächsten sichtbaren Schritt. Dann baue den Recorder für Bild und Controller-Eingaben und teste ihn mit mir.”

The SSH handoff carries source code and this brief. Sony and Codex accounts, pairing material, and stream keys are set up on the M1.

## Work toward the first stream

On November 9–11, verify the M1 connection, video and DualSense takeover. Build a small local recorder on the existing bridge. Record received frame IDs and timestamps alongside applied controller states on the same monotonic clock. Add a clear start and stop and keep recording off the input path. The recorder and training data are still pending. Demonstrate the current mission for about two minutes and capture an example of getting unstuck when it comes up.

On November 12–14, test short autonomous stretches in different mission situations. Read the current objective and use the yellow minimap route when present. At arrival or on mission transition, read the HUD again and pick up the next objective. Sidewalks, shortcuts, bumps and police chases are part of the show. Measure progress, recovery, route resumption and how often Kerim needs to take over. Build fast local steering and trigger control from the freshest game frames. Use the agent for decisions such as continuing, recovering, reorienting, retrying a failed checkpoint, switching character when prompted, or evading police and resuming the objective. Release held inputs if frames stop or the human takes over. Evaluate Jev on recordings in parallel only if the core loop is working.

On November 15, rehearse with OBS locally for at least ten minutes using the M1 viewer and game audio. Check input takeover, dropped frames, and reconnect behavior. Check YouTube, Twitch and X separately before the public stream and measure each platform's viewer delay. The viewer delay can help align commentary later. Driving still needs the local feedback loop.

On November 16, aim for a GTA V Story Mode pilot with manual takeover available. On November 19, verify GTA VI's video, controls, prompts and minimap on the PS5 before letting the agent drive. Carry over the controller bridge and recovery behavior and adapt the HUD interpretation to the new game. Live AI commentators can follow after the gameplay pilot. [Rockstar release timing](https://support.rockstargames.com/articles/29jV3Cv2cCgvwM1XgtMO5o/grand-theft-auto-vi-regional-pre-load-and-release-times-on-playstation-5-and-xbox-series-x-or-s)

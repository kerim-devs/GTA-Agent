# Log

Measurements and decisions, newest last. A number that was not measured is marked as an estimate.

## 2026-11-10

Wi-Fi, morning. Round trip to the console 54 ms on average, 12 to 150 corrupt frame notices per minute, about a third of the frames visibly damaged, 15 gaps longer than a second in 11.6 minutes. Input to picture, measured with "look behind" in a standing car: 596 to 1162 ms on press, 431 to 603 ms on release.

Minimap readers. The labelling and implementation run finished after the handoff note was written. On the held-out sheets (48 tiles, 11 with a route) all three readers report no false route and find all 11 routes. `impl_trace`: near bearing median error 5.1 degrees, all within 45 degrees, minimap class right on 94 percent, about 1 ms per crop. Against Kerim's steering on the recordings the sign of the read bearing agrees in 85 percent of the 47 moments of strong steering. Details in `lab/minimap/RESULTS.md`.

Codex as the head. Three calls of `codex exec` with one 720p frame each and low reasoning effort took 6.5 to 7.2 s. A text-only call took 6.6 s and a rejected request returned after 3.9 s, so about 4 s are start-up of the CLI and about 3 s the model. It read driving, on foot and the presence of a route correctly on all three frames, and missed that the third frame was a tinted special scene without a HUD. A call used up to about 26,000 tokens.

Wired connection, afternoon. PS5 and Mac both on the router by cable, the PS5 kept its address 192.168.178.40. Round trip 1.5 ms. Input to picture, measured on foot by nudging the camera with the right stick and timing the first changed frame: 210 to 254 ms at 30 fps (12 clean samples) and 193 to 233 ms at 60 fps (8 samples, median 208 ms). The onset is sharp: the picture stays at noise level and then jumps within one frame. No corrupt frame notice in three minutes at 30 fps, four in the first minute at 60 fps. The bridge now runs at 60 fps.

Graphics mode. GTA V ran in "Wiedergabetreue" (fidelity, 30 fps). The setting sits under Einstellungen, Anzeige, Grafikmodus; a new value shows in italics and is applied only when the pause menu is left, pressing cross on it reverts it. Switched to "Leistung" (performance, 60 fps) through the bridge. Input to picture afterwards, same camera method at 60 fps stream: 120 to 156 ms, median 135 ms (10 samples). Ten corrupt frame notices in 17 minutes.

Decisions. The agent's eyes stay on Remote Play over the cable until the capture card has been measured. The head runs through the Codex CLI and is asked only on events. With the game in performance mode the target of 150 ms input to picture is met; the driver's delay setting should start at 0.14 s, not at the 0.21 s the P3 card was written with.

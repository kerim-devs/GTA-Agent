"""Render the P60 evidence report from the frozen measurement artifacts."""

import json
from collections import Counter

from measure import HERE, ROOT


def pct(value):
    return f"{100 * value:.2f}%"


def main():
    metrics = json.loads((HERE / "metrics.json").read_text())
    text = [
        "P60 is blocked, not complete. The recorded death-to-seat error is repaired and covered by offline regressions. The new roadside questions remain laboratory-only: the best whole-frame 8B wording reaches 90.44% carriageway-versus-rest accuracy but falsely calls 20 of 101 carriageway frames safe (19.80%, against a 5% limit). The full test gate also has two unrelated failures because PyAV is absent and installation is outside this card. No console action was taken.",
        "The corpus is in `lab/where/frames.json`, `vehicles.json`, `labels.json` and the numbered JPEG contact sheets. It contains 360 reviewed foot candidates, of which 251 are usable: 101 carriageway, 43 roadside, 77 open ground/yard and 30 inside. The other 109 are explicitly excluded. The requested roughly 300 usable foot examples were not reached. `label-review.json` records 56 corrected codes from a second visual check, including wrongly labelled roadway frames, cutscenes and obscured supporting surfaces. Asphalt gutters on the road side of a raised kerb count as carriageway; raised kerbs and sidewalks count as roadside. The review happened after exploratory measurements, so these are development labels, not blinded validation. Ten 12 November Kerim section manifests and three current pilot sessions supply daylight, night, town, country, interiors, first-person and several third-person camera views. The first-person hillside samples are open ground. Source recording paths, capture times and exact video frame indices are retained. Samples are clustered within recordings, not an independent held-out population. The current labels.json is authoritative for scoring; raw answer logs retain their original label-at-run for provenance.",
        "The vehicle corpus contains 216 reviewed detector boxes from the existing P57 fresh-detection pool, with 171 usable labels: 89 driving, 49 stopped traffic/occupied, and 33 visibly parked candidates. Forty-five ambiguous boxes are excluded. Review compared the source frame with frames 0.75 seconds before and after. The 33 parked labels do not prove an invisible driver's seat empty; they are candidate labels, not a certified empty-vehicle positive set. This limitation prevents a parked-empty success claim even when the traffic-to-parked rejection metric passes. The requested roughly 200 fully classifiable vehicle examples were therefore not obtained.",
        "Capture time is resolved through `frames.jsonl` to its `i` index before decoding. In Kerim 20261112-092019, capture time reaches 901.9294 seconds while video media duration is only 873.05 seconds. Seeking directly by media seconds would silently label the wrong images. The original recordings were only read.",
        "`judge.WHERE_QUESTIONS`, `ask_where` and `parse_where` contain the exact measured prompts and strict answer parsing. The existing six-question `JOINT` and asynchronous runtime `Reader` are unchanged. `whole` uses the entire image resized to width 640; foot `crop` uses x=15..85%, y=25..100%; vehicle crops pad the detected box by 80% of its dimensions, at least 8% of the image, and retain a red target rectangle. Foot pairs ask position plus edge; vehicle pairs ask vehicle state plus position. The plain variants use a second, shorter wording. Prompts, replies, conditional token probabilities, capture times and response durations are preserved. Malformed replies count as errors, not correct abstentions.",
        "Both models ran only at the authorized PC endpoint `192.168.0.248:1234`. The 4B run is a smaller-model comparison on that PC, not a Mac fallback test. `judge.py` has configurable ordered servers but no bundled Mac model or configured Mac endpoint. The card permits network only to the PC, so Mac fallback behavior and Mac latency remain unverified. Request timings are wall-clock request durations; measurement streams sometimes ran concurrently, and video decoding time is excluded.",
        "Carriageway results follow. The binary score counts an unknown or malformed answer as incorrect. False-safe means a true carriageway image called roadside, open ground or inside; its denominator is all 101 carriageway images.",
        "| Model / variant | Frames | Binary correct | False-safe | Format errors | Median / p95 seconds |\n|---|---:|---:|---:|---:|---:|",
    ]
    for dataset, variants in metrics.items():
        if "foot" not in dataset:
            continue
        model = dataset.rsplit("-", 1)[-1]
        for variant, qs in variants.items():
            s = qs["where"]
            text.append(
                f"| {model} {variant} | {s['n']} | {pct(s['binary_accuracy'])} | {s['false_safe']}/{s['carriageway_n']} ({pct(s['false_safe_rate'])}) | {s['errors']} | {s['seconds']['p50']:.3f} / {s['seconds']['p95']:.3f} |"
            )
    text += [
        "The short 8B whole-frame wording clears the 90% binary mark by 0.44 percentage points but misses the false-safe limit by 14.80 points. All 20 carriageway mistakes are roadside answers: 13 are in 20261112-111357, including the underpass and highway; five are in 105402, including kerbside gutters; one is in 085011; and one is the onset of walking in the road at 22 seconds in 143714. The corresponding crop reaches 90.04% binary accuracy but still falsely calls 18/101 carriageway images safe (17.82%), missing the safety limit by 12.82 points. The smaller 4B whole/plain variant reaches only 66.14% binary accuracy and 16.83% false-safe, missing the respective marks by 23.86 and 11.83 points. The original wording fails much more severely. Confidence thresholding is not a repair: some wrong roadside answers have probability at least 0.95.",
        "Vehicle results follow. The safety denominator is the 138 traffic/driving labels; overall accuracy includes the weaker parked-candidate labels. Passing this negative metric does not establish a reliable empty-seat detector or safe crossing behavior.",
        "| Model / variant | Boxes | Class correct | Traffic called parked | Format errors | Median / p95 seconds |\n|---|---:|---:|---:|---:|---:|",
    ]
    for dataset, variants in metrics.items():
        if "vehicle" not in dataset:
            continue
        model = dataset.rsplit("-", 1)[-1]
        for variant, qs in variants.items():
            s = qs["vehicle"]
            text.append(
                f"| {model} {variant} | {s['n']} | {pct(s['accuracy'])} | {s['false_parked']}/{s['traffic_driving_n']} ({pct(s['false_parked_rate'])}) | {s['errors']} | {s['seconds']['p50']:.3f} / {s['seconds']['p95']:.3f} |"
            )
    text += [
        "The original 8B crop/single vehicle question passes the negative mark at 5/138, or 3.62%, but its overall three-class accuracy is 46.78%. The smaller 4B model falsely calls 22/138 traffic vehicles parked, 15.94%, missing the limit by 5.94 points. A visible driver, temporal motion relative to the road, lane/stop-line geometry, and a stable vehicle track are more defensible complementary signals than a missing person box. Parked-empty positive labels need an observable empty seat or a continuous exit/entry sequence without another occupant.",
        "Edge results use 40 visually directional labels and 211 unknown labels. Unknown includes off-road positions and genuinely ambiguous edges. It is a separate qualification problem; high accuracy from answering unknown is not evidence of usable steering.",
        "| Model / variant | Frames | All labels correct | Directional labels correct | Format errors | Median / p95 seconds |\n|---|---:|---:|---:|---:|---:|",
    ]
    for dataset, variants in metrics.items():
        for variant, qs in variants.items():
            if "edge" not in qs:
                continue
            s = qs["edge"]
            text.append(
                f"| {dataset.rsplit('-', 1)[-1]} {variant} | {s['n']} | {pct(s['accuracy'])} | {s['directional_correct']}/{s['directional_n']} | {s['errors']} | {s['seconds']['p50']:.3f} / {s['seconds']['p95']:.3f} |"
            )
    text.append(
        "Complete confusion counts follow, with one row per ground-truth class. C/S/O/I mean carriageway/roadside/open/inside; P/T/D mean parked-candidate/traffic/driving. U is model abstention and E is malformed response. Vehicle and edge matrices use their own explicitly named columns."
    )
    for question, columns in (
        ("where", ["carriageway", "roadside", "open", "inside", "unknown", "error"]),
        ("vehicle", ["parked", "traffic", "driving", "unknown", "error"]),
        ("edge", ["left", "right", "unknown", "error"]),
    ):
        text.append(
            f"| {question}: model / variant | Actual | "
            + " | ".join(columns)
            + " |\n|---|---|"
            + "---:|" * len(columns)
        )
        for dataset, variants in metrics.items():
            for variant, qs in variants.items():
                if question not in qs:
                    continue
                for actual, counts in qs[question]["confusion"].items():
                    text.append(
                        f"| {dataset.rsplit('-', 1)[-1]} {variant} | {actual} | "
                        + " | ".join(str(counts.get(c, 0)) for c in columns)
                        + " |"
                    )
    text += [
        "Probability calibration follows for every measured question/variant. Each cell is count / mean declared probability / empirical class accuracy. Empty bins are shown as none. These are conditional probabilities normalized across the offered answer letters, not calibrated confidence in safety.",
        "| Model / variant / question | p < .5 | .5 <= p < .8 | .8 <= p < .95 | p >= .95 |\n|---|---|---|---|---|",
    ]
    for dataset, variants in metrics.items():
        for variant, qs in variants.items():
            for question, s in qs.items():
                cells = []
                for bucket in ("<0.5", "0.5-0.8", "0.8-0.95", ">=0.95"):
                    c = s["calibration"].get(bucket)
                    cells.append(
                        "none"
                        if c is None
                        else f"{c['n']} / {c['mean_probability']:.3f} / {pct(c['accuracy'])}"
                    )
                text.append(
                    f"| {dataset.rsplit('-', 1)[-1]} {variant} {question} | " + " | ".join(cells) + " |"
                )
    text += [
        "No new roadside or parked signal is enabled in the live loop, `foot.py`, or vehicle selection. The positional mark fails and the edge question is unusable. The vehicle rejection mark passes in isolation, but the question measured a particular marked detector box, while the current `Reader.poll(rgb, capture)` receives no detector target or identity. Appending a vehicle answer to the six-question prompt would change the measured question and could apply one car's answer to another. The positive empty-vehicle labels are also insufficient.",
        "The exact integration handoff is to provide a separate timestamped vehicle judgment at `conductor.py`'s existing judge-poll/Observation construction boundary: pass a normalized target box and its detector capture time into a separate asynchronous vehicle request, retain that same box in the returned evidence, and carry it separately from the six-question mode judgment. A corresponding optional `Observation.vehicle_judgment` in `contract.py` would preserve its own capture clock. The consumer must reject future/stale evidence, mismatched tracks and changed boxes before applying the measured crop/single answer. Those conductor/contract edits are outside this card and are left undone. After the road-position and direction marks pass, a separate field with its own age is needed for road evidence as well; do not merge answers with different capture times under a single newer timestamp.",
        "The independent seat repair is active. In 143128 the map is clean `none` from t=21.925, but the judge's accepted mode becomes `vehicle` near t=22.524. `player_mode()` preferred that accepted mode over the absent map, so the old one-second confirmation could report success after death. A clean absent map now vetoes seat confirmation even when the judge says vehicle, and clears the continuous proof. A clean none-mode, fresh death/banner answer, fresh contradictory mode, or wasted/busted HUD also clears it. Stale banners do not veto new proof. Existing accepted vehicle mode with a visible flat map remains supported; requiring a tilted map everywhere was not necessary to repair the demonstrated error. Terminal reasons now name the missing roadside eye and final known road position; successful confirmation explicitly says seated.",
    ]
    death = json.loads((HERE / "death-replay.json").read_text())["ticks"]
    text.append(
        f"`death_replay.py` replays {len(death)} recorded seat-window ticks with original minimap readings and original timestamped judge answers. The pre-change implementation reports done on {sum(r['before']['status'] == 'done' for r in death)} ticks; the corrected implementation reports done on {sum(r['after']['status'] == 'done' for r in death)}. The first reconstructed old success is at {next(r['t'] for r in death if r['before']['status'] == 'done'):.3f} seconds, about one play tick from the recorded success. This isolates seat proof after an existing press; it is not a movement or full-controller replay."
    )
    text += [
        "The model cases extend the existing EntryGame simulation with lateral target geometry and stored measured position answers. Wrong answers are sampled from the measured class-specific pool; every fifth delivery is deliberately two seconds old, while other deliveries retain their measured request duration. The new eye is deliberately not consumed, so successes below demonstrate the existing map fallback under that input, not successful new visual control. Full per-tick pads, reasons and observed answer IDs/ages are in `model-cases.json`.",
        "| Model case | Acceptance met | End / seconds | Presses | Final lateral x |\n|---|---|---|---:|---:|",
    ]
    for c in json.loads((HERE / "model-cases.json").read_text()):
        text.append(
            f"| {c['case']} | {c['met']} | {c['result']['status']} / {c['trace'][-1]['t']:.1f} | {len(c['presses'])} | {c['final_x']} |"
        )
    text.append(
        "The timeout case has a 0.2-second budget and ends at x=1.96 inside the lane, with a neutral pad and an explicit still-in-lane reason. It is an unmet requirement, not a passing roadside guarantee. The simulation's road and target geometry is simplified; it cannot establish real collision clearance or the requested live twenty-second parked-empty capability."
    )
    replay = list(map(json.loads, (HERE / "replay-ticks.jsonl").read_text().splitlines()))
    if len(replay) == 870:
        changes = Counter(r["policy_changed_from_HEAD"] for r in replay)
        text.append(
            f"The 143714 entry replay covers all 870 recorded ticks, t=5.950..46.015, with the recorded duration=40. Original detections were not logged, so `replay-detections.json` contains 162 fresh 4 Hz detections recomputed from the original frames. `replay-answers.jsonl` contains real PC judge answers; each becomes available after its measured response duration and retains its capture age. `replay-ticks.jsonl` records the original pad, shadow pad, age and unqualified visual advice for every tick. On identical reconstructed observations, {changes[True]} ticks change pad/status against HEAD and {sum(r['reason_changed_from_HEAD'] for r in replay)} change reason. Differences from the historical recording occur on {sum(r['different_from_recording'] for r in replay)} ticks and cannot be attributed solely to P60 because the detections and timing were reconstructed. The recorded figure does not follow shadow decisions. Since the new eye is not enabled, there is no claim that this replay fixes the pickup pursuit or the ending in the junction."
        )
    else:
        text.append(f"Replay is still incomplete: {len(replay)}/870 ticks. No complete replay claim is made.")
    text += [
        "Validation used `env -u PS5_HOST .venv/bin/python -m pytest -q tests/test_wiring.py tests/test_p60_judge.py tests/test_p60_vehicle_entry.py tests/test_vehicle_entry.py tests/test_judge.py tests/test_foot.py` in pilot: 220 passed in 5.34 seconds (`lab/where/gate-focused.log`). The automated tests use stored responses and synthetic observations; they never ask the server. Ruff check and format checks pass. The original full sandbox gate completed with 3337 passed, 3 skipped, 236 xfailed, six CoreML setup errors and two missing-PyAV failures. The CoreML errors were `tests/test_objects.py::test_real_traffic_and_player_exclusion`, `test_bad_frames_are_rejected[None]`, `[bad1]`, `[bad2]`, `test_reports_below_the_confidence_floor_are_left_out`, and `test_the_real_detector_gives_the_cut_out_figure_beside_the_filtered_list`; the cache under `~/Library/Caches/org.python.python/com.apple.e5rt.e5bundlecache` was denied. With local cache permission, the same Detector successfully produced the offline replay detections.",
        "The two non-sandbox failures are `tests/test_trimming.py::test_packet_copy_b_frames_and_failure_checks` and `tests/test_trimming.py::test_action_video_reader_uses_original_clock_and_resets_motion`, both `ModuleNotFoundError: No module named 'av'`. They predate the changes in this run and are outside the allowed files. `docs/tasks/README.md:11` states: “The Python environment of your package is already installed and there is no network.” P60 grants only the judge endpoint exception, and its allowed write set excludes dependency/environment changes. No dependency was installed and no unrelated test was skipped or changed. A second exact `env -u PS5_HOST .venv/bin/python tools/gate.py --full` run with local CoreML permission is recorded in `lab/where/gate-full.log`. It finished with 3358 passed, 1 skipped, 236 xfailed and three failures: the same two missing-PyAV tests plus `tests/test_wiring.py::test_a_plan_from_the_head_starts_and_stops_every_new_skill[enter_vehicle]`, whose exact status reason still expected the old text. That direct vehicle-entry assertion was updated for the intentional road/eye suffix and passed in the subsequent focused run. The historical full log is retained unchanged; the full suite was not rerun after that test-only correction. The two dependency failures remain unresolved, so the card does not meet its Done condition.",
    ]
    log = (HERE / "gate-full.log").read_text()
    summaries = [
        line
        for line in log.splitlines()
        if " failed," in line or " passed," in line or "gate failed at:" in line
    ]
    text.append(
        "Latest full-gate output: "
        + ("; ".join(summaries[-3:]) if summaries else "still running; no final result yet")
    )
    text += [
        "Reproduction commands from the repository root are `env -u PS5_HOST pilot/.venv/bin/python lab/where/measure.py sample`, `... measure.py vehicles`, `... measure.py freeze`, and `... measure.py run` with `--dataset vehicle`, `--model qwen/qwen3-vl-4b`, or `--variants whole-plain-single crop-plain-single whole-pair` as appropriate. The original 8B run uses the default four whole/crop single/pair variants. Use `... analyze.py` for tables, `... replay.py detect`, `... replay.py judge`, `... replay.py replay`, `... death_replay.py`, and `... model_cases.py` for evidence. Only explicit laboratory run/judge commands contact the authorized PC; replay, model probes and automated tests are offline. Review labels are intentionally frozen, not regenerated by the model.",
        "The first supervised console check, after the blocked qualification/integration work is resolved, should reproduce the night-highway death with a false accepted vehicle mode and confirm that no seat success occurs on a missing map. Then inspect a passing pickup that stops at a junction, a truly empty parked car across the road, and a near-deadline exit from the lane, checking capture age, box identity and the actual ending position. The console remains untested in this task and was never contacted.",
        "The work remains on the existing `feat/pilot-where` branch without Git writes or a PR. The global AGENTS.md requires branch/PR delivery, but this worker's README makes Git metadata read-only and forbids commit/stash/checkout/reset, and P60 permits network only to the judge. That delivery constraint remains explicit rather than being bypassed. No forbidden integration file, recording, daemon, PS5 configuration or secret was changed or accessed. The next owner must resolve the missing dependency, qualify road position and direction, strengthen empty-seat labels, and authorize the scoped integration boundary before treating P60 as complete.",
    ]
    size = sum(p.stat().st_size for p in HERE.rglob("*") if p.is_file())
    text.append(
        f"The laboratory directory currently contains {size:,} bytes, below the 6,000,000-byte limit."
    )
    # Keep table rows adjacent, but separate prose paragraphs.
    output = ""
    for part in text:
        if part.startswith("|") and output.endswith("|\n"):
            output += part + "\n"
        else:
            output += ("\n" if output else "") + part + "\n"
    target = ROOT / "docs/reports/P60-the-eye-for-the-roadside.md"
    target.write_text(output)
    print(target)


if __name__ == "__main__":
    main()

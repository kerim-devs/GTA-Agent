P106 makes the avoider brake substantially earlier for the two daytime crashes, including the lorry while GPS speed is unavailable, but does not meet the complete acceptance criteria. The recordings do not establish a full-L2 stopping deceleration, the remaining distance is below the planning stopping distance in the crash replays, and the additional brake requests include visible faults. This is an uncommitted implementation and measurement result, not a collision-free or console-ready release. The once-only gate runs all functional checks successfully and exits 1 because its default runtime limit is exceeded.

Only `pilot/src/pilot/avoid.py`, the inherited `DriveRoute._around` implementation and its `AROUND_*` constants in `pilot/src/pilot/skills.py`, one intentionally changed assertion in `pilot/tests/test_avoid.py`, the new `test_brake_for_the_lane.py`, its small JSON fixture, and `lab/avoid/p106*` artifacts were written. In this checkout `_around` belongs to the `Skill` base class; this is the same method inherited by `DriveRoute`, not an additional change to the skill system. No console, daemon, credentials, network, Git write, recording write, other worktree or P104 file was used. The task's explicit no-commit rule supersedes the general commit/PR workflow; no commit or PR exists. The unavailable `explorer` was replaced with read-only local file commands.

The detector measurement uses `objects.Detector` with the existing YOLOX-L model, confidence 0.4 and normal `detect_split` player exclusion. `nice -n 15 pilot/.venv/bin/python lab/avoid/p106_detect.py --run` processes recorded pilot frames admitted by `Reader`'s 0.05-second minimum interval, with a three-second pause every 150 frames and between windows. Additional bounded invocations add the 26–40-second truck pass and the start/end of the rainy drive. Exactly 5,301 inferences were reserved and completed; `p106-inferences.txt` prevents exceeding 6,000 on resumption. Median capture spacing is 0.0677 s. Measured inference median/p95/maximum is 0.0572/0.0718/0.1123 s. Replay results are delivered 0.15 s after capture and evaluated on the original pilot tick times, with the GPS value available on that tick and reset on skill-attempt changes. This is a fixed-delay offline replay of candidate frames, not a reconstruction of the unlogged live reader's busy/drop decisions or motion flag. It therefore does not prove the exact live detection sequence. The replay excludes non-follow/coast commands, assumes the unlogged motion flag does not veto a brake, and counts the avoider's requests independently of the route driver's own L2. Stored boxes allow repeating all analysis without further inference. The artifacts occupy about 12 MB; the largest individual file is about 2 MB.

The [approach fixture](../../pilot/tests/fixtures/p106_approaches.json) contains exact boxes, confidence, capture time, frame ID and causal GPS, with no images. [Raw boxes and old/new commands](../../lab/avoid/p106-replay-summary.json), [the replay program](../../lab/avoid/p106_replay.py) and [the detector receipt](../../lab/avoid/p106-detect-log.txt) retain the numerical evidence. The [daytime contact sheet](../../lab/avoid/p106-contacts.jpg) puts the first visible contacts around 273.50 s and 296.50 s, approximately ±0.10 s. These precede the task card's aftermath timestamps. A first L2 after an impact must not be called timely braking.

| Approach | First identifiable box and growth | Remaining time at that box | Old avoider | New avoider | First-brake distance versus stopping distance |
| --- | --- | --- | --- | --- | --- |
| `035459`, silver SUV in the queue, day | 271.9685 s, frame 272246, height 26.58 px; 37.13 px at 272.2031, 48.63 at 272.5040, 58.48 at 273.0213 and 91.80 at 273.3216 | About 1.53 s to visible contact; GPS 22.86 m/s | Pedal 1 and no push while beyond FAR; by 273.0213 the zero-age geometry replay gives steer +0.145 and pedal about 0.775. The final tick replay requests no avoidance L2 before contact; its late sideways motion moves the target outside the corridor | Full L2 and zero R2 at 272.2864, using frame 272255 captured at 272.1201. GPS 22.18 m/s; fitted TTC 0.789 s at capture | Box estimate 31.87 m at capture, about 28.18 m after box age. Constant-speed time-to-impact estimate about 26.92 m. Required 88.56 m at the 3 m/s² planning rate, including 0.25 s response and 1 m gap. Shortfall about 60 m; stopping is not proved |
| `035459`, lorry, day | 294.0582 s, frame 273564, height 43.35 px; 62.14 at 295.0743, 79.75 at 295.5398, 92.62 at 296.0105, 137.36 at 296.2913 | About 2.44 s, initially outside the own-lane corridor; GPS absent at first detection. First own-lane box is 295.0743, about 1.43 s before contact | Starts a small push around 295.29. Geometric urgency arrives near 296.2, but GPS is absent. First replayed applied avoidance brake is 297.0404, after contact; another at 297.7428 | Full L2 at 295.2409, using frame 273625 from 295.0743, GPS 16.75 m/s, TTC 1.942 s. Growth continues to authorize L2 through the subsequent GPS gap | Width-assisted distance 25.20 m at capture, 22.40 m after age; time-to-impact estimate 21.09 m. Required 51.97 m at 3 m/s². Shortfall about 30 m; the lagging GPS value makes the true requirement uncertain |
| `034036`, night pile | Several cars exchange lane position during the weave. The eventual lead car is identifiable in a partial box at 22.7632, frame 205831, height 36.37 px, width 60.17; height 41.17/width 73.74 at 23.4809 and height 35.37/width 88.01 at 24.0134, then height 109.3 at 24.1966. Earlier candidate boxes from about 20.3 cannot be assigned an unbroken identity with confidence | About 1.44 s from the confirmed partial box to the approximately 24.2 s contact | Four brake onsets from 24.3468 onward, after contact. Height alone calls the partially hidden vehicle steady | Full L2 at 22.9458 from width growth, GPS 13.94 m/s and TTC 1.552 s. Further onsets are retained in the raw replay, not merged away | About 16.38 m after box age, versus 36.85 m required at 3 m/s². Insufficient. This does not prove the first appearance of that vehicle earlier in the weave |
| `034630`, red-light queue, night | Central traffic is boxed by 61.9929, frame 229354, height about 31.5 px. The central lead box at 63.3641 is 39.08 px high and 53.17 px wide; by 64.9951 it is 59.7 px high. A closer right-hand car is passed in the same approach, so an exact earliest identity is not established | The car reaches the queue around 65–66 s; identity/contact uncertainty is at least 0.5 s | No avoidance brake in the 59–70 s replay, including the subsequent push | L2 begins at 62.444 for the initial traffic and at 63.545 for the central lead box, GPS 10.71 m/s, TTC 1.005 s; another onset at 65.030 | Central-box distance about 20.27 m after age versus 22.79 m required at 3 m/s². Later GPS jumps to about 22 m/s while contact/occlusion confounds the reading. No reliable stopping margin can be asserted |
| `030418`, alleged garbage-truck obstruction | The 0–40 s replay shows a truck passed on the left at 19–23 s and a cola box truck passed on the right at 26–34 s. The latter has clear boxes throughout the approach; the later 55–183 s sheets show the SUV stuck at the parking ramp | No verified rear-end contact or 23-second garbage-truck hold in the inspected recording | No braking for the 26–34 s side pass | No braking for that side pass; the separate 35.014 onset concerns another vehicle | This named case is unverified, not a successful crash-prevention result. The [annotated side-pass frames](../../lab/avoid/p106-garbage-approach-targets.jpg) document the discrepancy |

The daytime car is therefore first detected only about 35 m of nominal travel before contact, and the daytime lorry about 2.44 s before contact but only 1.43 s before contact once it enters the own-lane corridor. At night the confirmed partial queue-car box leaves about 1.44 s. These are the measured ranges for these scenes, not detector recall estimates. A comparable night-time lorry rear-end approach is not established by these clips, so no night-lorry range is claimed. The [night pile](../../lab/avoid/p106-night-pile-targets.jpg) and [red-light approach](../../lab/avoid/p106-night-light-targets.jpg) show why an ID based only on nearest box can switch vehicles. The daytime lorry disappears from retained central boxes between roughly 296.79 and 297.31 s when the own car pitches up over it; the detector also alternates truck/bus. These cases motivate width growth and a bounded memory of an already justified brake, not unlimited braking on a missing object.

The brake measurement is an observed GPS fall, not a physical full-L2 calibration. [All candidate pulses and samples](../../lab/avoid/p106-braking.json), the [measurement program](../../lab/avoid/p106_braking.py), [day frames](../../lab/avoid/p106-brakes-day.jpg) and [rain frames](../../lab/avoid/p106-brakes-rain.jpg) retain the pulse duration, actual shaped trigger, initial speed and readings 0.5–3 s later. Four visibly usable examples give the following one-second apparent decelerations; they are not averaged over only the trigger-on duration.

| Recording / pulse start | Sent L2 / duration | Initial GPS speed | Apparent fall per second after about 1 s | After about 3 s |
| --- | --- | --- | --- | --- |
| Day `035459` 167.282 s | 0.75–0.805 / 0.378 s | 17.06 m/s | 2.80 m/s² | GPS unavailable |
| Day `035459` 462.977 s | 0.46–0.64 / 0.378 s | 9.90 m/s | 0.04 m/s² | 1.08 m/s² |
| Rain `024817` 51.281 s | 0.45–0.805 / 0.292 s | 16.94 m/s | 3.92 m/s² | 1.91 m/s² |
| Rain `024817` 101.671 s | 0.39–0.48 / 0.285 s | 8.06 m/s | 6.11 m/s² | 2.46 m/s² |

Their one-second median is 3.36 m/s² and range 0.04–6.11. The day pair spans 0.04–2.80 and the rain pair 3.92–6.11, illustrating how GPS lag, quantization, throttle reapplication and route geometry dominate a short pulse measurement. The 38 m/s reading just after the curb/turn at 181 s, the tree strike near 234 s, and the lorry impact near 297 s are not used as proof of powerful brakes. Full L2 while moving straight is not represented by these clean examples. The code's 3 m/s² is an explicit planning assumption near the observed median, not a conservative measured lower bound and not an assertion that full L2 achieves exactly 3 m/s². A controlled full-L2 calibration remains necessary. Even optimistic replay timing cannot turn the displayed shortfalls into positive stopping margins at that rate.

The implementation passes `gps_speed` into the avoider and adds an explicit brake request to `Around`. A median fit of inverse box size over at most 0.6 s provides TTC after at least three boxes and 0.15 s of separation; width replaces height when the box is conspicuously flattened by occlusion. This estimator is independent of the truck/bus size label. There is no FAR restriction on the brake calculation. With known speed the law compares estimated distance with relative closing speed squared over twice the planning deceleration, plus detection age, 0.25 s response allowance and a 1 m gap. A steady or retreating lead vehicle produces no collision brake. Unknown, invalid or nonfinite speed uses the growth TTC threshold of 3 s. An immediately close first box can brake before growth is available, but a distant first box cannot distinguish a moving vehicle from a stationary one, so it waits for the short growth observation. This is a remaining delay against the card's strongest “at once” interpretation.

The original wider P96 steering corridor and chosen passing side remain. The braking corridor is narrower at its centre; its outer part requires convergence toward the centre, reducing brakes for cars moving away in the neighbouring lane. Full L2 suppresses R2 and remains outside the route driver's pulse limiter. It releases below 2 m/s or on explicit stillness, and the pedal stays released close enough to wait without creeping. The P101 bypass still commits to its free side at low speed. A previously justified brake survives a lost box only until its original capture is 0.6 s old; a stale or future observation never authorizes it. This retains steering while slowing, but does not demonstrate a measured safe passing speed or a completed live pass. Relative TTC, camera/bumper offset, assumed class heights and the 800-pixel focal scale remain approximate; height loss, turning vehicles, camera pitch, road slope and track swaps can over- or under-estimate distance and closing speed. The daytime queue's fitted TTC of 0.789 s versus about 1.38 s of actual remaining time at that capture is one measured underestimate.

The cost is material. Counts below are transitions from no avoidance L2 to avoidance L2 on the original follow/coast ticks; even brief repeated pulses are counted separately. They are requests from frozen recordings, not the driver's total recorded brakes. The stated full windows are retained, including their real traffic and collisions, rather than relabelled as empty roads after inspecting the output.

| Replay window | Seconds | Before pulses / minute | After pulses / minute |
| --- | --- | --- | --- |
| `035459` 250–266 s | 16 | 1 / 3.75 | 4 / 15.00 |
| `040426` 91–168 s | 77 | 3 / 2.34 | 13 / 10.13 |
| `024817` 13–104.7 s, three contiguous batches | 91.7 | 3 / 1.96 | 21 / 13.74 |
| `005357` 400–520 s | 120 | 2 / 1.00 | 15 / 7.50 |

The clearly open own-lane freeway interval 420–475 s has zero onsets both before and after, despite adjacent traffic and the recurring false person box on the pickup. That is 55 seconds, not proof of a fleet-wide zero-fault rate. The entire 400–520 s interval is not traffic-free: the pickup rapidly approaches several vehicles and a lorry. Visual review identifies seven plainly inappropriate after-onsets and nine more whose collision path or detection identity is not established; those nine are conservatively counted as faults for acceptance. Thus the conservative cost is 16 fault/unproved onsets in 304.7 s, or 3.15/minute. Twelve of those start while the old avoider is not asking for a brake. This is below the requested “does not brake without a reason” standard. Their frames and every other after-onset are named below; a vehicle in another lane or beside a bend is counted as a fault rather than excused by its box.

`nice -n 15 pilot/.venv/bin/python -m pytest -q pilot/tests/test_brake_for_the_lane.py pilot/tests/test_avoid.py pilot/tests/test_player_driving.py pilot/tests/test_drive_queue.py pilot/tests/test_round_what_stands.py` reports `107 passed in 4.22s`. The new suite covers both recorded daytime approaches, absent/invalid speed, partial occlusion, a steady lead vehicle, adjacent parked/oncoming vehicles, stale/future/repeated detections, low-speed release, bounded occlusion memory and untouched manoeuvre pads. A small delayed-motion test stops before an obstacle at both 22 and 34 m/s when it is visible far enough ahead. Its explicit 3 m/s² dynamics and final passive drag are a model check, not a game measurement. A separate recorded-queue assertion preserves the negative stopping margin; it prevents calling earlier L2 a proven stop. `p106_red.py` temporarily loads HEAD contents using `git show`, runs the new suite and restores both owned files byte for byte. [The baseline receipt](../../lab/avoid/p106-before-tests.txt) is `14 failed, 10 passed`: both recorded early-brake tests, the recorded GPS-gap and wholly unknown-speed tests, both far-obstacle stopping cases, the recorded negative-margin check, all four invalid/unknown-speed cases, the width-growth case, waiting without creep and bounded occlusion memory fail before the change. P96/P101 tests are otherwise unchanged. The one changed avoider test formerly required a closer box to leave less throttle than a farther one and called only the close one urgent; both boxes have the same short TTC, so it now requires zero pedal and full brake at both distances while preserving the larger close steering push.

The whole gate was run exactly once as `cd pilot && nice -n 15 .venv/bin/python tools/gate.py`. Its [receipt](../../lab/avoid/p106-gate.txt) ends with `3852 passed, 1 skipped, 1376 deselected, 1 xfailed in 148.57s (0:02:28)`, `gate passed in 149.13s (default)`, then `default gate exceeded 90 seconds`. The process exit is 1. Ruff and format checks pass, and the intermittent silent-server test does not fail in this run. The runtime-limit failure is left intact and the gate is not repeated.

The next console trips must be judged on fresh evidence, not these counterfactual pads. For comparable daytime, night and rain town routes, count video-confirmed collision-followed entries into `recovery-reverse` or `bypass-reverse` within three seconds of contact, per kilometre of trustworthy forward distance. Integrate time in every `bypass-*` and `recovery-*` state from `result.driver_state`, and report seconds and seconds/km. Keep the denominator's GPS gaps and route recalculations visible instead of treating them as travel. Count `around_pedal` transitions to -1 per minute on visually labelled traffic-free stretches, separately from route-driver L2; inspect `result.pad`, `sent_pad` and the frames where attribution is ambiguous. Targets are zero rear-end-triggered recoveries for these approaches, zero obstacle-induced bypass/recovery time after a contact, and zero unreasoned avoidance brake pulses on clear stretches. A comparative claim needs at least three matched town trips and several minutes of labelled clear driving, with their durations and kilometres reported; these are proposed acceptance denominators, not accomplished runs. Full-L2 deceleration, real stopping margins, lane discrimination at bends, suppressed brakes with the actual motion flag, and safe passing under changed steering remain unproved. The garbage-truck example and a comparable night-lorry approach need a verified recording reference before their requested measurements can be completed.

Every after-onset is listed below, including repeats of an old request, so no newly introduced pulse is omitted. Times are command-tick times; frame IDs identify the earlier detector frame shown in the linked sheets. “Old active” means the old avoider requests L2 on that same tick, not that onset times match. “Observed traffic” names a visible reason; it does not prove that full L2 was necessary or that a counterfactual pass would succeed. “Unproved” is counted as a fault in the conservative acceptance total.

Recording `035459`, batch `same-clean`: [frames 1](../../lab/avoid/p106-same-clean-brakes-1.jpg).

| Onset s | Detector frame | Old active | Visual assessment |
| --- | --- | --- | --- |
| 259.474 | 271495 | no | observed traffic: Black car crossing the intersection |
| 259.641 | 271507 | yes | observed traffic: Black car crossing the intersection |
| 260.893 | 271582 | no | unproved: Small vehicle box after the intersection turn; collision path unproved |
| 263.477 | 271733 | no | unproved: Small car-labelled box at the palm tree; identity and brake attribution unproved |

Recording `040426`, batch `day-clean`: [frames 1](../../lab/avoid/p106-day-clean-brakes-1.jpg), [frames 2](../../lab/avoid/p106-day-clean-brakes-2.jpg).

| Onset s | Detector frame | Old active | Visual assessment |
| --- | --- | --- | --- |
| 109.817 | 296449 | no | observed traffic: Closing car ahead or crossing the junction |
| 110.767 | 296504 | no | observed traffic: Closing lorry ahead |
| 111.470 | 296549 | no | observed traffic: Closing car ahead or crossing the junction |
| 112.687 | 296621 | no | observed traffic: Closing car ahead or crossing the junction |
| 115.072 | 296765 | no | fault: Oncoming vehicle left of the own lane |
| 129.454 | 297622 | yes | fault: Duplicate box on the own white car after the impact |
| 129.637 | 297633 | yes | fault: Duplicate own-car box, a second onset in the same incident |
| 136.078 | 298020 | no | observed traffic: Closing lorry ahead |
| 136.327 | 298033 | no | observed traffic: Closing lorry ahead |
| 137.461 | 298103 | no | unproved: Small vehicle beyond the adjacent lorry; target association unproved |
| 143.752 | 298477 | no | observed traffic: Closing car ahead or crossing the junction |
| 145.851 | 298604 | yes | fault: Lorry left beside the right-hand bend after the intended path turns away |
| 166.841 | 299863 | no | unproved: Vehicle beyond the junction while the own car turns onto the pavement |

Recording `024817`, batch `rain-start`: [frames 1](../../lab/avoid/p106-rain-start-brakes-1.jpg).

| Onset s | Detector frame | Old active | Visual assessment |
| --- | --- | --- | --- |
| 16.237 | 17845 | no | observed traffic: Queue ahead |
| 16.671 | 17876 | no | observed traffic: Queue ahead |
| 17.389 | 17919 | no | observed traffic: Queue ahead |
| 31.218 | 18746 | no | observed traffic: Car crossing the intersection |
| 31.470 | 18763 | no | observed traffic: Car crossing the intersection |

Recording `024817`, batch `rain-clean`: [frames 1](../../lab/avoid/p106-rain-clean-brakes-1.jpg), [frames 2](../../lab/avoid/p106-rain-clean-brakes-2.jpg).

| Onset s | Detector frame | Old active | Visual assessment |
| --- | --- | --- | --- |
| 41.929 | 19390 | no | observed traffic: Closing car ahead or crossing the junction |
| 47.166 | 19703 | no | fault: White car in the adjacent right lane |
| 48.734 | 19797 | no | observed traffic: Closing car ahead or crossing the junction |
| 51.938 | 19990 | no | observed traffic: Closing car ahead or crossing the junction |
| 53.191 | 20065 | no | observed traffic: Closing car ahead or crossing the junction |
| 60.465 | 20501 | no | unproved: Central traffic at the junction; lane ownership unproved |
| 60.931 | 20527 | no | unproved: Same junction traffic, repeated onset; lane ownership unproved |
| 61.265 | 20548 | no | unproved: Same junction traffic, repeated onset; lane ownership unproved |
| 61.498 | 20562 | no | unproved: Same junction traffic, repeated onset; lane ownership unproved |
| 63.884 | 20705 | no | observed traffic: Closing car ahead or crossing the junction |
| 67.252 | 20907 | no | unproved: Vehicle right beside the current track; the retained threat may already be clear |
| 79.183 | 21623 | no | observed traffic: Closing car ahead or crossing the junction |
| 81.301 | 21749 | no | observed traffic: Closing car ahead or crossing the junction |
| 83.669 | 21892 | yes | observed traffic: Closing car ahead or crossing the junction |

Recording `024817`, batch `rain-end`: [frames 1](../../lab/avoid/p106-rain-end-brakes-1.jpg).

| Onset s | Detector frame | Old active | Visual assessment |
| --- | --- | --- | --- |
| 92.578 | 22423 | yes | fault: Oversized false vehicle box over the road/own car |
| 97.299 | 22709 | no | fault: Oversized false vehicle box over the road/own car |

Recording `005357`, batch `freeway-clean`: [frames 1](../../lab/avoid/p106-freeway-clean-brakes-1.jpg), [frames 2](../../lab/avoid/p106-freeway-clean-brakes-2.jpg).

| Onset s | Detector frame | Old active | Visual assessment |
| --- | --- | --- | --- |
| 416.382 | 277266 | no | observed traffic: Closing vehicle ahead on the freeway |
| 417.165 | 277312 | no | observed traffic: Closing vehicle ahead on the freeway |
| 477.243 | 280913 | no | observed traffic: Closing vehicle ahead on the freeway |
| 479.979 | 281079 | no | observed traffic: Closing vehicle ahead on the freeway |
| 481.714 | 281182 | no | observed traffic: Closing vehicle ahead on the freeway |
| 482.231 | 281214 | no | observed traffic: Closing vehicle ahead on the freeway |
| 482.899 | 281254 | no | observed traffic: Closing vehicle ahead on the freeway |
| 484.214 | 281322 | no | observed traffic: Closing vehicle ahead on the freeway |
| 484.532 | 281342 | no | observed traffic: Closing vehicle ahead on the freeway |
| 484.832 | 281360 | no | observed traffic: Closing vehicle ahead on the freeway |
| 514.778 | 283134 | no | observed traffic: Closing lorry ahead |
| 516.064 | 283209 | no | observed traffic: Closing lorry ahead |
| 518.682 | 283362 | no | observed traffic: Closing lorry ahead |
| 518.934 | 283376 | no | observed traffic: Closing lorry ahead |
| 519.602 | 283419 | no | observed traffic: Closing lorry ahead |

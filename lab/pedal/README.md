# How the car answers to the accelerator

`measure.py` holds the right trigger at given strengths with the wheel straight and reads from the minimap how fast the map moves. It sends what it is asked to, without the profile's shaping.

Measured on 11 November over Remote Play, in a Vapid Radius on level ground, speed in pixels of the minimap crop per second.

| Strength | Held | First motion | Speed at the end |
|---|---|---|---|
| 0.10 | 2 s | none | 0 |
| 0.20 | 2 s | none | 0 |
| 0.30 | 2 s | after 1.85 s | 0.2 |
| 0.33 | 3 s | after 1.41 s | 0.1 |
| 0.36 | 3 s | after 0.51 s | 39 |
| 0.40 | 3 s | after 0.77 s | 49 |
| 0.45 | 2 s | after 0.68 s | 48 |
| 0.60 | 2 s | after 0.38 s | 122 |

The accelerator does nothing below about 0.35. The driver's pedal values under its cruise (0.07 while turning round, 0.18 without a speed reading, 0.22 in a bend) all lay under that: in session 20261111-123334 the car stood still on them, the driver took it for stuck, reversed at full brake and tried again, three times over, until it gave up. The profile now lifts both triggers over 0.35 the way it lifts the right stick over 0.3. The brake was not measured on its own.

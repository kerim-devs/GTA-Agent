"""Run the new behavioural assertions against the unchanged pre-P98 driver."""

import importlib.util

from p98_replay import ROOT, baseline

spec = importlib.util.spec_from_file_location(
    "p98_tests", ROOT / "pilot/tests/test_drive_through.py"
)
tests = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tests)
old, cfg = baseline()
tests.Driver = old
tests.drive_config = lambda _: cfg
cases = [
    (
        "straight heading",
        lambda: tests.test_heading_correction_does_not_brake_a_straight_road(),
    ),
    ("slow exit lock", lambda: tests.test_slow_car_gets_the_lock_for_a_visible_exit()),
]
for road in tests.drive_through_roads():
    cases.append(
        (
            road,
            lambda road=road: (
                tests.test_drive_through_roads_with_the_existing_car_profiles(
                    road, "fast-low-grip" if road == "exit" else "nominal"
                )
            ),
        )
    )
failed = 0
for name, run in cases:
    try:
        run()
    except AssertionError:
        print(f"EXPECTED FAIL before P98: {name}", flush=True)
        failed += 1
    else:
        print(f"UNEXPECTED PASS before P98: {name}", flush=True)
assert failed == len(cases), (failed, len(cases))

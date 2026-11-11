"""Offline tests never depend on an installed native recognition framework."""

import pytest


@pytest.fixture(autouse=True)
def optional_ocr(monkeypatch):
    monkeypatch.setattr("pilot.gps.recognize", lambda crop: None)


def pytest_addoption(parser):
    parser.addoption("--full", action="store_true", help="Include the full delay/scale/car matrix")


LIVE_MAP_MATRICES = (
    "test_live_zoom_wrong_screen_preserves_forward_input_refusals",
    "test_coastal_land_target_and_real_cinematic_return_finish_only_after_map_proof",
    "test_live_zoom_near_and_far_are_distinct_verified_travel",
    "test_live_zoom_mission_with_unreadable_player_finishes_on_observed_proof",
)


def pytest_collection_modifyitems(config, items):
    if config.getoption("--full"):
        return
    selected, wide = [], []
    seen = set()
    for item in items:
        parameters = getattr(getattr(item, "callspec", None), "params", {})
        keep = True
        if item.originalname in LIVE_MAP_MATRICES:
            # They replay real frames through the readers and take seconds a case: one of each by default.
            keep = item.originalname not in seen
            seen.add(item.originalname)
        elif item.originalname == "test_closed_loop_grid":
            keep = parameters["delay"] == 0.21 and parameters["seed"] == 0 and parameters["dead_zone"] == 0.25
        elif item.originalname == "test_unknown_car_ranges":
            keep = (
                parameters["delay"] == 0.3
                and parameters["dead_zone"] == 0.25
                and parameters["scale"] == 2.0
                and parameters["name"] == "right"
            )
        (selected if keep else wide).append(item)
    items[:] = selected
    config.hook.pytest_deselected(items=wide)

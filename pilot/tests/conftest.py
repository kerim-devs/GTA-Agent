"""Offline tests never depend on an installed native recognition framework."""

import pytest


@pytest.fixture(autouse=True)
def optional_ocr(monkeypatch):
    monkeypatch.setattr("pilot.gps.recognize", lambda crop: None)


@pytest.fixture(autouse=True)
def no_ways_remembered():
    from pilot import wayround

    wayround.WAYS.reset()


def pytest_addoption(parser):
    parser.addoption("--full", action="store_true", help="Include the full delay/scale/car matrix")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--full"):
        return
    selected, wide = [], []
    for item in items:
        parameters = getattr(getattr(item, "callspec", None), "params", {})
        keep = True
        if item.originalname == "test_closed_loop_grid":
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

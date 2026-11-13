import pytest

from pilot.cli import drive_config


def test_settings_start_from_the_measured_delay_and_take_overrides():
    config = drive_config(["cruise_throttle=0.4", "max_recoveries=2"])
    assert (config.command_delay, config.cruise_throttle, config.max_recoveries) == (0.14, 0.4, 2)
    # Bold carries the road-speed settings; careful retains the console baseline.
    assert (config.speed_limit, config.slow_speed, config.damage_hold) == (28.0, 3.0, 2.0)
    careful = drive_config(["style=careful"])
    assert (careful.speed_limit, careful.slow_speed, careful.damage_hold) == (22.0, 5.0, 2.0)
    # L2 for speed only in short pulses and only well above walking pace: a held brake ends in reverse.
    assert (config.brake_pulse, config.brake_floor) == (0.35, 7.0)
    assert drive_config(["speed_limit=9"]).speed_limit == 9


@pytest.mark.parametrize("setting", ["cruise=0.4", "cruise_throttle=fast"])
def test_a_wrong_setting_stops_the_run(setting):
    with pytest.raises(SystemExit):
        drive_config([setting])

import pytest

from pilot.cli import drive_config


def test_settings_start_from_the_measured_delay_and_take_overrides():
    config = drive_config(["cruise_throttle=0.4", "max_recoveries=2"])
    assert (config.command_delay, config.cruise_throttle, config.max_recoveries) == (0.14, 0.4, 2)


@pytest.mark.parametrize("setting", ["cruise=0.4", "cruise_throttle=fast"])
def test_a_wrong_setting_stops_the_run(setting):
    with pytest.raises(SystemExit):
        drive_config([setting])

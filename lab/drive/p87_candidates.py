"""Rejected P87 trials, isolated from the installed driver's globals and files."""

import inspect
import textwrap

from pilot.drive import Driver, _target
from steady import geometry


def farther_target(path, radius):
    shape = geometry({"path": path, "arrow": 0})
    if radius < 20 and shape is not None and shape[1] < 15:
        radius = 20
    return _target(path, radius)


def candidate(config, variant):
    if variant == "baseline":
        return Driver(config)
    source = textwrap.dedent(inspect.getsource(Driver.step))
    scope = dict(Driver.step.__globals__)
    if variant in ("continuous", "combined"):
        before = (
            "self.config.steering_bias + (1 - self.config.steering_bias) * abs(target)"
        )
        after = "self.config.steering_bias * min(1.0, abs(adjusted) / 15) + (1 - self.config.steering_bias) * abs(target)"
        if source.count(before) != 1:
            raise ValueError(
                "The production steering law changed; rebase the rejected experiment"
            )
        source = source.replace(before, after)
    if variant in ("farther", "combined"):
        scope["_target"] = farther_target
    if variant not in ("continuous", "combined", "farther"):
        raise ValueError(variant)
    # Only the installed, local Driver source is compiled, never recording data.
    exec(compile(source, __file__, "exec"), scope)  # noqa: S102
    experiment = type("Experiment", (Driver,), {"step": scope["step"]})
    return experiment(config)

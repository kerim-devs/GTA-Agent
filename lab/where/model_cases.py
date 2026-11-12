"""Five offline acceptance probes, including explicit unmet behavior, not console proof."""

import json
import sys
from dataclasses import asdict, replace

from measure import HERE, ROOT

sys.path.insert(0, str(ROOT / "pilot/tests"))
from test_vehicle_entry import EntryGame, run_game
from pilot.contract import Answer, Judgment


class MeasuredGame(EntryGame):
    def __init__(self, *, scenario, eye=True, **kwargs):
        super().__init__(**kwargs)
        self.scenario = scenario
        self.eye = eye
        self.crossed = False
        self.observed = []
        self.labels = json.loads((HERE / "labels.json").read_text())["foot_pages"]
        self.responses = [
            r
            for r in map(json.loads, (HERE / "answers-foot-8b.jsonl").read_text().splitlines())
            if r["variant"] == "whole-plain-single"
        ]

    def observation(self, time):
        if self.scenario == "parked_across":
            self.distance = max(0.3, abs(self.road_x + 12))
        observation = super().observation(time)
        if self.scenario in {"parked_across", "passing_then_waiting"} and observation.objects:
            box = observation.objects[0].box
            target = 0.25 if self.scenario == "parked_across" else min(0.8, 0.2 + time * 0.3)
            shift = (target - 0.5) * 1280
            objects = tuple(
                replace(o, box=(o.box[0] + shift, o.box[1], o.box[2] + shift, o.box[3]))
                for o in observation.objects
            )
            observation = replace(observation, objects=objects)
        sample, delay = None, None
        if self.eye:
            truth = "C" if self.road_x is not None and abs(self.road_x) < 7 else "S"
            samples = [
                r
                for r in self.responses
                if self.labels[str(int(r["id"][1:]) // 24)].split()[int(r["id"][1:]) % 24].startswith(truth)
            ]
            sample = samples[int(time * 4) % len(samples)]
            # Every fifth delivery arrives too late; others retain measured request latency.
            delay = 2.0 if int(time * 4) % 5 == 0 else sample["duration"]
            judgment = Judgment(
                time - delay,
                {k: Answer(**v) for k, v in sample["answers"].items()},
                sample["probabilities"],
                delay,
                "stored",
            )
            observation = replace(observation, judgment=judgment)
        self.observed.append(
            {
                "time": time,
                "x": self.road_x,
                "distance": self.distance,
                "answer_id": None if sample is None else sample["id"],
                "answer": None if sample is None else sample["answers"],
                "age": delay,
            }
        )
        return observation

    def apply(self, time, pad):
        super().apply(time, pad)
        self.crossed |= self.road_x is not None and self.road_x < 0


def main():
    cases = [
        ("passing_then_waiting", dict(distance=3, road_x=12, driver=True), 12),
        ("parked_across", dict(distance=24, road_x=12), 40),
        ("start_lane", dict(distance=2, road_x=0, driver=True), 6),
        ("timeout_lane", dict(distance=2, road_x=0, driver=True), 0.2),
        ("no_judge", dict(distance=2, eye=False), 12),
    ]
    results = []
    for name, kwargs, duration in cases:
        game = MeasuredGame(scenario=name, **kwargs)
        result, game, presses, ticks = run_game(game, duration=duration)
        met = {
            "passing_then_waiting": not presses and not game.seated,
            "parked_across": game.crossed and game.seated,
            "start_lane": abs(game.road_x or 0) >= 7 and not presses,
            "timeout_lane": abs(game.road_x or 0) >= 7,
            "no_judge": game.seated,
        }[name]
        results.append(
            {
                "case": name,
                "met": met,
                "result": asdict(result),
                "presses": presses,
                "seated": game.seated,
                "crossed": game.crossed,
                "final_x": game.road_x,
                "longest_lane_idle": game.longest_lane_idle,
                "tick_count": len(ticks),
                "observations": game.observed,
                "trace": [
                    {
                        "t": t,
                        "pad": asdict(r.pad),
                        "status": r.status,
                        "reason": r.reason,
                    }
                    for t, r in ticks
                ],
            }
        )
        print(
            name,
            "met",
            met,
            "status",
            result.status,
            "presses",
            len(presses),
            "x",
            game.road_x,
            "seated",
            game.seated,
        )
    (HERE / "model-cases.json").write_text(json.dumps(results, separators=(",", ":")) + "\n")


if __name__ == "__main__":
    main()

"""Offline combat model. Its physics are assumptions, not a GTA benchmark."""

import argparse
import json
import math
import random
from collections import deque
from pathlib import Path

from pilot.combat import Fight, Melee
from pilot.contract import NEUTRAL_PAD, Blip, Hud, Reading
from pilot.skills import Observation


def simulate(seed, *, pressure=1.0, melee=False, map_lost=False):
    rng = random.Random(seed)
    dt = 1 / 30
    camera = rng.uniform(-math.pi, math.pi)
    enemies = []
    for _ in range(3):
        angle = rng.uniform(-math.pi, math.pi)
        distance = rng.uniform(4, 10) if melee else rng.uniform(12, 42)
        enemies.append({"x": math.sin(angle) * distance, "y": math.cos(angle) * distance, "hp": 12.0})
    skill = Melee({}) if melee else Fight({"cover": "yes"})
    health, last_hit = 1.0, -100.0
    hidden = False
    cover_available = rng.random() < 0.85
    lock = None
    previous = NEUTRAL_PAD
    history = deque()
    recovery_ticks = cover_taps = invalid_attacks = 0
    delayed = ((), health)
    result = None
    for tick in range(902):
        now = tick * dt
        visible = []
        for enemy in enemies:
            if enemy["hp"] <= 0:
                continue
            bearing = math.atan2(enemy["x"], enemy["y"]) - camera
            distance = math.hypot(enemy["x"], enemy["y"])
            visible.append(Blip("red", math.sin(bearing) * distance, math.cos(bearing) * distance))
        history.append((now, tuple(visible), health))
        while history and history[0][0] <= now - 0.14:
            _, blips, seen_health = history.popleft()
            delayed = blips, seen_health
        blips, seen_health = delayed
        corrupt = map_lost or now < 0.14 or rng.random() < 0.07 or 5.0 < now < 5.3
        if corrupt:
            blips = ()
        else:
            blips = tuple(
                Blip("red", b.x + rng.gauss(0, 0.45), b.y + rng.gauss(0, 0.45))
                for b in blips
                if rng.random() >= 0.025
            )
        reading = Reading("flat", "none", None, None, None, corrupt, 0.9, blips=blips)
        result = skill.step(Observation(reading, False, now, hud=Hud(health=seen_health)))
        pad = result.pad
        if result.status != "running":
            assert pad == NEUTRAL_PAD
            break
        front_red = any(abs(math.degrees(math.atan2(b.x, b.y))) <= 12 for b in blips)
        if (corrupt and pad.l2) or ((pad.r2 or "circle" in pad.buttons) and (corrupt or not front_red)):
            invalid_attacks += 1
        if seen_health < 0.3 and not pad.l2 and not pad.r2:
            recovery_ticks += 1
        if "r1" in pad.buttons and "r1" not in previous.buttons:
            hidden = cover_available
            cover_taps += 1
        camera += pad.right[0] * math.radians(180) * dt
        if not pad.l2:
            lock = None
        elif not previous.l2:
            candidates = []
            for index, enemy in enumerate(enemies):
                angle = math.atan2(enemy["x"], enemy["y"]) - camera
                angle = math.atan2(math.sin(angle), math.cos(angle))
                if enemy["hp"] > 0 and abs(angle) < math.radians(25):
                    candidates.append((math.hypot(enemy["x"], enemy["y"]), index))
            lock = min(candidates)[1] if candidates else None
        if lock is not None and enemies[lock]["hp"] > 0:
            if pad.r2:
                enemies[lock]["hp"] -= 34 * dt
            if "circle" in pad.buttons and "circle" not in previous.buttons:
                enemies[lock]["hp"] -= 6
        incoming = sum(enemy["hp"] > 0 for enemy in enemies)
        if incoming and (not hidden or pad.l2) and rng.random() < 0.20:
            health = max(0.0, health - incoming * 0.0025 * pressure)
            last_hit = now
        if health > 0 and now - last_hit > 2 and health < 0.5:
            health = min(0.5, health + 0.15 * dt)
        previous = pad
    assert result is not None and result.status != "running"
    assert now <= (10 if melee else 30) + dt and result.pad == NEUTRAL_PAD
    return {
        "seed": seed,
        "status": result.status,
        "reason": result.reason,
        "seconds": round(now, 3),
        "remaining": sum(enemy["hp"] > 0 for enemy in enemies),
        "cleared": all(enemy["hp"] <= 0 for enemy in enemies),
        "health": round(health, 3),
        "cover_taps": cover_taps,
        "low_health_neutral_ticks": recovery_ticks,
        "invalid_attacks": invalid_attacks,
        "neutral_end": result.pad == NEUTRAL_PAD,
    }


def summarize(runs):
    return {
        "seeds": len(runs),
        "cleared": sum(run["cleared"] for run in runs),
        "clear_rate": sum(run["cleared"] for run in runs) / len(runs),
        "max_seconds": max(run["seconds"] for run in runs),
        "neutral_ends": sum(run["neutral_end"] for run in runs),
        "invalid_attacks": sum(run["invalid_attacks"] for run in runs),
        "reasons": {
            reason: sum(r["reason"] == reason for r in runs) for reason in sorted({r["reason"] for r in runs})
        },
        "runs": runs,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seeds", type=int, default=100)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.seeds < 1:
        parser.error("--seeds must be positive")
    report = {
        "assumptions": {
            "hz": 30,
            "delay_seconds": 0.14,
            "enemies": 3,
            "enemy_hp": 12,
            "gun_damage_per_second": 34,
            "punch_damage": 6,
            "camera_degrees_per_second": 180,
            "lock_cone_degrees": 25,
            "frame_dropout": 0.07,
            "individual_blip_dropout": 0.025,
            "blip_jitter_pixels": 0.45,
            "burst_dropout_seconds": [5, 5.3],
            "hit_probability_per_tick": 0.2,
            "damage_per_enemy_hit": 0.0025,
            "cover_available_probability": 0.85,
            "recovery_delay": 2,
            "recovery_per_second": 0.15,
            "recovery_ceiling": 0.5,
            "warning": "Synthetic model only; damage, lock-on, cover and camera gains are uncalibrated.",
        },
        "fight": summarize([simulate(seed) for seed in range(args.seeds)]),
        "overwhelming_fire": summarize([simulate(seed, pressure=30) for seed in range(args.seeds)]),
        "lost_map": summarize([simulate(seed, map_lost=True) for seed in range(args.seeds)]),
        "melee": summarize([simulate(seed, melee=True) for seed in range(args.seeds)]),
    }
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: {k: v for k, v in value.items() if k != "runs"}
                for key, value in report.items()
                if key != "assumptions"
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

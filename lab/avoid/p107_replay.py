"""Compare HEAD and current avoidance on identical boxes and recorded causal speed."""

import argparse
import gzip
import importlib.util
import json
import math
import subprocess
import sys

from pilot import avoid
from pilot.contract import Command, Detection, Observation, Reading
from pilot.skills import DriveRoute

from p107_measure import EXTRA, HERE, SESSIONS, events, load


def baseline():
    name = 'pilot.p107_baseline'
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
    sys.modules[name] = module
    source = subprocess.check_output(['git', 'show', 'HEAD:pilot/src/pilot/avoid.py'], text=True)
    exec(compile(source, '<P107 baseline>', 'exec'), module.__dict__)
    return module


def threats(avoider):
    result = []
    for t in avoider.things:
        if not t.braking:
            continue
        contact = t.contact()
        result.append({'box': t.box, 'kind': t.kind, 'seen': t.seen, 'distance': t.distance(),
                       'ttc': contact if contact is not None and math.isfinite(contact) else None,
                       'closing': (t.distance() + avoid.CAMERA) / contact if contact else None})
    return result


def replay(session, latency):
    _, ticks = load(session)
    if session == EXTRA:
        ticks = [t for t in ticks if 75.5 <= t['t'] <= 86.5]
    boxes = list(map(json.loads, (HERE / f'p107-{session}-boxes.jsonl').open()))
    old = baseline()
    before, after = old.Avoider(), DriveRoute({})
    cursor, attempt = -1, None
    with gzip.open(HERE / f'p107-{session}-replay.jsonl.gz', 'wt') as output:
        for tick in ticks:
            now = tick['t']
            while cursor + 1 < len(boxes) and boxes[cursor + 1]['t'] + latency <= now:
                cursor += 1
            current_attempt = (tick.get('skill') or {}).get('attempt_id')
            if current_attempt != attempt:
                before, after = old.Avoider(), DriveRoute({})
                attempt = current_attempt
            row = boxes[cursor] if cursor >= 0 else None
            speed = tick['reading']['gps_speed']
            active = tick['active'] and row is not None
            objects = tuple(Detection(**obj) for obj in row['objects']) if row else ()
            first = before.step(objects, row['t'], now, speed=speed) if active else old.CLEAR
            # The log has the resulting stick, not the unmodified driver command. Remove
            # the baseline replay's push; clipping and different live detections are unobservable.
            steer = max(-1, min(1, tick['result']['pad']['left'][0] - first.steer))
            if active:
                reading = Reading(**tick['reading'])
                obs = Observation(reading, True, now, objects=objects, objects_time=row['t'])
                pad = after._around(Command(steer, 1, 0, 'follow'), obs)
                second = pad.l2
            else:
                second = 0
            tick['recorded'] = tick['active'] and tick['result'].get('around_pedal') == -1
            tick['before'] = bool(active and first.brake and (speed is None or speed > 2))
            tick['after'] = bool(active and second)
            tick['after_strength'] = second
            detail = {'t': now, 'dt': tick['dt'], 'active': bool(active), 'speed': speed,
                      'recorded': tick['recorded'], 'before': tick['before'], 'after': tick['after'],
                      'after_strength': second, 'steer': steer,
                      'frame_id': row['frame_id'] if row else None,
                      'threats': threats(before) if tick['before'] else [],
                      'after_threats': threats(after.avoider) if tick['after'] else []}
            output.write(json.dumps(detail, separators=(',', ':'), allow_nan=False) + '\n')
    result = {'follow': sum(t['dt'] for t in ticks if t['active']), 'latency': latency,
              'events': {v: events(ticks, v) for v in ('recorded', 'before', 'after')},
              'after_equivalent_full_l2_seconds': sum(t['dt'] * t['after_strength'] for t in ticks)}
    result['seconds'] = {v: sum(e['seconds'] for e in ev) for v, ev in result['events'].items()}
    print(session, 'onsets', {v: len(ev) for v, ev in result['events'].items()},
          'seconds', {v: round(t, 3) for v, t in result['seconds'].items()},
          'percent', {v: round(100 * t / result['follow'], 3) for v, t in result['seconds'].items()})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', nargs='+', choices=(*SESSIONS, EXTRA))
    parser.add_argument('--latency', type=float, default=.15)
    args = parser.parse_args()
    target = HERE / 'p107-replay.json'
    summary = json.loads(target.read_text()) if target.exists() else {}
    summary.update({s: replay(s, args.latency) for s in args.only or SESSIONS})
    target.write_text(json.dumps(summary, indent=2) + '\n')

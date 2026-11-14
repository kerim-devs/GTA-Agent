"""Frozen P106/P107 and working-tree replay, with no inference or console access."""

import argparse
import gzip
import importlib.util
import json
import math
import subprocess
import sys

from pilot import avoid, skills
from pilot.contract import Command, Detection, Observation, Reading

from p107_measure import HERE, SESSIONS, load

BASE = '6124b3d'


def version(ref, label):
    modules = []
    for file in ('avoid', 'skills'):
        name = f'pilot.p109_{label}_{file}'
        module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
        sys.modules[name] = module
        source = subprocess.check_output(['git', 'show', f'{ref}:pilot/src/pilot/{file}.py'], text=True)
        if file == 'skills':
            source = source.replace('from .avoid import', f'from .p109_{label}_avoid import')
        exec(compile(source, f'<{label} {file}>', 'exec'), module.__dict__)
        modules.append(module)
    return modules


P106, P106_SKILLS = version('af48de4^', 'p106')
P107, P107_SKILLS = version(BASE, 'p107')
VERSIONS = {'p106': (P106, P106_SKILLS), 'p107': (P107, P107_SKILLS), 'p109': (avoid, skills)}


def finite(value):
    return value if value is None or math.isfinite(value) else 'inf'


def instrument(module, skill_module):
    class Traced(module.Avoider):
        def step(self, *args, **kwargs):
            self.lane = kwargs.get('lane', 0)
            self.result = super().step(*args, **kwargs)
            return self.result

    skill = skill_module.DriveRoute({})
    skill.avoider = Traced()
    return skill


def reason(thing, module, speed, age, lane):
    inside = thing.in_path() if module is P106 else thing.in_path(lane)
    contact, distance = thing.contact(), thing.distance()
    if getattr(thing, 'held', False) and thing.braking:
        return 'held full brake'
    if getattr(thing, 'queuing', False) and thing.braking:
        return 'close queue'
    if not inside:
        return 'outside brake lane'
    if speed is None:
        return 'unknown speed TTC' if thing.braking else 'unknown speed no imminent TTC'
    if speed <= 2:
        return 'near rest'
    if contact is None:
        return 'first close box' if thing.braking else 'short history'
    if contact == math.inf:
        return 'steady/shrinking fit'
    raw = (distance + module.CAMERA) / contact
    closing = min(speed, raw)
    if module is not P106:
        if thing.kind in module.VEHICLES and speed > 5 and raw > module.ONCOMING * speed and thing.lateral[-1][1] > .25:
            return 'oncoming veto'
        if speed > 5 and closing < .7 * speed and contact - age > module.FOLLOW_TTC and distance > module.BRAKE_GAP:
            return 'slower lead coast'
    stopping = closing * (module.BRAKE_DELAY + age) + closing ** 2 / (2 * module.DECELERATION) + module.BRAKE_GAP
    return ('full brake' if thing.braking == 1 else 'scaled brake') if distance <= stopping else 'outside stopping distance'


def details(skill, module, speed, now):
    tracker = skill.avoider
    output = []
    for thing in tracker.things:
        offset, wide, near = module._seen(thing)
        if abs(offset) > .2 and not thing.braking:
            continue
        contact = thing.contact()
        inside = thing.in_path() if module is P106 else thing.in_path(tracker.lane)
        output.append({'box': thing.box, 'kind': thing.kind, 'seen': thing.seen,
                       'matched': thing in tracker.matched.values(), 'in_path': inside,
                       'lateral': thing.lateral[-1][1], 'near': near, 'distance': thing.distance(),
                       'ttc': finite(contact), 'closing': finite((thing.distance() + module.CAMERA) / contact) if contact else None,
                       'brake': thing.braking, 'reason': reason(thing, module, speed, now - thing.seen, tracker.lane)})
    return {'l2': float(tracker.result.brake), 'pedal': tracker.result.pedal,
            'lane': tracker.lane, 'tracks': output}


def replay(session, clip=False, latency=.15):
    _, ticks = load(session)
    if clip:
        ticks = [t for t in ticks if 93 <= t['t'] <= 96.5]
    boxes = list(map(json.loads, (HERE / f'p{109 if clip else 107}-{session}-boxes.jsonl').open()))
    cursor, attempt = -1, None
    controllers = {}
    summary = {'follow': sum(t['dt'] for t in ticks if t['active']), 'versions': {}}
    for name in VERSIONS:
        summary['versions'][name] = {'seconds': 0., 'equivalent_full_l2_seconds': 0., 'onsets': 0, 'events': []}
    active_before = {k: False for k in VERSIONS}
    trace, fixture_rows, detections = [], [], {}
    for tick in ticks:
        now = tick['t']
        while cursor + 1 < len(boxes) and boxes[cursor + 1]['t'] + latency <= now:
            cursor += 1
        current = (tick.get('skill') or {}).get('attempt_id')
        if current != attempt or not controllers:
            controllers = {k: instrument(*v) for k, v in VERSIONS.items()}
            push = P106.Avoider()
            attempt = current
        if cursor < 0 or not tick['active']:
            active_before = {k: False for k in VERSIONS}
            continue
        row = boxes[cursor]
        speed = tick['reading']['gps_speed']
        objects = tuple(Detection(**obj) for obj in row['objects'])
        first = push.step(objects, row['t'], now, speed=speed)
        steer = max(-1, min(1, tick['result']['pad']['left'][0] - first.steer))
        obs = Observation(Reading(**tick['reading']), True, now, objects=objects, objects_time=row['t'])
        detail = {'t': now, 'dt': tick['dt'], 'speed': speed, 'frame_id': row['frame_id'],
                  'capture': row['t'], 'recorded_around_pedal': tick['result'].get('around_pedal'),
                  'recorded_l2': tick['result']['pad']['l2'], 'recorded_r2': tick['result']['pad']['r2']}
        for name, controller in controllers.items():
            pad = controller._around(Command(steer, 1, 0, 'follow'), obs)
            stats = summary['versions'][name]
            if pad.l2:
                stats['seconds'] += tick['dt']
                stats['equivalent_full_l2_seconds'] += tick['dt'] * pad.l2
                if not active_before[name]:
                    stats['onsets'] += 1
                    stats['events'].append({'start': now, 'end': now, 'seconds': 0.})
                event = stats['events'][-1]
                event['end'] = now + tick['dt']
                event['seconds'] += tick['dt']
            active_before[name] = bool(pad.l2)
            if clip:
                detail[name] = {**details(controller, VERSIONS[name][0], speed, now), 'l2': pad.l2, 'r2': pad.r2}
            else:
                detail[name] = {'l2': pad.l2, 'r2': pad.r2}
        trace.append(detail)
        if clip:
            detections[str(row['frame_id'])] = {'t': row['t'], 'objects': row['objects']}
            fixture_rows.append({'now': now, 'frame_id': row['frame_id'], 'steer': steer,
                                 'reading': {k: tick['reading'][k] for k in
                                             ('bearing', 'far_bearing', 'arrow', 'confidence', 'corrupt', 'gps_speed')}})
    for stats in summary['versions'].values():
        stats['percent'] = 100 * stats['seconds'] / summary['follow']
    if clip:
        suffix = '' if latency == .05 else f'-{latency:.2f}'
        (HERE / f'p109-night-trace{suffix}.jsonl').write_text(''.join(json.dumps(r, separators=(',', ':'), allow_nan=False) + '\n' for r in trace))
        fixture = {'session': session, 'latency': latency, 'detections': detections, 'rows': fixture_rows}
        if latency == .05:
            (HERE.parents[1] / 'pilot/tests/fixtures/p109_brake_held.json').write_text(json.dumps(fixture, separators=(',', ':')) + '\n')
    else:
        with gzip.open(HERE / f'p109-{session}-replay.jsonl.gz', 'wt') as output:
            for row in trace:
                output.write(json.dumps(row, separators=(',', ':')) + '\n')
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--trips', action='store_true')
    parser.add_argument('--latency', type=float)
    args = parser.parse_args()
    sessions = SESSIONS if args.trips else ('073626',)
    latency = args.latency if args.latency is not None else .15 if args.trips else .05
    result = {s: replay(s, not args.trips, latency) for s in sessions}
    suffix = '' if latency == .05 else f'-{latency:.2f}'
    target = HERE / ('p109-trip-replay.json' if args.trips else f'p109-night-replay{suffix}.json')
    target.write_text(json.dumps(result, indent=2) + '\n')
    for s, summary in result.items():
        print(s, summary['follow'], {k: {f: round(v[f], 6) for f in ('seconds', 'percent', 'onsets')} for k, v in summary['versions'].items()})

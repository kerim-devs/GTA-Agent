"""Old/new avoider on identical stored boxes, without loading the detector."""

import importlib.util
import json
import subprocess
import sys
import argparse
from dataclasses import asdict
from pathlib import Path

from pilot import avoid
from pilot.contract import Detection

HERE = Path(__file__).resolve().parent
ROOT = Path('/Users/kerim/recordings/pilot')


def baseline():
    name = 'pilot.p106_old_avoid'
    module = importlib.util.module_from_spec(importlib.util.spec_from_loader(name, loader=None))
    sys.modules[name] = module
    source = subprocess.check_output(['git', 'show', 'HEAD:pilot/src/pilot/avoid.py'], text=True)
    exec(compile(source, '<P106 baseline avoid.py>', 'exec'), module.__dict__)
    return module


def replay(name, old, latency):
    from p106_detect import WINDOWS
    rows = list(map(json.loads, (HERE / f'p106-{name}.jsonl').open()))
    session, start, end = WINDOWS[name]
    source = ROOT / ('20261114-' + session)
    frames = {f['frame_id']: f for f in map(json.loads, (source / 'frames.jsonl').open())}
    ticks = [r for r in map(json.loads, (source / 'play.jsonl').open())
             if r.get('frame_id') in frames and start <= frames[r['frame_id']]['t'] < end]
    before, after = old.Avoider(), avoid.Avoider()
    events = {'before': [], 'after': []}
    previous = {'before': False, 'after': False}
    samples = []
    cursor, attempt = -1, None
    for tick in ticks:
        now = frames[tick['frame_id']]['t']
        while cursor + 1 < len(rows) and rows[cursor + 1]['t'] + latency <= now:
            cursor += 1
        if cursor < 0:
            continue
        row = rows[cursor]
        current_attempt = (tick.get('skill') or {}).get('attempt_id')
        if current_attempt != attempt:
            before, after = old.Avoider(), avoid.Avoider()
            attempt = current_attempt
        objects = tuple(Detection(**obj) for obj in row['objects'])
        speed = tick['reading']['gps_speed']
        active = (tick.get('result') or {}).get('driver_state') in ('follow', 'coast')
        first = before.step(objects, row['t'], now) if active else old.CLEAR
        second = after.step(objects, row['t'], now, speed=speed) if active else avoid.CLEAR
        brakes = {
            'before': bool(active and first.urgent and speed is not None and speed > 5),
            'after': bool(active and second.brake and (speed is None or speed > 2)),
        }
        details = [
            {'kind': t.kind, 'box': t.box, 'distance': t.distance(),
             'contact': t.contact() if t.contact() != float('inf') else None,
             'braking': t.braking, 'seen': t.seen}
            for t in after.things if t.braking
        ]
        sample = {'t': row['t'], 'now': now, 'frame_id': row['frame_id'], 'speed': speed,
                  'before': asdict(first), 'after': asdict(second), 'brakes': brakes,
                  'threats': details}
        samples.append(sample)
        for version in events:
            if brakes[version] and not previous[version]:
                events[version].append({'t': now, 'frame_t': row['t'], 'frame_id': row['frame_id'],
                                        'speed': speed, 'other_brakes': brakes['after' if version == 'before' else 'before'],
                                        'threats': details if version == 'after' else []})
            previous[version] = brakes[version]
    summary = {'seconds': end - start, 'frames': len(rows), 'latency': latency,
               'events': events,
               'per_minute': {version: len(e) * 60 / (end - start) for version, e in events.items()}}
    (HERE / f'p106-{name}-replay.jsonl').write_text(''.join(json.dumps(s, separators=(',', ':')) + '\n' for s in samples))
    print(name, 'frames', len(rows), 'seconds', round(summary['seconds'], 2),
          'onsets', {v: len(e) for v, e in events.items()},
          'per minute', {v: round(r, 3) for v, r in summary['per_minute'].items()})
    print('after onsets', [(round(e['t'], 3), e['frame_id']) for e in events['after']])
    return summary


if __name__ == '__main__':
    from p106_detect import WINDOWS
    parser = argparse.ArgumentParser()
    parser.add_argument('--latency', type=float, default=.15)
    args = parser.parse_args()
    old = baseline()
    summaries = {name: replay(name, old, args.latency) for name in WINDOWS}
    (HERE / 'p106-replay-summary.json').write_text(json.dumps(summaries, indent=2) + '\n')

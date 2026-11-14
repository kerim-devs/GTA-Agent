"""Bounded, resumable offline measurement; never connects to the console."""

import argparse
import bisect
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

import cv2

HERE = Path(__file__).resolve().parent
ROOT = Path('/Users/kerim/recordings/pilot')
SESSIONS = ('051709', '052018', '052402', '052653', '053655', '054734', '055349', '055729')
EXTRA = '061133'


def load(session):
    source = ROOT / ('20261114-' + session)
    frames = {f['frame_id']: f for f in map(json.loads, (source / 'frames.jsonl').open())}
    ticks = list(map(json.loads, (source / 'play.jsonl').open()))
    for index, tick in enumerate(ticks):
        tick['dt'] = max(0, ticks[index + 1]['t'] - tick['t']) if index + 1 < len(ticks) else 0
        tick['frame'] = frames.get(tick.get('frame_id'))
        tick['active'] = tick.get('result', {}).get('driver_state') in ('follow', 'coast')
    return source, ticks


def events(ticks, key):
    result, event = [], None
    for tick in ticks:
        if tick.get(key, False):
            if event is None:
                event = {'start': tick['t'], 'seconds': 0, 'speed': tick['reading']['gps_speed']}
                result.append(event)
            event['seconds'] += tick['dt']
            event['end'] = tick['t'] + tick['dt']
        else:
            event = None
    times = [t['t'] for t in ticks]
    for index, event in enumerate(result):
        event['id'] = index + 1
        # A descriptive GPS fall through one second after release, not brake causality.
        samples = [t['reading']['gps_speed'] for t in ticks[bisect.bisect_left(times, event['start']):
                   bisect.bisect_right(times, event['end'] + 1)]]
        speeds = [v for v in samples if v is not None]
        event['lost'] = max(0, event['speed'] - min(speeds)) if speeds and event['speed'] is not None else None
    return result


def plan(session, quiet_interval=.27):
    source, ticks = load(session)
    if session == EXTRA:
        ticks = [t for t in ticks if 75.5 <= t['t'] <= 86.5]
    for tick in ticks:
        tick['recorded'] = tick['active'] and tick.get('result', {}).get('around_pedal') == -1
    onsets = events(ticks, 'recorded')
    windows = [(e['start'] - 1.5, e['end'] + 1) for e in onsets]
    selected, last = [], -1e6
    for tick in ticks:
        f = tick['frame']
        if not f or (not tick['active'] and session != EXTRA):
            continue
        dense = any(a <= f['t'] <= b for a, b in windows)
        interval = .05 if session == EXTRA else .1 if dense else quiet_interval
        if f['t'] - last < interval:
            continue
        last = f['t']
        selected.append((f, tick))
    return source, ticks, onsets, selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--only', nargs='+', choices=(*SESSIONS, EXTRA))
    args = parser.parse_args()
    plans = {s: plan(s) for s in args.only or SESSIONS}
    summary = {s: {'frames': len(p[3]), 'follow': sum(t['dt'] for t in p[1] if t['active']),
                   'events': p[2]} for s, p in plans.items()}
    recorded = HERE / 'p107-recorded.json'
    previous = json.loads(recorded.read_text()) if recorded.exists() else {}
    previous.update(summary)
    recorded.write_text(json.dumps(previous, indent=2) + '\n')
    print({s: {'frames': len(p[3]), 'onsets': len(p[2]),
                'seconds': round(sum(e['seconds'] for e in p[2]), 3),
                'follow': round(summary[s]['follow'], 3)} for s, p in plans.items()}, flush=True)
    total = sum(len(p[3]) for p in plans.values())
    print('planned total', total, flush=True)
    if not args.run:
        return
    from pilot.objects import Detector
    if os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise RuntimeError('Use nice -n 15')
    counter = HERE / 'p107-inferences.txt'
    used = int(counter.read_text()) if counter.exists() else 0
    pending = 0
    for s in args.only or SESSIONS:
        target = HERE / f'p107-{s}-boxes.jsonl'
        done = {json.loads(line)['frame_id'] for line in target.open()} if target.exists() else set()
        pending += sum(f['frame_id'] not in done for f, _ in plans[s][3])
    if used + pending > 6000:
        raise RuntimeError(f'{used} used + {pending} pending exceeds 6000')
    detector = Detector()
    for s in args.only or SESSIONS:
        source, _, _, samples = plans[s]
        target = HERE / f'p107-{s}-boxes.jsonl'
        done = {json.loads(line)['frame_id'] for line in target.open()} if target.exists() else set()
        capture = cv2.VideoCapture(str(source / 'video.mp4'))
        at = -1
        with target.open('a') as output:
            for f, tick in samples:
                if f['frame_id'] in done:
                    continue
                if at < 0 or f['i'] - at > 120:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, f['i'])
                else:
                    for _ in range(f['i'] - at - 1):
                        capture.grab()
                ok, pixels = capture.read()
                at = f['i']
                if not ok:
                    raise RuntimeError((s, f))
                used += 1
                counter.write_text(str(used) + '\n')
                begun = time.perf_counter()
                objects, _, vehicle = detector.detect_split(cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB))
                row = {**f, 'objects': [asdict(o) for o in objects],
                       'excluded_vehicle': asdict(vehicle) if vehicle else None,
                       'inference_seconds': round(time.perf_counter() - begun, 4)}
                output.write(json.dumps(row, separators=(',', ':')) + '\n')
                output.flush()
                if used % 100 == 0:
                    print(s, 'total', used, 'pause 3s', flush=True)
                    time.sleep(3)
        capture.release()
        print('finished', s, 'total', used, flush=True)
        time.sleep(3)


if __name__ == '__main__':
    main()

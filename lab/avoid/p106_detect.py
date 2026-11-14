"""Bounded detector replay at the live reader's interval on recorded pilot ticks.

Run once with nice -n 15. Existing output is never overwritten or detected again.
The reservation counter includes an interrupted inference, so retries cannot exceed 6000.
"""

import argparse
import bisect
import json
import os
import time
from dataclasses import asdict
from pathlib import Path

import cv2

from pilot.objects import Detector, Reader

HERE = Path(__file__).resolve().parent
ROOT = Path('/Users/kerim/recordings/pilot')
WINDOWS = {
    'day-queue': ('035459', 266, 275),
    'day-lorry': ('035459', 290, 298),
    'night-pile': ('034036', 18, 28),
    'night-light': ('034630', 59, 70),
    'garbage': ('030418', 0, 26),
    'garbage-approach': ('030418', 26, 40),
    'same-clean': ('035459', 250, 266),
    'day-clean': ('040426', 91, 168),
    'rain-clean': ('024817', 35, 90),
    'rain-start': ('024817', 13, 35),
    'rain-end': ('024817', 90, 104.7),
    'freeway-clean': ('005357', 400, 520),
}


def rows(session, start, end):
    source = ROOT / ('20261114-' + session)
    frames = {f['frame_id']: f for f in map(json.loads, (source / 'frames.jsonl').open())}
    ticks = list(map(json.loads, (source / 'play.jsonl').open()))
    times = [r['t'] for r in ticks]
    selected, last = [], -1e6
    for row in ticks:
        frame = frames.get(row.get('frame_id'))
        if not frame or not start <= frame['t'] < end or frame['t'] - last < .05:
            continue
        last = frame['t']
        # Use the reading that was available when the captured frame was processed.
        selected.append((frame, row))
    return source, selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true')
    parser.add_argument('--only', nargs='+', choices=WINDOWS)
    args = parser.parse_args()
    plans = [(name, *rows(*WINDOWS[name])) for name in (args.only or WINDOWS)]
    print('interval', Reader.__init__.__defaults__[0], 'planned',
          {name: len(samples) for name, _, samples in plans}, flush=True)
    if not args.run:
        return
    if os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise RuntimeError('Must run at nice 15 or lower priority')
    counter = HERE / 'p106-inferences.txt'
    used = int(counter.read_text()) if counter.exists() else 0
    pending = sum(len(samples) for name, _, samples in plans if not (HERE / f'p106-{name}.jsonl').exists())
    if used + pending > 6000:
        raise RuntimeError(f'{used} used + {pending} pending exceeds 6000')
    detector = Detector()
    for name, source, samples in plans:
        target = HERE / f'p106-{name}.jsonl'
        if target.exists():
            print('kept existing', target, flush=True)
            continue
        capture = cv2.VideoCapture(str(source / 'video.mp4'))
        at = -1
        with target.open('x') as output:
            for index, (frame, row) in enumerate(samples):
                if at < 0:
                    capture.set(cv2.CAP_PROP_POS_FRAMES, frame['i'])
                else:
                    for _ in range(frame['i'] - at - 1):
                        capture.grab()
                ok, pixels = capture.read()
                at = frame['i']
                if not ok:
                    raise RuntimeError((name, frame))
                used += 1
                counter.write_text(str(used) + '\n')
                begun = time.perf_counter()
                objects, person, vehicle = detector.detect_split(cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB))
                result = {
                    't': frame['t'], 'i': frame['i'], 'frame_id': frame['frame_id'],
                    'play_t': row['t'], 'speed': row['reading']['gps_speed'],
                    'gps_distance': row['reading']['gps_distance'],
                    'state': (row.get('result') or {}).get('driver_state'),
                    'attempt': (row.get('skill') or {}).get('attempt_id'),
                    'around_pedal': (row.get('result') or {}).get('around_pedal'),
                    'sent_pad': row.get('sent_pad'), 'pad': row.get('result', {}).get('pad'),
                    'objects': [asdict(obj) for obj in objects],
                    'excluded_vehicle': asdict(vehicle) if vehicle else None,
                    'inference_seconds': round(time.perf_counter() - begun, 4),
                }
                output.write(json.dumps(result, separators=(',', ':')) + '\n')
                if (index + 1) % 150 == 0:
                    output.flush()
                    print(name, index + 1, '/', len(samples), 'total', used, 'pause 3s', flush=True)
                    time.sleep(3)
        capture.release()
        print('finished', name, len(samples), 'total', used, flush=True)
        time.sleep(3)


if __name__ == '__main__':
    main()

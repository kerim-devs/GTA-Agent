"""Fill the pre-onset pictures that fell in recovery rather than following, within the same budget."""

import bisect
import json
import os
import time
from dataclasses import asdict

import cv2

from p107_measure import HERE, SESSIONS, load


if __name__ == '__main__':
    if os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise RuntimeError('Use nice -n 15')
    from pilot.objects import Detector

    detector = Detector()
    counter = HERE / 'p107-inferences.txt'
    used = int(counter.read_text())
    events = json.loads((HERE / 'p107-recorded.json').read_text())
    for session in SESSIONS:
        source, ticks = load(session)
        target = HERE / f'p107-{session}-boxes.jsonl'
        rows = list(map(json.loads, target.open()))
        times = sorted(r['t'] for r in rows)
        selected, last = [], -1e6
        for tick in ticks:
            frame = tick['frame']
            if not frame or tick['active'] or frame['t'] - last < .15:
                continue
            if not any(e['start'] - 1.5 <= frame['t'] <= e['start'] for e in events[session]['events']):
                continue
            at = bisect.bisect_left(times, frame['t'])
            if min(abs(times[j] - frame['t']) for j in (at - 1, at) if 0 <= j < len(times)) <= .08:
                continue
            selected.append(frame)
            last = frame['t']
        if used + len(selected) > 6000:
            raise RuntimeError('Frame budget exhausted')
        capture = cv2.VideoCapture(str(source / 'video.mp4'))
        for frame in selected:
            capture.set(cv2.CAP_PROP_POS_FRAMES, frame['i'])
            ok, pixels = capture.read()
            if not ok:
                raise RuntimeError(frame)
            used += 1
            counter.write_text(str(used) + '\n')
            start = time.perf_counter()
            objects, _, vehicle = detector.detect_split(cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB))
            rows.append({**frame, 'objects': [asdict(o) for o in objects],
                         'excluded_vehicle': asdict(vehicle) if vehicle else None,
                         'inference_seconds': time.perf_counter() - start, 'pre_onset': True})
        capture.release()
        target.write_text(''.join(json.dumps(r, separators=(',', ':')) + '\n'
                                  for r in sorted(rows, key=lambda r: r['t'])))
        print(session, 'added', len(selected), 'total inferences', used, flush=True)
        time.sleep(3)

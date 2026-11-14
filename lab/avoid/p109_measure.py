"""Read-only night approach measurement, bounded to 1500 detector frames including the gate."""

import json
import os
import time
from dataclasses import asdict

import cv2

from p107_measure import HERE, load


def main():
    from pilot.objects import Detector

    if os.getpriority(os.PRIO_PROCESS, 0) < 15:
        raise RuntimeError('Use nice -n 15')
    source, ticks = load('073626')
    samples, last = [], -1e6
    for tick in ticks:
        frame = tick['frame']
        if frame and 93 <= frame['t'] <= 96.5 and frame['t'] - last >= .05:
            samples.append(frame)
            last = frame['t']
    target = HERE / 'p109-073626-boxes.jsonl'
    done = {json.loads(line)['frame_id'] for line in target.open()} if target.exists() else set()
    counter = HERE / 'p109-inferences.txt'
    used = int(counter.read_text()) if counter.exists() else 0
    pending = [f for f in samples if f['frame_id'] not in done]
    if used + len(pending) + 12 > 1500:
        raise RuntimeError('Detector budget exceeded (12 gate calls reserved)')
    print('frames', len(samples), 'pending', len(pending), 'gate reserve', 12, flush=True)
    if not pending:
        return
    detector = Detector()
    capture = cv2.VideoCapture(str(source / 'video.mp4'))
    at = -1
    with target.open('a') as output:
        for index, frame in enumerate(pending):
            if at < 0:
                capture.set(cv2.CAP_PROP_POS_FRAMES, frame['i'])
            else:
                for _ in range(frame['i'] - at - 1):
                    capture.grab()
            ok, pixels = capture.read()
            at = frame['i']
            if not ok:
                raise RuntimeError(frame)
            used += 1
            counter.write_text(str(used) + '\n')
            begun = time.perf_counter()
            objects, _, vehicle = detector.detect_split(cv2.cvtColor(pixels, cv2.COLOR_BGR2RGB))
            row = {**frame, 'objects': [asdict(o) for o in objects],
                   'excluded_vehicle': asdict(vehicle) if vehicle else None,
                   'inference_seconds': time.perf_counter() - begun}
            output.write(json.dumps(row, separators=(',', ':')) + '\n')
            output.flush()
            if (index + 1) % 25 == 0:
                print('completed', used, 'pause 3s', flush=True)
                time.sleep(3)
    capture.release()
    print('finished', used, flush=True)


if __name__ == '__main__':
    main()

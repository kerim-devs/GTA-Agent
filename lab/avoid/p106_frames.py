"""Small contact sheets from read-only recordings; no detector or console access."""

import argparse
import bisect
import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path('/Users/kerim/recordings/pilot')
HERE = Path(__file__).resolve().parent


def sheet(session, times, label, boxes=None):
    source = ROOT / ('20261114-' + session)
    frames = [json.loads(line) for line in (source / 'frames.jsonl').open()]
    stamps = [f['t'] for f in frames]
    capture = cv2.VideoCapture(str(source / 'video.mp4'))
    canvas = np.zeros(((len(times) + 2) // 3 * 250, 3 * 448, 3), dtype=np.uint8)
    for n, t in enumerate(times):
        index = min(bisect.bisect_left(stamps, t), len(frames) - 1)
        capture.set(cv2.CAP_PROP_POS_FRAMES, frames[index]['i'])
        ok, frame = capture.read()
        if not ok:
            raise RuntimeError((session, t))
        for obj in (boxes[n] if boxes else []):
            x0, y0, x1, y1 = map(round, obj['box'])
            cv2.rectangle(frame, (x0, y0), (x1, y1), (0, 0, 255), 3)
            cv2.putText(frame, obj['kind'], (x0, y0 - 4), cv2.FONT_HERSHEY_SIMPLEX,
                        .6, (0, 0, 255), 2)
        small = cv2.resize(frame, (448, 224))
        y, x = n // 3 * 250, n % 3 * 448
        canvas[y:y + 224, x:x + 448] = small
        cv2.putText(canvas, f'{session} {stamps[index]:.3f}s #{frames[index]["frame_id"]}',
                    (x + 5, y + 243), cv2.FONT_HERSHEY_SIMPLEX, .43, (255, 255, 255), 1)
    capture.release()
    target = HERE / f'p106-{label}.jpg'
    cv2.imwrite(str(target), canvas, [cv2.IMWRITE_JPEG_QUALITY, 75])
    print(target)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('session')
    parser.add_argument('label')
    parser.add_argument('times', type=float, nargs='+')
    args = parser.parse_args()
    sheet(args.session, args.times, args.label)

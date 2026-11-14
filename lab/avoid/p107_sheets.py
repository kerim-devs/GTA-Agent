"""Small chronological contact sheets of every recorded avoidance onset."""

import argparse
import bisect
import json

import cv2
import numpy as np

from p107_measure import HERE, ROOT, SESSIONS


def sheets(session, pending=False):
    events = (json.loads((HERE / 'p107-pending.json').read_text())[session] if pending else
              json.loads((HERE / 'p107-recorded.json').read_text())[session]['events'])
    source = ROOT / ('20261114-' + session)
    frames = list(map(json.loads, (source / 'frames.jsonl').open()))
    times = [f['t'] for f in frames]
    capture = cv2.VideoCapture(str(source / 'video.mp4'))
    for group in range(0, len(events), 5):
        canvas = np.zeros((5 * 228, 1080, 3), dtype=np.uint8)
        for r, event in enumerate(events[group:group + 5]):
            for c, delta in enumerate((-.4, 0, .7)):
                f = frames[min(len(frames)-1, bisect.bisect_left(times, event['start'] + delta))]
                capture.set(cv2.CAP_PROP_POS_FRAMES, f['i'])
                ok, pixels = capture.read()
                if not ok:
                    raise RuntimeError(f)
                canvas[r*228:r*228+202, c*360:(c+1)*360] = cv2.resize(pixels, (360, 202))
                identity = event['key'] if pending else f"#{event['id']:02}"
                title = f"{session} {identity} {f['t']:.2f}s"
                cv2.putText(canvas, title, (c*360+5, r*228+219), cv2.FONT_HERSHEY_SIMPLEX,
                            .45, (255, 255, 255), 1, cv2.LINE_AA)
        kind = 'pending' if pending else 'sheet'
        target = HERE / f'p107-{session}-{kind}-{group//5+1}.jpg'
        quality = 80
        while True:
            ok, encoded = cv2.imencode('.jpg', canvas, [cv2.IMWRITE_JPEG_QUALITY, quality])
            if len(encoded) < 300000:
                break
            quality -= 5
        target.write_bytes(encoded.tobytes())
        print(target.name, len(encoded))
    capture.release()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--only', nargs='+', choices=SESSIONS)
    parser.add_argument('--pending', action='store_true')
    args = parser.parse_args()
    for session in args.only or SESSIONS:
        sheets(session, args.pending)

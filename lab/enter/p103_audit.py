"""Read-only sparse P103 frames and attempt receipts; run sequentially at nice 15."""
import json
from pathlib import Path

import cv2
import numpy as np

OUT = Path(__file__).parent
BASE = Path('/Users/kerim/recordings/pilot')


def rows(path):
    return [json.loads(line) for line in path.open()]


def main():
    cv2.setNumThreads(1)
    runs = []
    for sid in ('20261114-011429', '20261114-010438', '20261114-004115', '20261114-011017'):
        folder = BASE / sid
        play, frames, head = (rows(folder / name) for name in ('play.jsonl', 'frames.jsonl', 'head.jsonl'))
        index = {r['frame_id']: r['i'] for r in frames}
        video = cv2.VideoCapture(str(folder / 'video.mp4'))
        requests = [r for r in head if r['type'] == 'request']
        origin = requests[0]['t'] - play[0]['t']
        attempts = [r for r in head if r['type'] == 'trip_attempt' and r['name'] == 'enter_vehicle']
        for receipt in attempts:
            raw = [r for r in play if (r.get('skill') or {}).get('attempt_id') == receipt['attempt_id']]
            if not raw:
                continue
            start, end = raw[0]['t'], raw[-1]['t']
            wanted = sid == '20261114-011429'
            wanted |= sid == '20261114-010438' and (end >= 282 or 150 <= end <= 170)
            wanted |= sid == '20261114-004115' and ((start <= 246 and end >= 210) or (start <= 466 and end >= 452))
            wanted |= sid == '20261114-011017' and start <= 52 and end >= 34
            if not wanted:
                continue
            presses, last = [], False
            for row in raw:
                pressed = 'triangle' in (row.get('sent_pad') or {}).get('buttons', [])
                if pressed and not last:
                    presses.append(row['t'])
                last = pressed
            moments = sorted(set([start, start+(end-start)/3, start+2*(end-start)/3, end-0.1, *presses]))
            tiles, samples = [], []
            for t in moments:
                row = min(raw, key=lambda r: abs(r['t']-t))
                i = index[row['frame_id']]
                source = f'video.mp4:{i}'
                if video.isOpened():
                    video.set(cv2.CAP_PROP_POS_FRAMES, i)
                    ok, bgr = video.read()
                else:
                    request = min(requests, key=lambda r: abs(r['t'] - origin - row['t']))
                    source = request['frame_file']
                    t = request['t'] - origin
                    row = min(play, key=lambda r: abs(r['t'] - t))
                    i = index[row['frame_id']]
                    bgr = cv2.imread(str(folder / source))
                    ok = bgr is not None
                if not ok:
                    raise RuntimeError((sid, i))
                samples.append({'source': source, 't': row['t'], 'video_frame': i, 'frame_id': row['frame_id'], 'reading': row['reading']})
                tile = cv2.resize(bgr, (640,360))
                cv2.putText(tile, f"{sid} #{receipt['attempt_id']} {row['t']:.2f}s f{i}", (8,20), 0, .5, (0,255,255), 1)
                tiles.append(tile)
            while len(tiles)%2:
                tiles.append(np.zeros_like(tiles[0]))
            name = f"p103-{sid}-{receipt['attempt_id']}.jpg"
            cv2.imwrite(str(OUT/name), np.vstack([np.hstack(tiles[i:i+2]) for i in range(0,len(tiles),2)]), [cv2.IMWRITE_JPEG_QUALITY,75])
            run = {'session':sid, 'attempt':receipt['attempt_id'], 'start':start, 'end':end, 'status':receipt['status'], 'reason':receipt['reason'], 'presses':presses, 'sheet':name, 'samples':samples}
            runs.append(run)
            print(sid, receipt['attempt_id'], round(start,2), round(end,2), receipt['status'], receipt['reason'], 'presses', [round(t,2) for t in presses], flush=True)
        video.release()
    (OUT/'p103-attempts.json').write_text(json.dumps(runs,indent=2)+'\n')


if __name__ == '__main__':
    main()

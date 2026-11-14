"""Keep recorded boxes, causal readings and baseline requests for regression tests."""

import bisect
import gzip
import json

from p107_measure import HERE, load
from p107_replay import baseline
from pilot.contract import Detection

CASES = {
    'oncoming_bend': ('051709', 123.2, 126.0),
    'oncoming_second': ('055729', 89.0, 93.0),
    'slower': ('051709', 73.2, 78.0),
    'slower_release': ('053655', 612.7, 615.7),
    'hidden_queue': ('061133', 75.5, 85.2),
}


if __name__ == '__main__':
    result = {}
    for name, (session, start, end) in CASES.items():
        _, ticks = load(session)
        times = [t['t'] for t in ticks]
        boxes = {r['frame_id']: r for r in map(json.loads, (HERE / f'p107-{session}-boxes.jsonl').open())}
        rows = []
        detections = {}
        for r in map(json.loads, gzip.open(HERE / f'p107-{session}-replay.jsonl.gz', 'rt')):
            if not start <= r['t'] <= end or not r['active']:
                continue
            tick = ticks[bisect.bisect_left(times, r['t'])]
            box = boxes[r['frame_id']]
            detections[str(r['frame_id'])] = {'t': box['t'], 'objects': box['objects']}
            rows.append({'now': r['t'], 'dt': r['dt'], 'frame_id': r['frame_id'],
                         'reading': {k: tick['reading'][k] for k in
                                     ('bearing', 'far_bearing', 'arrow', 'confidence', 'corrupt', 'gps_speed')},
                         'steer': r['steer'], 'before': r['before']})
        result[name] = {'session': session, 'start': start, 'end': end,
                        'detections': detections, 'rows': rows}
    _, ticks = load('035459')
    times = [t['t'] for t in ticks]
    original = json.loads((HERE.parents[1] / 'pilot/tests/fixtures/p106_approaches.json').read_text())
    for name in ('queue', 'lorry'):
        old = baseline().Avoider()
        rows, detections = [], {}
        for r in original[name]['rows']:
            tick = ticks[bisect.bisect_right(times, r['now'])-1]
            before = old.step(tuple(Detection(**o) for o in r['objects']), r['t'], r['now'], speed=r['speed'])
            detections[str(r['frame_id'])] = {'t': r['t'], 'objects': r['objects']}
            reading = {k: tick['reading'][k] for k in
                       ('bearing', 'far_bearing', 'arrow', 'confidence', 'corrupt', 'gps_speed')}
            rows.append({'now': r['now'], 'dt': 0, 'frame_id': r['frame_id'], 'reading': reading,
                         'steer': tick['result']['pad']['left'][0], 'before': bool(before.brake)})
        result['p106_' + name] = {'session': '035459', 'detections': detections, 'rows': rows}
    target = HERE.parents[1] / 'pilot/tests/fixtures/p107_brakes.json'
    target.write_text(json.dumps(result, separators=(',', ':')) + '\n')
    print(target, target.stat().st_size)

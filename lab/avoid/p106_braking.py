"""Observed GPS fall after isolated L2 pulses; this is not a wheel-speed sensor."""

import bisect
import json
from pathlib import Path
from statistics import median

HERE = Path(__file__).resolve().parent
ROOT = Path('/Users/kerim/recordings/pilot')


def measure(session):
    rows = list(map(json.loads, (ROOT / ('20261114-' + session) / 'play.jsonl').open()))
    times = [r['t'] for r in rows]
    pulses, active = [], []
    for row in rows:
        pad = row.get('sent_pad') or {}
        state = row.get('result', {}).get('driver_state')
        brake = pad.get('l2', 0) > 0 and state in ('follow', 'coast')
        if brake:
            active.append(row)
        elif active:
            pulses.append((active, row['t']))
            active = []
    results = []
    for pulse, end in pulses:
        first = pulse[0]
        t = first['t']
        speed = first['reading']['gps_speed']
        if end - t < .2 or speed is None or speed < 8:
            continue
        samples = []
        for delay in (.5, 1, 1.5, 2, 2.5, 3):
            row = rows[min(bisect.bisect_left(times, t + delay), len(rows)-1)]
            v = row['reading']['gps_speed']
            samples.append({'dt': round(row['t']-t, 3), 'speed': v,
                            'fall_per_second': None if v is None else (speed-v)/(row['t']-t)})
        results.append({'session': session, 'start': t, 'end': end, 'duration': end-t,
                        'frame_id': first['frame_id'], 'speed': speed,
                        'l2_min': min(r['sent_pad']['l2'] for r in pulse),
                        'l2_max': max(r['sent_pad']['l2'] for r in pulse), 'after': samples})
    return results


if __name__ == '__main__':
    result = [r for s in ('035459', '034630', '024817', '040426', '005357') for r in measure(s)]
    (HERE / 'p106-braking.json').write_text(json.dumps(result, indent=2) + '\n')
    for r in result:
        print(r['session'], f"{r['start']:.3f}-{r['end']:.3f}",
              f"L2={r['l2_min']:.2f}-{r['l2_max']:.2f} v={r['speed']:.2f}",
              'a@.5,1,1.5,2,2.5,3s', [None if a['fall_per_second'] is None else round(a['fall_per_second'], 2) for a in r['after']])

"""Keep exact recorded approach boxes and causal GPS readings in small test fixtures."""

import bisect
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = Path('/Users/kerim/recordings/pilot')
CASES = {
    'queue': ('day-queue', '035459', 271.8, 273.65, 273.50),
    'lorry': ('day-lorry', '035459', 293.8, 296.8, 296.50),
    'pile': ('night-pile', '034036', 20.3, 25.1, 24.20),
    'light': ('night-light', '034630', 59, 67, 65.0),
    'garbage': ('garbage-approach', '030418', 26, 34, 32.0),
}


if __name__ == '__main__':
    result = {}
    for name, (source, session, start, end, contact) in CASES.items():
        ticks = list(map(json.loads, (ROOT / ('20261114-' + session) / 'play.jsonl').open()))
        times = [r['t'] for r in ticks]
        selected = []
        for row in map(json.loads, (HERE / f'p106-{source}.jsonl').open()):
            if not start <= row['t'] <= end:
                continue
            now = row['t'] + .15
            tick = ticks[max(0, bisect.bisect_right(times, now)-1)]
            selected.append({'t': row['t'], 'now': now, 'frame_id': row['frame_id'],
                             'speed': tick['reading']['gps_speed'], 'objects': row['objects']})
        result[name] = {'session': '20261114-' + session, 'contact': contact,
                        'contact_note': 'Visual contact estimate, +/-0.1s; garbage is a side pass, not a verified collision.',
                        'rows': selected}
    target = HERE.parents[1] / 'pilot/tests/fixtures/p106_approaches.json'
    target.write_text(json.dumps(result, separators=(',', ':')) + '\n')
    print(target, target.stat().st_size, 'bytes')

"""Small reproducible tables from the saved boxes; no inference or console access."""

import json
import math

from pilot.avoid import _seen
from pilot.contract import Command, Detection, Observation, Reading
from pilot.skills import DriveRoute

from p107_measure import HERE, SESSIONS


if __name__ == '__main__':
    cases = json.loads((HERE.parents[1] / 'pilot/tests/fixtures/p107_brakes.json').read_text())
    evidence = {}
    for name, case in cases.items():
        skill = DriveRoute({})
        rows = []
        for r in case['rows']:
            detection = case['detections'][str(r['frame_id'])]
            reading = Reading('tilted', 'purple', **r['reading'])
            pad = skill._around(Command(r['steer'], 1, 0, 'follow'), Observation(
                reading, True, r['now'], objects=tuple(Detection(**o) for o in detection['objects']),
                objects_time=detection['t']))
            things = []
            for t in skill.avoider.matched.values():
                contact = t.contact()
                things.append({'kind': t.kind, 'box': t.box, 'height': t.box[3] - t.box[1],
                               'width': t.box[2] - t.box[0], 'near': _seen(t)[2],
                               'distance': t.distance(), 'ttc': contact if contact != math.inf else 'infinite',
                               'raw_closing': (t.distance() + 6) / contact if contact else None,
                               'in_picture_path': t.in_path(), 'queuing': t.queuing, 'brake': t.braking})
            rows.append({'now': r['now'], 'capture': detection['t'], 'dt': r['dt'],
                         'speed': reading.gps_speed, 'before': r['before'], 'l2': pad.l2, 'r2': pad.r2,
                         'near_bearing': reading.bearing, 'far_bearing': reading.far_bearing,
                         'arrow': reading.arrow, 'things': things})
        braking = [r for r in rows if r['l2']]
        evidence[name] = {'first_before': next((r['now'] for r in rows if r['before']), None),
                          'first_after': braking[0]['now'] if braking else None,
                          'last_after': braking[-1]['now'] if braking else None,
                          'last_speed': braking[-1]['speed'] if braking else None,
                          'before_seconds': sum(r['dt'] for r in rows if r['before']),
                          'after_seconds': sum(r['dt'] for r in braking)}
        if name.startswith('p106'):
            evidence[name]['first_tick'] = braking[0]
        if name == 'hidden_queue':
            evidence[name]['pictures'] = [min(rows, key=lambda r: abs(r['capture'] - t)) for t in
                                         (76.94, 78.69, 78.84, 79.07, 79.37, 79.99, 80.46, 83.92)]
    (HERE / 'p107-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    for name, row in evidence.items():
        print(name, {k: v for k, v in row.items() if k not in ('pictures', 'first_tick')})
    totals = json.loads((HERE / 'p107-table.json').read_text())
    for category in ('standing', 'slower', 'oncoming', 'crossing', 'beside', 'nothing'):
        print(category, ' | '.join(f"{version}: {totals[version][category]['count']} / "
              f"{totals[version][category]['seconds']:.3f} s / {totals[version][category]['gps_loss_mean']:.2f} m/s"
              for version in ('recorded', 'before', 'after')))
    replay = json.loads((HERE / 'p107-replay.json').read_text())
    follow = sum(replay[s]['follow'] for s in SESSIONS)
    for version in ('recorded', 'before', 'after'):
        seconds = sum(replay[s]['seconds'][version] for s in SESSIONS)
        onsets = sum(len(replay[s]['events'][version]) for s in SESSIONS)
        print(version, 'follow', follow, 'seconds', seconds, 'percent', 100 * seconds / follow,
              'onsets', onsets, 'per minute', onsets * 60 / follow)

"""Recorded reference rates, synthetic startup and cached GPS-stage timing."""

import json
from collections import Counter
from time import perf_counter

import p104


def save(name, result):
    (p104.OUT / name).write_text(json.dumps(result, indent=2) + '\n')
    print(name, json.dumps(result), flush=True)


def run():
    stats = {}
    for name in ['015516', '005357', '024431', '015901', '014037', '024817']:
        rows = p104.load(p104.RECORDINGS / ('20261114-' + name) / 'play.jsonl')
        drive = [r for r in rows if (r.get('skill') or {}).get('name') == 'drive_route']
        missing = Counter()
        for row in drive:
            reading, skill = row.get('reading') or {}, row['skill']
            missing['distance'] += reading.get('gps_distance') is None
            missing['speed'] += reading.get('gps_speed') is None
            missing['unknown_reason'] += skill.get('speed_reason') == 'unknown-speed'
            missing['unknown_follow'] += skill.get('speed_reason') == 'unknown-speed' and skill.get('driver_state') == 'follow'
        known = [r['reading']['gps_distance'] for r in drive if r.get('reading') and r['reading'].get('gps_distance') is not None]
        stats[name] = dict(ticks=len(drive), missing=missing, known_km_share=sum(v >= 1000 for v in known) / max(1, len(known)))
    save('p104-recorded-summary.json', stats)
    modules = [('before', p104.original()), ('after', p104.gps)]
    startup = []
    for quantum in [1, 10]:
        for acceleration in [2, 4, 8]:
            row = dict(quantum=quantum, acceleration=acceleration)
            for name, module in modules:
                meter = module.Speedometer()
                for i in range(30):
                    at = i / 4
                    distance = round((2000 - acceleration * at * at / 2) / quantum) * quantum
                    speed = meter.update(at + .15, module.Fix(distance, quantum=quantum), sampled_at=at)
                    if speed is not None:
                        row[name] = dict(first_speed_at=at + .15, speed=speed, actual_at_capture=acceleration * at)
                        break
            startup.append(row)
    save('p104-startup.json', startup)
    timing = {}
    for name, module in modules:
        costs = []
        for session in p104.SESSIONS:
            samples = p104.load(p104.OUT / f'p104-replay-{session}.jsonl')
            deliveries = iter([r for r in samples if r['version'] == name and 'delivered_at' in r])
            next_value = next(deliveries, None)
            meter = module.Speedometer()
            for row in p104.load(p104.OUT / f'p104-ticks-{session}.jsonl'):
                t = row['frame_time']
                fixes = []
                while next_value is not None and next_value['delivered_at'] <= t:
                    fixes.append(next_value)
                    next_value = next(deliveries, None)
                start = perf_counter()
                for value in fixes:
                    fix = value['fix']
                    meter.update(value['delivered_at'], None if fix is None else module.Fix(**fix), sampled_at=value['sampled_at'])
                meter.update(t)
                costs.append(1000 * (perf_counter() - start))
        timing[name] = p104.np.percentile(costs, [50, 95, 99]).tolist()
    save('p104-tick-cost.json', timing)


if __name__ == '__main__':
    run()

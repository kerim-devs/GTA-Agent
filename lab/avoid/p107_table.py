"""Join each replay onset to its reviewed scene, keeping unmatched onsets explicit."""

import bisect
import gzip
import json
from statistics import median

from p107_measure import HERE, SESSIONS


def match(event, labels):
    def gap(label):
        return max(label['start'] - event['end'], event['start'] - label['end'], 0)
    nearest = min(labels, key=lambda l: (gap(l), abs(l['start'] - event['start'])))
    return nearest if gap(nearest) <= 0.75 else None


if __name__ == '__main__':
    summaries = json.loads((HERE / 'p107-replay.json').read_text())
    labels = json.loads((HERE / 'p107-labels.json').read_text())
    extra_path = HERE / 'p107-extra-labels.json'
    extra = json.loads(extra_path.read_text()) if extra_path.exists() else {}
    result, pending, table = {}, {}, {}
    for session in SESSIONS:
        samples = list(map(json.loads, gzip.open(HERE / f'p107-{session}-replay.jsonl.gz', 'rt')))
        times = [r['t'] for r in samples]
        result[session], pending[session] = {}, []
        for version, events in summaries[session]['events'].items():
            result[session][version] = []
            for event in events:
                key = f"{version}-{event['id']}"
                label = labels[session][event['id']-1] if version == 'recorded' else match(event, labels[session])
                manual = next((m for m in extra.get(session, []) if abs(m['start'] - event['start']) < 0.03), None) if version != 'recorded' else None
                category = manual['class'] if manual else label['class'] if label else 'unreviewed'
                if category == 'unreviewed':
                    pending[session].append({**event, 'key': key})
                row = {**event, 'class': category, 'source_id': label['id'] if label else None,
                       'note': manual.get('note', '') if manual else label['note'] if label else ''}
                interval = samples[bisect.bisect_left(times, event['start']):
                                   bisect.bisect_right(times, event['end'])]
                # The closing speed shown here is the uncapped estimate at onset. The old
                # brake law actually used min(own speed, this estimate).
                field = 'after_threats' if version == 'after' else 'threats'
                reason = next((r for r in interval if r[field] and r['speed'] is not None and r['speed'] > 0), None)
                if reason:
                    estimates = [t['closing'] for t in reason[field] if t['closing'] is not None]
                    if estimates:
                        row['closing'] = max(estimates)
                        row['own'] = reason['speed']
                        row['ratio'] = row['closing'] / row['own']
                result[session][version].append(row)
                total = table.setdefault(version, {}).setdefault(category, {
                    'count': 0, 'seconds': 0, 'gps_loss_sum': 0, 'gps_known': 0,
                    'closing': [], 'own': [], 'ratio': []})
                total['count'] += 1
                total['seconds'] += event['seconds']
                if event['lost'] is not None:
                    total['gps_loss_sum'] += event['lost']
                    total['gps_known'] += 1
                for k in ('closing', 'own', 'ratio'):
                    if k in row:
                        total[k].append(row[k])
    for totals in table.values():
        for total in totals.values():
            total['gps_loss_mean'] = total['gps_loss_sum'] / total['gps_known'] if total['gps_known'] else None
            for k in ('closing', 'own', 'ratio'):
                values = total[k]
                total[k] = {'n': len(values), 'median': median(values) if values else None,
                            'min': min(values) if values else None, 'max': max(values) if values else None}
    (HERE / 'p107-classified.json').write_text(json.dumps(result, indent=2) + '\n')
    (HERE / 'p107-table.json').write_text(json.dumps(table, indent=2) + '\n')
    (HERE / 'p107-pending.json').write_text(json.dumps(pending, indent=2) + '\n')
    for version, totals in table.items():
        print(version, {c: (t['count'], round(t['seconds'], 3), round(t['gps_loss_mean'] or 0, 2))
                        for c, t in totals.items()})
    print('pending', {s: len(es) for s, es in pending.items()})

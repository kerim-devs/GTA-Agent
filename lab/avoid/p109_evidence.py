"""Summarize saved replays and retain every changed interval and night tick."""

import gzip
import json

from p107_measure import HERE, SESSIONS
from p107_table import match


def main():
    summaries = json.loads((HERE / 'p109-trip-replay.json').read_text())
    labels = json.loads((HERE / 'p107-labels.json').read_text())
    extra = json.loads((HERE / 'p107-extra-labels.json').read_text())
    result = {'follow': sum(s['follow'] for s in summaries.values()), 'versions': {}, 'extensions': [], 'archive_differences': []}
    for name in ('p106', 'p107', 'p109'):
        seconds = sum(s['versions'][name]['seconds'] for s in summaries.values())
        onsets = sum(s['versions'][name]['onsets'] for s in summaries.values())
        result['versions'][name] = {'seconds': seconds, 'percent': 100 * seconds / result['follow'],
                                     'onsets': onsets, 'onsets_per_minute': 60 * onsets / result['follow'],
                                     'equivalent_full_l2_seconds': sum(s['versions'][name]['equivalent_full_l2_seconds'] for s in summaries.values()),
                                     'classes': {}}
    for session in SESSIONS:
        classified = {}
        for name in ('p107', 'p109'):
            classified[name] = []
            for event in summaries[session]['versions'][name]['events']:
                label = match(event, labels[session])
                manual = next((m for m in extra.get(session, []) if abs(m['start'] - event['start']) < .03), None)
                source = manual or label or {'class': 'unreviewed', 'note': ''}
                tagged = {**event, 'class': source['class'], 'note': source.get('note', '')}
                classified[name].append(tagged)
                counts = result['versions'][name]['classes'].setdefault(source['class'], {'onsets': 0, 'seconds': 0.})
                counts['onsets'] += 1
                counts['seconds'] += event['seconds']
        archive = {r['t']: r for r in map(json.loads, gzip.open(HERE / f'p107-{session}-replay.jsonl.gz', 'rt'))}
        segment = None
        for row in map(json.loads, gzip.open(HERE / f'p109-{session}-replay.jsonl.gz', 'rt')):
            older = archive[row['t']]
            if bool(older['after']) != bool(row['p107']['l2']):
                result['archive_differences'].append({'session': session, 't': row['t'], 'frame_id': row['frame_id'],
                                                       'archived_frame': older['frame_id'], 'archived': older['after_strength'],
                                                       'current': row['p107']['l2']})
            changed = row['p109']['l2'] > 0 and row['p107']['l2'] == 0
            if changed:
                if segment is None or row['t'] - segment['end'] > .001:
                    source = next(e for e in classified['p109'] if e['start'] <= row['t'] < e['end'])
                    segment = {'session': session, 'start': row['t'], 'end': row['t'], 'seconds': 0.,
                               'class': source['class'], 'note': source['note'], 'onset': source['start']}
                    result['extensions'].append(segment)
                segment['end'] = row['t'] + row['dt']
                segment['seconds'] += row['dt']
            else:
                segment = None
    (HERE / 'p109-comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    rows = list(map(json.loads, (HERE / 'p109-night-trace.jsonl').open()))
    table = ['| Tick / capture s | Box xyxy px | GPS m/s | Lateral | TTC s / raw closing m/s | P106 | P107 | P109 L2 |',
             '| --- | --- | --- | --- | --- | --- | --- | --- |']
    for row in rows:
        if not 94.3 <= row['t'] <= 96.2:
            continue
        target = next((t for t in row['p107']['tracks'] if t['box'][2] > 520 and t['box'][1] > 300 and t['lateral'] < 1.5), None)
        box = ','.join(f'{v:.1f}' for v in target['box']) if target else 'none'
        lateral = f"{target['lateral']:.3f}" if target else '-'
        numbers = 'unknown' if target is None or target['ttc'] is None else f"{target['ttc']:.3f} / {target['closing']:.2f}"
        actions = []
        for name in ('p106', 'p107'):
            value = row[name]
            if value['l2']:
                actions.append(f"L2 {value['l2']:.0f}" + (' queue' if target and target['reason'] == 'close queue' and name == 'p107' else ''))
            else:
                actions.append('clear' if value['r2'] == 1 else f"pedal {value['r2']:.3f}")
        table.append(f"| {row['t']:.4f} / {row['capture']:.4f} | {box} | {row['speed']:.2f} | {lateral} | {numbers} | {actions[0]} | {actions[1]} | {row['p109']['l2']:.0f} |")
    (HERE / 'p109-ticks.md').write_text('\n'.join(table) + '\n')


if __name__ == '__main__':
    main()

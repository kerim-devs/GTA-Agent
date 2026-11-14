"""Summarize labelled prints and every recorded missing-distance stretch."""

import json
from collections import Counter

import p104


def main():
    bench = {r['crop']: r for r in p104.load(p104.OUT / 'p104-bench.jsonl')}
    gaps = p104.load(p104.OUT / 'p104-gaps.jsonl')
    categories = Counter()
    durations = Counter()
    lines = ['| Session | Missing distance, seconds | Duration | Frame / printed metres | Old OCR | Diagnosis |',
             '| --- | --- | ---: | --- | --- | --- |']
    for gap in gaps:
        row = bench[gap['crop']]
        texts = ' / '.join(' + '.join(x) for x in row['before']['texts']) or '(no text)'
        if row['value'] is None:
            cause = 'HUD absent at arrival'
        elif row['before']['value'] == row['value']:
            cause = 'Correct exemplar; reacquisition / consensus timing'
        elif row['before']['value'] is not None:
            cause = 'Wrong OCR; not a meter fault'
        elif row['background'] == 'light-road':
            cause = 'Light road obscures digits / decimal / unit'
        else:
            cause = 'Turn symbol / blip or unit contamination'
        categories[cause] += 1
        durations[cause] += gap['end'] - gap['start']
        lines.append(f"| {gap['session']} | {gap['start']:.3f}–{gap['end']:.3f} | {gap['end']-gap['start']:.3f} | "
                     f"[{row['frame']}, {row['t']:.3f}s](../../lab/gps/{gap['crop']}) / {row['value']} | "
                     f"`{texts.replace('|', '/')}` | {cause} |")
    (p104.OUT / 'p104-gap-table.md').write_text('\n'.join(lines)+'\n')
    scores = {}
    for background in ('all', 'light-road', 'dark-road', 'absent'):
        rows = [r for r in bench.values() if background == 'all' or r['background'] == background]
        scores[background] = {'total':len(rows), 'visible':sum(r['value'] is not None for r in rows)}
        for name in ('before', 'after'):
            scores[background][name] = dict(
                correct=sum(r['value'] is not None and r['value'] == r[name]['value'] for r in rows),
                wrong=sum(r[name]['value'] is not None and r[name]['value'] != r['value'] for r in rows),
                missed=sum(r['value'] is not None and r[name]['value'] is None for r in rows))
    replay = {}
    for session in p104.SESSIONS:
        samples = p104.load(p104.OUT / f'p104-replay-{session}.jsonl')
        ticks = p104.load(p104.OUT / f'p104-ticks-{session}.jsonl')
        delivery = [r for r in samples if 'delivered_at' in r]
        replay[session] = {}
        for name in ('before', 'after'):
            valid = [r for r in delivery if r['version']==name and r['fix'] is not None]
            replay[session][name] = dict(parsed=len(valid), not_freshened=sum(
                r['accepted_at'] is None or abs(r['accepted_at'] - r['sampled_at']) > 1e-6 for r in valid))
        previously_missing = [r for r in ticks if r['recorded_speed'] is None]
        replay[session]['recovered_original_unknown'] = dict(total=len(previously_missing),
            with_speed=sum(r['after_speed'] is not None for r in previously_missing))
    result = dict(scores=scores, gap_categories=categories, gap_seconds=durations, replay=replay)
    (p104.OUT / 'p104-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))
    for row in bench.values():
        if row['before']['value'] is not None and row['before']['value'] != row['value']:
            print('OLD WRONG',row['crop'],row['value'],row['before']['value'])
    for row in p104.load(p104.OUT / 'p104-sim.jsonl'):
        if not row['before']['reached'] or row['before']['max_distance'] > 5:
            print('EXISTING SIM FAILURE',json.dumps(row))


if __name__ == '__main__':
    main()

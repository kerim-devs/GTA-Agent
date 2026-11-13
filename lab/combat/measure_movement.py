"""Time-weighted movement evidence using the corpus evaluator's aligned windows."""
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'pilot/tools'))
from evaluate_combat import jsonl, intervals, describe, summarize


def weighted_median(values):
    if not values:
        return None
    threshold = sum(w for _, w in values) / 2
    cumulative = 0
    for value, weight in sorted(values):
        cumulative += weight
        if cumulative >= threshold:
            return value


def samples(pads, start, end, key):
    for a, b in zip(pads, pads[1:], strict=False):
        weight = max(0, min(end, b['t']) - max(start, a['t']))
        x, y = a[key]
        if weight and (x*x+y*y)**.5 > .2:
            yield x, y, weight


def main():
    path = ROOT/'lab/combat/recorded-rhythm.json'
    data = json.loads(path.read_text())
    pads = {r:jsonl(Path('/Users/kerim/recordings/kerim')/r/'pad.jsonl') for r in {h['recording'] for h in data['hits']} | {r['recording'] for r in data['rows']}}
    evidence = {}
    for group in ('red', 'no-red'):
        hits = [h for h in data['hits'] if h['group'] == group]
        movements = [s for h in hits for s in samples(pads[h['recording']],h['time'],h['time']+2,'left')]
        axes = {k:[] for k in ('x_negative','x_positive','y_negative','y_positive')}
        for x,y,w in movements:
            axis,value = ('x',x) if abs(x)>=abs(y) else ('y',y)
            axes[f'{axis}_{"negative" if value<0 else "positive"}'].append((abs(value),w))
        evidence[group] = {'hits':len(hits),'active_seconds':sum(w for x,y,w in movements),
                           'axes':{key:{'seconds':sum(w for _,w in values),'median_active_axis':weighted_median(values)} for key,values in axes.items()}}
    locks = {(row['recording'], *m['interval']) for row in data['rows'] if row['group']=='red' for m in row['lock_measurements']}
    turns = [(abs(x),w) for rec,start,end in locks for x,y,w in samples(pads[rec],max(0,start-.5),start,'right') if abs(x)>=abs(y)]
    evidence['turn_before_lock'] = {'seconds':sum(w for _,w in turns),'median_active_x':weighted_median(turns),'locks':len(locks)}
    # Cover/reload in the firing interval or up to two seconds after it, deduplicated.
    for group in ('red','no-red'):
        nearby={k:{} for k in ('r1','square')}
        for row in data['rows']:
            if row['group'] != group:continue
            start,end=(t-row['lead'] for t in row['picture_window'])
            for key in nearby:
                for span in intervals(pads[row['recording']],key,start,end+2):
                    # Store only rising edges within this interval; ignore controls held before it.
                    actual=intervals(pads[row['recording']],key,0,pads[row['recording']][-1]['t'])
                    for edge in actual:
                        if start<=edge[0]<=end+2:
                            nearby[key][(row['recording'],edge[0])]=edge[0]-end
        evidence[group]['near_fire_edges']={key:describe(list(values.values())) for key,values in nearby.items()}
    data['summary']=summarize(data['rows'],data['hits'])
    path.write_text(json.dumps(data,indent=2)+'\n')
    (ROOT/'lab/combat/movement.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence,indent=2))


if __name__=='__main__':main()

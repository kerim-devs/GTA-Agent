"""Compare P65's historical evidence and both fixed-schedule controller runs."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
LAB=ROOT/'lab/combat'

def rows(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

def fire_count(value):
    if isinstance(value,dict):
        return sum(v for k,v in value.items() if k=='fire' and isinstance(v,(int,float)))+sum(fire_count(v) for k,v in value.items() if k!='fire')
    if isinstance(value,list):return sum(map(fire_count,value))
    return 0

new=rows(LAB/'p77-final.jsonl')
old=rows(LAB/'baseline-fixed.jsonl')
assert len(new)==len(old)==20
assert len({r['scene']['id'] for r in new})==20
old={r['scene']['id']:r for r in old}
history={r['scene']['id']:r for r in rows(ROOT/'lab/reaction/ledger.jsonl') if r.get('approach')=='pilot+guard' and r.get('scene',{}).get('kind')=='enemy'}
comparison=[]
for row in new:
    scene=row['scene']['id'];before=old[scene];p65=history[scene]
    reaction=before['metrics'].get('reaction_s')
    historical=p65['metrics'].get('reaction_s')
    comparison.append({'scene':scene,'p65_aim_1s':historical is not None and historical<=1,
                       'p65_fired':fire_count(p65.get('guard',{}))>0,
                       'old_aim_1s':reaction is not None and reaction<=1,
                       'old_fired':fire_count(before.get('guard',{}))>0,**row['p77']})
summary={key:sum(row[key] for row in comparison) for key in ('p65_aim_1s','p65_fired','old_aim_1s','old_fired','aim_within_1s','fired')}
result={'method':'P65 and old fixed replay aim uses the stored first enemy-answer transition (L2), firing uses guard fire tick counts. Final P77 uses all raw samples after onset before compaction. Fixed replay is 30Hz with modelled 100ms head delay; not measured decision latency.', 'summary':summary,'rows':comparison}
(LAB/'replay-comparison.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))

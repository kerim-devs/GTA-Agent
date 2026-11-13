"""Report the failed upper-right component experiment without a runtime reader."""
import json
from pathlib import Path
lab=Path(__file__).resolve().parent
features=json.loads((lab/'weapon-components.json').read_text())['features']
results={}
for name,key,threshold in [('count>=3','components',3),('largest>=99','largest',99),('ink>=238','ink',238),('largest>=238','largest',238)]:
    counts={key:0 for key in ('TP','TN','FP','FN')}
    for feature in features:
        actual=feature['label']=='armed'
        predicted=feature[key]>=threshold
        counts['TP' if actual and predicted else 'FN' if actual else 'FP' if predicted else 'TN']+=1
    results[name]=counts
(lab/'weapon-score.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))

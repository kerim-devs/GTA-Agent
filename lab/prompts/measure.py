"""Score the frozen prompt samples, keeping source-recording exclusions explicit."""

import json
from pathlib import Path

from pilot import prompts

root = Path(__file__).resolve().parent
raw = json.loads((root / 'p71-fixture-raw.json').read_text())
evidence = json.loads((root / 'evidence.json').read_text())
fixtures = evidence['replay_fixtures']
score = sum(prompts.offer(row['raw_help']).button == fixture['button'] for row, fixture in zip(raw, fixtures, strict=True))
held = {'20261111-164039', '20261111-172549'}
training = prompts.TABLE
try:
    prompts.TABLE = [row for row in training if not all(example.split('@')[0] in held for example in row['examples'])]
    checks = [(row, fixture) for row, fixture in zip(raw, fixtures, strict=True) if row['recording'] in held]
    correct = sum(prompts.offer(row['raw_help']).button == fixture['button'] for row, fixture in checks)
finally:
    prompts.TABLE = training
print(json.dumps({'training': {'correct': score, 'total': len(raw)}, 'independent_holdout': {'correct': correct, 'total': len(checks)}}, indent=2))

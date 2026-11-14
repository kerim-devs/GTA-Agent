"""One native OCR request over bounded alternate preparations of the same print."""

import cv2
import numpy as np

import p104


def patches(crop):
    raw = crop[119:141, 53:120]
    gray = cv2.cvtColor(raw, cv2.COLOR_RGB2GRAY)
    result = [raw, cv2.cvtColor(cv2.createCLAHE(clipLimit=2, tileGridSize=(4, 2)).apply(gray), cv2.COLOR_GRAY2RGB)]
    for size in (3, 5):
        top = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, np.ones((size, size), np.uint8))
        top = np.clip(top.astype(float) * 4, 0, 255).astype(np.uint8)
        result.append(cv2.cvtColor(top, cv2.COLOR_GRAY2RGB))
    image = np.full((len(result) * 140, 335, 3), 100, np.uint8)
    for j, patch in enumerate(result):
        image[j * 140 + 15:j * 140 + 125] = cv2.resize(patch, None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)
    return image


if __name__ == '__main__':
    module = p104.original()
    source = p104.subprocess.check_output(['git', 'show', 'HEAD:pilot/src/pilot/gps.py'], text=True)
    source = source[source.index('def recognize('):source.index('\n\nclass Reader:')]
    source = source.replace('def recognize(crop: np.ndarray)', 'def text_patch(crop: np.ndarray)')
    source = source.replace('patch = cv2.resize(crop[118:142, 36:120], None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)', 'patch = crop')
    source = source.replace('texts.append(str(candidates[0].string()))', 'texts.append((str(candidates[0].string()), float(candidates[0].confidence()), [list(p) for p in observation.boundingBox()]))')
    source = source.split('    fix = parse(texts)')[0] + '    return texts\n'
    exec(source, module.__dict__)
    rows = []
    for label in p104.load(p104.OUT / 'p104-labels.jsonl'):
        crop = cv2.cvtColor(cv2.imread(str(p104.OUT / label['crop'])), cv2.COLOR_BGR2RGB)
        start = p104.perf_counter()
        texts = module.text_patch(patches(crop))
        bands = [[] for _ in range(4)]
        for text, confidence, ((x,y),(w,h)) in texts:
            band = min(3, int((1-y-h/2)*4))
            bands[band].append(text)
        fixes = [module.parse(b) for b in bands]
        values = [None if f is None else f.distance for f in fixes]
        valid = [v for v in values if v is not None and values.count(v) >= 2]
        result = valid[0] if valid and len(set(valid)) == 1 else None
        rows.append(dict(label, values=values, texts=texts, result=result, ms=1000*(p104.perf_counter()-start)))
    p104.dump(p104.OUT / 'p104-ensemble.jsonl', rows)
    judged = [r for r in rows if 'value' in r]
    print('correct', sum(r['result'] == r['value'] and r['value'] is not None for r in judged),
          'wrong', sum(r['result'] is not None and r['result'] != r['value'] for r in judged), 'of', len(judged))
    print('ms p50/p95', np.percentile([r['ms'] for r in rows], [50,95]))
    for r in judged:
        if r['result'] != r['value']:
            print(r['crop'], r['value'], r['values'], r['result'])

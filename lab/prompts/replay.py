"""Extract P71 evidence frames and replay frozen text readings without a console."""

import json
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parent


def extract():
    data = json.loads((ROOT / 'evidence.json').read_text())
    raw = json.loads((ROOT / 'p71-fixture-raw.json').read_text())
    folder = ROOT / 'frames'
    folder.mkdir(exist_ok=True)
    for i, row in enumerate(data['replay_fixtures']):
        video = Path('/Users/kerim/recordings/kerim') / row['recording'] / 'video.mp4'
        capture = cv2.VideoCapture(str(video))
        capture.set(cv2.CAP_PROP_POS_FRAMES, raw[i]['reading_i'])
        ok, frame = capture.read()
        capture.release()
        if not ok:
            raise RuntimeError(f'No frame at {video}:{row["t"]}')
        cv2.imwrite(str(folder / f'{i:02d}.jpg'), frame, [cv2.IMWRITE_JPEG_QUALITY, 55])
    print(f'Extracted {len(data["replay_fixtures"])} recorded prompt frames')


if __name__ == '__main__':
    extract()

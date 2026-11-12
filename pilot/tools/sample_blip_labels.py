"""Prepare reproducible, unannotated sampling sheets before manual labeling."""

import json
from pathlib import Path

import cv2
import numpy as np

from pilot.minimap import read


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    output = root / "lab/blips"
    crops = np.load(root / "lab/minimap/data/crops.npy", mmap_mode="r")
    order = np.random.default_rng(12026).permutation(len(crops))
    groups = {"flat": [], "tilted": []}
    for idx in order:
        result = read(crops[idx])
        if not result.corrupt and result.minimap in groups and len(groups[result.minimap]) < 80:
            groups[result.minimap].append(int(idx))
        if all(len(group) == 80 for group in groups.values()):
            break
    (output / "sampling.json").write_text(
        json.dumps(
            {
                "seed": 12026,
                "method": (
                    "permutation without replacement; reader map type and noncorrupt only, "
                    "no blip filtering; manual classification overrides reader type"
                ),
                "groups": groups,
            },
            indent=2,
        )
        + "\n"
    )
    for name, ids in groups.items():
        for start in range(0, len(ids), 8):
            tiles = []
            for idx in ids[start : start + 8]:
                tile = np.zeros((370, 520, 3), np.uint8)
                tile[:340] = cv2.resize(
                    cv2.cvtColor(crops[idx], cv2.COLOR_RGB2BGR), (520, 340), interpolation=cv2.INTER_NEAREST
                )
                cv2.putText(
                    tile, f"{idx}  (260 x 170)", (5, 365), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (255, 255, 255), 1
                )
                tiles.append(tile)
            rows = [np.concatenate(tiles[j : j + 2], axis=1) for j in range(0, len(tiles), 2)]
            cv2.imwrite(str(output / f"sample-{name}-{start // 8}.png"), np.concatenate(rows))
    print("Prepared 80 flat and 80 tilted candidates from seed 12026.")


if __name__ == "__main__":
    main()

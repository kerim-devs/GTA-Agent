"""Show that cable and Wi-Fi UI glyphs survive unrelated gameplay backgrounds."""

import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pilot/src"))
from pilot.hud import read

lab = ROOT / "lab/screens"
fixtures = ROOT / "pilot/tests/fixtures/screens"
rows = json.loads((lab / "fixtures.json").read_text())
menus = [
    (fixtures / f"{r['id']}.png", r["screen"]) for r in rows if r["screen"] != "game"
]
menus += [
    (ROOT / "lab/hud/fixtures" / f"{name}.png", screen)
    for name, screen in (
        ("wifi-08196", "pause"),
        ("wifi-08243", "map"),
        ("wifi-00332", "weapon_wheel"),
        ("wifi-03424", "phone"),
    )
]
backgrounds = [fixtures / f"{r['id']}.png" for r in rows if r["screen"] == "game"]
results = []
(lab / "review").mkdir(exist_ok=True)
for page in range(2):
    sheet = np.zeros((5 * 200, 4 * 320, 3), np.uint8)
    for row, (menu_path, expected) in enumerate(menus[page * 5 : page * 5 + 5]):
        menu = cv2.imread(str(menu_path))
        mask = (
            cv2.imread(str(lab / "masks" / f"{expected}.png"), cv2.IMREAD_GRAYSCALE) > 0
        )
        images = [(menu_path.stem, menu)]
        for background_path in backgrounds:
            composite = cv2.imread(str(background_path))
            composite[mask] = menu[mask]
            actual = read(cv2.cvtColor(composite, cv2.COLOR_BGR2RGB)).screen
            results.append(
                {
                    "menu": menu_path.stem,
                    "background": background_path.stem,
                    "expected": expected,
                    "actual": actual,
                }
            )
            images.append((f"{expected}: {background_path.stem}", composite))
        for col, (label, bgr) in enumerate(images):
            y, x = row * 200, col * 320
            sheet[y : y + 180, x : x + 320] = cv2.resize(bgr, (320, 180))
            cv2.putText(
                sheet,
                label,
                (x + 3, y + 195),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.4,
                (255, 255, 255),
                1,
            )
    cv2.imwrite(str(lab / "review" / f"composites-{page}.jpg"), sheet)
output = {
    "cases": results,
    "passed": all(r["expected"] == r["actual"] for r in results),
}
(lab / "composites.json").write_text(json.dumps(output, indent=2) + "\n")
print(
    f"{sum(r['expected'] == r['actual'] for r in results)}/{len(results)} composites correct"
)
raise SystemExit(0 if output["passed"] else 1)

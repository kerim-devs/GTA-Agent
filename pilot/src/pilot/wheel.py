"""Conservative character-wheel reader calibrated on the P75 recordings.

The white outer arc marks the current character, not the selected character.
Selection uses the colored wedge. Unrepresented appearances abstain.
"""

import base64
import zlib
from dataclasses import dataclass

import cv2
import numpy as np

# 24x24 grayscale wheel signatures, from lab/story's existing reference frames.
# They recognize layout only; selection is measured independently below.
_SIGNATURES = (
    (
        "eJzj5ePnE5CvPX9u49Su+RvOnywT5+RgZ2VhAYoKxl5ZVlkQFZBdllpcvupiKBcHGyurgIBQ/8mK/NyMKSsufJyc"
        "mVtQd7qFm52djU9AbnZFQXZa/IrymbPnJaZm5ZfNFWdnZ+fj4ZOMzUiMTdo75cyGk8mxKRkxYuxsnJw8XHx8EiHR"
        "IXHHpsy8djk9LDZUlJebhYOLi4dfVE3Zy99r3tTavdO9/NxFubm5Odk4efhM/UpKrGzsS1d0rJgcaQdUDRLn4NFe"
        "On/j62WqTpYB0enTqkV4QeJAl/KEffv++9chB0mPtEU21TK8YHEeHnbevFPLb0675ssnFuJtIMrLww0CvLzsfJV3"
        "Lv948LWHj1fMURKqmAekvu/TkX0ffu3j4+Ph4eXj5eYCy3Cz81k/Pnr01acgfkn/MAsBHi4uTk4uIODg4d129PDl"
        "7SLiibm5ObY8QGFOTg4g4FRfVR8y7b675dK57bPyxEDKgRJs7HxLS+tir5/Uijhxdv+OfilObi6QchZ21hlls6qO"
        "afHk9VR3JbcqQ8TZWTnYNC8sOqDKyVu0cNW26VNkuMDiLGxAqczrOhzs7HZzF/f0J/EAzWDnYAMKs7OzSnACSYnq"
        "9tICG7BT2FjZQeLASANinUm99RmFXCD1bGAxEGBh5es+2pvRcV2dixUkCtIEAuxsLJoZCVFFqXwsrOwQcQCdoJkg"
    ),
    (
        "eJzj5OTi5ubi5OTmERAVFRQSFJOWkZGRlpJiZWVjZ2Nl5+IUUTeykBQU4ucXFhURFhZmZWVlYWHj5ORw9k8sdOTl"
        "5+fj4eEHAiZmJiYmZhZWNl9LDy9PoHFc7IpVXBwcDCAAlOKNdE0IihdkY2MVi1+Vzs4GFmdkYhKMd/NMTRRmYhYK"
        "Ts3ar8UKFGTl5WRkZLbzsI6yZWURcA+PT62fwc7AKKpiaiHKzKzhb+/nLMpjl5mWnJW1V5GRPyAwpi6cR0BSz93Y"
        "xcY48dycy0szJqczqVWUN7Rly3DI6cer2elbTP30+/fHgrLZjPppvjmeOWqM7LoOMkqaTgtPv7nxqCh7K5NZXmpz"
        "aYsrEyObgoSMisvKtk2dh3oz9jJbV8RHV9XHsDAxcwjKqNluu3fk4dcJGXtYRDNi40rLVNmE/UPM5bQMFhxdeuNt"
        "bdZWdo6AuOjUcB7RhILcXAd108L1c04dSKucziEWHmrikadhu2xu+5xCBdP+taklRzNmpnL5p4b45CfJxJw8d3Dn"
        "FDnZtevj+6adP6bM7hKbU5QiL1jcU9OT2qnGr7Kqvnval8l8XKJZmZmyfPyli1dunTVFjpfPYPvap3e0+Li4DHNk"
        "uLi4nOcu7Z6QzsfNyW1w71U0Lw8wdvl5geJytb2l+fa8QHE+rQw+YPRw83NxAiPecFpPc0YZUDs3Dw8vLw8PF4hk"
        "5xDuOzUhp+2GJpAJNAGYQrh4gICXk0M/Pyu2PE+UnZMLAgC7lpQO"
    ),
)
_TEMPLATES = tuple(
    np.frombuffer(zlib.decompress(base64.b64decode(value)), dtype=np.uint8).reshape(24, 24)
    for value in _SIGNATURES
)
_Y, _X = np.mgrid[550:700, 1080:1235]
_R = np.hypot(_X - 1157, _Y - 623)
_A = np.degrees(np.arctan2(_Y - 623, _X - 1157))
_MASKS = {
    slot: (_R >= 42) & (_R <= 58) & (np.abs((_A - angle + 180) % 360 - 180) <= 16)
    for slot, angle in {"left": 180, "top": -90, "right": 0, "bottom": 90}.items()
}


@dataclass(frozen=True)
class Wheel:
    visible: bool = False
    highlight: str | None = None
    disabled: frozenset[str] = frozenset()


def wheel(frame) -> Wheel:
    """Read RGB 720p frames; unknown layouts and ambiguous colors say nothing."""
    if not isinstance(frame, np.ndarray) or frame.shape != (720, 1280, 3):
        return Wheel()
    if frame.dtype != np.uint8:
        return Wheel()
    crop = cv2.cvtColor(frame[560:681, 1095:1216], cv2.COLOR_RGB2GRAY)
    small = cv2.resize(crop, (24, 24), interpolation=cv2.INTER_AREA)
    correlations = [float(cv2.matchTemplate(small, ref, cv2.TM_CCOEFF_NORMED)[0, 0]) for ref in _TEMPLATES]
    if max(correlations) < 0.75:
        return Wheel()
    pixels = {slot: frame[550:700, 1080:1235][mask].astype(np.float32) for slot, mask in _MASKS.items()}
    green = pixels["top"]
    cyan = pixels["left"]
    orange = pixels["right"]
    candidates = []
    if (
        np.count_nonzero(
            (green[:, 1] > 1.18 * green[:, 0]) & (green[:, 1] > 1.18 * green[:, 2]) & (green[:, 1] > 50)
        )
        >= 40
    ):
        candidates.append("top")
    if (
        np.count_nonzero(
            (cyan[:, 1] > 1.08 * cyan[:, 0]) & (cyan[:, 2] > 1.02 * cyan[:, 0]) & (cyan[:, 1] > 50)
        )
        >= 50
    ):
        candidates.append("left")
    if (
        np.count_nonzero(
            (orange[:, 0] > 1.15 * orange[:, 1]) & (orange[:, 1] > 1.1 * orange[:, 2]) & (orange[:, 0] > 50)
        )
        >= 250
    ):
        candidates.append("right")
    # Only recorded locked/absent portraits are supported. Unknown availability is not
    # guessed from a single dark pixel or the scene behind the translucent UI.
    disabled = frozenset()
    if correlations[1] >= 0.9 and pixels["top"].mean() < 65 and pixels["left"].mean() < 85:
        disabled = frozenset({"top", "left"})
    return Wheel(True, candidates[0] if len(candidates) == 1 else None, disabled)

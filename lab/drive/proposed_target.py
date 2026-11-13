"""Unaccepted P84 experiment: spatial fitting stops before a sharp bend."""

import itertools
from math import hypot, sqrt


def fitted_target(path, radius: float):
    previous = path[0]
    if len(path) >= 2 and hypot(*previous) > radius:
        # Fit the observed near stretch before continuing it under the arrow.
        # Two raster samples amplify pixel noise when projected back to 8 px.
        samples = [(0.0, *previous)]
        distance = 0.0
        last_segment = None
        for before, point in itertools.pairwise(path):
            segment = point[0] - before[0], point[1] - before[1]
            length = hypot(*segment)
            if last_segment is not None:
                dot = segment[0] * last_segment[0] + segment[1] * last_segment[1]
                if dot < 0.866 * length * hypot(*last_segment):
                    break
            distance += length
            samples.append((distance, *point))
            last_segment = segment
            if distance >= 16.0:
                break
        mean_s, mean_x, mean_y = (
            sum(p[i] for p in samples) / len(samples) for i in range(3)
        )
        variance = sum((s - mean_s) ** 2 for s, _, _ in samples)
        dx = sum((s - mean_s) * (x - mean_x) for s, x, _ in samples) / variance
        dy = sum((s - mean_s) * (y - mean_y) for s, _, y in samples) / variance
        x, y = mean_x - mean_s * dx, mean_y - mean_s * dy
        length = hypot(dx, dy)
        if length > 0:
            dx, dy = dx / length, dy / length
            projection = x * dx + y * dy
            discriminant = projection * projection - x * x - y * y + radius * radius
            if discriminant < 0 and projection > 0:
                # Aim at the line's nearest point until the short circle reaches
                # it; the first visible point would start cutting the corner.
                return x - projection * dx, y - projection * dy
            if discriminant >= 0:
                along = -projection + sqrt(discriminant)
                if along < 0:
                    return x + along * dx, y + along * dy
    for point in path[1:]:
        before, after = hypot(*previous), hypot(*point)
        if before <= radius <= after and after > before:
            fraction = (radius - before) / (after - before)
            return tuple(
                a + fraction * (b - a) for a, b in zip(previous, point, strict=True)
            )
        if before >= radius:
            return previous
        previous = point
    return previous

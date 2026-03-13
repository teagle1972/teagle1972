from __future__ import annotations


def draw_rounded_rect(canvas, x1: int, y1: int, x2: int, y2: int, radius: int, **kwargs) -> int:
    r = max(4, int(radius))
    points = [
        x1 + r, y1,
        x2 - r, y1,
        x2, y1,
        x2, y1 + r,
        x2, y2 - r,
        x2, y2,
        x2 - r, y2,
        x1 + r, y2,
        x1, y2,
        x1, y2 - r,
        x1, y1 + r,
        x1, y1,
    ]
    return int(canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs))

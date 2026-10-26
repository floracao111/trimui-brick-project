"""Turn a list of pen points into a sketch PNG. Standard library only."""
import math

from pixelgrid import GRID_H, GRID_W, png_from_raw

CANVAS_W, CANVAS_H = 640, 480  # 4:3, the same shape as the handheld's screen and the pixel grid
MAX_POINTS = 5000
BACKGROUND = (207, 210, 202)
INK = (43, 43, 43)


def clean_points(points):
    """Check client-supplied points. They are [x, y] pairs between 0 and 1 (a share of the canvas)."""
    if not isinstance(points, list) or not 2 <= len(points) <= MAX_POINTS:
        raise ValueError(f"points must be a list of 2 to {MAX_POINTS} pairs")
    cleaned = []
    for p in points:
        if not isinstance(p, (list, tuple)) or len(p) != 2:
            raise ValueError("each point must be [x, y]")
        x, y = p
        if isinstance(x, bool) or isinstance(y, bool) or not all(isinstance(v, (int, float)) for v in (x, y)):
            raise ValueError("point values must be numbers")
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError("point values must be finite")
        cleaned.append((min(max(float(x), 0.0), 1.0), min(max(float(y), 0.0), 1.0)))
    return cleaned


def points_to_png(points, width=CANVAS_W, height=CANVAS_H, radius=1.6):
    buf = bytearray(bytes(BACKGROUND) * (width * height))
    offsets = [
        (dx, dy)
        for dy in range(-2, 3)
        for dx in range(-2, 3)
        if dx * dx + dy * dy <= radius * radius + 0.5
    ]

    def stamp(cx, cy):
        ix, iy = int(round(cx)), int(round(cy))
        for dx, dy in offsets:
            x, y = ix + dx, iy + dy
            if 0 <= x < width and 0 <= y < height:
                i = (y * width + x) * 3
                buf[i:i + 3] = bytes(INK)

    pixels = [(x * (width - 1), y * (height - 1)) for x, y in points]
    stamp(*pixels[0])
    for (x0, y0), (x1, y1) in zip(pixels, pixels[1:]):
        steps = max(1, int(max(abs(x1 - x0), abs(y1 - y0))))
        for i in range(1, steps + 1):
            t = i / steps
            stamp(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)

    raw = bytearray()
    stride = width * 3
    for row in range(height):
        raw += b"\x00" + buf[row * stride:(row + 1) * stride]
    return png_from_raw(width, height, raw)


def ink_cells(points, width=GRID_W, height=GRID_H):
    """The grid cells the pen's path passes through. Points are 0 to 1 pairs from clean_points()."""
    cells = set()

    def add(x, y):
        cells.add((min(int(x * width), width - 1), min(int(y * height), height - 1)))

    add(*points[0])
    for (x0, y0), (x1, y1) in zip(points, points[1:]):
        steps = max(1, int(max(abs(x1 - x0) * width, abs(y1 - y0) * height) * 3))
        for i in range(1, steps + 1):
            t = i / steps
            add(x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
    return cells

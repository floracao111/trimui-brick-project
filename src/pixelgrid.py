"""Pixel grids: parse Claude's reply, check it, and render it. Standard library only."""
import json
import re
import struct
import zlib

GRID_W, GRID_H = 64, 48  # 4:3, and 16x this is 1024x768, the Brick Pro's screen

# code -> (name, color). The model picks the background and colors from these.
PALETTE = {
    "k": ("black", "#0d0d14"),
    "w": ("white", "#ffffff"),
    "g": ("light gray", "#a8a8b8"),
    "G": ("dark gray", "#55556a"),
    "r": ("red", "#e63946"),
    "R": ("dark red", "#8f1d2c"),
    "o": ("orange", "#ff8a1f"),
    "y": ("bright yellow", "#ffe51a"),
    "Y": ("gold", "#d9a400"),
    "l": ("lime green", "#7be04a"),
    "n": ("dark green", "#1f8a3a"),
    "c": ("cyan", "#45d6ff"),
    "b": ("blue", "#2f6bff"),
    "B": ("navy", "#1a2a7a"),
    "p": ("purple", "#8a3ffc"),
    "m": ("pink", "#ff5fb0"),
    "t": ("skin tan", "#f2c9a0"),
    "T": ("brown", "#7a4a1e"),
}


def _colors(*rows):
    return {code: (name, color) for code, name, color in rows}


# Each scheme is a mood. The server picks one per drawing (or the player chooses), and the model
# must use only that scheme's codes. "classic" is the original bright palette.
SCHEMES = {
    "classic": {"description": "bright, saturated arcade colors", "colors": PALETTE},
    "gothic": {
        "description": "blacks, charcoal and dark reds with bone white; dark and moody",
        "colors": _colors(
            ("a", "near-black", "#07060a"), ("b", "charcoal", "#1b1a22"), ("c", "dark slate", "#33313d"),
            ("d", "ash gray", "#5c5a68"), ("e", "bone", "#d8d2c4"), ("f", "dried blood", "#3d0b12"),
            ("g", "dark red", "#6e1019"), ("h", "crimson", "#a8132a"), ("i", "deep purple", "#2a1033"),
            ("j", "faded purple", "#5b2a63"),
        ),
    },
    "mono": {
        "description": "pure black and white with shades of gray, like an old monochrome game",
        "colors": _colors(
            ("a", "black", "#000000"), ("b", "gray 1", "#1c1c1c"), ("c", "gray 2", "#383838"),
            ("d", "gray 3", "#555555"), ("e", "gray 4", "#717171"), ("f", "gray 5", "#8d8d8d"),
            ("g", "gray 6", "#aaaaaa"), ("h", "gray 7", "#c6c6c6"), ("i", "gray 8", "#e2e2e2"),
            ("j", "white", "#ffffff"),
        ),
    },
    "pastel": {
        "description": "soft, light pastel colors with a gentle plum outline",
        "colors": _colors(
            ("a", "plum", "#6b5876"), ("b", "rose", "#ffb3c6"), ("c", "peach", "#ffcfb0"),
            ("d", "butter", "#fff3b0"), ("e", "mint", "#b8f0d0"), ("f", "sky", "#b5dcff"),
            ("g", "lavender", "#d4c1ff"), ("h", "cream", "#fff8ee"), ("i", "blush", "#ffd6e4"),
            ("j", "sage", "#c9e4b8"), ("k", "lilac gray", "#b9b0c9"),
        ),
    },
    "gameboy": {
        "description": "only four shades of green, like the original Game Boy",
        "colors": _colors(
            ("a", "darkest green", "#0f380f"), ("b", "dark green", "#306230"),
            ("c", "light green", "#8bac0f"), ("d", "lightest green", "#9bbc0f"),
        ),
    },
    "synthwave": {
        "description": "neon purples, magentas, orange and cyan, like an 80s night drive",
        "colors": _colors(
            ("a", "ink purple", "#12042b"), ("b", "deep violet", "#2b0a5c"), ("c", "indigo", "#3d1a8a"),
            ("d", "magenta", "#ff2fa0"), ("e", "hot pink", "#ff77c8"), ("f", "orange", "#ff9a3c"),
            ("g", "sun yellow", "#ffe14d"), ("h", "cyan", "#2ff3ff"), ("i", "teal", "#0f9cb8"),
            ("j", "white", "#ffffff"), ("k", "midnight", "#1a1040"),
        ),
    },
    "sepia": {
        "description": "browns, tans and parchment, like an old faded photograph",
        "colors": _colors(
            ("a", "dark umber", "#2b1a0e"), ("b", "brown", "#5a3a1e"), ("c", "leather", "#8a5a2b"),
            ("d", "tan", "#b98a52"), ("e", "sand", "#dcc08a"), ("f", "parchment", "#f0e2bf"),
            ("g", "faded ink", "#4a3a2c"), ("h", "rust", "#9b4a22"),
        ),
    },
    "toxic": {
        "description": "black with acid green, neon purple and warning orange",
        "colors": _colors(
            ("a", "black", "#050505"), ("b", "charcoal", "#1a1a1a"), ("c", "acid green", "#b6ff00"),
            ("d", "dark green", "#3d7d00"), ("e", "neon purple", "#a21cff"), ("f", "deep purple", "#3a0a66"),
            ("g", "warning orange", "#ff6a00"), ("h", "bone", "#ecf5e0"),
        ),
    },
}


def _dilate(cells, radius, width=GRID_W, height=GRID_H):
    out = set()
    for x, y in cells:
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if 0 <= x + dx < width and 0 <= y + dy < height:
                    out.add((x + dx, y + dy))
    return out


def fit_to_sketch(rows, ink, outline, min_coverage=0.6):
    """Check the art follows the player's lines. ink is the set of (x, y) cells the line passes through.

    Returns (rows, problems). Small gaps along the line are filled in with the outline code.
    A big miss, or outlined parts the sketch does not have (a stem it never drew), is a problem.
    """
    if not ink:
        return rows, []
    width, height = len(rows[0]), len(rows)
    outline_cells = {(x, y) for y, row in enumerate(rows) for x, code in enumerate(row) if code == outline}
    missing = [c for c in ink if c not in _dilate(outline_cells, 1, width, height)]
    coverage = 1 - len(missing) / len(ink)
    problems = []
    if coverage < min_coverage:
        problems.append(
            f"only {coverage:.0%} of the sketch's # cells carry the outline code '{outline}'. "
            "Keep every # cell in place, same position and size, and put the outline code on it"
        )
    near_sketch = _dilate(ink, 2, width, height)
    extras = [c for c in outline_cells if c not in near_sketch]
    if len(extras) > max(8, int(0.06 * len(ink))):
        xs, ys = [c[0] for c in extras], [c[1] for c in extras]
        problems.append(
            f"{len(extras)} outline cells are away from the sketch's lines (columns {min(xs)}-{max(xs)}, "
            f"rows {min(ys)}-{max(ys)}). Do not add outlined parts the sketch does not have, and draw "
            "background details without the outline code"
        )
    if problems:
        return rows, problems
    grid = [list(row) for row in rows]
    for x, y in missing:
        grid[y][x] = outline
    return ["".join(row) for row in grid], []


def parse_reply(text):
    """Pull the JSON object out of a reply, even if it has code fences or extra words."""
    match = re.search(r"\{.*\}", text.strip(), re.S)
    if not match:
        raise ValueError("no JSON object found in the reply")
    data = json.loads(match.group(0))
    if "rows" not in data:
        raise ValueError("the reply has no 'rows'")
    return data


def validate(rows, width=GRID_W, height=GRID_H, palette=PALETTE):
    """Return a list of problems. An empty list means the grid is good."""
    if not isinstance(rows, list) or not all(isinstance(r, str) for r in rows):
        return ["rows must be a list of strings"]
    problems = []
    if len(rows) != height:
        problems.append(f"expected {height} rows, got {len(rows)}")
    for i, row in enumerate(rows):
        if len(row) != width:
            problems.append(f"row {i} has {len(row)} characters, expected {width}")
        bad = sorted(set(row) - set(palette))
        if bad:
            problems.append(f"row {i} uses codes not in the palette: {''.join(bad)}")
    return problems


def _longest_run(items):
    """Return (length, start) of the longest run of equal neighbours."""
    best, i = (0, 0), 0
    while i < len(items):
        j = i
        while j + 1 < len(items) and items[j + 1] == items[i]:
            j += 1
        if j - i + 1 > best[0]:
            best = (j - i + 1, i)
        i = j + 1
    return best


def _fix_length(row, width):
    """Add or remove single pixels from the longest run, where nobody will see it."""
    while len(row) != width:
        run, i = _longest_run(row)
        if len(row) < width:
            row = row[:i] + row[i] + row[i:]
        elif run >= 2:
            row = row[:i] + row[i + 1:]
        else:
            row = row[:-1]
    return row


def repair(rows, width=GRID_W, height=GRID_H, max_off=4):
    """Fix small counting slips. Returns (rows, number_of_fixes). Big errors are left for validate()."""
    if not isinstance(rows, list) or not all(isinstance(r, str) for r in rows):
        return rows, 0
    if abs(len(rows) - height) > max_off or any(abs(len(r) - width) > max_off for r in rows):
        return rows, 0
    fixes = 0
    rows = list(rows)
    while len(rows) != height:
        run, i = _longest_run(rows)
        if len(rows) < height:
            rows.insert(i, rows[i])
        elif run >= 2:
            del rows[i]
        else:
            rows.pop()
        fixes += 1
    fixed = []
    for row in rows:
        if len(row) != width:
            row = _fix_length(row, width)
            fixes += 1
        fixed.append(row)
    return fixed, fixes


def _rgb(hex_color):
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def render_svg(rows, palette=PALETTE, scale=16):
    rects = []
    for y, row in enumerate(rows):
        for x, code in enumerate(row):
            rects.append(
                f'<rect x="{x * scale}" y="{y * scale}" width="{scale}" height="{scale}" '
                f'fill="{palette[code][1]}"/>'
            )
    w, h = len(rows[0]) * scale, len(rows) * scale
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
        f'shape-rendering="crispEdges">' + "".join(rects) + "</svg>"
    )


def png_from_raw(width, height, raw):
    """Wrap raw RGB scanlines (each starting with a 0 filter byte) as PNG bytes."""

    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def render_png(rows, palette=PALETTE, scale=16):
    """Return PNG bytes. Written by hand so it needs no image library."""
    raw = bytearray()
    for row in rows:
        line = b"".join(bytes(_rgb(palette[code][1])) * scale for code in row)
        raw += (b"\x00" + line) * scale
    return png_from_raw(len(rows[0]) * scale, len(rows) * scale, raw)

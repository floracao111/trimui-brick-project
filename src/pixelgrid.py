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

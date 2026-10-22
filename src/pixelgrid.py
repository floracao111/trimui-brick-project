"""Pixel grids: parse Claude's reply, check it, and render it. Standard library only."""
import json
import re
import struct
import zlib

GRID_W, GRID_H = 32, 24

# code -> (what it is for, color)
PALETTE = {
    ".": ("black background", "#000000"),
    "Y": ("bright yellow, main body color", "#ffe51a"),
    "S": ("shade", "#f5b800"),
    "D": ("deep shade", "#d98e00"),
    "O": ("dark outline", "#6b3d00"),
    "B": ("stem brown", "#8a5a00"),
    "K": ("very dark tip", "#3b2000"),
    "W": ("white", "#ffffff"),
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

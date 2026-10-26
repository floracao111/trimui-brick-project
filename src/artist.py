"""Ask Claude to colour a sketch in as pixel art, check it, and retry if it is wrong.

Runs on the node. It calls Claude Code in headless mode, signed in with my Claude account.
ANTHROPIC_API_KEY is removed from the environment so usage goes to the subscription.
"""
import argparse
import json
import os
import random
import subprocess
import sys

from pixelgrid import (
    GRID_H, GRID_W, SCHEMES, fit_to_sketch, parse_reply, render_png, render_svg, repair, validate,
)
from sketch import clean_points, ink_cells

PROMPT = """Read the image at {path}. It is a rough single-line sketch drawn with a joystick on a toy-like gray screen. Decide what it shows, then colour it in as detailed 90s video-game pixel art on a grid that is exactly {w} columns wide and {h} rows tall.

{fidelity}

Colour scheme: "{scheme}" ({description}). Let it set the whole mood of the picture.

Art direction:
- Give each filled area two or three shading tones from the scheme.
- Choose the background color yourself, any color in the palette (not always black), one that makes the subject stand out. Fill the whole background with it.

Use only these palette codes, one character per pixel:
{palette}

Reply with ONLY a JSON object and nothing else, in this form:
{{"subject": "<one or two words>", "outline": "<one palette code>", "background": "<one palette code>", "rows": ["<{w} characters>", ... {h} strings in total ...]}}
"""

TRACE = """Stay true to the sketch. This map shows the {w} by {h} grid. # marks the cells the player's line passes through, and . is empty (row 0 is at the top, column 0 at the left):
{map}

Rules:
- Trace it. Keep every # cell as part of the outline, in the same position and size. Do not redraw, move, resize or re-compose what was drawn, and do not replace it with your own idea of the subject.
- Do not add any part to the subject that the sketch lacks: no stem, leaves, legs, face, arms, hat or anything else. Only colour in and shade what the lines show, filling the areas they enclose.
- You may add a background behind and around it (sky, ground, stars, a pattern) away from the lines. Background details have no outline, and must not touch the subject or look like part of it.
- Pick one outline code and use it only on the # cells."""

FREE = """Make the subject fill most of the grid and give it a dark outline. Pick one outline code and use it only for the outline."""

RETRY = """

Your previous reply had these problems:
{problems}
Fix them and reply again with ONLY the JSON object."""


class GridError(Exception):
    pass


def ink_map(ink, w=GRID_W, h=GRID_H):
    return "\n".join("".join("#" if (x, y) in ink else "." for x in range(w)) for y in range(h))


def build_prompt(path, problems=None, w=GRID_W, h=GRID_H, scheme="classic", ink=None):
    spec = SCHEMES[scheme]
    palette = "\n".join(f"{code} = {name} {color}" for code, (name, color) in spec["colors"].items())
    fidelity = TRACE.format(w=w, h=h, map=ink_map(ink, w, h)) if ink else FREE
    prompt = PROMPT.format(
        path=path, w=w, h=h, scheme=scheme, description=spec["description"], palette=palette, fidelity=fidelity
    )
    if problems:
        prompt += RETRY.format(problems="\n".join(f"- {p}" for p in problems))
    return prompt


def run_claude(prompt, timeout=560, model=None, effort=None):
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    cmd = ["claude", "-p", prompt, "--allowedTools", "Read", "--output-format", "text"]
    if model:
        cmd += ["--model", model]
    # Low effort drew a good 64x48 banana in about 78 s; the default took about 196 s.
    cmd += ["--effort", effort or os.environ.get("STRETCH_EFFORT", "low")]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL)
    if done.returncode != 0:
        raise GridError(f"claude exited with {done.returncode}: {done.stderr.strip()[:300]}")
    return done.stdout


def draw(path, run=run_claude, attempts=3, ink=None, scheme=None):
    """Return {"subject", "rows", "attempts", "repaired", "scheme"}. Raises GridError if no attempt is valid."""
    scheme = scheme if scheme in SCHEMES else random.choice(list(SCHEMES))
    palette = SCHEMES[scheme]["colors"]
    problems = None
    for attempt in range(1, attempts + 1):
        reply = run(build_prompt(path, problems, scheme=scheme, ink=ink))
        fixes = 0
        try:
            data = parse_reply(reply)
            data["rows"], fixes = repair(data["rows"])
            problems = validate(data["rows"], palette=palette)
            if not problems and ink:
                outline = data.get("outline")
                if outline not in palette:
                    problems = ["'outline' must be one of the palette codes"]
                else:
                    data["rows"], problems = fit_to_sketch(data["rows"], ink, outline)
        except ValueError as err:
            problems = [str(err)]
        if not problems:
            return {
                "subject": data.get("subject", ""), "rows": data["rows"], "attempts": attempt,
                "repaired": fixes, "scheme": scheme,
            }
    raise GridError(f"no valid grid after {attempts} attempts: {problems}")


def main():
    parser = argparse.ArgumentParser(description="Colour a sketch in as pixel art.")
    parser.add_argument("sketch", help="path to a PNG sketch")
    parser.add_argument("-o", "--out", default="out", help="folder for the results")
    parser.add_argument("--points", help="JSON file of the pen points, to make the model trace the sketch")
    parser.add_argument("--scheme", help="color scheme: " + ", ".join(SCHEMES) + " (default: random)")
    args = parser.parse_args()
    ink = None
    if args.points:
        with open(args.points) as f:
            ink = ink_cells(clean_points(json.load(f)))
    result = draw(os.path.abspath(args.sketch), ink=ink, scheme=args.scheme)
    palette = SCHEMES[result["scheme"]]["colors"]
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "grid.json"), "w") as f:
        json.dump({"subject": result["subject"], "scheme": result["scheme"], "rows": result["rows"]}, f, indent=1)
    with open(os.path.join(args.out, "art.svg"), "w") as f:
        f.write(render_svg(result["rows"], palette))
    with open(os.path.join(args.out, "art.png"), "wb") as f:
        f.write(render_png(result["rows"], palette))
    print(f"subject: {result['subject']}  scheme: {result['scheme']}  attempts: {result['attempts']}  saved to {args.out}/")


if __name__ == "__main__":
    sys.exit(main())

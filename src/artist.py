"""Ask Claude to redraw a sketch as a pixel grid, check it, and retry if it is wrong.

Runs on the node. It calls Claude Code in headless mode, signed in with my Claude account.
ANTHROPIC_API_KEY is removed from the environment so usage goes to the subscription.
"""
import argparse
import os
import subprocess
import sys

from pixelgrid import GRID_H, GRID_W, PALETTE, parse_reply, render_png, render_svg, validate

PROMPT = """Read the image at {path}. It is a rough single-line sketch drawn with a joystick on a toy-like gray screen. Decide what it shows, then redraw it as 90s video-game pixel art on a grid that is exactly {w} columns wide and {h} rows tall, centered on a black background.

Use only these palette codes, one character per pixel:
{palette}

Reply with ONLY a JSON object and nothing else, in this form:
{{"subject": "<one or two words>", "rows": ["<{w} characters>", ... {h} strings in total ...]}}
"""

RETRY = """

Your previous reply had these problems:
{problems}
Fix them and reply again with ONLY the JSON object."""


class GridError(Exception):
    pass


def build_prompt(path, problems=None, w=GRID_W, h=GRID_H, palette=PALETTE):
    lines = "\n".join(f"{code} = {what} {color}" for code, (what, color) in palette.items())
    prompt = PROMPT.format(path=path, w=w, h=h, palette=lines)
    if problems:
        prompt += RETRY.format(problems="\n".join(f"- {p}" for p in problems))
    return prompt


def run_claude(prompt, timeout=280, model=None):
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    cmd = ["claude", "-p", prompt, "--allowedTools", "Read", "--output-format", "text"]
    if model:
        cmd += ["--model", model]
    done = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env, stdin=subprocess.DEVNULL)
    if done.returncode != 0:
        raise GridError(f"claude exited with {done.returncode}: {done.stderr.strip()[:300]}")
    return done.stdout


def draw(path, run=run_claude, attempts=3):
    """Return {"subject", "rows", "attempts"}. Raises GridError if no attempt is valid."""
    problems = None
    for attempt in range(1, attempts + 1):
        reply = run(build_prompt(path, problems))
        try:
            data = parse_reply(reply)
            problems = validate(data["rows"])
        except ValueError as err:
            problems = [str(err)]
        if not problems:
            return {"subject": data.get("subject", ""), "rows": data["rows"], "attempts": attempt}
    raise GridError(f"no valid grid after {attempts} attempts: {problems}")


def main():
    parser = argparse.ArgumentParser(description="Redraw a sketch as pixel art.")
    parser.add_argument("sketch", help="path to a PNG sketch")
    parser.add_argument("-o", "--out", default="out", help="folder for the results")
    args = parser.parse_args()
    result = draw(os.path.abspath(args.sketch))
    os.makedirs(args.out, exist_ok=True)
    with open(os.path.join(args.out, "art.svg"), "w") as f:
        f.write(render_svg(result["rows"]))
    with open(os.path.join(args.out, "art.png"), "wb") as f:
        f.write(render_png(result["rows"]))
    print(f"subject: {result['subject']}  attempts: {result['attempts']}  saved to {args.out}/")


if __name__ == "__main__":
    sys.exit(main())

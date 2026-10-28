# What you are working on

Stretch a Sketch: draw with the two joysticks of a TrimUI Brick Pro, and Claude redraws the
sketch as 90s video-game pixel art. Read `PLAN.md` for the full idea.

This repo lives on the student's laptop. You run here, on the laptop.

## The three machines

- **Laptop (here).** Where you write and change files. This copy is the real one.
- **Node.** An Oracle Ubuntu arm64 server, reached with `ssh mynode`. We build, test and run the
  pipeline there. Never ask for an address, a password or a port. If `ssh mynode` fails, stop and
  show the student the exact error.
- **Brick Pro handheld.** Reachable over USB with `adb` when it is in Data mode (root shell, Tina Linux,
  glibc 2.33, SDL2 in /usr/trimui/lib). Read-only commands (`adb shell ...`) are fine. Anything that writes
  to the device or its SD card needs the student's OK first, and the student launches apps from its menu.

## How to work

1. Change files here, in this repo.
2. `scripts/forge.sh test` copies the code to the node and runs the tests there.
3. `scripts/forge.sh draw <sketch.png>` also asks Claude on the node to redraw a sketch.
4. `scripts/forge.sh serve` runs the server on the node with a tunnel; the laptop test page is at http://localhost:8765. The server listens on localhost only. Drawing is a job: POST /api/draw, then poll /api/jobs/<id>.
5. Show the student the real output, word for word. Never guess or invent output. If something
   fails, show the error, fix the file here, and run again.

Never edit files on the node by hand. If a file there is wrong, fix it here and copy it again.

## Rules

- Python standard library only. Install nothing with pip, and do not use `sudo` anywhere without
  asking. The node and the handheld have no extra libraries.
- `ANTHROPIC_API_KEY` must stay unset on the node. The node uses the student's Claude account, not
  an API key.
- Never put logins, tokens, keys, or anything from `~/.claude` into this repo.
- The art must trace the player's sketch (see `fit_to_sketch` in `src/pixelgrid.py`) and add no parts the sketch lacks. Colour schemes live in `SCHEMES`; each scheme has its own codes.
- Pixel grids are 64 columns by 48 rows, one character per pixel, using only the codes in
  `src/pixelgrid.py`. The model chooses the background and colors from that palette. Change the palette there, not in prompts.
- Keep `PLAN.md` and `README.md` honest: mark what is planned and what is tested.
- Before running each command, say in one sentence what it does.

## Git

Commit and push only when the student asks. End every commit message with a `Co-Authored-By:`
trailer naming your model.

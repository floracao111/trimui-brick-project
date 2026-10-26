# Stretch a Sketch

*Draw a rough line. The AI stretches it into 90s pixel art.*

- **Device**: TrimUI Brick Pro (Allwinner A133p, 1GB RAM, 64GB SD card)
- **Model(s)**: Claude Sonnet 5.5 (via Claude Code)
- **Status**: prototype (node side works; handheld app not built yet)

## What this is

An Etch A Sketch for a retro Linux handheld. Draw with the two joysticks, and the app turns every sketch into 90s video-game pixel art, with button options to customize the look. My own cloud node asks Claude to redraw each sketch as a pixel grid, then renders the result.

Read the full plan in [PLAN.md](PLAN.md).

## What works so far

On my Oracle node, a small server takes pen points, turns them into a sketch, and has Claude colour it in as a 64 by 48 pixel grid, tracing the player's lines. The code checks the grid (size and palette), retries if it is wrong, and renders it as a PNG. A laptop simulator (two big red windows, a stretched pixel-game title, and a controller with two on-screen joysticks that tilt as you press keys) lets me draw with the keyboard or a game controller and see the result. The handheld app and getting code onto the Brick Pro are not built yet.

```
scripts/forge.sh test               # copy the code to the node and run the tests there
scripts/forge.sh draw sketch.png    # redraw a sketch as pixel art; results land in out/
scripts/forge.sh serve              # run the server on the node, then open http://localhost:8765
```

### Real results so far

Top row: the sketches. Bottom row: what Claude on my node made from each one, colouring in the lines exactly where they were drawn, in a different color scheme each time (named under each picture). The sketches are test drawings made by a script to look like joystick lines. Each took between 58 and 96 seconds at low effort.

<table>
<tr><td align="center"><img src="images/results/flower-sketch.png" width="180" alt="flower sketch"></td><td align="center"><img src="images/results/flower-sketch.png" width="180" alt="flower sketch"></td><td align="center"><img src="images/results/house-sketch.png" width="180" alt="house sketch"></td><td align="center"><img src="images/results/fish-sketch.png" width="180" alt="fish sketch"></td><td align="center"><img src="images/results/star-sketch.png" width="180" alt="star sketch"></td></tr>
<tr><td align="center"><img src="images/results/flower-gothic-art.png" width="180" alt="flower as pixel art in the gothic scheme"><br><sub>gothic</sub></td><td align="center"><img src="images/results/flower-pastel-art.png" width="180" alt="flower as pixel art in the pastel scheme"><br><sub>pastel</sub></td><td align="center"><img src="images/results/house-synthwave-art.png" width="180" alt="house as pixel art in the synthwave scheme"><br><sub>synthwave</sub></td><td align="center"><img src="images/results/fish-mono-art.png" width="180" alt="fish as pixel art in the mono scheme"><br><sub>mono</sub></td><td align="center"><img src="images/results/star-gameboy-art.png" width="180" alt="star as pixel art in the gameboy scheme"><br><sub>gameboy</sub></td></tr>
</table>

The code is in `src/`, the tests in `tests/`, and `CLAUDE.md` is the briefing the AI reads first.

Semester project for PSAM 5600 B: Small Linux Devices, Large Language Models (Parsons School of Design, Fall 2026). Course index card: [mfadt/sld-fall-2026/projects/floracao111.md](https://github.com/mfadt/sld-fall-2026/blob/main/projects/floracao111.md)

Inspired by the classic Etch A Sketch toy, a trademark of its owner. This project is not affiliated with it.

## Attribution

All coursework here is co-authored with AI models per course policy. See commit history for `Co-Authored-By:` trailers naming each model that contributed.

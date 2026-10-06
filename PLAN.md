# Stretch a Sketch: project plan

*Draw a rough line. The AI stretches it into art.*

PSAM 5600 B, Fall 2026. Device: TrimUI Brick Pro. Co-author: Claude Sonnet 5.5 (via Claude Code).

## Idea

An Etch A Sketch for a retro Linux handheld. Draw with the two joysticks, pick colors and a style with the buttons, and a model turns the sketch into a finished AI image.

The Brick Pro is a game handheld with no drawing tool and no AI. This project makes it do something it was never meant to do, using the two sticks the way an Etch A Sketch uses its two knobs.

Like the toy, you draw one continuous line and can't lift the pen. The AI has to make sense of that single wiggly line, and that limit is part of the fun.

## How it works

```
 Brick Pro                 Oracle cloud node            Gemini
 ---------                 -----------------            ------
 sticks draw a sketch --> receives the sketch  -->  turns it into
 buttons pick style        builds the prompt         a finished image
 shows the result     <--  returns the image    <--
```

1. **Handheld app.** A small native app. Left stick moves the pen horizontally, right stick vertically. Buttons change color and style, send the sketch, and clear the screen.
2. **Node server.** Runs on my Oracle cloud node. It receives the sketch, adds a prompt based on the chosen style, calls Gemini, and sends the image back. The API key stays on the node.
3. **Gemini.** Google's image model does the sketch-to-image step.
4. **Own language model (later).** Once the node hosts its own model, it will turn the button choices into a richer prompt.

The node and the handheld are both arm64, so code built on the node runs on the handheld.

## Steps

1. Drawing canvas prototype on my laptop.
2. Node server that turns a sketch into an AI image.
3. Get the app running on the Brick Pro.
4. Connect the handheld to the node, end to end.
5. Add color and style menus, and the self-hosted model on the node.
6. Documentation, license, and a tagged release.

## Prior art

Turning a sketch into an AI image is not new. Phone and web tools like [Krea](https://www.krea.ai/apps/sketch-to-image), [Scribble Diffusion](https://creati.ai/ai-tools/scribble-diffusion/), SketchAI and Canva already do it. I could not find one that runs on a retro Linux handheld, draws with two joysticks, or uses a model hosted on the user's own node.

Related work:

- [TekaSketch](https://www.yankodesign.com/2025/10/01/this-diy-raspberry-pi-camera-turns-your-photos-into-automated-etch-a-sketch-art/) turns photos into Etch A Sketch drawings, the opposite direction.
- [SandSketch](https://forum.v1e.com/t/sandtable-etch-a-sketch/42882) drives a sand table with the two sticks of a controller.
- [trimui-brick-chrome](https://github.com/vhu231/trimui-brick-chrome) runs Chrome on the Brick Pro. It is a foundation others could build on, not what this project does.

## Attribution

All work is co-authored with Claude Sonnet 5.5 (via Claude Code). Commits carry `Co-Authored-By:` trailers, and session transcripts are kept.

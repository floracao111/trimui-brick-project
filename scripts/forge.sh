#!/usr/bin/env bash
# Runs on the laptop and drives the node over SSH.
#   scripts/forge.sh test              copy the code to the node and run the tests there
#   scripts/forge.sh draw sketch.png   also ask Claude to redraw a sketch, and fetch the result into out/
set -euo pipefail

NODE="${NODE:-mynode}"
DIR="stretch-a-sketch"
cd "$(dirname "$0")/.."

push_code() {
  ssh "$NODE" "mkdir -p $DIR"
  COPYFILE_DISABLE=1 tar --no-xattrs -czf - src tests | ssh "$NODE" "cd $DIR && tar xzf -"
}

case "${1:-}" in
  test)
    push_code
    ssh "$NODE" "cd $DIR && python3 -m unittest discover -s tests -v"
    ;;
  draw)
    [ -f "${2:-}" ] || { echo "usage: scripts/forge.sh draw <sketch.png>"; exit 1; }
    push_code
    scp -q "$2" "$NODE:$DIR/sketch.png"
    ssh "$NODE" "cd $DIR && PATH=\$HOME/.local/bin:\$PATH python3 src/artist.py sketch.png -o out"
    mkdir -p out && scp -q "$NODE:$DIR/out/art.png" "$NODE:$DIR/out/art.svg" out/
    echo "saved out/art.png and out/art.svg"
    ;;
  *)
    echo "usage: scripts/forge.sh test | draw <sketch.png>"
    exit 1
    ;;
esac

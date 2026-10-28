#!/bin/sh
# Runs on the node (not the laptop): starts the Stretch a Sketch server for the handheld.
# It is reachable from outside, but only answers requests that carry the token in ~/stretch-a-sketch/.token.
# Make a token once with:  head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n' > .token; chmod 600 .token
# Keep it running after you log out with:  setsid nohup sh scripts/start-server.sh > server.log 2>&1 < /dev/null &
cd "$HOME/stretch-a-sketch"
export PATH="$HOME/.local/bin:$PATH" STRETCH_HOST=0.0.0.0 STRETCH_TOKEN="$(cat .token)"
exec python3 src/server.py

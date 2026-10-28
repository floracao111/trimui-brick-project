#!/usr/bin/env bash
# Build a program for the Brick Pro on the node, as a self-contained (static) binary, and fetch it.
#   scripts/build-device.sh hello      builds device/src/hello.c into device/bin/hello
# Static means it carries its own C library, so the handheld's older glibc (2.33) cannot get in the way.
set -euo pipefail
NODE="${NODE:-mynode}"; NAME="${1:?usage: scripts/build-device.sh <name>}"
cd "$(dirname "$0")/.."
ssh "$NODE" "mkdir -p stretch-a-sketch/device"
COPYFILE_DISABLE=1 tar --no-xattrs -czf - device/src | ssh "$NODE" "cd stretch-a-sketch && tar xzf -"
ssh "$NODE" "cd stretch-a-sketch/device/src && mkdir -p ../bin && gcc -O2 -Wall -static -o ../bin/$NAME $NAME.c -lm"
mkdir -p device/bin && scp -q "$NODE:stretch-a-sketch/device/bin/$NAME" "device/bin/$NAME"
file "device/bin/$NAME"
echo "built device/bin/$NAME ($(wc -c < "device/bin/$NAME") bytes)"

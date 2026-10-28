#!/bin/sh
# Stretch Hello. The menu has already exited, so the screen is free for us.
cd "$(dirname "$0")"
./hello > log.txt 2>&1

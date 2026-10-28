#!/bin/sh
# Sends points.json to the node, waits for the pixel art, and saves it as grid.txt.
# Progress goes to state.txt: "sending", "waiting <seconds>", "done", or "error <why>".
cd "$(dirname "$0")"
SERVER=http://127.0.0.1:8765
TOKEN=
[ -f server.conf ] && . ./server.conf
rm -f grid.txt
echo sending > state.txt
resp=$(curl -s -m 20 -X POST -H "Content-Type: application/json" -H "X-Token: $TOKEN" --data-binary @points.json "$SERVER/api/draw")
id=$(echo "$resp" | sed -n 's/.*"id": *"\([0-9a-f]*\)".*/\1/p')
if [ -z "$id" ]; then
  echo "error $(echo "${resp:-cannot reach $SERVER}" | cut -c1-80)" > state.txt
  exit 1
fi
n=0
while [ $n -lt 300 ]; do
  s=$(curl -s -m 15 -H "X-Token: $TOKEN" "$SERVER/api/jobs/$id")
  case "$s" in
    *'"status": "done"'*)
      if curl -s -m 30 -H "X-Token: $TOKEN" "$SERVER/api/jobs/$id/grid.txt" -o grid.txt; then echo done > state.txt; else echo "error could not fetch the art" > state.txt; fi
      exit 0 ;;
    *'"status": "error"'*)
      echo "error $(echo "$s" | cut -c1-80)" > state.txt
      exit 1 ;;
  esac
  echo "waiting $((n * 2))" > state.txt
  sleep 2
  n=$((n + 1))
done
echo "error timed out" > state.txt
exit 1

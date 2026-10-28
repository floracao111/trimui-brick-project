"""Stretch a Sketch server. Runs on the node. Standard library only.

  POST /api/draw                 {"points": [[x, y], ...], "scheme": "random"}  ->  {"id": "..."}   (x and y are 0 to 1)
  GET  /api/schemes              the color schemes the player can pick from
  GET  /api/jobs/<id>            ->  {"status": "queued|working|done|error", ...}
  GET  /api/jobs/<id>/art.png    the pixel art
  GET  /api/jobs/<id>/sketch.png the sketch the model was shown
  GET  /api/jobs/<id>/grid.txt   the pixel art as plain text for the handheld: "P <code> <rrggbb>" lines, then "R <row>" lines
  GET  /                         the laptop test page

Listens on 127.0.0.1 only unless STRETCH_HOST is set, and then STRETCH_TOKEN is required.
Drawing takes about two minutes, so requests become jobs and clients poll.
"""
import hmac
import json
import os
import queue
import random
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from pixelgrid import SCHEMES, render_png
from sketch import clean_points, ink_cells, points_to_png

ROOT = Path(__file__).resolve().parent.parent
MAX_BODY = 300_000
MAX_QUEUE = 3
JOB_ID = re.compile(r"^[0-9a-f]{12}$")


class Busy(Exception):
    pass


class Jobs:
    def __init__(self, artist, workdir):
        self.artist = artist
        self.workdir = Path(workdir)
        self.jobs = {}
        self.lock = threading.Lock()
        self.pending = queue.Queue(MAX_QUEUE)
        threading.Thread(target=self._worker, daemon=True).start()

    def submit(self, points, scheme="random"):
        job_id = uuid.uuid4().hex[:12]
        folder = self.workdir / job_id
        folder.mkdir(parents=True)
        (folder / "sketch.png").write_bytes(points_to_png(points))
        if scheme not in SCHEMES:
            scheme = random.choice(list(SCHEMES))
        with self.lock:
            self.jobs[job_id] = {
                "id": job_id, "status": "queued", "folder": folder, "made": time.time(),
                "scheme": scheme, "ink": ink_cells(points),
            }
        try:
            self.pending.put_nowait(job_id)
        except queue.Full:
            with self.lock:
                del self.jobs[job_id]
            raise Busy()
        return job_id

    def get(self, job_id):
        with self.lock:
            job = self.jobs.get(job_id)
            return dict(job) if job else None

    def _worker(self):
        while True:
            job_id = self.pending.get()
            with self.lock:
                job = self.jobs[job_id]
                job["status"] = "working"
            try:
                result = self.artist(str(job["folder"] / "sketch.png"), ink=job["ink"], scheme=job["scheme"])
                palette = SCHEMES[result.get("scheme", job["scheme"])]["colors"]
                (job["folder"] / "art.png").write_bytes(render_png(result["rows"], palette))
                (job["folder"] / "grid.txt").write_text(grid_text(result["rows"], palette))
                update = {"status": "done", "subject": result["subject"], "attempts": result["attempts"]}
            except Exception as err:  # keep the worker alive whatever the model does
                update = {"status": "error", "error": str(err)[:300]}
            with self.lock:
                job.update(update, seconds=round(time.time() - job["made"]))


def grid_text(rows, palette):
    """The art as plain text, so the handheld can read it with a few lines of C."""
    used = sorted({code for row in rows for code in row})
    lines = [f"P {code} {palette[code][1].lstrip('#')}" for code in used]
    return "\n".join(lines + [f"R {row}" for row in rows]) + "\n"


def public(job):
    return {k: v for k, v in job.items() if k not in ("folder", "made", "ink")}


def make_server(host, port, artist, workdir, token=None):
    jobs = Jobs(artist, workdir)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

        def send(self, status, body, kind="application/json"):
            self.send_response(status)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def send_json(self, status, obj):
            self.send(status, json.dumps(obj).encode())

        def allowed(self):
            if token is None:
                return True
            given = self.headers.get("X-Token", "")
            return hmac.compare_digest(given.encode(), token.encode())

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                page = (ROOT / "web" / "index.html").read_bytes()
                return self.send(200, page, "text/html; charset=utf-8")
            if not path.startswith("/api/"):
                return self.send_json(404, {"error": "not found"})
            if not self.allowed():
                return self.send_json(401, {"error": "token required"})
            if path == "/api/schemes":
                return self.send_json(200, {"schemes": {n: v["description"] for n, v in SCHEMES.items()}})
            parts = path.split("/")  # ['', 'api', 'jobs', id, (file)]
            if len(parts) >= 4 and parts[2] == "jobs" and JOB_ID.match(parts[3]):
                job = jobs.get(parts[3])
                if job is None:
                    return self.send_json(404, {"error": "no such job"})
                if len(parts) == 4:
                    return self.send_json(200, public(job))
                if len(parts) == 5 and parts[4] in ("art.png", "sketch.png", "grid.txt"):
                    file = job["folder"] / parts[4]
                    if file.exists():
                        kind = "text/plain" if file.suffix == ".txt" else "image/png"
                        return self.send(200, file.read_bytes(), kind)
                    return self.send_json(404, {"error": "not ready"})
            return self.send_json(404, {"error": "not found"})

        def do_POST(self):
            if self.path.split("?")[0] != "/api/draw":
                return self.send_json(404, {"error": "not found"})
            if not self.allowed():
                return self.send_json(401, {"error": "token required"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self.send_json(400, {"error": "bad Content-Length"})
            if not 0 < length <= MAX_BODY:
                return self.send_json(413 if length > MAX_BODY else 400, {"error": "bad body size"})
            try:
                body = json.loads(self.rfile.read(length))
                points = clean_points(body["points"])
                scheme = body.get("scheme", "random")
                if scheme != "random" and scheme not in SCHEMES:
                    raise ValueError(f"unknown scheme: choose random or one of {', '.join(SCHEMES)}")
            except (ValueError, KeyError, TypeError, AttributeError) as err:
                return self.send_json(400, {"error": f"bad request: {err}"})
            try:
                job_id = jobs.submit(points, scheme)
            except Busy:
                return self.send_json(429, {"error": "busy, try again in a minute"})
            self.send_json(202, {"id": job_id})

    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.jobs = jobs
    return httpd


def main():
    from artist import draw

    host = os.environ.get("STRETCH_HOST", "127.0.0.1")
    port = int(os.environ.get("STRETCH_PORT", "8765"))
    token = os.environ.get("STRETCH_TOKEN") or None
    if host not in ("127.0.0.1", "localhost") and not token:
        sys.exit("Refusing to listen beyond localhost without STRETCH_TOKEN set.")
    workdir = Path(os.environ.get("STRETCH_JOBS", ROOT / "out" / "jobs"))
    workdir.mkdir(parents=True, exist_ok=True)
    httpd = make_server(host, port, draw, workdir, token)
    print(f"Stretch a Sketch server on http://{host}:{port}  (token {'on' if token else 'off'})", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()

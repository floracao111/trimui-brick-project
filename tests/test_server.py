import http.client
import json
import os
import sys
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from server import make_server  # noqa: E402
from sketch import CANVAS_H, CANVAS_W, clean_points, ink_cells, points_to_png  # noqa: E402
from pixelgrid import GRID_H, GRID_W, SCHEMES  # noqa: E402

with open(os.path.join(HERE, "fixtures", "banana-reply.json")) as f:
    BANANA = json.load(f)

LINE = [[0.1 + i * 0.008, 0.5 + (i % 5) * 0.004] for i in range(100)]


CALLS = []


def fake_artist(path, **kwargs):
    assert os.path.exists(path)
    CALLS.append(kwargs)
    return {"subject": "fake banana", "rows": BANANA["rows"], "attempts": 1, "scheme": "classic"}


def broken_artist(path, **kwargs):
    raise RuntimeError("the model fell over")


class SketchTests(unittest.TestCase):
    def test_png_signature_and_size(self):
        png = points_to_png([(0.1, 0.1), (0.9, 0.9)])
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(int.from_bytes(png[16:20], "big"), CANVAS_W)
        self.assertEqual(int.from_bytes(png[20:24], "big"), CANVAS_H)

    def test_clamps_out_of_range_points(self):
        self.assertEqual(clean_points([[-1, 2], [0.5, 0.5]]), [(0.0, 1.0), (0.5, 0.5)])

    def test_rejects_bad_points(self):
        for bad in ("nope", [], [[0.1, 0.1]], [[0.1]], [["a", "b"], [1, 1]], [[float("nan"), 0], [1, 1]], [[True, 0], [1, 1]]):
            with self.assertRaises(ValueError, msg=repr(bad)):
                clean_points(bad)

    def test_too_many_points(self):
        with self.assertRaises(ValueError):
            clean_points([[0.5, 0.5]] * 5001)


class InkTests(unittest.TestCase):
    def test_a_straight_line_covers_a_row_of_cells(self):
        cells = ink_cells([(0.0, 0.5), (1.0, 0.5)])
        self.assertEqual({y for _, y in cells}, {GRID_H // 2})
        self.assertEqual({x for x, _ in cells}, set(range(GRID_W)))

    def test_points_on_the_edge_stay_inside_the_grid(self):
        cells = ink_cells([(1.0, 1.0), (0.0, 0.0)])
        self.assertTrue(all(0 <= x < GRID_W and 0 <= y < GRID_H for x, y in cells))

    def test_a_diagonal_has_no_gaps(self):
        cells = sorted(ink_cells([(0.0, 0.0), (1.0, 1.0)]))
        for (x0, y0), (x1, y1) in zip(cells, cells[1:]):
            self.assertLessEqual(max(abs(x1 - x0), abs(y1 - y0)), 1)


class ServerTests(unittest.TestCase):
    def start(self, artist=fake_artist, token=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        httpd = make_server("127.0.0.1", 0, artist, self.tmp.name, token)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.shutdown)
        self.port = httpd.server_address[1]

    def call(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        data = json.dumps(body) if body is not None else None
        conn.request(method, path, body=data, headers=headers or {})
        res = conn.getresponse()
        result = (res.status, res.read())
        conn.close()
        return result

    def wait_for(self, job_id, headers=None):
        for _ in range(100):
            status, raw = self.call("GET", f"/api/jobs/{job_id}", headers=headers)
            job = json.loads(raw)
            if job["status"] in ("done", "error"):
                return job
            time.sleep(0.05)
        self.fail("job never finished")

    def test_draw_then_fetch_the_art(self):
        self.start()
        status, raw = self.call("POST", "/api/draw", {"points": LINE})
        self.assertEqual(status, 202)
        job = self.wait_for(json.loads(raw)["id"])
        self.assertEqual((job["status"], job["subject"]), ("done", "fake banana"))
        status, png = self.call("GET", f"/api/jobs/{job['id']}/art.png")
        self.assertEqual((status, png[:8]), (200, b"\x89PNG\r\n\x1a\n"))
        status, png = self.call("GET", f"/api/jobs/{job['id']}/sketch.png")
        self.assertEqual(status, 200)

    def test_the_handheld_gets_the_art_as_plain_text(self):
        self.start()
        _, raw = self.call("POST", "/api/draw", {"points": LINE})
        job = self.wait_for(json.loads(raw)["id"])
        status, text = self.call("GET", f"/api/jobs/{job['id']}/grid.txt")
        self.assertEqual(status, 200)
        lines = text.decode().splitlines()
        rows = [l[2:] for l in lines if l.startswith("R ")]
        self.assertEqual(rows, BANANA["rows"])
        palette = {l.split()[1]: l.split()[2] for l in lines if l.startswith("P ")}
        self.assertTrue(set("".join(rows)) <= set(palette))
        self.assertTrue(all(len(v) == 6 for v in palette.values()))

    def test_the_artist_is_given_the_sketch_cells_and_a_scheme(self):
        self.start()
        CALLS.clear()
        _, raw = self.call("POST", "/api/draw", {"points": LINE, "scheme": "gothic"})
        job = self.wait_for(json.loads(raw)["id"])
        self.assertEqual(job["scheme"], "gothic")
        self.assertEqual(CALLS[-1]["scheme"], "gothic")
        self.assertEqual(CALLS[-1]["ink"], ink_cells(clean_points(LINE)))

    def test_random_scheme_becomes_a_real_scheme(self):
        self.start()
        _, raw = self.call("POST", "/api/draw", {"points": LINE})
        self.assertIn(self.wait_for(json.loads(raw)["id"])["scheme"], SCHEMES)

    def test_unknown_scheme_is_a_400(self):
        self.start()
        self.assertEqual(self.call("POST", "/api/draw", {"points": LINE, "scheme": "rainbow"})[0], 400)

    def test_schemes_are_listed(self):
        self.start()
        status, raw = self.call("GET", "/api/schemes")
        self.assertEqual(status, 200)
        self.assertEqual(set(json.loads(raw)["schemes"]), set(SCHEMES))

    def test_bad_points_are_a_400(self):
        self.start()
        self.assertEqual(self.call("POST", "/api/draw", {"points": "nope"})[0], 400)
        self.assertEqual(self.call("POST", "/api/draw", {"nothing": 1})[0], 400)

    def test_artist_failure_becomes_an_error_job(self):
        self.start(artist=broken_artist)
        _, raw = self.call("POST", "/api/draw", {"points": LINE})
        job = self.wait_for(json.loads(raw)["id"])
        self.assertEqual(job["status"], "error")
        self.assertIn("fell over", job["error"])

    def test_unknown_job_and_path_traversal(self):
        self.start()
        self.assertEqual(self.call("GET", "/api/jobs/abcdef012345")[0], 404)
        self.assertEqual(self.call("GET", "/api/jobs/../../etc/passwd")[0], 404)

    def test_token_is_required_when_set(self):
        self.start(token="secret")
        self.assertEqual(self.call("POST", "/api/draw", {"points": LINE})[0], 401)
        self.assertEqual(self.call("POST", "/api/draw", {"points": LINE}, {"X-Token": "wrong"})[0], 401)
        self.assertEqual(self.call("POST", "/api/draw", {"points": LINE}, {"X-Token": "secret"})[0], 202)

    def test_page_is_served_without_a_token(self):
        self.start(token="secret")
        status, page = self.call("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"Stretch a Sketch", page)


if __name__ == "__main__":
    unittest.main()

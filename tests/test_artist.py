import json
import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from artist import GridError, build_prompt, draw  # noqa: E402
from pixelgrid import SCHEMES  # noqa: E402

with open(os.path.join(HERE, "fixtures", "banana-reply.json")) as f:
    GOOD = json.dumps(json.load(f))

BANANA = json.loads(GOOD)
SKETCH = os.path.join(HERE, "fixtures", "banana-scribble.png")


class FakeClaude:
    """Stands in for the real model so the retry loop can be tested without a network."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.prompts = []

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return self.replies.pop(0)


class DrawTests(unittest.TestCase):
    def test_good_reply_needs_one_attempt(self):
        result = draw(SKETCH, scheme="classic", run=FakeClaude(GOOD))
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["subject"], "banana")

    def test_a_one_character_slip_is_repaired_without_a_retry(self):
        slip = json.loads(GOOD)
        slip["rows"][4] = slip["rows"][4] + slip["rows"][4][-1]
        result = draw(SKETCH, scheme="classic", run=FakeClaude(json.dumps(slip)))
        self.assertEqual((result["attempts"], result["repaired"]), (1, 1))

    def test_bad_reply_is_retried_with_the_problems(self):
        fake = FakeClaude('{"subject": "x", "rows": ["too short"]}', GOOD)
        result = draw(SKETCH, scheme="classic", run=fake)
        self.assertEqual(result["attempts"], 2)
        self.assertIn("previous reply had these problems", fake.prompts[1])

    def test_gives_up_after_three_bad_replies(self):
        bad = "no json at all"
        with self.assertRaises(GridError):
            draw(SKETCH, scheme="classic", run=FakeClaude(bad, bad, bad))

    def test_a_random_scheme_is_chosen_when_none_is_given(self):
        seen = set()
        for _ in range(40):
            fake = FakeClaude("no json")
            try:
                draw(SKETCH, run=fake, attempts=1)
            except GridError:
                pass
            seen.add(next(n for n in SCHEMES if f'Colour scheme: "{n}"' in fake.prompts[0]))
        self.assertGreater(len(seen), 1)

    def test_prompt_with_the_sketch_map_says_not_to_add_parts(self):
        ink = {(3, 4), (4, 4)}
        prompt = build_prompt("/tmp/sketch.png", scheme="gothic", ink=ink)
        self.assertIn("# marks the cells", prompt)
        self.assertIn("no stem", prompt)
        self.assertIn("gothic", prompt)
        self.assertIn("...##" + "." * 59, prompt)  # row 4 of the map: cells 3 and 4 are marked

    def test_prompt_names_the_image_and_the_palette(self):
        prompt = build_prompt("/tmp/sketch.png")
        self.assertIn("/tmp/sketch.png", prompt)
        self.assertIn("r = red", prompt)
        self.assertIn("64 columns", prompt)
        self.assertIn("not always black", prompt)


OUTLINE = "k"
INK = {(x, y) for y, row in enumerate(BANANA["rows"]) for x, c in enumerate(row) if c == OUTLINE}


class TraceTests(unittest.TestCase):
    def reply(self, outline=OUTLINE, rows=None):
        return json.dumps({"subject": "banana", "outline": outline, "background": "b", "rows": rows or BANANA["rows"]})

    def test_art_that_follows_the_lines_is_accepted(self):
        result = draw(SKETCH, scheme="classic", ink=INK, run=FakeClaude(self.reply()))
        self.assertEqual(result["attempts"], 1)

    def test_art_that_ignores_the_lines_is_sent_back(self):
        fake = FakeClaude(self.reply(outline="w"), self.reply())
        result = draw(SKETCH, scheme="classic", ink=INK, run=fake)
        self.assertEqual(result["attempts"], 2)
        self.assertIn("carry the outline code", fake.prompts[1])

    def test_an_unknown_outline_code_is_sent_back(self):
        fake = FakeClaude(self.reply(outline="?"), self.reply())
        self.assertEqual(draw(SKETCH, scheme="classic", ink=INK, run=fake)["attempts"], 2)


if __name__ == "__main__":
    unittest.main()

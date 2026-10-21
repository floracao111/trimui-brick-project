import json
import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from artist import GridError, build_prompt, draw  # noqa: E402

with open(os.path.join(HERE, "fixtures", "banana-reply.json")) as f:
    GOOD = json.dumps(json.load(f))

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
        result = draw(SKETCH, run=FakeClaude(GOOD))
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["subject"], "banana")

    def test_bad_reply_is_retried_with_the_problems(self):
        fake = FakeClaude('{"subject": "x", "rows": ["too short"]}', GOOD)
        result = draw(SKETCH, run=fake)
        self.assertEqual(result["attempts"], 2)
        self.assertIn("previous reply had these problems", fake.prompts[1])

    def test_gives_up_after_three_bad_replies(self):
        bad = "no json at all"
        with self.assertRaises(GridError):
            draw(SKETCH, run=FakeClaude(bad, bad, bad))

    def test_prompt_names_the_image_and_the_palette(self):
        prompt = build_prompt("/tmp/sketch.png")
        self.assertIn("/tmp/sketch.png", prompt)
        self.assertIn("Y = bright yellow", prompt)
        self.assertIn("32 columns", prompt)


if __name__ == "__main__":
    unittest.main()

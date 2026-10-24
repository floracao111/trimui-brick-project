import json
import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from pixelgrid import GRID_H, GRID_W, PALETTE, parse_reply, render_png, render_svg, repair, validate  # noqa: E402

with open(os.path.join(HERE, "fixtures", "banana-reply.json")) as f:
    BANANA = json.load(f)


class ValidateTests(unittest.TestCase):
    def test_real_banana_reply_is_valid(self):
        self.assertEqual(validate(BANANA["rows"]), [])

    def test_wrong_row_count(self):
        self.assertTrue(validate(BANANA["rows"][:-1]))

    def test_wrong_row_length(self):
        rows = list(BANANA["rows"])
        rows[3] = rows[3] + "."
        self.assertTrue(any("row 3" in p for p in validate(rows)))

    def test_code_not_in_palette(self):
        rows = list(BANANA["rows"])
        rows[0] = "Z" + rows[0][1:]
        self.assertTrue(any("not in the palette" in p for p in validate(rows)))

    def test_rows_must_be_strings(self):
        self.assertTrue(validate("not a list"))


class RepairTests(unittest.TestCase):
    def test_a_good_grid_is_untouched(self):
        rows, fixes = repair(BANANA["rows"])
        self.assertEqual((rows, fixes), (BANANA["rows"], 0))

    def test_a_row_one_character_too_long_is_shortened(self):
        bad = list(BANANA["rows"])
        bad[5] = bad[5] + bad[5][-1]
        rows, fixes = repair(bad)
        self.assertEqual((validate(rows), fixes), ([], 1))

    def test_a_row_one_character_too_short_is_lengthened(self):
        bad = list(BANANA["rows"])
        bad[7] = bad[7][:-1]
        rows, fixes = repair(bad)
        self.assertEqual((validate(rows), fixes), ([], 1))

    def test_a_missing_or_extra_row_is_fixed(self):
        rows, fixes = repair(BANANA["rows"][:-1])
        self.assertEqual((validate(rows), fixes), ([], 1))
        rows, fixes = repair(BANANA["rows"] + [BANANA["rows"][0]])
        self.assertEqual((validate(rows), fixes), ([], 1))

    def test_big_errors_are_left_for_a_retry(self):
        bad = list(BANANA["rows"])
        bad[2] = bad[2][:30]
        rows, fixes = repair(bad)
        self.assertEqual(fixes, 0)
        self.assertTrue(validate(rows))

    def test_repair_never_invents_new_colors(self):
        bad = list(BANANA["rows"])
        bad[9] = bad[9] + "k"
        rows, _ = repair(bad)
        self.assertTrue(set("".join(rows)) <= set("".join(BANANA["rows"])) | {"k"})


class ParseTests(unittest.TestCase):
    def test_plain_json(self):
        self.assertEqual(parse_reply('{"subject": "x", "rows": []}')["subject"], "x")

    def test_json_inside_code_fence_and_chatter(self):
        text = 'Here you go:\n```json\n{"subject": "x", "rows": ["."]}\n```\nEnjoy!'
        self.assertEqual(parse_reply(text)["rows"], ["."])

    def test_no_json(self):
        with self.assertRaises(ValueError):
            parse_reply("I could not do that")

    def test_missing_rows(self):
        with self.assertRaises(ValueError):
            parse_reply('{"subject": "x"}')


class RenderTests(unittest.TestCase):
    def test_png_has_signature_and_size(self):
        png = render_png(BANANA["rows"], scale=4)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        width = int.from_bytes(png[16:20], "big")
        height = int.from_bytes(png[20:24], "big")
        self.assertEqual((width, height), (GRID_W * 4, GRID_H * 4))

    def test_svg_has_one_rect_per_pixel(self):
        svg = render_svg(BANANA["rows"])
        self.assertEqual(svg.count("<rect"), GRID_W * GRID_H)

    def test_palette_codes_are_single_characters_with_hex_colors(self):
        for code, (_, color) in PALETTE.items():
            self.assertEqual(len(code), 1)
            self.assertRegex(color, r"^#[0-9a-f]{6}$")


if __name__ == "__main__":
    unittest.main()

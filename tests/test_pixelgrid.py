import json
import os
import sys
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from pixelgrid import GRID_H, GRID_W, PALETTE, SCHEMES, fit_to_sketch, parse_reply, render_png, render_svg, repair, validate  # noqa: E402

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


class SchemeTests(unittest.TestCase):
    def test_every_scheme_is_well_formed(self):
        self.assertIs(SCHEMES["classic"]["colors"], PALETTE)
        self.assertGreaterEqual(len(SCHEMES), 6)
        for name, spec in SCHEMES.items():
            self.assertTrue(spec["description"], name)
            self.assertGreaterEqual(len(spec["colors"]), 4, name)
            for code, (label, color) in spec["colors"].items():
                self.assertEqual(len(code), 1, name)
                self.assertRegex(color, r"^#[0-9a-f]{6}$", name)

    def test_every_scheme_validates_and_renders_a_grid(self):
        for name, spec in SCHEMES.items():
            code = next(iter(spec["colors"]))
            rows = [code * GRID_W] * GRID_H
            self.assertEqual(validate(rows, palette=spec["colors"]), [], name)
            self.assertEqual(render_png(rows, spec["colors"], scale=2)[:8], b"\x89PNG\r\n\x1a\n", name)


class FitToSketchTests(unittest.TestCase):
    W, H = 20, 20

    def grid(self, outline_cells):
        rows = [["b"] * self.W for _ in range(self.H)]
        for x, y in outline_cells:
            rows[y][x] = "k"
        return ["".join(r) for r in rows]

    def test_no_sketch_means_nothing_to_check(self):
        rows = self.grid([])
        self.assertEqual(fit_to_sketch(rows, set(), "k"), (rows, []))

    def test_small_gaps_in_the_line_are_filled(self):
        ink = {(x, 2) for x in range(2, 18)}
        rows, problems = fit_to_sketch(self.grid({(x, 2) for x in range(2, 14)}), ink, "k")
        self.assertEqual(problems, [])
        self.assertEqual(rows[2][17], "k")

    def test_a_big_miss_is_a_problem(self):
        ink = {(x, 2) for x in range(2, 18)}
        _, problems = fit_to_sketch(self.grid({(x, 15) for x in range(2, 18)}), ink, "k")
        self.assertTrue(any("carry the outline code" in p for p in problems))

    def test_an_added_stem_is_a_problem(self):
        ink = {(x, 2) for x in range(2, 18)}
        stem = {(10, y) for y in range(8, 19)}
        _, problems = fit_to_sketch(self.grid(ink | stem), ink, "k")
        self.assertTrue(any("away from the sketch" in p for p in problems))

    def test_a_sketch_of_one_line_in_the_corner_stays_there(self):
        ink = {(0, y) for y in range(0, 10)}
        rows, problems = fit_to_sketch(self.grid(ink), ink, "k")
        self.assertEqual(problems, [])
        self.assertEqual(rows, self.grid(ink))


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

import json
import os
import re
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)

import region  # noqa: E402
from scripts import make_coastline  # noqa: E402


class GridTests(unittest.TestCase):
    def test_wind_grid_size(self):
        self.assertEqual((region.NX, region.NY), (226, 146))

    def test_grid_ends_on_the_box_edges(self):
        self.assertAlmostEqual(region.LON_MIN + (region.NX - 1) * region.DX, region.LON_MAX)
        self.assertAlmostEqual(region.LAT_MIN + (region.NY - 1) * region.DY, region.LAT_MAX)

    def test_box_reaches_45_22_north(self):
        self.assertGreaterEqual(region.LAT_MAX, 45 + 22 / 60)

    def test_box_that_is_not_a_whole_number_of_steps_is_rejected(self):
        with self.assertRaises(ValueError):
            region.grid_points(42.5, 44.51, 0.02)

    def test_float_rounding_does_not_drop_the_last_row(self):
        # (45.4 - 42.5) / 0.02 evaluates to 144.99999999999991, so int() would lose a row.
        self.assertEqual(region.grid_points(42.5, 45.4, 0.02), 146)


class CoastlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(os.path.join(ROOT, "adriatic_coastline.json")) as f:
            cls.segments = json.load(f)
        cls.points = [p for seg in cls.segments for p in seg]

    def test_structure(self):
        self.assertGreater(len(self.segments), 0)
        for seg in self.segments:
            self.assertGreaterEqual(len(seg), 2)
            for p in seg:
                self.assertEqual(len(p), 2)
                self.assertTrue(all(isinstance(v, (int, float)) for v in p))

    def test_reaches_past_the_region_on_every_side(self):
        lons = [p[0] for p in self.points]
        lats = [p[1] for p in self.points]
        self.assertLessEqual(min(lons), region.LON_MIN - 0.1)
        self.assertGreaterEqual(max(lons), region.LON_MAX + 0.1)
        self.assertLessEqual(min(lats), region.LAT_MIN - 0.1)
        self.assertGreaterEqual(max(lats), region.LAT_MAX + 0.1)

    def test_stays_inside_the_clip_box(self):
        west, east, south, north = make_coastline.clip_box()
        for lon, lat in self.points:
            self.assertTrue(west <= lon <= east and south <= lat <= north, (lon, lat))


class ClipTests(unittest.TestCase):
    def test_line_leaving_the_box_is_split(self):
        line = [[0, 0], [1, 0], [5, 0], [1, 1], [0, 1]]
        self.assertEqual(
            make_coastline.clip([line], 0, 2, 0, 2),
            [[[0, 0], [1, 0]], [[1, 1], [0, 1]]],
        )

    def test_single_points_are_dropped(self):
        self.assertEqual(make_coastline.clip([[[1, 1], [9, 9]]], 0, 2, 0, 2), [])


class PackagingTests(unittest.TestCase):
    def test_dockerfile_ships_the_files_the_wind_script_needs(self):
        with open(os.path.join(ROOT, "Dockerfile")) as f:
            copied = " ".join(re.findall(r"^COPY\s+(.*)$", f.read(), flags=re.M))
        for name in ("load_and_merge_gribs.py", "region.py", "adriatic_coastline.json", "marine_grib.py", "grib_validate.py"):
            self.assertIn(name, copied)

    def test_dockerfile_installs_every_external_tool_the_wind_script_runs(self):
        # The apt layer is installed without recommends, so a tool is only there if it is listed
        # (bzip2 used to arrive as a recommend and its removal broke the wind job in CI).
        with open(os.path.join(ROOT, "load_and_merge_gribs.py")) as f:
            tools = set(re.findall(r'subprocess\.run\(\s*\[\s*"([\w.-]+)"', f.read()))
        with open(os.path.join(ROOT, "Dockerfile")) as f:
            dockerfile = f.read()
        installed_elsewhere = {"rm"}  # coreutils
        self.assertIn("bzip2", tools)
        self.assertIn("cdo", tools)
        for tool in tools - installed_elsewhere:
            self.assertRegex(dockerfile, re.compile(rf"^\s+{re.escape(tool)}\s*\\$", re.M), tool)

    def test_dockerignore_keeps_credentials_out_of_the_build_context(self):
        with open(os.path.join(ROOT, ".dockerignore")) as f:
            self.assertIn("secrets.yaml", f.read().split())

    def test_gitignore_keeps_credentials_out_of_git(self):
        with open(os.path.join(ROOT, ".gitignore")) as f:
            self.assertIn("secrets.yaml", f.read().split())


if __name__ == "__main__":
    unittest.main()

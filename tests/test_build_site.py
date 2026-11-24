import json
import os
import tempfile
import unittest

from tests import helpers  # noqa: F401  (puts the repo root on sys.path)

import build_site

NOW = "2026-11-24T13:41:07Z"
LATER = "2026-11-24T19:00:00Z"


def write(path, content=b"x" * 10):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = self.tmp.name

    def path(self, *parts):
        return os.path.join(self.root, *parts)

    def artifact(self, name, run, png=True, content=b"new-data"):
        d = self.path("artifacts", name)
        if name == "wind":
            write(os.path.join(d, f"aladin_adriacenter_{run}.grb"), content)
            if png:
                write(os.path.join(d, f"aladin_wind_{run}.png"), b"png-" + run.encode())
        else:
            write(os.path.join(d, f"copernicus_adriacenter_{run}.grb"), content)
            write(os.path.join(d, "marine_meta.json"), json.dumps({"data_updated_utc": "2026-11-23T18:45:00.584Z"}).encode())
        return d

    def prev(self, wind=None, marine=None, status=False, name="prev"):
        d = self.path(name)
        os.makedirs(d, exist_ok=True)
        if wind:
            write(os.path.join(d, f"aladin_adriacenter_{wind}.grb"), b"old-wind")
            write(os.path.join(d, "aladin_adriacenter_latest.grb"), b"old-wind")
            write(os.path.join(d, f"aladin_wind_{wind}.png"), b"old-png")
            write(os.path.join(d, "aladin_wind_latest.png"), b"old-png")
        if marine:
            write(os.path.join(d, f"copernicus_adriacenter_{marine}.grb"), b"old-marine")
            write(os.path.join(d, "copernicus_adriacenter_latest.grb"), b"old-marine")
        return d

    def build(self, ts, wind_result, marine_result, prev=None, wind=None, marine=None, now=NOW, out="site"):
        out_dir = self.path(out)
        status, outcomes, changed = build_site.build(
            ts, {"wind": wind_result, "marine": marine_result}, {"wind": wind, "marine": marine}, prev, out_dir, now)
        return status, outcomes, changed, out_dir

    def files(self, d):
        return sorted(f for f in os.listdir(d))

    def read(self, *parts):
        with open(self.path(*parts)) as f:
            return f.read()

    # --- state machine -------------------------------------------------------------------------

    def test_both_succeed_with_nothing_published_before(self):
        status, outcomes, changed, out = self.build(
            "2026112318", "success", "success", None, self.artifact("wind", "2026112318"), self.artifact("marine", "2026112318"))
        self.assertEqual(outcomes, {"wind": "new", "marine": "new"})
        self.assertEqual([status["assets"][n]["state"] for n in ("wind", "marine")], ["ok", "ok"])
        self.assertEqual(self.files(out), sorted([
            "README.md", "aladin_adriacenter_2026112318.grb", "aladin_adriacenter_latest.grb",
            "aladin_wind_2026112318.png", "aladin_wind_latest.png",
            "copernicus_adriacenter_2026112318.grb", "copernicus_adriacenter_latest.grb", "index.html", "status.json"]))
        self.assertTrue(changed)
        self.assertEqual(status["assets"]["marine"]["data_updated_utc"], "2026-11-23T18:45:00.584Z")

    def test_latest_files_are_real_copies_not_symlinks(self):
        _, _, _, out = self.build("2026112318", "success", "success", None,
                                  self.artifact("wind", "2026112318"), self.artifact("marine", "2026112318"))
        for name in ("aladin_adriacenter_latest.grb", "copernicus_adriacenter_latest.grb", "aladin_wind_latest.png"):
            self.assertFalse(os.path.islink(os.path.join(out, name)))

    def test_bootstrap_from_the_old_workflows_gh_pages(self):
        prev = self.prev(wind="2026112312")  # no status.json, no marine
        status, outcomes, changed, out = self.build("2026112312", "skipped", "success", prev, None,
                                                    self.artifact("marine", "2026112312"))
        self.assertEqual(outcomes, {"wind": "kept", "marine": "new"})
        self.assertEqual(status["assets"]["wind"]["state"], "ok")
        self.assertEqual(status["assets"]["wind"]["run"], "2026112312")
        self.assertEqual(self.read("site", "aladin_adriacenter_2026112312.grb"), "old-wind")
        self.assertTrue(changed)

    def test_a_failed_wind_job_keeps_the_previous_file_and_warns(self):
        prev = self.prev(wind="2026112312", marine="2026112312")
        status, outcomes, _, out = self.build("2026112318", "failure", "success", prev, None,
                                              self.artifact("marine", "2026112318"))
        wind = status["assets"]["wind"]
        self.assertEqual((wind["state"], wind["run"], wind["failed_for"], wind["failed_since_utc"]),
                         ("stale", "2026112312", "2026112318", NOW))
        self.assertEqual(status["assets"]["marine"]["run"], "2026112318")
        self.assertEqual(self.read("site", "aladin_adriacenter_latest.grb"), "old-wind")
        for text in (self.read("site", "README.md"), self.read("site", "index.html")):
            self.assertIn("failed for Wind (ALADIN)", text)
            self.assertIn("different ALADIN runs", text)

    def test_a_failed_marine_job_keeps_the_previous_file(self):
        prev = self.prev(wind="2026112312", marine="2026112312")
        status, _, _, out = self.build("2026112318", "success", "failure", prev, self.artifact("wind", "2026112318"), None)
        self.assertEqual(status["assets"]["marine"]["state"], "stale")
        self.assertEqual(self.read("site", "copernicus_adriacenter_latest.grb"), "old-marine")
        self.assertEqual(self.read("site", "aladin_adriacenter_latest.grb"), "new-data")

    def test_both_failing_keeps_both_previous_files(self):
        prev = self.prev(wind="2026112312", marine="2026112312")
        status, outcomes, _, out = self.build("2026112318", "failure", "cancelled", prev)
        self.assertEqual(outcomes, {"wind": "failed", "marine": "failed"})
        self.assertEqual([status["assets"][n]["state"] for n in ("wind", "marine")], ["stale", "stale"])
        self.assertEqual(self.read("site", "aladin_adriacenter_latest.grb"), "old-wind")
        self.assertEqual(self.read("site", "copernicus_adriacenter_latest.grb"), "old-marine")

    def test_a_failure_without_any_previous_file_is_reported_as_missing(self):
        status, _, _, out = self.build("2026112318", "success", "failure", None, self.artifact("wind", "2026112318"), None)
        self.assertEqual(status["assets"]["marine"]["state"], "missing")
        self.assertFalse([f for f in self.files(out) if f.startswith("copernicus")])
        self.assertIn("not available", self.read("site", "index.html"))

    def test_a_successful_job_without_a_usable_file_counts_as_failed(self):
        prev = self.prev(wind="2026112312")
        empty = self.path("artifacts", "wind")
        os.makedirs(empty)
        status, outcomes, _, _ = self.build("2026112318", "success", "skipped", prev, empty, None)
        self.assertEqual((outcomes["wind"], status["assets"]["wind"]["state"]), ("failed", "stale"))

    def test_an_artifact_for_the_wrong_run_is_not_used(self):
        prev = self.prev(wind="2026112312")
        status, outcomes, _, _ = self.build("2026112318", "success", "skipped", prev, self.artifact("wind", "2026112400"), None)
        self.assertEqual(outcomes["wind"], "failed")
        self.assertEqual(status["assets"]["wind"]["run"], "2026112312")

    def test_recovery_clears_the_warning(self):
        prev = self.prev(wind="2026112312", marine="2026112312")
        _, _, _, stale_out = self.build("2026112318", "failure", "success", prev, None, self.artifact("marine", "2026112318"))
        status, outcomes, _, out = self.build("2026112318", "success", "skipped", stale_out,
                                              self.artifact("wind", "2026112318"), None, now=LATER, out="site2")
        self.assertEqual(status["assets"]["wind"]["state"], "ok")
        self.assertIsNone(status["assets"]["wind"]["failed_since_utc"])
        self.assertNotIn("Warning", self.read("site2", "README.md"))

    def test_an_older_run_never_replaces_a_newer_one(self):
        _, _, _, published = self.build("2026112318", "success", "success", None, self.artifact("wind", "2026112318"),
                                        self.artifact("marine", "2026112318", content=b"old-marine"), out="published")
        status, outcomes, changed, out = self.build("2026112312", "skipped", "success", published, None,
                                                    self.artifact("marine", "2026112312"))
        self.assertEqual(outcomes["marine"], "guarded")
        self.assertEqual(status["assets"]["marine"]["run"], "2026112318")
        self.assertEqual(self.read("site", "copernicus_adriacenter_latest.grb"), "old-marine")
        self.assertFalse(changed)

    def test_a_skipped_asset_without_a_previous_file_is_missing_not_ok(self):
        status, _, _, _ = self.build("2026112318", "skipped", "success", None, None, self.artifact("marine", "2026112318"))
        self.assertEqual(status["assets"]["wind"]["state"], "missing")

    # --- change detection ----------------------------------------------------------------------

    def test_the_same_failure_again_does_not_change_the_site(self):
        prev = self.prev(wind="2026112312", marine="2026112312")
        _, _, first_changed, first = self.build("2026112318", "failure", "skipped", prev, now=NOW, out="a")
        self.assertTrue(first_changed)
        _, _, again_changed, _ = self.build("2026112318", "failure", "skipped", first, now=LATER, out="b")
        self.assertFalse(again_changed)

    def test_the_failure_since_time_survives_repeated_failures(self):
        prev = self.prev(wind="2026112312")
        _, _, _, first = self.build("2026112318", "failure", "skipped", prev, now=NOW, out="a")
        status, _, _, _ = self.build("2026113000", "failure", "skipped", first, now=LATER, out="b")
        self.assertEqual(status["assets"]["wind"]["failed_since_utc"], NOW)
        self.assertEqual(status["assets"]["wind"]["failed_for"], "2026113000")

    def test_different_content_with_the_same_name_and_size_is_a_change(self):
        prev = self.prev(wind="2026112318", marine="2026112318")
        _, _, _, first = self.build("2026112318", "success", "skipped", prev,
                                    self.artifact("wind", "2026112318", content=b"AAAAAAAA"), None, out="a")
        _, _, changed, _ = self.build("2026112318", "success", "skipped", first,
                                      self.artifact("wind", "2026112318", content=b"BBBBBBBB"), None, now=LATER, out="b")
        self.assertTrue(changed)

    def test_nothing_new_and_nothing_changed(self):
        prev = self.prev(wind="2026112318", marine="2026112318")
        _, _, _, first = self.build("2026112318", "skipped", "skipped", prev, out="a")
        _, _, changed, _ = self.build("2026112318", "skipped", "skipped", first, now=LATER, out="b")
        self.assertFalse(changed)

    # --- rendered text -------------------------------------------------------------------------

    def test_readme_embeds_the_timestamped_png_never_the_latest_copy(self):
        _, _, _, out = self.build("2026112318", "success", "success", None,
                                  self.artifact("wind", "2026112318"), self.artifact("marine", "2026112318"))
        readme = self.read("site", "README.md")
        self.assertIn("![Latest ALADIN wind forecast](aladin_wind_2026112318.png)", readme)
        self.assertNotIn("aladin_wind_latest", readme)

    def test_a_new_wind_file_without_png_gets_no_image_not_an_old_one(self):
        prev = self.prev(wind="2026112312")
        _, _, _, out = self.build("2026112318", "success", "skipped", prev,
                                  self.artifact("wind", "2026112318", png=False), None)
        self.assertNotIn("![", self.read("site", "README.md"))
        self.assertFalse([f for f in self.files(out) if f.endswith(".png")])

    def test_the_website_never_contains_an_image(self):
        _, _, _, out = self.build("2026112318", "success", "success", None,
                                  self.artifact("wind", "2026112318"), self.artifact("marine", "2026112318"))
        index = self.read("site", "index.html")
        self.assertNotIn("<img", index)
        self.assertNotIn(".png", index)

    def test_the_attribution_is_on_both_pages(self):
        _, _, _, out = self.build("2026112318", "success", "success", None,
                                  self.artifact("wind", "2026112318"), self.artifact("marine", "2026112318"))
        for page in ("README.md", "index.html"):
            self.assertIn("10.48670/mds-00359", self.read("site", page))

    def test_status_json_is_valid_and_has_the_schema_version(self):
        _, _, _, out = self.build("2026112318", "success", "success", None,
                                  self.artifact("wind", "2026112318"), self.artifact("marine", "2026112318"))
        status = json.loads(self.read("site", "status.json"))
        self.assertEqual(status["schema"], 1)
        self.assertEqual(set(status["assets"]), {"wind", "marine"})

    def test_a_previous_status_that_points_to_a_missing_file_falls_back_to_the_filenames(self):
        prev = self.prev(wind="2026112312")
        write(os.path.join(prev, "status.json"), json.dumps(
            {"schema": 1, "updated_utc": NOW, "assets": {"wind": {"state": "ok", "run": "2026112400"}}}).encode())
        self.assertEqual(build_site.previous_state(prev, "wind")["run"], "2026112312")

    def test_latest_files_are_not_mistaken_for_runs_when_reading_the_previous_site(self):
        prev = self.prev(wind="2026112312")
        self.assertEqual(build_site.previous_state(prev, "wind")["run"], "2026112312")
        self.assertIsNone(build_site.previous_state(prev, "marine"))

    # --- command line --------------------------------------------------------------------------

    def test_main_writes_the_outputs_the_workflow_reads(self):
        out_file = self.path("gh_output")
        env = {"GITHUB_OUTPUT": out_file}
        old = {k: os.environ.get(k) for k in env}
        os.environ.update(env)
        try:
            code = build_site.main([
                "--ts", "2026112318", "--wind-result", "failure", "--marine-result", "success",
                "--prev", self.prev(wind="2026112312"), "--marine", self.artifact("marine", "2026112318"),
                "--out", self.path("cli_site"), "--now", NOW])
        finally:
            for k, v in old.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        self.assertEqual(code, 0)
        outputs = dict(line.split("=") for line in self.read("gh_output").split())
        self.assertEqual(outputs, {"changed": "true", "save_wind_marker": "false", "save_marine_marker": "true"})

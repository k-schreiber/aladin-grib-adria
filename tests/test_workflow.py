"""Structural guarantees of .github/workflows/process-grib.yml (text based, no YAML library needed)."""
import os
import re
import unittest

from tests import helpers

WORKFLOW = os.path.join(helpers.ROOT, ".github", "workflows", "process-grib.yml")


def load():
    with open(WORKFLOW) as f:
        text = f.read()
    jobs_text = text.split("\njobs:\n", 1)[1]
    parts = re.split(r"^  (\w+):\s*$", jobs_text, flags=re.M)
    jobs = {parts[i]: parts[i + 1] for i in range(1, len(parts), 2)}
    return text, jobs


def steps(job_text):
    return re.split(r"^      - ", job_text, flags=re.M)[1:]


class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text, cls.jobs = load()

    def test_the_four_jobs_exist(self):
        self.assertEqual(set(self.jobs), {"check", "wind", "marine", "publish"})

    def test_wind_and_marine_depend_only_on_check_and_never_on_each_other(self):
        for name, other in (("wind", "marine"), ("marine", "wind")):
            self.assertRegex(self.jobs[name], re.compile(r"^    needs: check\s*$", re.M))
            self.assertNotIn(f"needs.{other}", self.jobs[name])

    def test_publish_runs_even_when_wind_or_marine_failed(self):
        publish = self.jobs["publish"]
        self.assertRegex(publish, r"needs: \[check, wind, marine\]")
        self.assertIn("!cancelled()", publish)
        self.assertIn("needs.check.result == 'success'", publish)
        self.assertRegex(publish, re.compile(r"^    if: \$\{\{.*!cancelled\(\)", re.M))  # an expression, not a bare YAML tag

    def test_the_published_site_is_required_unless_the_branch_does_not_exist_yet(self):
        publish = self.jobs["publish"]
        self.assertNotIn("continue-on-error", publish)  # an unreadable gh-pages must fail the job, never look empty
        checkout = [s for s in steps(publish) if "ref: gh-pages" in s]
        self.assertEqual(len(checkout), 1)
        self.assertIn("steps.published.outputs.exists == 'true'", checkout[0])
        probe = [s for s in steps(publish) if "id: published" in s][0]
        self.assertIn("git ls-remote --exit-code --heads origin gh-pages", probe)
        self.assertRegex(probe, r"2\) echo \"exists=false\"")  # only 'no such branch' means a first deploy
        self.assertRegex(probe, r"\*\) .*exit 1")
        assemble = [s for s in steps(publish) if "id: site" in s][0]
        self.assertIn("--prev prev", assemble)
        self.assertIn('SITE_EXISTS" = "true"', assemble)

    def test_job_outputs_are_compared_as_strings(self):
        for line in self.text.splitlines():
            if line.strip().startswith("if:") and "need_" in line:
                for use in re.findall(r"outputs\.need_\w+(.{0,12})", line):
                    self.assertTrue(use.startswith(" == 'true'"), line)

    def test_every_job_has_a_timeout(self):
        for name, job in self.jobs.items():
            self.assertRegex(job, re.compile(r"^    timeout-minutes: \d+\s*$", re.M), f"{name} has no timeout")

    def test_the_copernicus_secrets_are_only_used_by_the_marine_job(self):
        for name, job in self.jobs.items():
            self.assertEqual("secrets.COPERNICUSMARINE" in job, name == "marine", name)
        self.assertEqual(self.text.count("secrets.COPERNICUSMARINE_SERVICE_USERNAME"), 1)

    def test_deploying_and_saving_markers_are_limited_to_main_and_not_dry_runs(self):
        self.assertRegex(self.text, r"DEPLOY: \$\{\{ github\.ref == 'refs/heads/main' && !\(.*inputs\.dry_run")
        for step in steps(self.jobs["publish"]):
            if "peaceiris/actions-gh-pages" in step or "actions/cache/save" in step or ".processed-marker" in step:
                self.assertIn("env.DEPLOY == 'true'", step.split("uses:")[0] + step, step[:60])

    def test_runs_on_other_branches_get_their_own_concurrency_group(self):
        self.assertRegex(self.text, r"group: aladin-pipeline-\$\{\{ github\.ref_name \}\}")
        self.assertIn("cancel-in-progress: false", self.text)

    def test_the_marker_keys_keep_the_wind_key_and_add_a_marine_key(self):
        self.assertEqual(len(re.findall(r"key: processed-\$\{\{", self.text)), 2)  # lookup + save, wind (unchanged key)
        self.assertEqual(len(re.findall(r"key: processed-marine-\$\{\{", self.text)), 2)

    def test_each_asset_is_decided_by_its_own_data(self):
        check = self.jobs["check"]
        self.assertIn("check_marine.py", check)
        # the water marker is keyed by the Copernicus update, never by the ALADIN run
        self.assertIn("key: processed-marine-${{ steps.marine_check.outputs.key }}", check)
        self.assertIn("key: processed-marine-${{ needs.check.outputs.marine_key }}", self.jobs["publish"])
        self.assertNotIn("processed-marine-${{ needs.check.outputs.timestamp }}", self.text)
        # an empty answer of one checker must not stop the other asset
        self.assertIn('[ -n "$TS" ]', check)
        self.assertIn('[ -n "$MARINE_KEY" ]', check)

    def test_the_marine_job_builds_for_the_reference_time_not_the_aladin_run(self):
        marine = self.jobs["marine"]
        self.assertIn('--timestamp "$REF"', marine)
        self.assertNotIn("$TS", marine)
        self.assertIn("--marine-ts", self.jobs["publish"])

    def test_the_schedule_is_dense_enough_to_notice_new_data_within_minutes(self):
        self.assertRegex(self.text, r"cron: '\*/(5|10|15) \* \* \* \*'")

    def test_the_wind_job_pins_the_run_to_the_one_the_checker_found(self):
        self.assertIn('-e ALADIN_RUN_TIMESTAMP="$TS"', self.jobs["wind"])

    def test_simulated_failures_only_work_in_dry_runs(self):
        for name in ("wind", "marine"):
            sim = [s for s in steps(self.jobs[name]) if f"inputs.simulate == '{name}'" in s]
            self.assertEqual(len(sim), 1, name)
            self.assertIn("inputs.dry_run", sim[0])

    def test_artifacts_only_contain_the_expected_files_and_overwrite_on_rerun(self):
        for name, job in (("wind", self.jobs["wind"]), ("marine", self.jobs["marine"])):
            upload = [s for s in steps(job) if "upload-artifact" in s][0]
            self.assertIn("overwrite: true", upload)
            self.assertNotIn("path: data\n", upload)
            self.assertNotIn("latest", upload)

    def test_the_yaml_parses_when_a_yaml_library_is_available(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        with open(WORKFLOW) as f:
            doc = yaml.safe_load(f)
        self.assertEqual(set(doc["jobs"]), {"check", "wind", "marine", "publish"})

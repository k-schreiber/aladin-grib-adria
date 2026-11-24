import importlib.util
import os
import unittest
from unittest import mock

from tests import helpers  # noqa: F401

HAVE_DEPS = all(importlib.util.find_spec(m) for m in ("requests", "bs4", "numpy", "matplotlib"))

LISTINGS = {
    "00": "",
    "06": '<a href="ALADLAMB4opendata_2026112306_CLSWIND_SPEED.grb.bz2">x</a>',
    "12": '<a href="ALADLAMB4opendata_2026112312_CLSWIND_SPEED.grb.bz2">x</a>',
    "18": '<a href="ALADLAMB4opendata_2026112318_CLSWIND_SPEED.grb.bz2">x</a>',  # newest, but a partial upload
}


def fake_get(url, timeout=None):
    run = url.rstrip("/").split("/")[-1]
    return mock.Mock(status_code=200, text=LISTINGS[run])


@unittest.skipUnless(HAVE_DEPS, "needs requests, beautifulsoup4, numpy and matplotlib")
class FindLatestRunTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import load_and_merge_gribs
        cls.m = load_and_merge_gribs

    def run_with(self, wanted):
        env = {"ALADIN_RUN_TIMESTAMP": wanted} if wanted else {}
        with mock.patch.dict(os.environ, env, clear=False), mock.patch.object(self.m.requests, "get", fake_get):
            if not wanted:
                os.environ.pop("ALADIN_RUN_TIMESTAMP", None)
            return self.m.find_latest_run()

    def test_without_an_override_the_newest_listed_run_is_used(self):
        self.assertEqual(self.run_with(None), ("18", "2026112318"))

    def test_the_run_the_checker_found_wins_over_a_newer_partial_upload(self):
        self.assertEqual(self.run_with("2026112312"), ("12", "2026112312"))

    def test_an_unknown_run_is_an_error_not_a_silent_fallback(self):
        with self.assertRaisesRegex(Exception, "2026112399"):
            self.run_with("2026112399")

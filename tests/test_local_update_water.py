import os
import tempfile
import unittest
from unittest import mock

try:
    import requests  # noqa: F401
    HAVE = True
except ImportError:
    HAVE = False


@unittest.skipUnless(HAVE, "requests not installed")
class LocalWaterUpdateTests(unittest.TestCase):
    def setUp(self):
        import local_update_water
        self.m = local_update_water
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.patches = [mock.patch.object(self.m, "OUTDIR", self.tmp.name),
                        mock.patch.dict(os.environ, {"COPERNICUSMARINE_SERVICE_USERNAME": "u",
                                                     "COPERNICUSMARINE_SERVICE_PASSWORD": "p"})]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)

    def path(self, name):
        return os.path.join(self.tmp.name, name)

    def fake_build(self, argv):
        ref, outdir = argv[1], argv[3]
        with open(os.path.join(outdir, f"copernicus_adriacenter_{ref}.grb"), "wb") as f:
            f.write(b"grib")
        return 0

    def test_builds_once_per_copernicus_update(self):
        with mock.patch.object(self.m.check_marine, "newest_update", return_value=("202611240350-202511-202311", "2026112400")), \
             mock.patch.object(self.m.marine_grib, "main", side_effect=self.fake_build) as build:
            self.assertEqual(self.m.main(), 0)
            self.assertEqual(self.m.main(), 0)
        self.assertEqual(build.call_count, 1)
        self.assertTrue(os.path.exists(self.path("copernicus_adriacenter_latest.grb")))

    def test_a_failed_build_keeps_the_old_files_and_is_retried(self):
        with open(self.path("copernicus_adriacenter_latest.grb"), "wb") as f:
            f.write(b"old")
        with mock.patch.object(self.m.check_marine, "newest_update", return_value=("202611240350-202511-202311", "2026112400")), \
             mock.patch.object(self.m.marine_grib, "main", return_value=1) as build:
            self.assertEqual(self.m.main(), 1)
            self.assertEqual(self.m.main(), 1)
        self.assertEqual(build.call_count, 2)
        with open(self.path("copernicus_adriacenter_latest.grb"), "rb") as f:
            self.assertEqual(f.read(), b"old")

    def test_without_credentials_nothing_runs(self):
        with mock.patch.dict(os.environ, {"COPERNICUSMARINE_SERVICE_USERNAME": ""}), \
             mock.patch.object(self.m.check_marine, "newest_update") as check:
            self.assertEqual(self.m.main(), 0)
        check.assert_not_called()

    def test_a_second_update_running_at_the_same_time_does_nothing(self):
        import fcntl
        with open(self.path(".water_lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with mock.patch.object(self.m.check_marine, "newest_update") as check:
                self.assertEqual(self.m.main(), 0)
        check.assert_not_called()

    def test_old_files_are_pruned(self):
        for day in range(20, 28):
            open(self.path(f"copernicus_adriacenter_202611{day}00.grb"), "wb").close()
        self.m.prune(self.tmp.name)
        self.assertEqual(len([f for f in os.listdir(self.tmp.name)]), self.m.KEEP)
        self.assertIn("copernicus_adriacenter_2026112700.grb", os.listdir(self.tmp.name))


if __name__ == "__main__":
    unittest.main()

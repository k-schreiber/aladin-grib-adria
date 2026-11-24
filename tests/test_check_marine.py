import unittest
from datetime import datetime, timezone
from unittest import mock

try:
    import requests  # noqa: F401
    HAVE_REQUESTS = True
except ImportError:
    HAVE_REQUESTS = False


@unittest.skipUnless(HAVE_REQUESTS, "requests not installed")
class CheckMarineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import check_marine
        cls.cm = check_marine

    NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)

    def fake_get(self, tree):
        return lambda url: tree[url]

    def test_the_newest_released_version_is_used_and_older_ones_are_never_fetched(self):
        base = self.cm.BASE
        prod = "MEDSEA_ANALYSISFORECAST_PHY_006_013"
        ds = "cmems_mod_med_phy-cur_anfc_4.2km-2D_PT1H-m"
        tree = {  # the live metadata uses rel "item"; an old version's file is gone (404)
            f"{base}/{prod}/product.stac.json": {"links": [
                {"rel": "item", "href": f"{ds}_202511/dataset.stac.json"},
                {"rel": "item", "href": f"{ds}_202611/dataset.stac.json"},
                {"rel": "item", "href": "other_202611/dataset.stac.json"}]},
            f"{base}/{prod}/{ds}_202611/dataset.stac.json": {"properties": {
                "admp_released_date": "2026-11-24T13:00:00Z", "admp_updated_data": "2026-11-23T11:36:10Z"}},
        }
        with mock.patch.object(self.cm, "get", self.fake_get(tree)):
            stamp, version = self.cm.latest_update(prod, ds, datetime(2026, 11, 24, 14, 0, tzinfo=timezone.utc))
        self.assertEqual((stamp.strftime("%H:%M"), version), ("11:36", "202611"))
        tree[f"{base}/{prod}/{ds}_202511/dataset.stac.json"] = {"properties": {
            "admp_released_date": "2025-11-01T00:00:00Z", "admp_updated_data": "2026-11-23T11:58:00Z"}}
        with mock.patch.object(self.cm, "get", self.fake_get(tree)):  # 202611 is not released yet at 12:00
            stamp, version = self.cm.latest_update(prod, ds, self.NOW)
        self.assertEqual((stamp.strftime("%H:%M"), version), ("11:58", "202511"))

    def test_key_has_the_latest_update_and_the_versions_and_ref_is_midnight_of_that_day(self):
        found = {"PHY": (datetime(2026, 11, 23, 11, 58, tzinfo=timezone.utc), "202511"),
                 "WAV": (datetime(2026, 11, 24, 3, 50, tzinfo=timezone.utc), "202311")}
        fetch = lambda product, dataset, now: found["PHY" if "PHY" in product else "WAV"]
        self.assertEqual(self.cm.newest_update(self.NOW, fetch), ("202611240350-202511-202311", "2026112400"))

    def test_a_switch_of_the_currents_version_changes_the_key_without_any_new_update_time(self):
        stamp = datetime(2026, 11, 24, 3, 50, tzinfo=timezone.utc)
        old = self.cm.newest_update(self.NOW, lambda p, d, n: (stamp, "202511" if "PHY" in p else "202311"))
        new = self.cm.newest_update(self.NOW, lambda p, d, n: (stamp, "202611" if "PHY" in p else "202311"))
        self.assertNotEqual(old[0], new[0])

    def test_main_prints_key_and_reference_time_separated_by_one_space(self):
        import io
        from contextlib import redirect_stdout
        with mock.patch.object(self.cm, "newest_update", return_value=("202611240350-202511-202311", "2026112400")):
            out = io.StringIO()
            with redirect_stdout(out):
                self.assertEqual(self.cm.main(), 0)
        self.assertEqual(out.getvalue(), "202611240350-202511-202311 2026112400\n")

    def test_a_metadata_failure_is_a_clean_exit_1(self):
        with mock.patch.object(self.cm, "newest_update", side_effect=OSError("down")):
            self.assertEqual(self.cm.main(), 1)


if __name__ == "__main__":
    unittest.main()

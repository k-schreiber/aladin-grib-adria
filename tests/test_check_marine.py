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

    def test_the_newest_released_version_is_used_and_its_update_time_is_the_key(self):
        base = self.cm.BASE
        prod = "MEDSEA_ANALYSISFORECAST_PHY_006_013"
        ds = "cmems_mod_med_phy-cur_anfc_4.2km-2D_PT1H-m"
        tree = {
            f"{base}/{prod}/product.stac.json": {"links": [
                {"rel": "child", "href": f"{ds}_202511/dataset.stac.json"},
                {"rel": "child", "href": f"{ds}_202611/dataset.stac.json"},
                {"rel": "child", "href": "other_202611/dataset.stac.json"}]},
            f"{base}/{prod}/{ds}_202511/dataset.stac.json": {"properties": {
                "admp_released_date": "2025-11-01T00:00:00Z", "admp_updated_data": "2026-11-23T11:58:00Z"}},
            f"{base}/{prod}/{ds}_202611/dataset.stac.json": {"properties": {
                "admp_released_date": "2026-11-24T13:00:00Z", "admp_updated_data": "2026-11-23T11:36:10Z"}},
        }
        with mock.patch.object(self.cm, "get", self.fake_get(tree)):
            before = self.cm.latest_update(prod, ds, self.NOW)  # 202611 is not released yet at 12:00
            after = self.cm.latest_update(prod, ds, datetime(2026, 11, 24, 14, 0, tzinfo=timezone.utc))
        self.assertEqual(before.strftime("%H:%M"), "11:58")
        self.assertEqual(after.strftime("%H:%M"), "11:36")

    def test_key_is_the_latest_update_of_both_datasets_and_ref_is_midnight_of_that_day(self):
        stamps = {"phy": datetime(2026, 11, 23, 11, 58, tzinfo=timezone.utc),
                  "wav": datetime(2026, 11, 24, 3, 50, tzinfo=timezone.utc)}
        fetch = lambda product, dataset, now: stamps["phy" if "phy" in product.lower() else "wav"]
        self.assertEqual(self.cm.newest_update(self.NOW, fetch), ("202611240350", "2026112400"))

    def test_a_metadata_failure_is_a_clean_exit_1(self):
        with mock.patch.object(self.cm, "newest_update", side_effect=OSError("down")):
            self.assertEqual(self.cm.main(), 1)


if __name__ == "__main__":
    unittest.main()

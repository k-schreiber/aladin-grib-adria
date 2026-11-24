import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest import mock

from tests.helpers import HAVE_ECCODES, HAVE_NETCDF, HAVE_NUMPY

import region

NEEDS_NUMPY = unittest.skipUnless(HAVE_NUMPY, "needs numpy")
NEEDS_ECCODES = unittest.skipUnless(HAVE_ECCODES and HAVE_NUMPY, "needs eccodes and numpy")
T0 = datetime(2026, 11, 23, 18, tzinfo=timezone.utc)


@NEEDS_NUMPY
class PureFunctionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import numpy as np
        import marine_grib
        cls.np, cls.mg = np, marine_grib

    def test_parse_timestamp(self):
        self.assertEqual(self.mg.parse_timestamp("2026112318"), T0)
        for bad in ("", "2026-11-23", "202611231", "2026112325", None):
            with self.assertRaises(ValueError):
                self.mg.parse_timestamp(bad)

    def test_request_box_is_the_region_padded_on_all_sides(self):
        box = self.mg.request_box()
        self.assertAlmostEqual(box["minimum_longitude"], region.LON_MIN - 0.01)
        self.assertAlmostEqual(box["maximum_longitude"], region.LON_MAX + 0.01)
        self.assertAlmostEqual(box["minimum_latitude"], region.LAT_MIN - 0.01)
        self.assertAlmostEqual(box["maximum_latitude"], region.LAT_MAX + 0.01)

    def test_the_wave_grids_edge_column_survives_the_padding(self):
        # the wave dataset's last longitude is 17.50000191, past 17.5 by float noise
        self.assertLess(17.50000191, self.mg.request_box()["maximum_longitude"])
        axis = self.np.array([17.41666794, 17.45833397, 17.50000191])
        self.assertEqual(list(self.mg.crop_index(axis, 13.0, 17.5)), [0, 1, 2])

    def test_fields_are_complete_and_unique(self):
        names = [f[0] for f in self.mg.FIELDS]
        params = [f[1] for f in self.mg.FIELDS]
        self.assertEqual(len(names), 11)
        self.assertEqual(len(set(names)), 11)
        self.assertEqual(len(set(params)), 11)
        self.assertEqual({f[3] for f in self.mg.FIELDS}, {"currents", "waves"})
        import grib_validate
        self.assertEqual(set(params), set(grib_validate.MARINE_RANGES))

    def test_no_dataset_version_is_requested_so_the_newest_one_is_used(self):
        import sys
        import types
        calls = []
        stub = types.ModuleType("copernicusmarine")
        stub.subset = lambda **kwargs: calls.append(kwargs)
        with mock.patch.dict(sys.modules, {"copernicusmarine": stub}), tempfile.TemporaryDirectory() as tmp:
            path = self.mg.fetch(self.mg.CURRENTS, ["uo", "vo"], T0, tmp, "currents")
        self.assertEqual(len(calls), 1)
        self.assertNotIn("dataset_version", calls[0])
        self.assertEqual(calls[0]["dataset_id"], "cmems_mod_med_phy-cur_anfc_4.2km-2D_PT1H-m")
        self.assertEqual((calls[0]["start_datetime"], calls[0]["end_datetime"]),
                         ("2026-11-23T18:00:00", "2026-11-27T18:00:00"))
        self.assertTrue(path.endswith("currents.nc"))

    def catalogue(self, now):
        import sys
        import types

        def version(label, released, updated, retired=None):
            return types.SimpleNamespace(label=label, parts=[types.SimpleNamespace(
                released_date=released, arco_updated_date=updated, retired_date=retired)])

        def describe(dataset_id, **kwargs):
            versions = {
                "cmems_mod_med_phy-cur_anfc_4.2km-2D_PT1H-m": [
                    version("202511", "2025-11-25T13:00:00.000Z", "2026-11-23T11:58:32Z", "2027-01-12T13:00:00.000Z"),
                    version("202611", "2026-11-24T13:00:00.000Z", "2026-11-25T12:00:00Z")],
                "cmems_mod_med_wav_anfc_4.2km_PT1H-i": [version("202311", "2023-11-30T11:00:00.000Z", "2026-11-23T18:45:00Z")],
            }[dataset_id]
            return types.SimpleNamespace(products=[types.SimpleNamespace(datasets=[types.SimpleNamespace(versions=versions)])])

        stub = types.ModuleType("copernicusmarine")
        stub.describe = describe
        with mock.patch.dict(sys.modules, {"copernicusmarine": stub}):
            return self.mg.catalogue_info(now=now)

    def test_before_a_new_version_is_released_the_old_one_is_in_use_and_its_retirement_is_reported(self):
        updated, in_use, retires = self.catalogue(datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc))
        self.assertEqual(in_use, {"currents": "202511", "waves": "202311"})  # 202611 is listed but not released yet
        self.assertEqual(retires, {"currents": "2027-01-12T13:00:00.000Z"})
        self.assertEqual(updated, "2026-11-23T18:45:00Z")

    def test_after_the_release_the_newest_version_is_followed_and_nothing_is_flagged(self):
        updated, in_use, retires = self.catalogue(datetime(2026, 11, 24, 13, 1, tzinfo=timezone.utc))
        self.assertEqual(in_use, {"currents": "202611", "waves": "202311"})
        self.assertEqual(retires, {})
        self.assertEqual(updated, "2026-11-25T12:00:00Z")

    def test_a_catalogue_failure_never_fails_the_run(self):
        import sys
        import types
        stub = types.ModuleType("copernicusmarine")

        def broken(**kwargs):
            raise RuntimeError("catalogue unavailable")

        stub.describe = broken
        with mock.patch.dict(sys.modules, {"copernicusmarine": stub}):
            self.assertEqual(self.mg.catalogue_info(), (None, {}, {}))

    def test_native_grid_counts_come_from_origin_step_and_region(self):
        self.assertEqual((region.MARINE_NX, region.MARINE_NY), (109, 70))
        self.assertAlmostEqual(region.MARINE_LONS[0], 13.0, places=5)
        self.assertAlmostEqual(region.MARINE_LONS[-1], 17.5, places=5)
        self.assertAlmostEqual(region.MARINE_LATS[0], 42.5208, places=3)
        self.assertGreaterEqual(region.MARINE_LATS[-1], 45 + 22 / 60)  # reaches 45°22'
        self.assertLessEqual(region.MARINE_LATS[-1], region.LAT_MAX + 1e-4)

    def test_forecast_window_is_97_hourly_steps(self):
        times = self.mg.expected_times(T0)
        self.assertEqual(times.size, region.MARINE_HOURS + 1)
        self.assertEqual(str(times[0]), "2026-11-23T18")
        self.assertEqual(str(times[-1]), "2026-11-27T18")

    def axes(self, lons=None, lats=None, times=None):
        np = self.np
        return (
            np.array(lons if lons is not None else region.MARINE_LONS),
            np.array(lats if lats is not None else region.MARINE_LATS),
            times if times is not None else self.mg.expected_times(T0),
        )

    def test_check_axes_accepts_matching_axes(self):
        self.mg.check_axes(self.axes(), self.axes(), T0)

    def test_check_axes_rejects_a_short_or_shifted_time_axis(self):
        times = self.mg.expected_times(T0)
        for bad in (times[:-1], times + 1):
            with self.assertRaisesRegex(ValueError, "time axis"):
                self.mg.check_axes(self.axes(times=bad), self.axes(), T0)

    def test_check_axes_rejects_a_half_hour_offset_that_hour_truncation_would_hide(self):
        shifted = self.mg.expected_times(T0).astype("datetime64[s]") + self.np.timedelta64(1800, "s")
        with self.assertRaisesRegex(ValueError, "time axis"):
            self.mg.check_axes(self.axes(times=shifted), self.axes(), T0)

    def test_the_attribution_names_the_dois_of_both_datasets(self):
        import build_site
        for source in (self.mg.CURRENTS, self.mg.WAVES):
            self.assertIn(source["doi"], build_site.ATTRIBUTION)

    def test_check_axes_rejects_datasets_on_different_grids(self):
        shifted = [x + 0.01 for x in region.MARINE_LONS]
        with self.assertRaisesRegex(ValueError, "differ in longitude"):
            self.mg.check_axes(self.axes(), self.axes(lons=shifted), T0)
        with self.assertRaisesRegex(ValueError, "differ in latitude"):
            self.mg.check_axes(self.axes(), self.axes(lats=region.MARINE_LATS[:-1]), T0)

    def test_check_axes_rejects_an_unexpected_grid_size(self):
        small = region.MARINE_LONS[:-1]
        with self.assertRaisesRegex(ValueError, "grid is"):
            self.mg.check_axes(self.axes(lons=small), self.axes(lons=small), T0)

    def test_crop_index_rejects_empty_or_split_selections(self):
        with self.assertRaises(ValueError):
            self.mg.crop_index(self.np.array([1.0, 2.0]), 13.0, 17.5)

    def test_permanent_errors_are_not_retried(self):
        calls = []

        def fail():
            calls.append(1)
            raise RuntimeError("Invalid username or password")

        with self.assertRaises(RuntimeError):
            self.mg.with_retries(fail, attempts=3, pause=0, sleep=lambda s: None)
        self.assertEqual(len(calls), 1)

    def test_transient_errors_are_retried_then_succeed(self):
        calls, sleeps = [], []

        def flaky():
            calls.append(1)
            if len(calls) < 3:
                raise ConnectionError("temporarily unavailable")
            return "ok"

        self.assertEqual(self.mg.with_retries(flaky, attempts=3, pause=30, sleep=sleeps.append), "ok")
        self.assertEqual((len(calls), sleeps), (3, [30, 30]))

    def test_transient_errors_give_up_after_the_last_attempt(self):
        calls = []

        def always():
            calls.append(1)
            raise ConnectionError("down")

        with self.assertRaises(ConnectionError):
            self.mg.with_retries(always, attempts=3, pause=0, sleep=lambda s: None)
        self.assertEqual(len(calls), 3)

    def test_missing_credentials_or_a_bad_timestamp_fail_cleanly(self):
        saved = {k: os.environ.pop(k, None) for k in
                 ("COPERNICUSMARINE_SERVICE_USERNAME", "COPERNICUSMARINE_SERVICE_PASSWORD")}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                self.assertEqual(self.mg.main(["--timestamp", "2026112318", "--outdir", tmp]), 1)
                self.assertEqual(self.mg.main(["--timestamp", "nonsense", "--outdir", tmp]), 1)
        finally:
            for k, v in saved.items():
                if v is not None:
                    os.environ[k] = v


@NEEDS_ECCODES
class WriteGribTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import eccodes
        import numpy as np
        import grib_validate
        import marine_grib
        cls.ec, cls.np, cls.gv, cls.mg = eccodes, np, grib_validate, marine_grib

    def test_header_contract_matches_the_wind_file(self):
        np, ec = self.np, self.ec
        lons, lats = np.array([13.0, 13.0417, 13.0833]), np.array([42.5208, 42.5625])
        data = {}
        for name, _, _, _ in self.mg.FIELDS:
            arr = 1.0 + 0.1 * np.arange(12, dtype=float).reshape(2, 2, 3)  # varying: a constant field packs with 0 bits
            arr[:, 0, 0] = np.nan
            data[name] = arr
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "m.grb")
            self.assertEqual(self.mg.write_grib(path, data, lons, lats, T0), 22)
            seen = []
            with open(path, "rb") as f:
                while True:
                    h = ec.codes_grib_new_from_file(f)
                    if h is None:
                        break
                    ec.codes_set(h, "missingValue", 9999.0)
                    seen.append({
                        k: ec.codes_get_long(h, k) for k in (
                            "editionNumber", "centre", "subCentre", "table2Version", "generatingProcessIdentifier",
                            "gridDefinition", "dataDate", "dataTime", "stepUnits", "timeRangeIndicator", "P1", "P2",
                            "indicatorOfParameter", "indicatorOfTypeOfLevel", "level", "Ni", "Nj", "jScansPositively",
                            "iDirectionIncrementGiven", "jDirectionIncrementGiven", "bitmapPresent", "bitsPerValue")
                    })
                    seen[-1]["values"] = ec.codes_get_values(h)
                    ec.codes_release(h)
        self.assertEqual(len(seen), 22)
        for m in seen:
            self.assertEqual((m["editionNumber"], m["centre"], m["subCentre"], m["table2Version"],
                              m["generatingProcessIdentifier"], m["gridDefinition"]), (1, 89, 0, 1, 2, 255))
            self.assertEqual((m["dataDate"], m["dataTime"]), (20261123, 1800))
            self.assertEqual((m["stepUnits"], m["timeRangeIndicator"], m["P2"]), (1, 0, 0))
            self.assertEqual((m["Ni"], m["Nj"], m["jScansPositively"]), (3, 2, 1))
            self.assertEqual((m["iDirectionIncrementGiven"], m["jDirectionIncrementGiven"]), (0, 0))
            self.assertEqual((m["bitmapPresent"], m["bitsPerValue"], m["level"]), (1, 12, 0))
            self.assertEqual(m["values"][0], 9999.0)  # the land point stays missing
        self.assertEqual([m["P1"] for m in seen[:2]], [0, 1])
        self.assertEqual([m["indicatorOfParameter"] for m in seen[::2]], [f[1] for f in self.mg.FIELDS])
        self.assertEqual([m["indicatorOfTypeOfLevel"] for m in seen[::2]], [f[2] for f in self.mg.FIELDS])

    def test_a_full_size_file_has_the_expected_shape_and_passes_validation(self):
        np = self.np
        lons, lats = np.array(region.MARINE_LONS), np.array(region.MARINE_LATS)
        steps = region.MARINE_HOURS + 1
        land = np.zeros((len(lats), len(lons)), dtype=bool)
        land[:, :40] = True  # 37 % land
        data = {}
        for name, _, _, _ in self.mg.FIELDS:
            base = 120.0 if name.startswith("VM") else 0.5
            arr = np.full((steps, len(lats), len(lons)), base)
            arr[:, land] = np.nan
            data[name] = arr
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "m.grb")
            self.assertEqual(self.mg.write_grib(path, data, lons, lats, T0), 11 * steps)
            self.gv.validate_marine(path, "2026112318")
            self.assertLess(os.path.getsize(path), 8e6)


@unittest.skipUnless(HAVE_NETCDF and HAVE_NUMPY, "needs xarray, h5netcdf, h5py and numpy")
class LoadDataTests(unittest.TestCase):
    """Reads small synthetic NetCDF files shaped like the Copernicus subsets, including the extra edge
    points a padded request returns and the 2e-6 degree longitude offset of the wave dataset."""

    @classmethod
    def setUpClass(cls):
        import numpy as np
        import xarray as xr
        import marine_grib
        cls.np, cls.xr, cls.mg = np, xr, marine_grib

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def write(self, name, variables, lon_offset=0.0, system="SYSTEM", dims=("time", "latitude", "longitude"),
              time_shift_minutes=0):
        np = self.np
        lons = np.array([12.9583] + list(region.MARINE_LONS) + [17.5417]) + lon_offset  # one point outside each side
        lats = np.array(list(region.MARINE_LATS) + [45.4375])
        times = self.mg.expected_times(T0).astype("datetime64[ns]") + np.timedelta64(time_shift_minutes, "m")
        base = (1000 * np.arange(lats.size)[:, None] + np.arange(lons.size)[None, :]).astype("float32")
        arr = np.broadcast_to(base, (times.size, lats.size, lons.size)).copy()
        arr[:, 5, 10] = np.nan  # a land point inside the region
        if dims[0] == "latitude":
            arr = arr.transpose(1, 0, 2)
        dataset = self.xr.Dataset({v: (dims, arr) for v in variables},
                                  coords={"time": times, "latitude": lats, "longitude": lons}, attrs={"source": system})
        path = os.path.join(self.tmp.name, name)
        dataset.to_netcdf(path, engine="h5netcdf")
        return path

    def paths(self, **kwargs):
        wave_names = [f[0] for f in self.mg.FIELDS if f[3] == "waves"]
        return (self.write("cur.nc", ["uo", "vo"], system="SYS-C", **{k: v for k, v in kwargs.items() if k != "wave"}),
                self.write("wav.nc", wave_names, lon_offset=1.9e-6, system="SYS-W", **kwargs.get("wave", {})))

    def test_edge_points_are_cropped_and_the_values_land_on_the_right_cells(self):
        data, lons, lats, systems = self.mg.load_data(*self.paths(), T0)
        self.assertEqual((lons.size, lats.size), (region.MARINE_NX, region.MARINE_NY))
        for name, _, _, _ in self.mg.FIELDS:
            self.assertEqual(data[name].shape, (region.MARINE_HOURS + 1, region.MARINE_NY, region.MARINE_NX))
        uo = data["uo"][0]
        self.assertEqual(uo[0, 0], 1.0)  # full grid cell (row 0, column 1): one extra column lies west of the region
        self.assertEqual(uo[-1, -1], 1000 * 69 + 109)  # the extra row and column beyond the region are gone
        self.assertTrue(self.np.isnan(uo[5, 9]))  # the land point moved one column west with the crop
        self.assertEqual(int(self.np.isnan(uo).sum()), 1)
        self.assertAlmostEqual(float(lons[0]), 13.0, places=4)
        self.assertAlmostEqual(float(lats[-1]), 45.3958, places=3)

    def test_the_model_system_of_each_file_is_returned(self):
        _, _, _, systems = self.mg.load_data(*self.paths(), T0)
        self.assertEqual(systems, {"currents": "SYS-C", "waves": "SYS-W"})

    def test_a_time_axis_shifted_by_half_an_hour_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "time axis"):
            self.mg.load_data(*self.paths(time_shift_minutes=30), T0)

    def test_unexpected_dimension_order_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unexpected dimensions"):
            self.mg.load_data(*self.paths(dims=("latitude", "time", "longitude")), T0)

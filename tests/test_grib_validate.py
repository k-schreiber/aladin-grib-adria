import os
import tempfile
import unittest
from datetime import datetime, timezone

from tests.helpers import HAVE_ECCODES, HAVE_NUMPY, write_grib1

NEEDS = unittest.skipUnless(HAVE_ECCODES and HAVE_NUMPY, "needs eccodes and numpy")
TS = "2026112318"


@NEEDS
class WindValidationTests(unittest.TestCase):
    LONS = [13.0, 15.25, 17.5]
    LATS = [42.5, 45.4]
    BASE = {2: 101325.0, 31: 180.0, 32: 5.0, 130: 1.0, 131: -1.0, 11: 285.0}
    STEPS = 3

    @classmethod
    def setUpClass(cls):
        import grib_validate
        cls.gv = grib_validate

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "wind.grb")

    def messages(self, skip=None, ts=TS, values=None):
        out = []
        for param, base in self.BASE.items():
            for step in range(self.STEPS):
                if skip == (param, step):
                    continue
                v = (values or {}).get((param, step)) or [base + i for i in range(6)]
                out.append(dict(param=param, step=step, ts=ts, lons=self.LONS, lats=self.LATS, values=v))
        return out

    def validate(self):
        self.gv.validate_wind(self.path, TS, ni=3, nj=2, steps=self.STEPS)

    def test_a_complete_file_passes_including_pressure_far_above_the_missing_sentinel(self):
        write_grib1(self.path, self.messages())
        self.validate()  # MSLP 101325 Pa must not be mistaken for the 9999 missing-value marker

    def test_direction_overshoot_from_packing_is_accepted(self):
        write_grib1(self.path, self.messages(values={(31, 1): [360.04] * 6}))
        self.validate()

    def test_a_missing_step_is_rejected(self):
        write_grib1(self.path, self.messages(skip=(32, 1)))
        with self.assertRaisesRegex(self.gv.ValidationError, "parameter 32: steps"):
            self.validate()

    def test_a_missing_parameter_is_rejected(self):
        write_grib1(self.path, [m for m in self.messages() if m["param"] != 11])
        with self.assertRaisesRegex(self.gv.ValidationError, "parameters"):
            self.validate()

    def test_wrong_reference_time_is_rejected(self):
        write_grib1(self.path, self.messages(ts="2026112400"))
        with self.assertRaisesRegex(self.gv.ValidationError, "reference time"):
            self.validate()

    def test_a_field_without_any_valid_value_is_rejected(self):
        write_grib1(self.path, self.messages(values={(32, 1): [None] * 6}))
        with self.assertRaisesRegex(self.gv.ValidationError, "no valid value"):
            self.validate()

    def test_out_of_range_values_are_rejected(self):
        write_grib1(self.path, self.messages(values={(32, 0): [500.0] * 6}))
        with self.assertRaisesRegex(self.gv.ValidationError, "outside"):
            self.validate()

    def test_wrong_grid_size_is_rejected(self):
        write_grib1(self.path, self.messages())
        with self.assertRaisesRegex(self.gv.ValidationError, "grid size"):
            self.gv.validate_wind(self.path, TS, ni=4, nj=2, steps=self.STEPS)

    def test_grib2_is_rejected(self):
        write_grib1(self.path, [dict(edition=2)])
        with self.assertRaisesRegex(self.gv.ValidationError, "edition"):
            self.validate()

    def test_both_time_range_encodings_of_cdo_are_accepted(self):
        write_grib1(self.path, [dict(m, trange=10) for m in self.messages()])
        self.validate()


@NEEDS
class MarineValidationTests(unittest.TestCase):
    LONS = [13.0, 13.1, 13.2, 13.3]
    LATS = [42.5, 42.6]
    STEPS = 3

    @classmethod
    def setUpClass(cls):
        import numpy as np
        import grib_validate
        import marine_grib
        cls.np, cls.gv, cls.mg = np, grib_validate, marine_grib

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "marine.grb")
        self.lons, self.lats = self.np.array(self.LONS), self.np.array(self.LATS)

    def data(self, mutate=None):
        np = self.np
        mask = np.zeros((self.STEPS, 2, 4), dtype=bool)
        mask[:, 0, :2] = True  # 2 of 8 points, then one more below: 3 land points = 0.375
        mask[:, 1, 0] = True
        data = {}
        for name, _, _, source in self.mg.FIELDS:
            values = np.full((self.STEPS, 2, 4), 0.5)
            if name.startswith("VM"):
                values = np.full((self.STEPS, 2, 4), 120.0)
            values[mask] = np.nan
            data[name] = values
        if mutate:
            mutate(data)
        return data

    def write(self, **kwargs):
        t0 = datetime(2026, 11, 23, 18, tzinfo=timezone.utc)
        self.mg.write_grib(self.path, self.data(**kwargs), self.lons, self.lats, t0)

    def validate(self):
        self.gv.validate_marine(self.path, TS, lons=self.lons, lats=self.lats, steps=self.STEPS)

    def test_what_write_grib_writes_passes(self):
        self.write()
        self.validate()

    def test_a_mask_that_changes_between_steps_is_rejected(self):
        def mutate(data):
            data["VHM0"][1, 1, 3] = self.np.nan
        self.write(mutate=mutate)
        with self.assertRaisesRegex(self.gv.ValidationError, "mask changes"):
            self.validate()

    def test_a_file_without_land_is_rejected(self):
        def mutate(data):
            for arr in data.values():
                arr[:] = 0.5
        self.write(mutate=mutate)
        with self.assertRaisesRegex(self.gv.ValidationError, "missing share"):
            self.validate()

    def test_implausible_wave_height_is_rejected(self):
        def mutate(data):
            data["VHM0"][0, 1, 3] = 40.0
        self.write(mutate=mutate)
        with self.assertRaisesRegex(self.gv.ValidationError, "parameter 100"):
            self.validate()

    def test_directions_up_to_360_5_are_accepted(self):
        def mutate(data):
            data["VMDR"][0, 1, 3] = 360.04
        self.write(mutate=mutate)
        self.validate()

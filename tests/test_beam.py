"""Independent checks of the closed-form beam equations."""

from __future__ import annotations

import unittest

from metron.beam import (
    beam_mass,
    maximum_bending_stress,
    second_moment_of_area,
    tip_deflection,
    yield_safety_factor,
)


class ReferenceCalculationTests(unittest.TestCase):
    """Hand-checkable reference values from the milestone brief."""

    def test_reference_second_moment(self) -> None:
        inertia = second_moment_of_area(width_m=0.020, thickness_m=0.004)
        self.assertAlmostEqual(inertia, 1.0666666666666667e-10, places=22)

    def test_reference_stress_is_18_75_mpa(self) -> None:
        stress = maximum_bending_stress(
            force_n=10.0,
            length_m=0.100,
            width_m=0.020,
            thickness_m=0.004,
        )
        self.assertAlmostEqual(stress, 18.75e6, places=6)

    def test_reference_deflection_is_0_446429_mm(self) -> None:
        deflection = tip_deflection(
            force_n=10.0,
            length_m=0.100,
            width_m=0.020,
            thickness_m=0.004,
            elastic_modulus_pa=70.0e9,
        )
        self.assertAlmostEqual(deflection * 1000.0, 0.4464285714285715, places=12)

    def test_reference_mass_is_21_6_g(self) -> None:
        mass = beam_mass(
            density_kg_m3=2700.0,
            width_m=0.020,
            thickness_m=0.004,
            length_m=0.100,
        )
        self.assertAlmostEqual(mass * 1000.0, 21.6, places=12)

    def test_reference_safety_factor_is_8(self) -> None:
        safety = yield_safety_factor(
            yield_strength_pa=150.0e6,
            bending_stress_pa=18.75e6,
        )
        self.assertAlmostEqual(safety, 8.0, places=12)


class ScalingLawTests(unittest.TestCase):
    def test_doubling_force_doubles_stress_and_deflection(self) -> None:
        stress_10n = maximum_bending_stress(10.0, 0.100, 0.020, 0.004)
        stress_20n = maximum_bending_stress(20.0, 0.100, 0.020, 0.004)
        deflection_10n = tip_deflection(10.0, 0.100, 0.020, 0.004, 70.0e9)
        deflection_20n = tip_deflection(20.0, 0.100, 0.020, 0.004, 70.0e9)

        self.assertAlmostEqual(stress_20n / stress_10n, 2.0, places=12)
        self.assertAlmostEqual(deflection_20n / deflection_10n, 2.0, places=12)

    def test_doubling_thickness_reduces_stress_by_four(self) -> None:
        stress_2mm = maximum_bending_stress(10.0, 0.100, 0.020, 0.002)
        stress_4mm = maximum_bending_stress(10.0, 0.100, 0.020, 0.004)

        self.assertAlmostEqual(stress_2mm / stress_4mm, 4.0, places=12)

    def test_doubling_thickness_reduces_deflection_by_eight(self) -> None:
        deflection_2mm = tip_deflection(10.0, 0.100, 0.020, 0.002, 70.0e9)
        deflection_4mm = tip_deflection(10.0, 0.100, 0.020, 0.004, 70.0e9)

        self.assertAlmostEqual(deflection_2mm / deflection_4mm, 8.0, places=12)

    def test_mass_scales_linearly_with_thickness(self) -> None:
        mass_2mm = beam_mass(2700.0, 0.020, 0.002, 0.100)
        mass_4mm = beam_mass(2700.0, 0.020, 0.004, 0.100)

        self.assertAlmostEqual(mass_4mm / mass_2mm, 2.0, places=12)


class FunctionGuardTests(unittest.TestCase):
    def test_non_positive_dimension_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            second_moment_of_area(0.020, 0.0)

    def test_non_finite_property_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            tip_deflection(10.0, 0.100, 0.020, 0.004, float("inf"))


if __name__ == "__main__":
    unittest.main()

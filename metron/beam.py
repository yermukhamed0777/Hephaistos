"""Closed-form Euler-Bernoulli cantilever calculations, all in SI units.

Sign convention: the beam runs along +x from an ideal clamp at x = 0 to a free
end at x = L. A positive transverse force F acts in -y at the free end.
The thickness t is measured along y (the bending direction), and the width b
is measured along z, perpendicular to the load.

Only nominal, linear-elastic, small-deflection behaviour is represented.
"""

from __future__ import annotations

import math


def _positive(name: str, value: float) -> float:
    """Return a finite, positive float or raise a clear ValueError."""
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite positive number; got {value!r}") from exc
    if not math.isfinite(number) or number <= 0.0:
        raise ValueError(f"{name} must be finite and > 0; got {value!r}")
    return number


def second_moment_of_area(width_m: float, thickness_m: float) -> float:
    """Second moment of area about the horizontal neutral axis, I = b t^3 / 12."""
    b = _positive("width_m", width_m)
    t = _positive("thickness_m", thickness_m)
    return b * t**3 / 12.0


def maximum_bending_stress(
    force_n: float,
    length_m: float,
    width_m: float,
    thickness_m: float,
) -> float:
    """Maximum nominal bending stress at the fixed end, sigma = F L (t/2) / I."""
    force = _positive("force_n", force_n)
    length = _positive("length_m", length_m)
    inertia = second_moment_of_area(width_m, thickness_m)
    thickness = _positive("thickness_m", thickness_m)
    return force * length * (thickness / 2.0) / inertia


def tip_deflection(
    force_n: float,
    length_m: float,
    width_m: float,
    thickness_m: float,
    elastic_modulus_pa: float,
) -> float:
    """Downward tip deflection, delta = F L^3 / (3 E I)."""
    force = _positive("force_n", force_n)
    length = _positive("length_m", length_m)
    modulus = _positive("elastic_modulus_pa", elastic_modulus_pa)
    inertia = second_moment_of_area(width_m, thickness_m)
    return force * length**3 / (3.0 * modulus * inertia)


def beam_mass(
    density_kg_m3: float,
    width_m: float,
    thickness_m: float,
    length_m: float,
) -> float:
    """Mass of a rectangular prismatic beam, m = rho b t L."""
    density = _positive("density_kg_m3", density_kg_m3)
    b = _positive("width_m", width_m)
    t = _positive("thickness_m", thickness_m)
    length = _positive("length_m", length_m)
    return density * b * t * length


def yield_safety_factor(yield_strength_pa: float, bending_stress_pa: float) -> float:
    """Yield safety factor, SF = S_y / sigma_max."""
    strength = _positive("yield_strength_pa", yield_strength_pa)
    stress = _positive("bending_stress_pa", bending_stress_pa)
    return strength / stress

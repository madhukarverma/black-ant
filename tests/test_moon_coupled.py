"""The Moon as a full body: the real J2000 baseline and the Moon beside the live Earth tow.
Full runs: `uv run python -m sim.scenarios.baseline` and `uv run python -m sim.scenarios.moon_coupled`."""

import numpy as np
import pytest

from sim.bodies import move_to_barycentre, real_planets, split_earth_moon
from sim.config import load_config
from sim.scenarios.baseline import build, integrate
from sim.scenarios.moon_coupled import run as coupled

CFG = load_config()


def test_split_keeps_the_barycentre_and_puts_the_moon_where_jpl_does():
    earth_cfg = [p for p in CFG["planets"] if p["name"] == "earth"]
    joint = real_planets(earth_cfg)
    split = real_planets(earth_cfg)
    split_earth_moon(split, CFG["moon"])
    e, m = split.index("earth"), split.index("moon")
    bary = (split.m[e] * split.pos[e] + split.m[m] * split.pos[m]) / (split.m[e] + split.m[m])
    bary_v = (split.m[e] * split.vel[e] + split.m[m] * split.vel[m]) / (split.m[e] + split.m[m])
    assert np.allclose(bary, joint.pos[1], rtol=0, atol=1e-3)        # metres
    assert np.allclose(bary_v, joint.vel[1], rtol=0, atol=1e-9)      # m/s
    d = np.linalg.norm(split.pos[m] - split.pos[e]) / 1e3
    assert d == pytest.approx(402_449, abs=50)                       # JPL Horizons, 2000-01-01 12:00 TDB


def test_baseline_moon_stays_bound_and_energy_holds():
    system = build(CFG, "planets")
    out = integrate(system, 0.5, CFG["baseline"]["dt_hours"] * 3600)
    print(f"Baseline 0.5 yr: energy {out['energy_error_max']:.1e}, Moon {out['moon_closest_km']:,.0f}-"
          f"{out['moon_farthest_km']:,.0f} km, month {out['moon_sidereal_month_days']:.3f} d")
    assert out["moon_bound"]
    assert out["energy_error_max"] < 1e-9
    assert 355_000 < out["moon_closest_km"] < 365_000 and 400_000 < out["moon_farthest_km"] < 408_000
    assert out["moon_sidereal_month_days"] == pytest.approx(27.32, abs=0.1)


def test_moon_beside_the_live_tow_short_window():
    out = coupled(years=0.25, epochs=[1.0])
    e = out["epochs"][0]
    print(f"Coupled 0.25 yr: Moon change {e['moon_distance_change']:.3%}, beam +{e['beam_peak_increase_from_moon']:.1%}, "
          f"off spot {e['moon_body_with_tow']['spot_error_max_km']:,.0f} km")
    assert e["checks"]["moon_stays_bound"] and e["checks"]["moon_distance_change_within_limit"]
    assert e["checks"]["asteroid_on_spot"] and e["checks"]["beam_misses_the_moon"]
    assert e["beam_peak_increase_from_moon"] > 0.05      # the Moon's pull on the asteroid is real and costs power


@pytest.mark.slow
def test_moon_beside_the_live_tow_all_epochs():
    out = coupled()
    for e in out["epochs"]:
        assert all(e["checks"].values()), (e["earth_au"], e["checks"])

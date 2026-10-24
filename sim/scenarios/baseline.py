"""The baseline: the real Sun, planets, Earth and Moon from J2000.0 with no push at all.

This is the guide's first milestone (section 5, hours 2-8: "Sun-Earth-Moon baseline with real initial
conditions"), the baseline due at the mid-point check-in, and the baseline drift for the conservation record.

Earth and the Moon are separate bodies here. Their pair starts on the Earth-Moon barycentre's J2000 orbit
(config.yaml planets), split using the Moon's real J2000 offset from JPL Horizons (sim/bodies.py).
The step is short (15 minutes) because the Moon goes round Earth in 27 days.

Reported:
- energy, momentum and angular momentum drift over the run (nothing pushes, so all three should hold);
- the Moon: closest and farthest distance, its month (sidereal), and that it stays bound to Earth;
- the Earth-Moon barycentre's year (benchmark 6: 365.256 days);
- convergence: the same run with the step halved, and how far the answers move (guide section 2.6).

Run from the project root:
    uv run python -m sim.scenarios.baseline                    # 10 years, planets included -> results/baseline.json
    uv run python -m sim.scenarios.baseline --bodies sem       # Sun, Earth and Moon only
    uv run python -m sim.scenarios.baseline --years 2 --out out
"""

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np

from ..bodies import System, move_to_barycentre, real_planets, split_earth_moon
from ..config import ROOT, load_config
from ..constants import AU, DAY, G, M_SUN, YEAR
from ..integrator import energy, gravity

MOON_SIDEREAL_MONTH_DAYS = 27.321661   # reference values, for comparison only (never fed into the run)
EMB_SIDEREAL_YEAR_DAYS = 365.256363


def build(cfg: dict, bodies: str = "planets") -> System:
    """Sun + planets (or just the Earth-Moon pair) on their real J2000 orbits, with Earth and Moon split."""
    planets = cfg["planets"] if bodies == "planets" else [p for p in cfg["planets"] if p["name"] == "earth"]
    system = real_planets(planets)
    split_earth_moon(system, cfg["moon"])
    move_to_barycentre(system)
    return system


def angular_momentum(m: np.ndarray, pos: np.ndarray, vel: np.ndarray) -> np.ndarray:
    return (m[:, None] * np.cross(pos, vel)).sum(axis=0)


def integrate(system: System, years: float, dt: float, measure: bool = True) -> dict:
    """Leapfrog (kick, drift, kick) with gravity only. Returns what was measured along the way."""
    m, pos, vel = system.m, system.pos, system.vel
    sun, earth, moon = system.index("sun"), system.index("earth"), system.index("moon")
    m_e, m_m = m[earth], m[moon]
    steps = round(years * YEAR / dt)
    e0 = energy(m, pos, vel)
    p0 = m @ vel
    l0 = angular_momentum(m, pos, vel)
    p_scale = float((m * np.linalg.norm(vel, axis=1)).sum())
    l_scale = float(np.linalg.norm(l0))

    def rel():
        return pos[moon] - pos[earth]

    def bary_angle():
        b = (m_e * pos[earth] + m_m * pos[moon]) / (m_e + m_m) - pos[sun]
        return math.atan2(b[1], b[0])

    r = rel()
    d_min = d_max = float(np.linalg.norm(r))
    d_sum, n_d = 0.0, 0
    moon_angle, last_m = 0.0, math.atan2(r[1], r[0])
    year_angle, last_y = 0.0, bary_angle()
    year_days = None
    hill_min_margin = math.inf
    e_err = p_err = l_err = 0.0
    every = max(1, round(DAY / dt))  # conservation checks once a simulated day
    acc = gravity(m, pos)
    for n in range(1, steps + 1):
        vel += acc * (dt / 2)
        pos += vel * dt
        acc = gravity(m, pos)
        vel += acc * (dt / 2)
        if not measure:
            continue
        r = rel()
        d = math.sqrt(float(r @ r))
        d_min, d_max = min(d_min, d), max(d_max, d)
        d_sum += d
        n_d += 1
        a = math.atan2(r[1], r[0])
        moon_angle += (a - last_m + math.pi) % (2 * math.pi) - math.pi
        last_m = a
        a = bary_angle()
        step = (a - last_y + math.pi) % (2 * math.pi) - math.pi
        if year_days is None and year_angle + step >= 2 * math.pi:
            frac = (2 * math.pi - year_angle) / step  # interpolate within the step
            year_days = ((n - 1) + frac) * dt / DAY
        year_angle += step
        last_y = a
        if n % every == 0:
            r_sun = float(np.linalg.norm(pos[earth] - pos[sun]))
            hill = r_sun * ((m_e + m_m) / (3 * M_SUN)) ** (1 / 3)
            hill_min_margin = min(hill_min_margin, hill / d)
            e_err = max(e_err, abs(energy(m, pos, vel) / e0 - 1))
            p_err = max(p_err, float(np.linalg.norm(m @ vel - p0)) / p_scale)
            l_err = max(l_err, float(np.linalg.norm(angular_momentum(m, pos, vel) - l0)) / l_scale)
    out = {"steps": steps, "earth_moon_m": (pos[moon] - pos[earth]).copy(), "earth_pos_m": (pos[earth] - pos[sun]).copy()}
    if measure:
        # Is the Moon bound to Earth at the end? Its energy relative to Earth must be negative.
        v_rel = vel[moon] - vel[earth]
        r = rel()
        two_body = 0.5 * float(v_rel @ v_rel) - G * (m_e + m_m) / float(np.linalg.norm(r))
        out.update({
            "energy_error_max": e_err, "momentum_error_max": p_err, "angular_momentum_error_max": l_err,
            "moon_closest_km": d_min / 1e3, "moon_farthest_km": d_max / 1e3, "moon_mean_km": d_sum / max(n_d, 1) / 1e3,
            "moon_sidereal_month_days": years * YEAR / DAY / (moon_angle / (2 * math.pi)),
            "earth_moon_year_days": year_days,
            "moon_bound": bool(two_body < 0 and hill_min_margin > 1),
            "hill_sphere_over_moon_distance_min": hill_min_margin,
        })
    return out


def convergence(cfg: dict, bodies: str, years: float, dt: float) -> dict:
    """Same start, step h and h/2: how far do Earth and the Moon end up apart?"""
    a = integrate(build(cfg, bodies), years, dt, measure=False)
    b = integrate(build(cfg, bodies), years, dt / 2, measure=False)
    moon_diff = float(np.linalg.norm(a["earth_moon_m"] - b["earth_moon_m"]))
    earth_diff = float(np.linalg.norm(a["earth_pos_m"] - b["earth_pos_m"]))
    # Leapfrog's error shrinks as h^2, so the h/2 answer is about 4 times closer to the truth than the h answer;
    # the difference is then about 3/4 of the h answer's own error.
    return {"years": years, "dt_hours": dt / 3600, "earth_position_change_km": earth_diff / 1e3,
            "moon_offset_change_km": moon_diff / 1e3,
            "moon_offset_change_share": moon_diff / float(np.linalg.norm(b["earth_moon_m"])),
            "estimated_error_km_at_h": {"earth": earth_diff * 4 / 3 / 1e3, "moon_offset": moon_diff * 4 / 3 / 1e3}}


def run(cfg: dict | None = None, years: float | None = None, bodies: str = "planets", dt_hours: float | None = None,
        convergence_years: float | None = None) -> dict:
    cfg = cfg or load_config()
    b = cfg["baseline"]
    years = b["years"] if years is None else years
    dt = (b["dt_hours"] if dt_hours is None else dt_hours) * 3600
    started = time.time()
    system = build(cfg, bodies)
    names = list(system.names)
    m = integrate(system, years, dt)
    m = {k: v for k, v in m.items() if not isinstance(v, np.ndarray)}
    conv = convergence(cfg, bodies, b["convergence_years"] if convergence_years is None else convergence_years, dt)
    checks = {
        "energy_constant": m["energy_error_max"] <= b["energy_error_max"],
        "moon_bound": m["moon_bound"],
        "earth_moon_year_within_0.1_day": m["earth_moon_year_days"] is not None
                                          and abs(m["earth_moon_year_days"] - EMB_SIDEREAL_YEAR_DAYS) <= 0.1,
        "moon_month_within_0.1_day": abs(m["moon_sidereal_month_days"] - MOON_SIDEREAL_MONTH_DAYS) <= 0.1,
        "converged_moon_offset_under_0.1pct": conv["moon_offset_change_share"] <= 1e-3,
    }
    return {"settings": {"bodies": names, "years": years, "dt_hours": dt / 3600,
                         "start": "J2000.0; planets from JPL approximate elements, Moon offset from JPL Horizons (DE441)",
                         "push": "none"},
            "measured": m,
            "reference": {"moon_sidereal_month_days": MOON_SIDEREAL_MONTH_DAYS,
                          "earth_moon_year_days": EMB_SIDEREAL_YEAR_DAYS,
                          "moon_distance_range_km": [356400, 406700]},
            "convergence": conv, "checks": {k: bool(v) for k, v in checks.items()}, "all_pass": bool(all(checks.values())),
            "run_seconds": round(time.time() - started, 1)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Unpushed baseline: Sun, planets, Earth and Moon from J2000.")
    parser.add_argument("--years", type=float, help="length of the run (default: config.yaml baseline.years)")
    parser.add_argument("--bodies", choices=["planets", "sem"], default="planets",
                        help="planets: Sun, Venus-Neptune, Earth, Moon; sem: Sun, Earth and Moon only")
    parser.add_argument("--dt-hours", type=float, help="step (default: config.yaml baseline.dt_hours)")
    parser.add_argument("--out", default="results", help="folder for baseline.json (default: results)")
    args = parser.parse_args()
    out = run(years=args.years, bodies=args.bodies, dt_hours=args.dt_hours)
    m, c = out["measured"], out["convergence"]
    print(f"Baseline, {out['settings']['years']:g} years, {len(out['settings']['bodies'])} bodies, step {out['settings']['dt_hours']:g} h")
    print(f"  energy drift      {m['energy_error_max']:.2e}   momentum {m['momentum_error_max']:.2e}   "
          f"angular momentum {m['angular_momentum_error_max']:.2e}")
    print(f"  Moon              {m['moon_closest_km']:,.0f} - {m['moon_farthest_km']:,.0f} km, month "
          f"{m['moon_sidereal_month_days']:.4f} d, bound {m['moon_bound']}")
    print(f"  Earth-Moon year   {m['earth_moon_year_days']:.4f} d (reference {EMB_SIDEREAL_YEAR_DAYS})")
    print(f"  h vs h/2 ({c['years']:g} yr)  Earth moves {c['earth_position_change_km']:.3f} km, "
          f"Moon offset {c['moon_offset_change_km']:.3f} km ({c['moon_offset_change_share']:.1e})")
    for k, v in out["checks"].items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    folder = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out
    folder.mkdir(parents=True, exist_ok=True)
    name = "baseline.json" if args.bodies == "planets" else "baseline_sem.json"
    (folder / name).write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {folder / name} in {out['run_seconds']:.0f} s")


if __name__ == "__main__":
    main()

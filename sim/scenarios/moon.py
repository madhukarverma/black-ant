"""The Moon test: does the Moon stay with Earth while the asteroid tows it?

At the start, middle and end of the journey, we step the Moon around Earth for 50 years with the
Sun's pull and the asteroid in place, then repeat without the asteroid, and compare the Moon's
closest and farthest distances from Earth.

The runs work in a frame that moves with Earth. Earth's own acceleration (from the Sun and the
asteroid) is taken off, so the Moon feels only the difference between each body's pull on the
Moon and its pull on Earth. That difference is computed exactly, not approximated.
Model limits: flat orbits; Earth circles the Sun at a fixed distance during each 50-year run; the asteroid is held
exactly on its spot and does not feel the Moon. sim/scenarios/moon_coupled.py runs the Moon as a full body with the
live tow instead.

Run from the project root:
    uv run python -m sim.scenarios.moon
    uv run python -m sim.scenarios.moon --asteroid-scale 100   # stress test: a 100 times heavier asteroid
"""

import argparse
import json
import math
import time

from ..config import ROOT, load_config
from ..constants import AU, DAY, G, GM_SUN, M_SUN, YEAR


def epochs(cfg: dict) -> dict[str, tuple[float, float]]:
    """(year, Earth's orbit size in AU) at the start, middle and end of the journey.

    Taken from the saved full journey (results/run.json, else out/run.json), otherwise from the steady-push
    formula. A quick look (one that never got near the target) is skipped, so "end" really is the end.
    """
    for path in (ROOT / "results" / "run.json", ROOT / "out" / "run.json"):
        if not path.exists():
            continue
        frames = [f for f in json.loads(path.read_text(encoding="utf-8"))["frames"] if f["earth_tow_active"]]
        if not frames or frames[-1]["earth_orbit_au"] < 0.95 * cfg["tows"][0]["stop_au"]:
            continue
        last = frames[-1]
        mid = min(frames, key=lambda f: abs(f["t"] - last["t"] / 2))
        return {"start": (0.0, frames[0]["earth_orbit_au"]), "middle": (mid["t"], mid["earth_orbit_au"]),
                "end": (last["t"], last["earth_orbit_au"])}
    tow = cfg["tows"][0]
    push = G * tow["asteroid_mass_kg"] / (tow["distance_km"] * 1e3) ** 2 * math.sqrt(0.5)  # along the orbit
    v0, v_end = math.sqrt(GM_SUN / AU), math.sqrt(GM_SUN / (tow["stop_au"] * AU))
    arrival = (v0 - v_end) / push
    v_mid = v0 - push * arrival / 2
    return {"start": (0.0, 1.0), "middle": (arrival / 2 / YEAR, GM_SUN / v_mid ** 2 / AU),
            "end": (arrival / YEAR, tow["stop_au"])}


def moon_run(earth_au: float, moon: dict, years: float, dt: float,
             asteroid_mass: float = 0.0, asteroid_distance: float = 6.371e8) -> dict:
    """Step the Moon around Earth with Earth at earth_au from the Sun. Returns the Moon's closest and
    farthest distance from Earth (km), its closest approach to the asteroid (km), and whether it left
    Earth's gravity zone (the Hill sphere)."""
    sqrt, cos, sin = math.sqrt, math.cos, math.sin
    big_r = earth_au * AU
    w = sqrt(GM_SUN / big_r ** 3)  # Earth's angular speed around the Sun
    mu = G * (moon["earth_mass_kg"] + moon["mass_kg"])
    gma = G * asteroid_mass
    k = asteroid_distance * sqrt(0.5)
    a_d3 = asteroid_distance ** 3
    r_sun3 = big_r ** 3
    hill = big_r * (moon["earth_mass_kg"] / (3 * M_SUN)) ** (1 / 3)

    def acc(x, y, t):
        r2 = x * x + y * y
        f = -mu / (r2 * sqrt(r2))
        ax, ay = f * x, f * y
        c, s = cos(w * t), sin(w * t)  # direction from the Sun to Earth
        sx, sy = -big_r * c, -big_r * s  # the Sun, seen from Earth
        dx, dy = sx - x, sy - y
        d2 = dx * dx + dy * dy
        g = GM_SUN / (d2 * sqrt(d2))
        ax += g * dx - GM_SUN * sx / r_sun3  # Sun's pull on the Moon minus its pull on Earth
        ay += g * dy - GM_SUN * sy / r_sun3
        if gma:
            px, py = k * (c - s), k * (s + c)  # asteroid: 45 degrees between ahead and away from the Sun
            dx, dy = px - x, py - y
            d2 = dx * dx + dy * dy
            g = gma / (d2 * sqrt(d2))
            ax += g * dx - gma * px / a_d3  # asteroid's pull on the Moon minus its pull on Earth
            ay += g * dy - gma * py / a_d3
        return ax, ay

    a, e = moon["a_km"] * 1e3, moon["eccentricity"]
    x, y = a * (1 + e), 0.0  # start at the Moon's farthest point, on the side away from the Sun
    vx, vy = 0.0, sqrt(mu / a * (1 - e) / (1 + e))
    t, h = 0.0, dt / 2
    ax, ay = acc(x, y, t)
    r_min = r_max = math.hypot(x, y)
    closest_asteroid = math.inf
    escaped = False
    for n in range(round(years * YEAR / dt)):
        vx += ax * h
        vy += ay * h
        x += vx * dt
        y += vy * dt
        t += dt
        ax, ay = acc(x, y, t)
        vx += ax * h
        vy += ay * h
        r = math.hypot(x, y)
        r_min, r_max = min(r_min, r), max(r_max, r)
        if gma and n % 8 == 0:
            c, s = cos(w * t), sin(w * t)
            closest_asteroid = min(closest_asteroid, math.hypot(k * (c - s) - x, k * (s + c) - y))
        if r > hill:
            escaped = True
            break
    return {"closest_km": r_min / 1e3, "farthest_km": r_max / 1e3,
            "closest_to_asteroid_km": None if math.isinf(closest_asteroid) else closest_asteroid / 1e3,
            "escaped": escaped, "hill_radius_km": hill / 1e3}


def compare(cfg: dict | None = None, years: float | None = None, asteroid_scale: float = 1.0,
            which: tuple[str, ...] = ("start", "middle", "end")) -> dict:
    """With-asteroid against no-asteroid Moon runs at each epoch, with a pass or fail against the limit."""
    cfg = cfg or load_config()
    moon = cfg["moon"]
    years = moon["years"] if years is None else years
    dt = moon["dt_minutes"] * 60
    tow = cfg["tows"][0]
    limit = cfg["safety"]["moon_distance_change_max_fraction"]
    results = {}
    for name, (year, earth_au) in epochs(cfg).items():
        if name not in which:
            continue
        base = moon_run(earth_au, moon, years, dt)
        towed = moon_run(earth_au, moon, years, dt, tow["asteroid_mass_kg"] * asteroid_scale, tow["distance_km"] * 1e3)
        change = max(abs(towed["closest_km"] / base["closest_km"] - 1), abs(towed["farthest_km"] / base["farthest_km"] - 1))
        results[name] = {"journey_year": round(year), "earth_au": round(earth_au, 4), "without_asteroid": base,
                         "with_asteroid": towed, "distance_change": change,
                         "ok": (not towed["escaped"]) and change <= limit}
    return {"settings": {"years": years, "dt_minutes": moon["dt_minutes"], "asteroid_scale": asteroid_scale,
                         "limit": limit, "model": "flat orbits; Earth at a fixed distance from the Sun in each run"},
            "epochs": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Moon test at the start, middle and end of the journey.")
    parser.add_argument("--years", type=float, help="length of each run (default: config.yaml)")
    parser.add_argument("--asteroid-scale", type=float, default=1.0, help="multiply the asteroid's mass (stress test)")
    args = parser.parse_args()
    started = time.time()
    out = compare(years=args.years, asteroid_scale=args.asteroid_scale)
    print(f"Moon test, {out['settings']['years']:g} years per run, asteroid x{args.asteroid_scale:g}")
    for name, r in out["epochs"].items():
        b, w = r["without_asteroid"], r["with_asteroid"]
        verdict = "escaped" if w["escaped"] else f"change {r['distance_change']:.4%}"
        print(f"  {name:6} year {r['journey_year']:5}  Earth {r['earth_au']:.3f} AU  "
              f"Moon {b['closest_km']:,.0f}-{b['farthest_km']:,.0f} km without, "
              f"{w['closest_km']:,.0f}-{w['farthest_km']:,.0f} km with  {verdict}  {'PASS' if r['ok'] else 'FAIL'}")
    path = ROOT / "out" / f"moon_runs_x{args.asteroid_scale:g}.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"Wrote {path} in {time.time() - started:.0f} s")


if __name__ == "__main__":
    main()

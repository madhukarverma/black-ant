"""The Moon as a full body beside the live Earth tow.

The long journey folds the Moon's mass into Earth (one body, 1-day steps). This scenario checks what that
leaves out, in short windows where everything is live at once: the Sun, Earth, the Moon, the tow asteroid,
the beam controller and E1's power budget, stepped every 30 minutes.

Two things are tested:
1. The Moon stays with Earth: its closest and farthest distance with the tow, against the same window
   without the asteroid (guide section 2.5 and the "Ignoring the Moon" mistake in section 8).
2. The tow still works with the Moon there. The Moon also pulls on the asteroid (up to about 12% as hard as
   Earth does, once a month), so the beam must do more. We compare beam power and the asteroid's drift off its
   spot with the Moon as a body against the journey's model (Moon folded into Earth), and against the power
   left for the Earth tow inside E1's 1e26 W.

Each window runs four times: Moon as a body with the asteroid (inside the power left by E1), the same with no
power limit (to see what the tow would ask for), Moon folded into Earth with the asteroid (the journey's model),
and Moon as a body without the asteroid. At 1.0 AU the start is the real J2000 Earth and Moon. At later epochs the
Earth-Moon pair is placed on a circular orbit of that size, with the Moon's real J2000 offset from Earth.
Model limits: no planets; no arrival-trim shape (the asteroid sits on its plain 45-degree spot).

Run from the project root:
    uv run python -m sim.scenarios.moon_coupled            # epochs from config.yaml -> results/moon_coupled.json
    uv run python -m sim.scenarios.moon_coupled --years 1 --epochs 1.0
"""

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np

from ..bodies import circular_planets, move_to_barycentre, real_planets, split_earth_moon
from ..config import ROOT, load_config
from ..constants import AU, DAY, G, YEAR
from ..forces import Beam, Tow, beam_for, ray_distance, spot
from ..integrator import gravity
from ..ledger import Ledger

MOON_RADIUS_KM = 1737.4


def middle_epoch_au(cfg: dict) -> tuple[float, str]:
    """Earth's orbit size halfway through the tow, from the latest saved journey."""
    for path in (ROOT / "results" / "run.json", ROOT / "out" / "run.json"):
        if path.exists():
            frames = [f for f in json.loads(path.read_text(encoding="utf-8"))["frames"] if f["earth_tow_active"]]
            if frames and frames[-1]["earth_orbit_au"] > 2.5:  # a full journey, not a quick look
                mid = min(frames, key=lambda f: abs(f["t"] - frames[-1]["t"] / 2))
                return mid["earth_orbit_au"], f"{path.relative_to(ROOT)} year {mid['t']:.0f}"
    return 1.85, "fallback (no full journey saved)"


def earth_tow_cap(cfg: dict) -> tuple[float, str]:
    """Power E1 leaves for the Earth tow: the total limit minus the most the Mars tow drew in the journey."""
    limit = cfg["beam"]["total_limit_w"]
    path = ROOT / "results" / "summary.json"
    if path.exists():
        mars = json.loads(path.read_text(encoding="utf-8")).get("tows", {}).get("mars-tow")
        if mars and mars.get("beam_max_w"):
            return limit - mars["beam_max_w"], "E1 limit minus the Mars tow's peak in results/summary.json"
    mars_cfg = next(t for t in cfg["tows"] if t["name"] == "mars-tow")
    return limit - mars_cfg["max_beam_w"], "E1 limit minus the Mars tow's own cap (config.yaml)"


def build(cfg: dict, earth_au: float, moon_body: bool, asteroid: bool):
    earth_cfg = next(p for p in cfg["planets"] if p["name"] == "earth")
    if earth_au == 1.0:
        system = real_planets([earth_cfg])
    else:
        system = circular_planets([{**earth_cfg, "a_au": earth_au}])
    if moon_body:
        split_earth_moon(system, cfg["moon"])
    earth = system.index("earth")
    tow = None
    if asteroid:
        t = next(t for t in cfg["tows"] if t["name"] == "earth-tow")
        distance = t["distance_km"] * 1e3
        p, v, _ = spot(system.pos, system.vel, np.zeros_like(system.pos), 0, earth, distance)
        idx = system.add(t["name"], t["asteroid_mass_kg"], p, v)
        tow = Tow(t["name"], earth, idx, t["asteroid_mass_kg"], distance, 99.0, t["max_beam_w"])
    move_to_barycentre(system)
    return system, tow


def window(cfg: dict, earth_au: float, moon_body: bool, asteroid: bool, years: float, dt: float,
           cap: float) -> dict:
    system, tow = build(cfg, earth_au, moon_body, asteroid)
    m, pos, vel = system.m, system.pos, system.vel
    sun, earth = system.index("sun"), system.index("earth")
    moon = system.index("moon") if moon_body else None
    wc = 2 * math.pi / (cfg["controller"]["correction_period_days"] * DAY)
    kp, kd = wc * wc, 2 * wc
    clearance = cfg["beam"]["earth_clearance_km"] * 1e3
    routes = [(d, math.cos(math.radians(d)), math.sin(math.radians(d))) for d in cfg["beam"]["route_angles_deg"]]
    settle = cfg["moon_coupled"]["settle_days"] * DAY
    ledger = Ledger()
    beam_acc = np.zeros_like(pos)
    st = {"beam_max_w": 0.0, "beam_min_w": math.inf, "capped_steps": 0, "no_route_steps": 0, "spot_error_max_km": 0.0,
          "moon_closest_km": math.inf, "moon_farthest_km": 0.0, "moon_to_asteroid_min_km": math.inf,
          "moon_to_beam_min_km": math.inf}

    def set_beam(acc):
        beam_acc.fill(0.0)
        if tow is None:
            return
        beam, capped = beam_for(tow, m.tolist(), pos.tolist(), vel.tolist(), acc.tolist(), sun, earth, kp, kd,
                                clearance, routes, cap)
        if beam is None:
            tow.beam = Beam()
            tow.no_route_steps += 1
            return
        tow.beam = beam
        tow.capped_steps += capped
        beam_acc[tow.asteroid] = np.array(beam.force) / m[tow.asteroid]

    def kick(acc, h):
        total = acc + beam_acc
        if tow is not None and tow.beam.power > 0:
            a = tow.asteroid
            ledger.book_beam(tow.beam, tuple((vel[a] + 0.5 * total[a] * h).tolist()), h)
        vel[:] += total * h

    p0 = ledger.total_momentum(m, vel)
    p_scale = float((m * np.linalg.norm(vel, axis=1)).sum())
    acc = gravity(m, pos)
    set_beam(acc)
    steps = round(years * YEAR / dt)
    capped_before = no_route_before = 0
    for n in range(1, steps + 1):
        kick(acc, dt / 2)
        pos += vel * dt
        acc = gravity(m, pos)
        set_beam(acc)
        kick(acc, dt / 2)
        t = n * dt
        if moon is not None:
            d = float(np.linalg.norm(pos[moon] - pos[earth])) / 1e3
            st["moon_closest_km"] = min(st["moon_closest_km"], d)
            st["moon_farthest_km"] = max(st["moon_farthest_km"], d)
        if tow is None:
            continue
        a = tow.asteroid
        if moon is not None:
            st["moon_to_asteroid_min_km"] = min(st["moon_to_asteroid_min_km"], float(np.linalg.norm(pos[moon] - pos[a])) / 1e3)
            if tow.beam.power > 0 and n % 4 == 0:
                q, o = tuple(pos[moon].tolist()), tuple(pos[a].tolist())
                back = tuple(-x for x in tow.beam.incoming)
                r_sun = float(np.linalg.norm(pos[a] - pos[sun]))
                st["moon_to_beam_min_km"] = min(st["moon_to_beam_min_km"],
                                                min(ray_distance(q, o, back, r_sun), ray_distance(q, o, tow.beam.outgoing)) / 1e3)
        if t < settle:
            capped_before, no_route_before = tow.capped_steps, tow.no_route_steps
            continue
        sp, _, _ = spot(pos, vel, acc, sun, earth, tow.distance)
        st["spot_error_max_km"] = max(st["spot_error_max_km"], float(np.linalg.norm(pos[a] - np.array(sp))) / 1e3)
        if tow.beam.power > 0:
            st["beam_max_w"] = max(st["beam_max_w"], tow.beam.power)
            st["beam_min_w"] = min(st["beam_min_w"], tow.beam.power)
    if tow is not None:
        st["capped_steps"] = tow.capped_steps - capped_before
        st["no_route_steps"] = tow.no_route_steps - no_route_before
        st["spot_error_max_share"] = st["spot_error_max_km"] * 1e3 / tow.distance
        st["momentum_error"] = float(np.linalg.norm(ledger.total_momentum(m, vel) - p0)) / p_scale
    if moon is not None:
        v_rel, r_rel = vel[moon] - vel[earth], pos[moon] - pos[earth]
        st["moon_bound"] = bool(0.5 * float(v_rel @ v_rel) - G * (m[earth] + m[moon]) / float(np.linalg.norm(r_rel)) < 0)
    return {k: (None if isinstance(v, float) and math.isinf(v) else v) for k, v in st.items()}


def run(cfg: dict | None = None, years: float | None = None, epochs=None, dt_hours: float | None = None) -> dict:
    cfg = cfg or load_config()
    mc = cfg["moon_coupled"]
    years = mc["years"] if years is None else years
    dt = (mc["dt_hours"] if dt_hours is None else dt_hours) * 3600
    cap, cap_source = earth_tow_cap(cfg)
    s = cfg["safety"]
    started = time.time()
    out = {"settings": {"years": years, "dt_hours": dt / 3600, "earth_tow_power_available_w": cap, "cap_source": cap_source,
                        "model": "Sun, Earth, Moon, tow asteroid; live beam controller; no planets; plain 45-degree spot",
                        "limits": {"moon_distance_change": s["moon_distance_change_max_fraction"],
                                   "spot_error_share": s["spot_error_max_fraction"]}},
           "epochs": []}
    for e in (mc["epochs_au"] if epochs is None else epochs):
        if e == "middle":
            au, src = middle_epoch_au(cfg)
        else:
            au, src = float(e), ("real J2000 start" if float(e) == 1.0 else "circular orbit")
        body = window(cfg, au, True, True, years, dt, cap)
        wanted = window(cfg, au, True, True, years, dt, math.inf)
        folded = window(cfg, au, False, True, years, dt, cap)
        free = window(cfg, au, True, False, years, dt, cap)
        steps_counted = round((years * YEAR - cfg["moon_coupled"]["settle_days"] * DAY) / dt)
        change = max(abs(body["moon_closest_km"] / free["moon_closest_km"] - 1),
                     abs(body["moon_farthest_km"] / free["moon_farthest_km"] - 1))
        checks = {
            "moon_stays_bound": body["moon_bound"],
            "moon_distance_change_within_limit": change <= s["moon_distance_change_max_fraction"],
            "asteroid_on_spot": body["spot_error_max_share"] <= s["spot_error_max_fraction"],
            "beam_always_has_a_route": body["no_route_steps"] == 0,
            "beam_misses_the_moon": body["moon_to_beam_min_km"] > MOON_RADIUS_KM,
        }
        out["epochs"].append({"earth_au": round(au, 4), "source": src, "moon_body_with_tow": body,
                              "moon_folded_with_tow": folded, "moon_body_no_tow": free,
                              "moon_distance_change": change,
                              "beam_peak_wanted_w": wanted["beam_max_w"],
                              "beam_peak_increase_from_moon": wanted["beam_max_w"] / folded["beam_max_w"] - 1,
                              "share_of_time_at_e1_limit": body["capped_steps"] / steps_counted,
                              "spare_e1_power_at_peak_w": cap - wanted["beam_max_w"],
                              "checks": checks, "all_pass": all(checks.values())})
    out["all_pass"] = all(e["all_pass"] for e in out["epochs"])
    out["run_seconds"] = round(time.time() - started, 1)
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="The Moon as a full body beside the live Earth tow.")
    parser.add_argument("--years", type=float, help="length of each window (default: config.yaml)")
    parser.add_argument("--epochs", nargs="+", help="Earth orbit sizes in AU, or 'middle' (default: config.yaml)")
    parser.add_argument("--dt-hours", type=float, help="step (default: config.yaml)")
    parser.add_argument("--out", default="results", help="folder for moon_coupled.json (default: results)")
    args = parser.parse_args()
    epochs = [e if e == "middle" else float(e) for e in args.epochs] if args.epochs else None
    out = run(years=args.years, epochs=epochs, dt_hours=args.dt_hours)
    st = out["settings"]
    print(f"Moon beside the live tow: {st['years']:g}-year windows, {st['dt_hours']:g} h steps, "
          f"Earth tow may use {st['earth_tow_power_available_w']:.3e} W ({st['cap_source']})")
    for e in out["epochs"]:
        b, f, n = e["moon_body_with_tow"], e["moon_folded_with_tow"], e["moon_body_no_tow"]
        print(f"\n  Earth at {e['earth_au']} AU ({e['source']})")
        print(f"    Moon {b['moon_closest_km']:,.0f}-{b['moon_farthest_km']:,.0f} km with tow, "
              f"{n['moon_closest_km']:,.0f}-{n['moon_farthest_km']:,.0f} km without: change {e['moon_distance_change']:.3%}")
        print(f"    beam wanted at peak {e['beam_peak_wanted_w']:.3e} W with Moon vs {f['beam_max_w']:.3e} W folded "
              f"({e['beam_peak_increase_from_moon']:+.1%}); at E1's limit {e['share_of_time_at_e1_limit']:.1%} of the time")
        print(f"    asteroid off spot {b['spot_error_max_km']:,.0f} km with Moon vs {f['spot_error_max_km']:,.0f} km folded; "
              f"closest Moon-asteroid {b['moon_to_asteroid_min_km']:,.0f} km; Moon-beam {b['moon_to_beam_min_km']:,.0f} km")
        for k, v in e["checks"].items():
            print(f"    {'PASS' if v else 'FAIL'}  {k}")
    folder = Path(args.out) if Path(args.out).is_absolute() else ROOT / args.out
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "moon_coupled.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nWrote {folder / 'moon_coupled.json'} in {out['run_seconds']:.0f} s")


if __name__ == "__main__":
    main()

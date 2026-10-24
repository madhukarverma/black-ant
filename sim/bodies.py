"""The bodies in a run and their starting positions and velocities (3D, ecliptic of J2000)."""

import math
from dataclasses import dataclass

import numpy as np

from .constants import AU, G, M_SUN


@dataclass
class System:
    names: list[str]
    m: np.ndarray    # masses, kg, shape (N,)
    pos: np.ndarray  # positions, m, shape (N, 3)
    vel: np.ndarray  # velocities, m/s, shape (N, 3)

    def index(self, name: str) -> int:
        return self.names.index(name)

    def add(self, name: str, mass: float, pos, vel) -> int:
        """Append a body and return its index."""
        self.names.append(name)
        self.m = np.append(self.m, mass)
        self.pos = np.vstack([self.pos, pos])
        self.vel = np.vstack([self.vel, vel])
        return len(self.names) - 1


def circular_planets(planets: list[dict]) -> System:
    """The Sun at the origin plus planets on flat, circular orbits at their mean longitudes."""
    names, m, pos, vel = ["sun"], [M_SUN], [[0.0, 0.0, 0.0]], [[0.0, 0.0, 0.0]]
    for p in planets:
        lon = math.radians(p["mean_longitude_deg"])
        r = p["a_au"] * AU
        v = math.sqrt(G * (M_SUN + p["mass_kg"]) / r)
        names.append(p["name"])
        m.append(p["mass_kg"])
        pos.append([r * math.cos(lon), r * math.sin(lon), 0.0])
        vel.append([-v * math.sin(lon), v * math.cos(lon), 0.0])
    return System(names, np.array(m, float), np.array(pos, float), np.array(vel, float))


def real_planets(planets: list[dict]) -> System:
    """The Sun at the origin plus planets on their real tilted, oval orbits, placed where the
    orbital elements put them (J2000.0 for the values in config.yaml), following JPL's steps."""
    names, m, pos, vel = ["sun"], [M_SUN], [[0.0, 0.0, 0.0]], [[0.0, 0.0, 0.0]]
    for p in planets:
        r, v = state_from_elements(p, G * (M_SUN + p["mass_kg"]))
        names.append(p["name"])
        m.append(p["mass_kg"])
        pos.append(r)
        vel.append(v)
    return System(names, np.array(m, float), np.array(pos, float), np.array(vel, float))


def state_from_elements(p: dict, mu: float) -> tuple[list[float], list[float]]:
    """Heliocentric position (m) and velocity (m/s) from orbital elements."""
    a, e = p["a_au"] * AU, p["e"]
    inc, node = math.radians(p["i_deg"]), math.radians(p["node_longitude_deg"])
    peri = math.radians(p["perihelion_longitude_deg"] - p["node_longitude_deg"])  # argument of perihelion
    mean_anomaly = math.radians(p["mean_longitude_deg"] - p["perihelion_longitude_deg"])
    mean_anomaly = (mean_anomaly + math.pi) % (2 * math.pi) - math.pi
    ecc_anomaly = mean_anomaly + e * math.sin(mean_anomaly)
    for _ in range(50):  # Kepler's equation: E - e sin E = M
        step = (ecc_anomaly - e * math.sin(ecc_anomaly) - mean_anomaly) / (1 - e * math.cos(ecc_anomaly))
        ecc_anomaly -= step
        if abs(step) < 1e-15:
            break
    cos_e, sin_e = math.cos(ecc_anomaly), math.sin(ecc_anomaly)
    root = math.sqrt(1 - e * e)
    x, y = a * (cos_e - e), a * root * sin_e  # in the orbit's plane, x toward perihelion
    rate = math.sqrt(mu / a ** 3) / (1 - e * cos_e)  # how fast E changes
    vx, vy = -a * sin_e * rate, a * root * cos_e * rate
    cw, sw, cn, sn, ci, si = math.cos(peri), math.sin(peri), math.cos(node), math.sin(node), math.cos(inc), math.sin(inc)
    rot = ((cw * cn - sw * sn * ci, -sw * cn - cw * sn * ci),
           (cw * sn + sw * cn * ci, -sw * sn + cw * cn * ci),
           (sw * si, cw * si))
    return ([rot[k][0] * x + rot[k][1] * y for k in range(3)],
            [rot[k][0] * vx + rot[k][1] * vy for k in range(3)])


def add_state_bodies(system: System, entries: list[dict]) -> list[int]:
    """Append bodies given by heliocentric position (AU) and velocity (AU/day), such as JPL Horizons
    vectors. Call before move_to_barycentre, while the Sun is at the origin. Returns their indices."""
    from .constants import DAY
    added = []
    for b in entries:
        pos = np.array(b["pos_au"], float) * AU + system.pos[0]
        vel = np.array(b["vel_au_per_day"], float) * AU / DAY + system.vel[0]
        added.append(system.add(b["name"], b["mass_kg"], pos, vel))
    return added


def start_planets(planets: list[dict], orbits: str = "real") -> System:
    if orbits == "real":
        return real_planets(planets)
    if orbits == "circular":
        return circular_planets(planets)
    raise ValueError(f"start_orbits must be 'real' or 'circular', not {orbits!r}")


def move_to_barycentre(system: System) -> None:
    """Shift so the centre of mass sits still at the origin; total momentum becomes zero."""
    total = system.m.sum()
    system.pos -= (system.m @ system.pos) / total
    system.vel -= (system.m @ system.vel) / total


def orbit_elements(system: System, body: int, sun: int = 0) -> dict:
    """Size (AU), eccentricity, tilt (degrees), distance (AU) and speed (m/s) of a body's orbit around the Sun."""
    r_vec = system.pos[body] - system.pos[sun]
    v_vec = system.vel[body] - system.vel[sun]
    mu = G * (system.m[sun] + system.m[body])
    r = float(np.linalg.norm(r_vec))
    v2 = float(v_vec @ v_vec)
    a = 1.0 / (2.0 / r - v2 / mu)
    e_vec = ((v2 - mu / r) * r_vec - float(r_vec @ v_vec) * v_vec) / mu
    h = np.cross(r_vec, v_vec)
    tilt = math.degrees(math.acos(max(-1.0, min(1.0, h[2] / float(np.linalg.norm(h))))))
    return {"a": a / AU, "e": float(np.linalg.norm(e_vec)), "i": tilt, "r": r / AU, "v": v2 ** 0.5}


def split_earth_moon(system: System, moon: dict) -> int:
    """Replace the Earth-Moon barycentre body ("earth", carrying the Moon's mass) by Earth and the Moon.

    The Moon's offset from Earth comes from JPL Horizons at J2000.0 (config: moon.j2000_geocentric, AU and
    AU/day, ecliptic of J2000). Earth and Moon sit on either side of the barycentre in the ratio of their
    masses, so the pair's centre of mass, total mass and momentum are unchanged. Returns the Moon's index.
    """
    from .constants import DAY
    earth = system.index("earth")
    m_e, m_m = moon["earth_mass_kg"], moon["mass_kg"]
    total = m_e + m_m
    if abs(system.m[earth] - total) > 1e-6 * total:
        raise ValueError(f"'earth' must carry the Moon's mass ({total:.6g} kg), not {system.m[earth]:.6g} kg")
    g = moon["j2000_geocentric"]
    rel_r = np.array(g["pos_au"], float) * AU
    rel_v = np.array(g["vel_au_per_day"], float) * AU / DAY
    bary_r, bary_v = system.pos[earth].copy(), system.vel[earth].copy()
    system.m[earth] = m_e
    system.pos[earth] = bary_r - (m_m / total) * rel_r
    system.vel[earth] = bary_v - (m_m / total) * rel_v
    return system.add("moon", m_m, bary_r + (m_e / total) * rel_r, bary_v + (m_e / total) * rel_v)

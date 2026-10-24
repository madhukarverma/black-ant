"""Arrival trim: steering Earth's orbit shape and plane during the tow so it arrives settled.

Jupiter's pull gives every inner orbit a "forced" eccentricity, pointing the same way as Jupiter's own
perihelion, of size e_J x b2/b1 (Laplace coefficients b_3/2^(1), b_3/2^(2) at a/a_J; Murray & Dermott,
Solar System Dynamics, ch. 7). An orbit that differs from it (a "free" part) swings around it: Earth
parked at 2.7 AU with a free part of 0.03-0.05 swings up to e 0.09 over a million years. Arriving with
the forced value leaves almost nothing to swing.

The tow can steer it. For a near-circular orbit (Gauss's equations, k = e cos w, h = e sin w, true
longitude L, pulls R out from the Sun and T ahead, n a = orbital speed):
    dk/dt = (R sin L + 2 T cos L) / (n a),   dh/dt = (-R cos L + 2 T sin L) / (n a)
Scaling the tow's pull through each lap by f(L) = 1 - beta/2 + (beta/2) cos(L - phi) averages to
    d(k, h)/dt = beta (sqrt(5)/4) A / (n a) along angle phi - atan(1/2)
for a tow at 45 degrees (R = T = A). So to push the orbit shape along angle psi, set phi = psi + 26.6 deg.
The pull only ever weakens (the asteroid sits farther out), so beam power can only drop.

The orbit plane is steered the same way. The giant planets force a plane on every inner orbit; an orbit
tipped away from it wobbles at its own rate, and at 2.7 AU that wobble is near the rate at which Earth's
spin axis turns, which makes Earth's axial tilt swing (sim/spin.py). Jupiter's and Saturn's planes rock
about the invariable plane at s6 = -26.3 arcsec/yr, so the forced plane (Laplace-Lagrange, inclination
part) sits at invariable + sum over j of b_j / (b + s6) x (plane_j - invariable), with
b_j = (n/4) (m_j/M_sun) alpha_j^2 b_3/2^(1)(alpha_j) and b = sum of b_j; at 2.7 AU that is about 1.88
times Jupiter's offset. A million-year test puts the smallest tilt swing there (3.9-4.7 deg; on Jupiter's
own plane 4.7-5.9; untrimmed about 12). With P = sin i sin node,
Q = sin i cos node and a pull N along the orbit pole, d(Q, P)/dt = N (cos L, sin L) / (n a). Lifting
the asteroid above the plane by lift_amp cos(L - phi) averages to a drift of (A' / 2 n a) along phi,
with A' = tow pull x sin(lift_amp); in-plane pull drops only by cos(lift).
"""

import math
from functools import lru_cache

from .constants import AU, G

TOW_ANGLE_SHIFT = math.atan(0.5)  # 26.6 degrees, for R = T


def laplace_b(s: float, j: int, alpha: float, points: int = 2048) -> float:
    """Laplace coefficient b_s^(j)(alpha) = (1/pi) * integral over 0..2pi of cos(j psi) / (1 - 2 alpha cos psi + alpha^2)^s."""
    total = 0.0
    for k in range(points):
        psi = 2 * math.pi * k / points
        total += math.cos(j * psi) / (1 - 2 * alpha * math.cos(psi) + alpha * alpha) ** s
    return 2 * total / points


def forced_eccentricity(a: float, a_jupiter: float) -> float:
    """How much of Jupiter's eccentricity an inner orbit of size a is forced to carry."""
    return _forced_share(round(a / a_jupiter, 4))


@lru_cache(maxsize=None)
def _forced_share(alpha: float) -> float:
    return laplace_b(1.5, 2, alpha) / laplace_b(1.5, 1, alpha)


def ecc_vector(p, v, sp, sv, mu: float) -> tuple[float, float]:
    """The (k, h) eccentricity vector in the ecliptic plane from heliocentric position and velocity."""
    rx, ry, rz = p[0] - sp[0], p[1] - sp[1], p[2] - sp[2]
    vx, vy, vz = v[0] - sv[0], v[1] - sv[1], v[2] - sv[2]
    r = math.sqrt(rx * rx + ry * ry + rz * rz)
    v2 = vx * vx + vy * vy + vz * vz
    rv = rx * vx + ry * vy + rz * vz
    c1, c2 = v2 / mu - 1 / r, rv / mu
    return c1 * rx - c2 * vx, c1 * ry - c2 * vy


class Trim:
    """Feedback on a towed planet's orbit shape and plane, through how strongly, and from how far above or
    below its plane, its tow pulls around each lap. Earth's tow steers both; Mars's tow steers the shape,
    so Mars too arrives with the eccentricity Jupiter forces and keeps clear of Earth's orbit."""

    def __init__(self, cfg: dict, base_distance: float):
        self.cfg = cfg
        self.base = base_distance
        self.beta, self.phi = 0.0, 0.0
        self.lift_amp, self.lift_phi = 0.0, 0.0
        self.free_e = self.free_tilt = None
        self.beta_sum, self.updates = 0.0, 0

    def update(self, m, pos, vel, sun: int, earth: int, jupiter: int, saturn: int) -> None:
        # "earth" is whichever planet this trim steers (Earth, or Mars on its own tow)
        """Re-aim at the forced orbit shape and plane for Earth's current orbit (run at check steps)."""
        rows = [list(map(float, pos[i])) + list(map(float, vel[i])) for i in (sun, earth, jupiter, saturn)]
        s, e, j, sat = rows
        mu_e, mu_j = G * (m[sun] + m[earth]), G * (m[sun] + m[jupiter])
        k, h = ecc_vector(e[:3], e[3:], s[:3], s[3:], mu_e)
        kj, hj = ecc_vector(j[:3], j[3:], s[:3], s[3:], mu_j)
        a_e = 1 / (2 / math.dist(e[:3], s[:3]) - sum((e[3 + c] - s[3 + c]) ** 2 for c in range(3)) / mu_e)
        a_j = 1 / (2 / math.dist(j[:3], s[:3]) - sum((j[3 + c] - s[3 + c]) ** 2 for c in range(3)) / mu_j)
        f = forced_eccentricity(a_e, a_j)
        dk, dh = f * kj - k, f * hj - h
        self.free_e = math.hypot(dk, dh)
        mu_s = G * (m[sun] + m[saturn])
        a_s = 1 / (2 / math.dist(sat[:3], s[:3]) - sum((sat[3 + c] - s[3 + c]) ** 2 for c in range(3)) / mu_s)
        tq, tp = self._forced_plane(a_e, ((a_j, m[jupiter] / m[sun], _pole(j, s)), (a_s, m[saturn] / m[sun], _pole(sat, s))))
        ne = _pole(e, s)  # P = pole x, Q = -pole y
        dq, dp = tq + ne[1], tp - ne[0]
        self.free_tilt = math.degrees(math.hypot(dq, dp))
        # Steer only on the stretch set in config.yaml: the orbit on arrival is what matters, and Mars must cross
        # Jupiter's 2:1 resonance at full push (a weakened push lets the resonance capture it).
        if not self.cfg["from_au"] * AU <= a_e <= self.cfg.get("to_au", math.inf) * AU:
            want_b, want_l = (0.0, 0.0), (0.0, 0.0)
        else:
            beta = self.cfg["beta_max"] * min(1.0, self.free_e / self.cfg["full_strength_at_e"])
            phi = math.atan2(dh, dk) + TOW_ANGLE_SHIFT
            lift = math.radians(self.cfg["lift_max_deg"]) * min(1.0, self.free_tilt / self.cfg["full_strength_at_tilt_deg"])
            psi = math.atan2(dp, dq)
            want_b, want_l = (beta * math.cos(phi), beta * math.sin(phi)), (lift * math.cos(psi), lift * math.sin(psi))
        # Move the commands only a little per update, so the spot never jumps and the asteroid is never left behind.
        self.beta, self.phi = _ramp((self.beta, self.phi), want_b, self.cfg["beta_step"])
        self.lift_amp, self.lift_phi = _ramp((self.lift_amp, self.lift_phi), want_l, math.radians(self.cfg["lift_step_deg"]))
        self.beta_sum += self.beta
        self.updates += 1

    def _forced_plane(self, a: float, giants) -> tuple[float, float]:
        """(Q, P) of the plane the giants force on an orbit of size a."""
        n = 2 * math.pi / (a / AU) ** 1.5 * 180 / math.pi * 3600  # arcsec per year
        inv_i, inv_node = (math.radians(x) for x in self.cfg["invariable_plane_deg"])
        q_inv, p_inv = math.sin(inv_i) * math.cos(inv_node), math.sin(inv_i) * math.sin(inv_node)
        b = [n / 4 * mass * (a / aj) ** 2 * laplace_b(1.5, 1, a / aj) for aj, mass, _ in giants]
        denom = sum(b) + self.cfg["s6_arcsec_per_year"]
        q, p = q_inv, p_inv
        for bj, (_, _, pole) in zip(b, giants):
            q += bj / denom * (-pole[1] - q_inv)
            p += bj / denom * (pole[0] - p_inv)
        return q, p

    def apply(self, tow, pos, sun: int, earth: int) -> None:
        # "earth" is the towed planet, as in update()
        """Hand the Earth tow its spot shape, and set its distance and lift for this step's checks."""
        tow.shape = self.shape
        lon = math.atan2(float(pos[earth][1] - pos[sun][1]), float(pos[earth][0] - pos[sun][0]))
        f = 1 - self.beta / 2 + (self.beta / 2) * math.cos(lon - self.phi)
        tow.distance = self.base / math.sqrt(f)
        tow.lift = self.lift_amp * math.cos(lon - self.lift_phi)

    def shape(self, lon: float):
        """Spot offsets at Earth's longitude lon: k along (out + ahead), kn along the orbit pole, and their first
        and second derivatives per radian. Distance d = base / sqrt(f), f = 1 - beta/2 + (beta/2) cos(lon - phi);
        lift = A cos(lon - psi); k = d cos(lift) / sqrt 2, kn = d sin(lift)."""
        b, base = self.beta, self.base
        c, s = math.cos(lon - self.phi), math.sin(lon - self.phi)
        f, f1, f2 = 1 - b / 2 + b / 2 * c, -b / 2 * s, -b / 2 * c
        d = base * f ** -0.5
        d1 = -0.5 * base * f ** -1.5 * f1
        d2 = 0.75 * base * f ** -2.5 * f1 * f1 - 0.5 * base * f ** -1.5 * f2
        A = self.lift_amp
        cl, sl = math.cos(lon - self.lift_phi), math.sin(lon - self.lift_phi)
        L, L1, L2 = A * cl, -A * sl, -A * cl
        cL, sL = math.cos(L), math.sin(L)
        r = math.sqrt(0.5)
        k = d * cL * r
        k1 = (d1 * cL - d * sL * L1) * r
        k2 = (d2 * cL - 2 * d1 * sL * L1 - d * cL * L1 * L1 - d * sL * L2) * r
        kn = d * sL
        kn1 = d1 * sL + d * cL * L1
        kn2 = d2 * sL + 2 * d1 * cL * L1 - d * sL * L1 * L1 + d * cL * L2
        return k, k1, k2, kn, kn1, kn2


def _ramp(now: tuple[float, float], want: tuple[float, float], step: float) -> tuple[float, float]:
    """Move a command (size, angle) toward the wanted (x, y) vector by at most `step`."""
    x, y = now[0] * math.cos(now[1]), now[0] * math.sin(now[1])
    dx, dy = want[0] - x, want[1] - y
    gap = math.hypot(dx, dy)
    if gap > step:
        dx, dy = dx * step / gap, dy * step / gap
    x, y = x + dx, y + dy
    return math.hypot(x, y), math.atan2(y, x) if (x or y) else now[1]


def _pole(body, sun) -> tuple[float, float, float]:
    rx, ry, rz = (body[c] - sun[c] for c in range(3))
    vx, vy, vz = (body[3 + c] - sun[3 + c] for c in range(3))
    hx, hy, hz = ry * vz - rz * vy, rz * vx - rx * vz, rx * vy - ry * vx
    hn = math.sqrt(hx * hx + hy * hy + hz * hz)
    return hx / hn, hy / hn, hz / hn

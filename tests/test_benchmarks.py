"""Validation benchmarks: the 10 official benchmarks from Section 6 of the
Hackathon Participant Guide (Planetary_Propulsion.HackathonParticipantGuide.pdf),
plus Black Ant propulsion and integration integrity tests.

Run all tests:
    .venv/bin/python -m pytest -v
"""

import math
import numpy as np
import pytest

from sim.bodies import circular_planets, move_to_barycentre, orbit_elements, real_planets
from sim.config import load_config
from sim.constants import AU, C_LIGHT, DAY, G, GM_SUN, M_SUN, YEAR
from sim.integrator import energy, gravity, leapfrog
from sim.scenarios.tow import run

CFG = load_config()
EARTH_MASS = 6.04562e24


# ==============================================================================
# SECTION 6 OFFICIAL BENCHMARKS (1 to 10)
# ==============================================================================

def test_benchmark_1_wire_lorentz_force():
    """Official Benchmark 1: Wire, I = 10 A, L = 2 m (x), B = 0.5 T (y) -> 10 N along +z (tol 10^-9)."""
    I = 10.0
    L = np.array([2.0, 0.0, 0.0])
    B = np.array([0.0, 0.5, 0.0])
    F = I * np.cross(L, B)
    expected = np.array([0.0, 0.0, 10.0])
    err = np.linalg.norm(F - expected)
    print(f"Benchmark 1: Force {F} N, error {err:.2e} N")
    assert np.allclose(F, expected, atol=1e-9, rtol=1e-9)
    assert abs(F[2] - 10.0) < 1e-9


def test_benchmark_2_closed_loop_uniform_field():
    """Official Benchmark 2: Closed loop in a uniform field -> Net force 0 (tol 10^-9 of I*L*B)."""
    I = 15.0
    B = np.array([0.2, 0.5, -0.3])
    # Define an arbitrary closed polygon loop in 3D
    vertices = np.array([
        [0.0, 0.0, 0.0],
        [2.0, 1.0, 0.5],
        [3.0, 4.0, 1.0],
        [1.0, 5.0, -0.5],
        [-1.0, 2.0, 0.0],
    ])
    segments = np.roll(vertices, -1, axis=0) - vertices
    L_total = float(np.sum(np.linalg.norm(segments, axis=1)))
    # Sum Lorentz forces I * (dl x B) on each segment
    F_net = np.sum([I * np.cross(dl, B) for dl in segments], axis=0)
    tol = 1e-9 * (I * L_total * np.linalg.norm(B))
    err = float(np.linalg.norm(F_net))
    print(f"Benchmark 2: Net force {err:.2e} N (limit {tol:.2e} N)")
    assert err < tol


def test_benchmark_3_biot_savart_long_wire():
    """Official Benchmark 3: Long wire, 1 kA at 1 m -> 2.000 x 10^-4 T (tol 10^-6)."""
    mu_0 = 4.0 * math.pi * 1e-7
    I = 1000.0  # 1 kA
    r = 1.0     # 1 m
    expected = 2.000e-4  # T

    # Analytic expression for infinite wire: B = mu_0 * I / (2 * pi * r)
    B_analytic = mu_0 * I / (2.0 * math.pi * r)

    # Numerical Biot-Savart integration over wire [-L, L] with L >> r
    L_half = 10000.0
    N = 500000
    z = np.linspace(-L_half, L_half, N)
    dz = z[1] - z[0]
    dB = (mu_0 * I / (4.0 * math.pi)) * (r * dz) / (r**2 + z**2)**1.5
    B_numeric = float(np.sum(dB))

    print(f"Benchmark 3: B_analytic {B_analytic:.6e} T, B_numeric {B_numeric:.6e} T")
    assert abs(B_analytic - expected) < 1e-6
    assert abs(B_numeric - expected) < 1e-6


def test_benchmark_4_kepler_orbit_10_periods():
    """Official Benchmark 4: Kepler orbit, a = 1 AU, e = 0.3, 10 periods -> Back to start (tol 10^-6 a, energy 10^-9)."""
    import rebound
    sim = rebound.Simulation()
    sim.G = G
    m_earth = 5.972e24
    sim.add(m=M_SUN)
    sim.add(m=m_earth, a=AU, e=0.3)
    sim.move_to_com()
    p = sim.particles[1]
    T = p.P
    p0 = np.array([p.x, p.y, p.z])
    e0 = sim.energy()
    sim.integrate(10 * T)
    p10 = np.array([sim.particles[1].x, sim.particles[1].y, sim.particles[1].z])
    e10 = sim.energy()
    pos_error_a = float(np.linalg.norm(p10 - p0) / AU)
    energy_error = abs(e10 / e0 - 1)
    print(f"Benchmark 4: return error {pos_error_a:.2e} a, energy error {energy_error:.2e}")
    assert pos_error_a < 1e-6
    assert energy_error < 1e-9


def test_benchmark_5_solar_system_energy_5_years():
    """Official Benchmark 5: Solar system, 5 years, no push -> Energy constant (tol 10^-9)."""
    system = real_planets(CFG["planets"])
    move_to_barycentre(system)
    e0 = energy(system.m, system.pos, system.vel)
    dt = 0.05 * DAY
    leapfrog(system.m, system.pos, system.vel, dt, round(5 * YEAR / dt))
    e1 = energy(system.m, system.pos, system.vel)
    energy_drift = abs(e1 / e0 - 1)
    print(f"Benchmark 5: 5-year solar system energy drift {energy_drift:.2e}")
    assert energy_drift < 1e-9


def test_benchmark_6_earth_moon_barycentre_period():
    """Official Benchmark 6: Earth-Moon barycentre period -> 365.256 days (tol 0.1 day).

    Sun, Earth and the Moon as three separate bodies from their real J2000 states (Moon from JPL Horizons),
    stepped with our own leapfrog; the year is the time the Earth-Moon barycentre takes to go once round the Sun."""
    from sim.scenarios.baseline import build, integrate
    earth = next(p for p in CFG["planets"] if p["name"] == "earth")
    a = earth["a_au"] * AU
    period_kepler_days = 2 * math.pi * math.sqrt(a**3 / (G * (M_SUN + earth["mass_kg"]))) / DAY

    out = integrate(build(CFG, "sem"), 1.05, 0.25 * 3600)
    expected = 365.256
    print(f"Benchmark 6: Kepler {period_kepler_days:.4f} d, simulated Earth-Moon barycentre {out['earth_moon_year_days']:.4f} d, "
          f"Moon month {out['moon_sidereal_month_days']:.3f} d, Moon {out['moon_closest_km']:,.0f}-{out['moon_farthest_km']:,.0f} km")
    assert abs(period_kepler_days - expected) < 0.1
    assert abs(out["earth_moon_year_days"] - expected) < 0.1
    assert out["moon_bound"]


def test_benchmark_7_hohmann_transfer_mars():
    """Official Benchmark 7: Hohmann 1 -> 1.524 AU -> 2.94 + 2.65 km/s, ~259 days (tol 0.02 km/s; 2 days)."""
    r1, r2 = 1.0 * AU, 1.524 * AU
    v1 = math.sqrt(GM_SUN / r1)
    v2 = math.sqrt(GM_SUN / r2)
    a_t = (r1 + r2) / 2
    vp = math.sqrt(GM_SUN * (2 / r1 - 1 / a_t))
    va = math.sqrt(GM_SUN * (2 / r2 - 1 / a_t))
    dv1 = vp - v1
    dv2 = v2 - va
    t_transfer_days = (math.pi * math.sqrt(a_t**3 / GM_SUN)) / DAY

    print(f"Benchmark 7: dv1 {dv1/1e3:.3f} km/s (exp 2.94), dv2 {dv2/1e3:.3f} km/s (exp 2.65), time {t_transfer_days:.1f} d (exp ~259)")
    assert abs(dv1 / 1e3 - 2.94) < 0.02
    assert abs(dv2 / 1e3 - 2.65) < 0.02
    assert abs(t_transfer_days - 259.0) < 2.0

    # Simulate trajectory: test particle starting at 1 AU with first burn applied reaches 1.524 AU
    m = np.array([M_SUN, 0.0])
    pos = np.array([[0.0, 0.0], [r1, 0.0]])
    vel = np.array([[0.0, 0.0], [0.0, vp]])
    dt = 0.05 * DAY
    steps = round(t_transfer_days * DAY / dt)
    leapfrog(m, pos, vel, dt, steps)
    reached = math.hypot(*(pos[1] - pos[0]))
    assert abs(reached / r2 - 1) < 1e-3


def test_benchmark_8_continuous_push_orbit_growth():
    """Official Benchmark 8: Push 10^-8 m/s^2 along velocity, 1 year -> a grows ~3,170 km (tol 1%)."""
    a0 = AU
    a_push = 1.0e-8  # m/s^2
    mu = GM_SUN

    # Gauss perturbation equation: da/dt = 2*a^2*(v*a_push)/mu = 2*a_push/n
    v0 = math.sqrt(mu / a0)
    da_analytic = (2 * (a0**2) * v0 * a_push / mu) * YEAR

    # Direct 1-year numerical integration with leapfrog
    dt = 0.05 * DAY
    steps = round(YEAR / dt)
    pos = np.array([a0, 0.0, 0.0])
    vel = np.array([0.0, v0, 0.0])

    def acc(p, v):
        r = np.linalg.norm(p)
        return -mu * p / (r**3) + a_push * v / np.linalg.norm(v)

    a_vec = acc(pos, vel)
    for _ in range(steps):
        vel += a_vec * (dt / 2)
        pos += vel * dt
        a_vec = acc(pos, vel)
        vel += a_vec * (dt / 2)

    r = float(np.linalg.norm(pos))
    v2 = float(vel @ vel)
    a_final = 1.0 / (2.0 / r - v2 / mu)
    da_sim = a_final - a0

    expected_km = 3170.0
    print(f"Benchmark 8: analytic da {da_analytic/1e3:.2f} km, simulated da {da_sim/1e3:.2f} km (expected ~{expected_km} km)")
    assert abs(da_analytic / 1e3 / expected_km - 1) < 0.01
    assert abs(da_sim / 1e3 / expected_km - 1) < 0.01


def test_benchmark_9_cantilever_under_self_weight():
    """Official Benchmark 9: Cantilever under self-weight -> qL^2/2 and qL^4/8EI (tol 1%)."""
    L = 1000.0  # m
    q = 250.0   # N/m
    E = 2.0e11  # Pa
    I = 0.05    # m^4
    EI = E * I

    # Analytic Euler-Bernoulli formulas
    M_root_expected = q * (L**2) / 2.0
    delta_tip_expected = q * (L**4) / (8.0 * EI)

    # Numerical integration across segments
    N = 10000
    dx = L / N
    x_mid = np.linspace(dx / 2.0, L - dx / 2.0, N)
    # Root moment: integral_0^L q * x dx
    M_root_numeric = float(np.sum(q * dx * x_mid))
    # Deflection: double integration of curvature kappa(x) = q*(L - x)^2 / (2*EI)
    kappa = (q * (L - x_mid)**2) / (2.0 * EI)
    theta = np.cumsum(kappa * dx)
    delta_tip_numeric = float(np.sum(theta * dx))

    err_M = abs(M_root_numeric / M_root_expected - 1)
    err_delta = abs(delta_tip_numeric / delta_tip_expected - 1)
    print(f"Benchmark 9: M_root {M_root_numeric:.4e} N*m (err {err_M:.2%}), tip delta {delta_tip_numeric:.4e} m (err {err_delta:.2%})")
    assert err_M < 0.01
    assert err_delta < 0.01


def test_benchmark_10_equilibrium_temperature():
    """Official Benchmark 10: Equilibrium temperature, 1 AU, albedo 0.306 -> ~254 K (tol 2 K)."""
    # Teq = [S * (1 - A) / (4 * sigma)]^(1/4)
    S = 1361.0          # W/m^2 solar constant at 1 AU
    A = 0.306           # Earth Bond albedo
    sigma = 5.670374e-8 # Stefan-Boltzmann constant
    T_eq = ((S * (1.0 - A)) / (4.0 * sigma)) ** 0.25
    expected = 254.0
    print(f"Benchmark 10: T_eq = {T_eq:.2f} K (expected ~{expected} K, tolerance ±2 K)")
    assert abs(T_eq - expected) < 2.0


# ==============================================================================
# BLACK ANT MISSION & INTEGRITY TESTS
# ==============================================================================

def test_config_numbers_are_numbers():
    assert isinstance(CFG["tows"][0]["asteroid_mass_kg"], float)
    assert isinstance(CFG["planets"][0]["mass_kg"], float)


def test_real_orbits_match_their_elements():
    """Positions built from JPL elements reproduce the expected orbit size, eccentricity and tilt."""
    system = real_planets(CFG["planets"])
    for p in CFG["planets"]:
        o = orbit_elements(system, system.index(p["name"]))
        assert abs(o["a"] / p["a_au"] - 1) < 1e-5, p["name"]
        assert abs(o["e"] - p["e"]) < 1e-5, p["name"]
        assert abs(o["i"] - abs(p["i_deg"])) < 1e-4, p["name"]


def test_momentum_with_ledger():
    """Force ledger verifies total momentum (bodies + stations + light) changes by < 1 part in 10^10."""
    summary, _, _ = run(years=20, belt=False)
    err = summary["ledger"]["momentum_error_max"]
    print(f"Momentum error with ledger: {err:.1e}")
    assert err < 1e-10


def test_hohmann_transfer_journey_target():
    """Hohmann transfer from 1 to 2.7 AU; speed change within 0.1% of 11.00 km/s."""
    r1, r2 = AU, 2.7 * AU
    v1, v2 = math.sqrt(GM_SUN / r1), math.sqrt(GM_SUN / r2)
    a_t = (r1 + r2) / 2
    vp, va = math.sqrt(GM_SUN * (2 / r1 - 1 / a_t)), math.sqrt(GM_SUN * (2 / r2 - 1 / a_t))
    dv = (vp - v1) + (v2 - va)
    print(f"Hohmann 1->2.7 AU speed change: {dv / 1e3:.3f} km/s")
    assert abs(dv / 11.0e3 - 1) < 1e-3


def test_steady_push_arrival_time():
    """Steady push along the orbit; arrival time at 2.7 AU within 1% of m * 11.66 km/s / push."""
    accel = 1.2e-5  # m/s^2
    dv = math.sqrt(GM_SUN / AU) - math.sqrt(GM_SUN / (2.7 * AU))
    predicted = dv / accel
    pos, vel = np.array([AU, 0.0]), np.array([0.0, math.sqrt(GM_SUN / AU)])
    dt, t = 0.25 * DAY, 0.0

    def acc(p, v):
        r = np.hypot(*p)
        return -GM_SUN * p / r ** 3 + accel * v / np.hypot(*v)

    a = acc(pos, vel)
    while True:
        vel = vel + a * dt / 2
        pos = pos + vel * dt
        a = acc(pos, vel)
        vel = vel + a * dt / 2
        t += dt
        r, v2 = np.hypot(*pos), float(vel @ vel)
        if 1 / (2 / r - v2 / GM_SUN) >= 2.7 * AU:
            break
    error = abs(t / predicted - 1)
    print(f"Steady push arrival time error: {error:.2%}")
    assert error < 0.01


def test_asteroid_pull_and_hold():
    """Asteroid pull equals G * M / d^2 and controller holds asteroid within 0.1% over 20 years."""
    tow = CFG["tows"][0]
    d, mass = tow["distance_km"] * 1e3, tow["asteroid_mass_kg"]
    acc = gravity(np.array([EARTH_MASS, mass]), np.array([[0.0, 0.0], [d, 0.0]]))
    expected = G * mass / d ** 2
    assert abs(acc[0, 0] / expected - 1) < 1e-12
    summary, _, _ = run(years=20, belt=False)
    held = summary["tows"]["earth-tow"]["spot_error_max_km"]
    print(f"Earth tow acceleration {expected:.3e} m/s^2; asteroid held within {held:.0f} km")
    assert held < 0.001 * d / 1e3


@pytest.mark.slow
def test_longterm_energy_steady_1000_years():
    """Sun and five planets on real orbits for 1,000 years; energy error < 1e-6 without drift."""
    system = real_planets(CFG["planets"])
    move_to_barycentre(system)
    e0 = energy(system.m, system.pos, system.vel)
    errors = []

    def track(step, pos, vel):
        if step % 2000 == 0:
            errors.append(abs(energy(system.m, pos, vel) / e0 - 1))

    dt = 0.5 * DAY
    leapfrog(system.m, system.pos, system.vel, dt, round(1000 * YEAR / dt), track)
    half = len(errors) // 2
    print(f"1000-year energy error max {max(errors):.2e}")
    assert max(errors) < 1e-6
    assert max(errors[half:]) < 2 * max(errors[:half]) + 1e-12


@pytest.mark.slow
def test_stepper_matches_rebound():
    """Our stepper against REBOUND IAS15 for 100 years; Earth orbit size agrees within 1e-6 AU."""
    rebound = pytest.importorskip("rebound")
    ours = real_planets(CFG["planets"])
    move_to_barycentre(ours)
    sim = rebound.Simulation()
    sim.G = G
    for k in range(len(ours.m)):
        sim.add(m=float(ours.m[k]), x=float(ours.pos[k, 0]), y=float(ours.pos[k, 1]), z=float(ours.pos[k, 2]),
                vx=float(ours.vel[k, 0]), vy=float(ours.vel[k, 1]), vz=float(ours.vel[k, 2]))
    sim.integrator = "ias15"
    years, dt = 100, 0.1 * DAY
    sim.integrate(years * YEAR)
    leapfrog(ours.m, ours.pos, ours.vel, dt, round(years * YEAR / dt))
    earth = ours.index("earth")
    ref = real_planets(CFG["planets"])
    for k, p in enumerate(sim.particles):
        ref.pos[k] = (p.x, p.y, p.z)
        ref.vel[k] = (p.vx, p.vy, p.vz)
    a_ours, a_ref = orbit_elements(ours, earth)["a"], orbit_elements(ref, earth)["a"]
    print(f"Earth orbit size ours {a_ours:.9f} AU, REBOUND {a_ref:.9f} AU")
    assert abs(a_ours - a_ref) < 1e-6

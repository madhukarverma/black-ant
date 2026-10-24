# Our approach: towing Earth with a light-held asteroid

## The idea in one paragraph

A 4 x 10^20 kg asteroid (about 670 km across) is parked 637,100 km from Earth, ahead of it and out
from the Sun. Its gravity pulls Earth very gently: 6.5 x 10^-8 m/s^2. Left alone it would fall onto
Earth, so a mirror tethered to it is pushed by a focused beam of light that holds it exactly in place.
Earth keeps being pulled, its orbit widens a little on every lap, and after about 8,000 years it reaches
2.7 AU. Mars sits across that path, so a second, smaller tow moves Mars out of the way first. Sunlight
mirrors keep Earth's sunlight and temperature at today's level the whole way.

## Why not Octo-Earth

Arms rooted on Earth push on Earth, and Earth pushes back on them equally (Newton's third law). Forces
inside the Earth-plus-machine system cancel, so they cannot move its centre of mass: to change Earth's
orbit, a force has to come from outside it (another mass's gravity, light from outside, or mass thrown
away). The arms also could not hold themselves up: a 12,000 km arm on Earth carries about 320 GPa at its
base in steel and about 53 GPa even in carbon nanotube, beyond either material's strength. Member 3's
audit and benchmark B8 make both points with numbers.

A gravity tractor gets around both: the asteroid is outside Earth, its pull is a real outside force, and
nothing touches Earth.

## The size of the job

| | |
| --- | --- |
| Earth's orbital speed | 29.8 km/s at 1 AU, 18.1 km/s at 2.7 AU |
| Energy Earth's orbit must gain | about 1.7 x 10^33 J |
| Pull on Earth | about 3.9 x 10^17 N (2.8 x 10^17 N of it along the orbit) |
| Time | about 8,500 of the 10,000 years allowed |

## The physics we use

| Rule | Where it is used | Code |
| --- | --- | --- |
| Newton's gravity between every pair of bodies | The Sun, Venus to Neptune, Ceres, Pallas, Vesta, Hygiea and both tow asteroids, all pulling on each other | `sim/integrator.py` |
| Leapfrog stepping (kick, drift, kick), 1-day steps | Keeps energy from drifting over thousands of years | `sim/integrator.py` |
| Light pressure on a mirror: force = (P/c)(in - out) | The beam that holds each asteroid; power for a force f is P = f^2 c / (2 in.f) | `sim/forces.py` |
| Newton's third law, booked | Every push has its partner: the beam station's recoil, the bounced light, asteroids sent away | `sim/ledger.py` |
| Real starting orbits | Planets from JPL's J2000 orbital elements; the big asteroids from JPL Horizons and the Small-Body Database | `sim/bodies.py`, `config.yaml` |
| Gauss's equations | Steering Earth's orbit shape and plane on arrival | `sim/secular.py` |
| Spin precession of an oblate Earth | Earth's axial tilt (the seasons) after the move | `sim/spin.py` |

Checks run every 100 days during the journey: safety, structures, orbits and the ledger. A check that
fails becomes a **flag** (when, how often, how bad); a flag that relies on one of our enablers names it.
That is the brief's "no unresolved flags" rule, made into code (`sim/flags.py`).

## The machine

**Where the asteroid sits.** 637,100 km from Earth, at 45 degrees between straight ahead and straight
out from the Sun. That angle gives the most pull along Earth's orbit for each watt of light: the beam
comes from the Sun's side, and light can only push, never pull.

**The beam.** Light arriving along "in" and bouncing off along "out" pushes with (P/c)(in - out). The
controller asks for the force that keeps the asteroid on its spot (what the spot's motion needs, minus
the gravity the asteroid already feels, plus a correction for any drift, with a 10-day response). No beam
may pass within 420,000 km of Earth (beyond the Moon's farthest point), so when the straight path would,
light arrives up to 30 degrees off the Sun line instead. About 8.4 x 10^25 W is needed.

**Power.** Mars's tow is served first; the Earth tow may use the rest of E1's 10^26 W. That leaves spare
power to catch the asteroid after a fault (see below).

**Structures.** Cables and anchors are sized for the most the beam can ever push (2P/c) with a 1.5
safety factor; the mirror is sized so it stays under 1,500 K. Earth tow: cables 10.5 km^2, anchor
10,500 km^2, mirror radius 2,600 km. Mars tow: 1.6 km^2, 1,600 km^2, 1,000 km.

## Mars goes first

Earth's path crosses Mars's orbit. Without help, Earth passes Mars at about 33,000 km
(`--no-mars-tow`). A smaller tow (9.8 x 10^18 kg asteroid, 100,000 km from Mars, giving Mars the same
pull) moves Mars from 1.52 AU out to **3.64 AU**, past Jupiter's 2:1 resonance at 3.28 AU.

Where Mars parks matters, because once Earth sits at 2.7 AU, Earth's own resonances join Jupiter's:

| Resonance (orbital periods) | With Jupiter, Mars at | With Earth at 2.7 AU, Mars at |
| --- | --- | --- |
| 2:1 | 3.278 AU | |
| 7:5 | | 3.379 AU |
| 11:6, 9:5, 7:4, 5:3 | 3.473, 3.516, 3.583, 3.701 AU | |
| 3:2, 8:5 | | 3.538, 3.694 AU |

3.64 AU sits between them all, with the widest gap from Earth's orbit (about 0.55 AU). Mars's tow also
steers Mars's orbit shape onto the value Jupiter forces (the same arrival trim as Earth's, below), but only
up to 3.1 AU: past that it must push at full strength, because a weakened push lets the 2:1 resonance catch
Mars, which happened in one of our runs.

## The Moon comes along

The Moon is held by Earth's gravity well inside Earth's Hill sphere, and that sphere grows as Earth
moves out. The tow asteroid's tide on the Earth-Moon pair is 0.12% of the Moon's own. Fifty-year runs of
Earth, Moon, asteroid and Sun at the start, middle and end of the journey, against runs without the
asteroid, change the Moon's distance by at most 0.05% (`sim/scenarios/moon.py`). An asteroid about 300
times heavier would be needed to disturb it.

## Keeping Earth livable

At 2.7 AU Earth would get 1/7.3 of today's sunlight and freeze (about 188 K). Sunlight mirrors (E3)
make up the difference: about 8 x 10^8 km^2 of thin film at 2.7 AU, supplying 86% of Earth's light by
then. The tow mirror's waste heat reaching Earth is at most about 0.24% of sunlight.

## Arriving settled: the arrival trim

Jupiter gives every orbit near it a "forced" eccentricity and a forced orbit plane. An orbit that
arrives off them wobbles around them for ever. Parked at 2.7 AU any old way, Earth's eccentricity drifts
up to 0.09 (sunlight swinging about 18% through each year) and its axial tilt swings between 15 and 28
degrees (today: 22.2 to 24.4).

So from 2.0 AU the Earth tow steers Earth's orbit as it pulls, using Gauss's equations
(`sim/secular.py`):

- **Shape:** the pull is made a little weaker on one side of each lap (the asteroid drifts farther out
  there), which turns Earth's eccentricity toward the forced value, 0.03 at 2.7 AU. Result in a
  million-year test: eccentricity stays under 0.056 (the real Earth's own maximum: 0.051).
- **Plane:** the asteroid rides up to 20 degrees above or below Earth's orbit plane around each lap,
  tipping the plane onto the forced one (computed from Jupiter's and Saturn's planes). Result: the tilt
  swing drops from about 12 degrees to about 4.

The pull only ever weakens, so the beam never needs more power, and the asteroid never comes closer.

## After arrival

The tow asteroids are sent away and the ledger keeps what they carried. A million-year run of the moved
solar system (REBOUND's MERCURIUS integrator, `sim/scenarios/longterm.py`) runs beside the real solar
system's own million years, so anything the moved Earth does is compared with what the real one does.
Three hazards remain that today's Earth does not have. Each has a counter with a number:

| Hazard | Size | Counter |
| --- | --- | --- |
| Asteroid impacts: 2.7 AU is inside the main belt | Many times Earth's natural rate of one 1 km impact per 500,000 years (`results/summary.json`, belt) | E1 nudges any asteroid found heading for Earth: 5 cm/s ten years ahead moves it about 47,000 km, about 10^14 W for a day |
| Big asteroids (Ceres, Pallas, Vesta, Hygiea) passing within 0.01 AU | Never in the real solar system; tens of times per million years after the move | E1 nudges each pass decades ahead: under an hour of a 10^25 W beam |
| Seasons: the remaining tilt swing of about 4 degrees | About 1% of yearly sunlight lands at a different latitude or season than today | The sunlight mirrors (E3), which already supply 86% of the light, re-aim that share |

The tilt swing cannot be removed by orbit choice alone: at 2.7 AU Earth's axis turns at about 35
arcseconds a year, close to a rate (26 arcseconds a year) at which Jupiter and Saturn tip every orbit's
plane, and that near-match amplifies it.

## Our three enablers

| Enabler | Provides | Limit |
| --- | --- | --- |
| E1 beamed-power station | Focused light for both tows; nudges dangerous asteroids | Up to 10^26 W; many independent stations, no single fault over a quarter of the power |
| E2 super-mirror material | Tow mirrors and cables | Absorbs 10^-7 of light; 100 GPa strength; density 2,000 kg/m^3; up to 1,500 K |
| E3 planet-scale manufacturing | Places both asteroids; builds the tow and sunlight mirrors | Asteroids up to 4 x 10^20 kg; mirrors up to 10^9 km^2 |

None creates energy or momentum from nothing: every push is booked with its reaction.

## What the stress tests found, and what we did

| Found | Fix | Re-tested |
| --- | --- | --- |
| Mars parked at 3.1 AU is thrown onto an Earth-crossing orbit within a million years (at 3.0 AU, out to 20 AU) | Park Mars past Jupiter's 2:1 resonance | |
| Mars parked at 3.4 AU, next to Earth's 7:5 resonance, drifts until its orbit crosses Earth's | Park Mars at 3.64 AU, between all the resonances, and trim its orbit shape | Parking scan: ten arrangements stable for a million years, orbits at least 0.26 AU apart |
| Steering Mars past 3.1 AU slowed it at the 2:1 resonance, which caught it | Steer Mars only up to 3.1 AU | In the final run |
| A beam outage of 3 hours lost the Earth tow's asteroid, which then fell through the Moon's orbit | Shared E1 budget, structures sized for full power, E1 built from independent stations | Earth tow survives a 15-hour blackout, half the stations down for 1.25 days, a quarter for 2.8 days; Mars tow 13 hours, 1.8 days, and indefinitely |
| Vesta passes Earth at about 0.012 AU during the journey (our limit 0.02) | E1 nudges it fifty years ahead | About 0.3 hours of a 10^25 W beam |
| Mars tow's cables and mirror too weak at its own power cap | Resized | Test at full power for both tows |
| Earth's eccentricity drifts to 0.09 after arrival | Shape trim | Under 0.056 |
| Earth's axial tilt swings 15 to 28 degrees | Plane trim onto the forced plane; mirrors for the rest | Swing about 4 degrees; about 1% of sunlight re-aimed |
| Our first belt sample was too cold (made-up orbits) | Real orbits from the JPL Small-Body Database | In the final run |

Every risk, how we check it and its status: [risk-register.md](risk-register.md).

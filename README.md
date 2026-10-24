











































































# Black Ant: towing Earth to 2.7 AU

Our entry for **Black Ant Robotics** at TransfiNITTe 2026: a simulation of a machine that moves Earth
from 1 AU to about 2.7 AU, near the asteroid belt, without harming the planet or life on it. All six
winning conditions (target within 10,000 years, Earth safe, structures at safety factor 1.5 or more,
benchmarks passing, every force booked, no unresolved flags) are in [docs/problem.md](docs/problem.md).

## Our approach in short

A **gravity tractor held in place by light**. A 4 x 10^20 kg asteroid sits 637,100 km from Earth and
pulls it gently with its own gravity; a focused light beam pushing on a mirror tethered to the asteroid
keeps it from falling onto Earth. Earth's orbit widens a little on every lap and reaches 2.7 AU in about
8,500 years. Mars is towed out of the way first (to 3.64 AU), sunlight mirrors keep Earth at today's
sunlight and temperature, and on the last stretch the tow steers Earth onto the orbit Jupiter lets it
keep. Every push is booked with its reaction, so energy and momentum are checked all the way.

Read [docs/approach.md](docs/approach.md) for the full plan, the physics and why Octo-Earth cannot work,
and [docs/risk-register.md](docs/risk-register.md) for every way it could fail and what we did about it.

## Results

**Status (24 Oct, latest run):** the journey passes every check (0 unresolved flags; Earth arrives in year
8,542 on the orbit Jupiter lets it keep). One problem is being fixed now: with its new shape trim, Mars's tow
slows down right at Jupiter's 2:1 resonance (3.28 AU), gets caught there and never reaches its 3.64 AU parking
orbit. Fix in progress: trim Mars only before 3.1 AU and cross the resonance at full push, as earlier runs did.
The million-year results and the full table follow in the next commit. Journey numbers: `results/summary.json`.

Every number above comes from `results/`. The run prints any flag at the end; a flag naming E1, E2 or E3
relies on one of our declared enablers, which the brief allows.

## Setup

Needs [uv](https://docs.astral.sh/uv/). From this folder:

```bash
uv python install 3.12
uv sync
```

## Run

```bash
uv run python -m sim.scenarios.tow --out results    # the full journey with every check, about 35 minutes
uv run python -m sim.scenarios.tow --no-belt --years 500   # a quick look
uv run python -m sim.scenarios.moon                 # the Moon test at the start, middle and end, about 20 seconds
uv run python -m sim.scenarios.baseline             # real Sun, planets, Earth and Moon from J2000, no push, 10 years, about 15 s
uv run python -m sim.scenarios.moon_coupled         # the Moon as a full body beside the live tow, about 45 s
uv run python -m sim.scenarios.longterm --only moved --state results/end_state.json --out results/longterm.json
                                                    # a million years after arrival, about 15 minutes
uv run python -m sim.scenarios.parking              # where Earth and Mars can park, a million years each
uv run python -m sim.scenarios.outage               # how long a beam can fail before its asteroid is lost
```

Add `--no-mars-tow` to the journey to see why Mars must move first, or `--orbits circular` for flat
circular starting orbits.

## Test bench (web app)

```bash
uv run python -m app.server      # then open http://localhost:8765 in a browser
```

Pick an experiment on the left, set its inputs and press Run: the page starts the same command-line run you
would type, shows its progress in the Log tab and opens the results when it finishes. Saved journeys (in `results/`
and `out/`) can be opened, played back, compared and exported as CSV. Tabs: Summary, Orbit, Forces & ledger, Earth
safety, Moon, Validation, Compare & export, Log. The physics stays in `sim/`; the app only reads what it saves.

## Test

```bash
uv run pytest -m "not slow" -v     # quick tests, about 40 seconds (these run on every pull request)
uv run pytest -v -s                # everything, a few minutes
```

## How we work

- **Nobody pushes to `main`.** Make a branch for your issue (`m2/safety-report`), push it, and open a
  pull request. Ashish reviews and merges; the quick tests must pass first.
- **Your tasks are GitHub issues**, labelled by role: `member-1` physics core, `member-2` safety and
  environment, `member-3` structures and enablers, `member-4` 3D viewer, `member-5` validation and pitch.
- **Rules live in `config.yaml`.** Every limit has its source next to it. If the organisers change a rule,
  change the number there and ask for a re-run; don't hard-code numbers anywhere else.
- **Numbers on slides come from `results/`**, never from memory.

## Where things are

| Path | What it holds |
| --- | --- |
| `docs/problem.md` | The brief and the winning conditions |
| `docs/approach.md` | Our plan, the physics, the machine, what we found and fixed |
| `docs/risk-register.md` | Every risk: why it matters, how we check it, the counter, its status, its owner |
| `config.yaml` | Every setting and working rule, with sources; change a number and re-run |
| `results/` | The final run: `summary.json` (every number and flag), `run.json` (one frame per 10 years, what the viewer plays), `end_state.json`, `longterm.json`, `outage.json`, `parking*.json` |
| `sim/bodies.py` | Bodies and their real starting orbits |
| `sim/integrator.py` | Gravity, the leapfrog stepper, total energy |
| `sim/forces.py` | Each tow's spot, and the beam that holds its asteroid there |
| `sim/ledger.py` | The force ledger: station recoil, bounced light, asteroids sent away |
| `sim/flags.py` | Checks and flags |
| `sim/checks/` | Safety (Member 2) and structure (Member 3) checks, run every 100 days |
| `sim/belt.py` | 1,000 test asteroids on real orbits: close passes and the impact estimate |
| `sim/secular.py` | The arrival trim: steering Earth's orbit shape and plane |
| `sim/spin.py` | Earth's spin axis, axial tilt and seasons |
| `sim/scenarios/` | The journey, the baseline, the Moon tests, the million-year run, the parking scan, the outage test |
| `tests/` | Benchmarks B1 to B9 and the checks |
| `data/` | Raw JPL data: Horizons vectors and Small-Body Database orbits |
| `sim-proto/` | The first JavaScript prototype, kept for quick experiments |
| `app/` | The test bench: a local web app (`app/server.py`, standard library only) and its page (`app/static/`) |

## Model limits

Planets Venus to Neptune start on their real tilted, oval orbits at J2000.0 (1 January 2000, noon),
from JPL's [orbital elements](https://ssd.jpl.nasa.gov/planets/approx_pos.html); Ceres, Pallas, Vesta
and Hygiea from JPL Horizons. No Mercury (its pull on Earth is tiny and it would need much shorter steps).
Earth carries the Moon's mass in the long runs. The Moon is a full body, from its real J2000 position (JPL Horizons),
in the baseline (`sim/scenarios/baseline.py`) and in short windows beside the live tow (`sim/scenarios/moon_coupled.py`). Our safety limits,
structural rules and enabler limits are stand-ins until the organisers publish theirs.

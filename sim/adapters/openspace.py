"""OpenSpace visualization adapter for Black Ant planetary propulsion simulations.

This adapter consumes simulation output (run.json) and generates OpenSpace scene
assets and JPL Horizons-compatible trajectory files (.hrz) for visualization in
OpenSpace 0.22.0-dev.

Coordinate Frames and Transformations:
--------------------------------------
- Simulation Frame: Black Ant positions are heliocentric Cartesian (x, y, z) in
  Astronomical Units (AU), defined in the Ecliptic of J2000.0 (ECLIPJ2000) frame.
- OpenSpace Scene Graph: Scene graph nodes for Black Ant bodies are parented to
  `sunAsset.SunCenter.Identifier` (the Sun's center, loaded from
  `scene/solarsystem/sun/transforms.asset`), maintaining heliocentric coordinates
  and avoiding mixing heliocentric and barycentric (SSB) frames.
- Horizons Vector Translation: OpenSpace's `HorizonsTranslation` component parses
  ephemeris vectors from `.hrz` files. The vectors are expected in kilometers (km)
  in the ECLIPJ2000 frame. OpenSpace automatically scales km to meters (* 1000)
  and rotates from ECLIPJ2000 to OpenSpace's internal GALACTIC frame using
  SpiceManager's position transformation matrix at J2000.

Units:
------
- Length: 1 AU = 149,597,870.7 km = 1.495978707e11 m (consistent with sim.constants.AU).
- File format: Ephemeris positions in `.hrz` files are recorded in kilometers (km).
- Body radii: Specified in SI meters (m) for RenderableSphereImageLocal.

Timestamps and Epochs:
----------------------
- Epoch t = 0.0 corresponds to J2000.0 (2000-Jan-01 12:00:00.0000 TDB, Julian Day 2451545.0).
- Time step: 1 simulation year is 1 Julian year (365.25 days = 31,557,600 seconds).
- Julian Day Number (JD) = 2451545.0 + t_years * 365.25.
- Dates beyond year 9999 (e.g. t > 8000 years): Formatted with 5-digit years
  (e.g., "10500-Mar-05 12:00:00.0000"). OpenSpace's tokenizer extracts date and time
  tokens separated by whitespace without buffer truncation. Note: CSPICE `str2et_c`
  calendar parsing for years > 9999 depends on SPICE kernel and calendar support.

Body Representation:
--------------------
- Handled bodies: Earth, Mars, asteroid (the tow asteroid), and optionally Jupiter.
- Absent bodies: Detected and handled explicitly; trajectories are NEVER fabricated
  for bodies not present in the simulation frames.
- Body Radii (nominal):
  - Earth: 6,371,000 m (6.371e6 m)
  - Mars: 3,389,500 m (3.3895e6 m)
  - Jupiter: 69,911,000 m (6.9911e7 m)
  - Asteroid: 335,000 m (3.35e5 m, mass-equivalent to ~4e20 kg tow asteroid)
- Tractor Link: When both Earth and the tow asteroid are present, a RenderableNodeLine
  connecting `BlackAnt_Earth` and `BlackAnt_TowAsteroid` is conditionally included.
  Fake laser beams or tractor links are never generated if endpoints are not tracked.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

# Physical and astronomical conversion constants
AU_M: float = 1.495978707e11
AU_KM: float = 149597870.7
J2000_JD: float = 2451545.0
DAYS_PER_JULIAN_YEAR: float = 365.25
SECONDS_PER_DAY: float = 86400.0

MONTH_NAMES: Sequence[str] = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
)

# Nominal body radii in meters
BODY_RADII_M: Mapping[str, float] = {
    "earth": 6371000.0,
    "mars": 3389500.0,
    "jupiter": 69911000.0,
    "asteroid": 335000.0,
}

# Display colors for trajectories (RGB normalized 0.0 - 1.0)
TRAIL_COLORS: Mapping[str, list[float]] = {
    "earth": [0.2, 0.7, 1.0],      # Light Blue
    "mars": [1.0, 0.4, 0.2],       # Red/Orange
    "asteroid": [0.95, 0.85, 0.3],  # Gold
    "jupiter": [0.85, 0.65, 0.45], # Tan/Orange
}

# Standard 1x1 pixel white RGBA PNG file (70 bytes, valid PNG specification)
# Used as a clean default texture for RenderableSphereImageLocal without external dependencies
WHITE_PNG_BYTES: bytes = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c63f8ffffff3f0005fe02fea73458fd0000000049454e44"
    "ae426082"
)


def years_to_jd(t_years: float, epoch_jd: float = J2000_JD) -> float:
    """Convert simulation time in Julian years from J2000.0 to Julian Day Number.

    Args:
        t_years: Simulation time elapsed in Julian years from epoch.
        epoch_jd: Julian day of the simulation epoch (default J2000.0 = 2451545.0).

    Returns:
        Julian Day Number (JD).
    """
    return epoch_jd + t_years * DAYS_PER_JULIAN_YEAR


def jd_to_calendar(jd: float) -> tuple[int, int, int, int, int, float]:
    """Convert Julian Day Number to Gregorian calendar (year, month, day, hour, min, sec).

    Uses the standard astronomical Gregorian calendar conversion (valid for all
    dates after October 15, 1582). Correctly handles 5-digit years (> 9999) and
    midnight rollover from floating-point rounding.

    Args:
        jd: Julian Day Number (e.g. 2451545.0 for J2000.0).

    Returns:
        Tuple of (year, month, day, hour, minute, second).
    """
    jd_offset = jd + 0.5
    z = int(math.floor(jd_offset))
    f = jd_offset - z

    if z < 2299161:
        a = z
    else:
        alpha = int((z - 1867216.25) / 36524.25)
        a = z + 1 + alpha - int(alpha / 4)

    b = a + 1524
    c = int((b - 122.1) / 365.25)
    d = int(365.25 * c)
    e = int((b - d) / 30.6001)

    day = b - d - int(30.6001 * e)
    month = e - 1 if e < 14 else e - 13
    year = c - 4716 if month > 2 else c - 4715

    total_sec = f * SECONDS_PER_DAY
    hour = int(total_sec // 3600)
    total_sec -= hour * 3600
    minute = int(total_sec // 60)
    second = total_sec - minute * 60

    # Guard against float rounding to 60.0000s
    if second >= 59.99995:
        second = 0.0
        minute += 1
        if minute >= 60:
            minute = 0
            hour += 1
            if hour >= 24:
                return jd_to_calendar(float(z) + 0.5)

    return year, month, day, hour, minute, second


def format_horizons_timestamp(jd: float) -> tuple[str, str, str]:
    """Format Julian Day into JPL Horizons standard timestamp tokens.

    Args:
        jd: Julian Day Number.

    Returns:
        Tuple of:
          - full_header_line: e.g. "2451545.000000000 = A.D. 2000-Jan-01 12:00:00.0000 TDB"
          - date_str: e.g. "2000-Jan-01" (or "10500-Mar-05" for year > 9999)
          - time_str: e.g. "12:00:00.0000"
    """
    year, month, day, hour, minute, second = jd_to_calendar(jd)
    month_name = MONTH_NAMES[month - 1]
    date_str = f"{year:04d}-{month_name}-{day:02d}"
    time_str = f"{hour:02d}:{minute:02d}:{second:07.4f}"
    full_line = f"{jd:17.9f} = A.D. {date_str} {time_str} TDB"
    return full_line, date_str, time_str


def format_spice_timestamp(jd: float) -> str:
    """Format Julian Day into standard OpenSpace / SPICE calendar timestamp string.

    Verified format matching working OpenSpace trajectory assets (e.g. Pioneer, Voyager,
    Rosetta, Gaia, Interstellar):
    'YYYY MON DD HH:MM:SS' (e.g. '2000 JAN 01 12:00:00').

    Args:
        jd: Julian Day Number.

    Returns:
        Formatted SPICE calendar date string accepted by SpiceManager::ephemerisTimeFromDate.
    """
    year, month, day, hour, minute, second = jd_to_calendar(jd)
    month_name = MONTH_NAMES[month - 1].upper()
    sec_int = int(math.floor(second))
    sec_frac = second - sec_int
    if sec_frac >= 0.0005:
        sec_str = f"{second:06.3f}"
    else:
        sec_str = f"{sec_int:02d}"
    return f"{year:04d} {month_name} {day:02d} {hour:02d}:{minute:02d}:{sec_str}"


def parse_run_data(run_path_or_dict: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Load and validate Black Ant simulation run data.

    Args:
        run_path_or_dict: Path to run.json or an already loaded dictionary.

    Returns:
        Validated run data dictionary containing 'frames' and 'meta'.

    Raises:
        FileNotFoundError: If the input file does not exist.
        ValueError: If the input data lacks required fields.
    """
    if isinstance(run_path_or_dict, (str, Path)):
        path = Path(run_path_or_dict)
        if not path.is_file():
            raise FileNotFoundError(f"Simulation run file not found: {path}")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    elif isinstance(run_path_or_dict, Mapping):
        data = dict(run_path_or_dict)
    else:
        raise TypeError(f"Expected path or dict, got {type(run_path_or_dict).__name__}")

    if "frames" not in data or not isinstance(data["frames"], list):
        raise ValueError("Invalid run data: 'frames' list is required")

    return data


def get_available_bodies(frames: Sequence[Mapping[str, Any]]) -> list[str]:
    """Identify celestial bodies present in the simulation frames.

    Args:
        frames: List of simulation frame dictionaries.

    Returns:
        List of body names found in the frames, in deterministic order.
    """
    bodies: set[str] = set()
    for frame in frames:
        pos = frame.get("pos", {})
        if isinstance(pos, dict):
            bodies.update(pos.keys())

    # Preferred presentation order: earth, mars, asteroid, jupiter, then any others
    preferred_order = ["earth", "mars", "asteroid", "jupiter"]
    ordered: list[str] = [b for b in preferred_order if b in bodies]
    remaining: list[str] = sorted(b for b in bodies if b not in preferred_order)
    return ordered + remaining


def generate_horizons_vector_text(
    frames: Sequence[Mapping[str, Any]],
    body_name: str,
    target_title: str | None = None,
) -> str:
    """Generate a JPL Horizons-compliant vector ephemeris file content (.hrz).

    The generated file matches the exact format parsed by OpenSpace's
    `modules/space/horizonsfile.cpp` (`readHorizonsVectorFile`):
    - Header contains 'Revised' and 'JPL' markers to pass `isValidHorizonsFile`.
    - Header contains 'JDTDB' to trigger Vector file detection in `readHorizonsFile`.
    - Data section bounded by '$$SOE' and '$$EOE'.
    - Alternating two-line records:
        Line 1: JulianDayNumber = A.D. YYYY-Mon-DD HH:MM:SS.0000 TDB
        Line 2:   X Y Z (Cartesian coordinates in kilometers)

    Args:
        frames: Sequence of simulation frames.
        body_name: Key of the body in frame['pos'] (e.g. 'earth', 'mars', 'asteroid').
        target_title: Optional human-readable title for the body in the header.

    Returns:
        String containing full .hrz file contents.

    Raises:
        ValueError: If no frames contain the specified body.
    """
    body_frames = [
        f for f in frames
        if "pos" in f and isinstance(f["pos"], dict) and body_name in f["pos"]
    ]

    if not body_frames:
        raise ValueError(f"No trajectory frames found for body '{body_name}'")

    display_title = target_title or body_name.capitalize()
    first_t = float(body_frames[0].get("t", 0.0))
    last_t = float(body_frames[-1].get("t", 0.0))
    first_jd = years_to_jd(first_t)
    last_jd = years_to_jd(last_t)
    _, start_date, start_time = format_horizons_timestamp(first_jd)
    _, stop_date, stop_time = format_horizons_timestamp(last_jd)

    lines: list[str] = [
        "*******************************************************************************",
        f" Revised: Jan 01, 2000          Black Ant Simulation / {display_title}",
        " JPL/Horizons Simulation Output Ephemeris",
        "*******************************************************************************",
        f"Target body name: {display_title}",
        "Center body name: Sun (10) {source: Black Ant heliocentric simulation}",
        "Center-site name: BODY CENTER",
        "*******************************************************************************",
        f"Start time      : A.D. {start_date} {start_time} TDB",
        f"Stop  time      : A.D. {stop_date} {stop_time} TDB",
        "Output units    : KM",
        "Output format   : 1 (position only)",
        "Reference frame : Ecliptic of J2000.0",
        "*******************************************************************************",
        "JDTDB",
        "   X     Y     Z",
        "*******************************************************************************",
        "$$SOE",
    ]

    for frame in body_frames:
        t_yr = float(frame.get("t", 0.0))
        jd = years_to_jd(t_yr)
        full_time_line, _, _ = format_horizons_timestamp(jd)

        # Coordinate conversion: AU -> km
        pos_au = frame["pos"][body_name]
        x_km = float(pos_au[0]) * AU_KM
        y_km = float(pos_au[1]) * AU_KM
        z_km = float(pos_au[2]) * AU_KM

        lines.append(full_time_line)
        lines.append(f"   {x_km:22.15E}  {y_km:22.15E}  {z_km:22.15E}")

    lines.append("$$EOE")
    lines.append("*******************************************************************************")
    lines.append("")  # Trailing newline

    return "\n".join(lines)


def generate_openspace_asset(
    bodies: Sequence[str],
    relative_trajectory_files: Mapping[str, str],
    time_bounds: tuple[str, str, float],
    has_tractor_link: bool = False,
    texture_filename: str = "sphere_texture.png",
) -> str:
    """Generate OpenSpace Lua scene asset content (black_ant.asset).

    The asset registers scene graph nodes for each body and its trajectory trail,
    and conditionally adds a RenderableNodeLine representing the asteroid tow link.

    Args:
        bodies: List of body keys present in the run.
        relative_trajectory_files: Mapping from body name to relative .hrz filename.
        time_bounds: Tuple of (start_iso_date, end_iso_date, sample_interval_seconds).
        has_tractor_link: Whether to add a RenderableNodeLine between Earth and Asteroid.
        texture_filename: Relative filename of the sphere texture PNG.

    Returns:
        Valid Lua code for black_ant.asset.
    """
    start_date, end_date, sample_interval = time_bounds

    node_identifiers: list[str] = []
    lua_parts: list[str] = [
        '-- Black Ant Planetary Propulsion Simulation Scene Asset',
        '-- Generated automatically by Black Ant OpenSpace Adapter',
        '-- Verified compatible with OpenSpace 0.22.0-dev',
        '',
        'local sunAsset = asset.require("scene/solarsystem/sun/transforms")',
        '',
        f'local sphereTexture = asset.resource("{texture_filename}")',
        '',
    ]

    # Trajectory files
    for body in bodies:
        hrz_file = relative_trajectory_files[body]
        var_name = f"{body}Trajectory"
        lua_parts.append(f'local {var_name} = asset.resource("{hrz_file}")')
    lua_parts.append("")

    # Node definitions for each body
    for body in bodies:
        display_name = body.capitalize()
        if body == "asteroid":
            display_name = "Tow Asteroid"

        node_id = f"BlackAnt_{display_name.replace(' ', '')}"
        trail_id = f"{node_id}Trail"
        node_identifiers.extend([trail_id, node_id])

        hrz_var = f"{body}Trajectory"
        radius_m = BODY_RADII_M.get(body, 100000.0)
        color = TRAIL_COLORS.get(body, [1.0, 1.0, 1.0])
        color_str = f"{{ {color[0]:.2f}, {color[1]:.2f}, {color[2]:.2f} }}"

        # Trail node (RenderableTrailTrajectory)
        lua_parts.extend([
            f'local {trail_id} = {{',
            f'  Identifier = "{trail_id}",',
            '  Parent = sunAsset.SunCenter.Identifier,',
            '  Renderable = {',
            '    Type = "RenderableTrailTrajectory",',
            '    Translation = {',
            '      Type = "HorizonsTranslation",',
            f'      HorizonsTextFile = {hrz_var},',
            '    },',
            f'    Color = {color_str},',
            f'    StartTime = "{start_date}",',
            f'    EndTime = "{end_date}",',
            f'    SampleInterval = {sample_interval:.1f},',
            '    ShowFullTrail = true,',
            '  },',
            '  GUI = {',
            f'    Name = "{display_name} Trail",',
            '    Path = "/Black Ant/Trajectories",',
            '    Focusable = false,',
            '  }',
            '}',
            '',
            f'local {node_id} = {{',
            f'  Identifier = "{node_id}",',
            '  Parent = sunAsset.SunCenter.Identifier,',
            '  Transform = {',
            '    Translation = {',
            '      Type = "HorizonsTranslation",',
            f'      HorizonsTextFile = {hrz_var},',
            '    }',
            '  },',
            '  Renderable = {',
            '    Type = "RenderableSphereImageLocal",',
            f'    Size = {radius_m:.1f},',
            '    Segments = 32,',
            '    Texture = sphereTexture,',
            '    Orientation = "Outside",',
            '  },',
            '  GUI = {',
            f'    Name = "{display_name}",',
            '    Path = "/Black Ant/Bodies",',
            '    Focusable = true,',
            '  }',
            '}',
            '',
        ])

    # Conditionally add Tractor Link if both earth and asteroid are present
    tractor_node_id = "BlackAnt_TractorLink"
    if has_tractor_link and "earth" in bodies and "asteroid" in bodies:
        node_identifiers.append(tractor_node_id)
        lua_parts.extend([
            '-- Active Asteroid Tow Gravity / Light Tractor Link',
            f'local {tractor_node_id} = {{',
            f'  Identifier = "{tractor_node_id}",',
            '  Renderable = {',
            '    Type = "RenderableNodeLine",',
            '    StartNode = "BlackAnt_Earth",',
            '    EndNode = "BlackAnt_TowAsteroid",',
            '    Color = { 0.2, 1.0, 0.4 },',
            '    LineWidth = 2.0,',
            '  },',
            '  GUI = {',
            '    Name = "Asteroid Tow Link",',
            '    Path = "/Black Ant/Mission",',
            '    Description = "Tractor link between Earth and the propulsion tow asteroid",',
            '    Focusable = false,',
            '  }',
            '}',
            '',
        ])

    # Lifecycle registration
    lua_parts.extend([
        'asset.onInitialize(function()',
    ])
    for nid in node_identifiers:
        lua_parts.append(f'  openspace.addSceneGraphNode({nid})')
    lua_parts.extend([
        'end)',
        '',
        'asset.onDeinitialize(function()',
    ])
    for nid in reversed(node_identifiers):
        lua_parts.append(f'  openspace.removeSceneGraphNode({nid})')
    lua_parts.extend([
        'end)',
        '',
    ])

    # Export nodes
    for nid in node_identifiers:
        lua_parts.append(f'asset.export({nid})')
    lua_parts.extend([
        '',
        'asset.meta = {',
        '  Name = "Black Ant Simulation",',
        '  Version = "1.0",',
        '  Description = [[Visualization of Black Ant planetary propulsion and asteroid tow',
        '    simulation converting Earth and Mars orbits.]],',
        '  Author = "Black Ant Simulation Team",',
        '  URL = "https://github.com/planetary-propulsion/black-ant",',
        '  License = "MIT license"',
        '}',
        '',
    ])

    return "\n".join(lua_parts)


def export_openspace(
    run_data_or_path: str | Path | Mapping[str, Any],
    out_dir: str | Path,
) -> dict[str, Any]:
    """Convert Black Ant simulation run into an OpenSpace visualization bundle.

    Creates:
    - Trajectory ephemeris files (<body_name>_trajectory.hrz) for all present bodies.
    - Standard 1x1 white PNG texture (sphere_texture.png) for RenderableSphereImageLocal.
    - Lua asset file (black_ant.asset) that loads the bodies, trails, and optional tow link.

    Args:
        run_data_or_path: Path to run.json or pre-loaded dictionary.
        out_dir: Target output directory where assets and trajectories will be saved.

    Returns:
        Dictionary containing paths to all created files.
    """
    data = parse_run_data(run_data_or_path)
    frames = data["frames"]
    if not frames:
        raise ValueError("Simulation run contains zero frames")

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    bodies = get_available_bodies(frames)
    if not bodies:
        raise ValueError("No celestial body positions found in simulation frames")

    created_files: dict[str, Any] = {
        "out_dir": str(out),
        "trajectories": {},
    }

    # 1. Write .hrz trajectory files for each present body
    relative_hrz: dict[str, str] = {}
    for body in bodies:
        filename = f"{body}_trajectory.hrz"
        hrz_text = generate_horizons_vector_text(frames, body)
        file_path = out / filename
        file_path.write_text(hrz_text, encoding="utf-8")
        relative_hrz[body] = filename
        created_files["trajectories"][body] = str(file_path)

    # 2. Write default 1x1 white texture PNG for RenderableSphereImageLocal
    texture_path = out / "sphere_texture.png"
    texture_path.write_bytes(WHITE_PNG_BYTES)
    created_files["texture"] = str(texture_path)

    # 3. Determine time boundaries for RenderableTrailTrajectory
    first_t = float(frames[0].get("t", 0.0))
    last_t = float(frames[-1].get("t", 0.0))
    first_jd = years_to_jd(first_t)
    last_jd = years_to_jd(last_t)
    start_spice = format_spice_timestamp(first_jd)
    end_spice = format_spice_timestamp(last_jd)

    # Sample interval calculation: duration in seconds divided by number of steps
    total_seconds = max(1.0, (last_jd - first_jd) * SECONDS_PER_DAY)
    sample_interval = max(SECONDS_PER_DAY, total_seconds / max(1, len(frames)))

    # Determine whether Earth tow link is active in data
    has_active_tow = any(f.get("earth_tow_active", False) for f in frames)
    has_tractor_link = has_active_tow and ("earth" in bodies) and ("asteroid" in bodies)

    # 4. Generate and write black_ant.asset
    asset_text = generate_openspace_asset(
        bodies=bodies,
        relative_trajectory_files=relative_hrz,
        time_bounds=(start_spice, end_spice, sample_interval),
        has_tractor_link=has_tractor_link,
        texture_filename="sphere_texture.png",
    )
    asset_path = out / "black_ant.asset"
    asset_path.write_text(asset_text, encoding="utf-8")
    created_files["asset"] = str(asset_path)

    return created_files


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line interface for the Black Ant OpenSpace adapter."""
    parser = argparse.ArgumentParser(
        description="Convert Black Ant simulation run output into OpenSpace 0.22.0-dev assets.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    # Default to results/run.json if present, otherwise out/run.json
    default_run = "results/run.json" if Path("results/run.json").is_file() else "out/run.json"
    parser.add_argument(
        "--run",
        default=default_run,
        help="Path to Black Ant run.json simulation output",
    )
    parser.add_argument(
        "--out",
        default="out/openspace",
        help="Output directory for generated OpenSpace asset and .hrz files",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    args = parser.parse_args(argv)

    run_path = Path(args.run)
    if not run_path.is_file():
        print(f"Error: Run file not found: {run_path}", file=sys.stderr)
        return 1

    try:
        res = export_openspace(run_path, args.out)
        out_dir = Path(res["out_dir"])
        print(f"Successfully generated OpenSpace visualization assets in: {out_dir}")
        print(f"  Asset file: {Path(res['asset']).name}")
        print(f"  Texture:    {Path(res['texture']).name}")
        for body, path in res["trajectories"].items():
            print(f"  Trajectory ({body}): {Path(path).name}")
        return 0
    except Exception as e:
        print(f"Error generating OpenSpace assets: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

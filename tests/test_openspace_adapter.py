"""Unit tests for the OpenSpace visualization adapter (sim.adapters.openspace)."""

import json
from pathlib import Path

import pytest

from sim.adapters.openspace import (
    AU_KM,
    BODY_RADII_M,
    J2000_JD,
    WHITE_PNG_BYTES,
    export_openspace,
    format_horizons_timestamp,
    format_spice_timestamp,
    generate_horizons_vector_text,
    generate_openspace_asset,
    get_available_bodies,
    jd_to_calendar,
    main,
    parse_run_data,
    years_to_jd,
)

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "sample_run.json"


def parse_horizons_vector_records(hrz_text: str) -> list[dict]:
    """Strict parser emulating OpenSpace HorizonsFile::readHorizonsVectorFile.

    Verifies:
    - Header contains valid target indicator ('Revised' or 'JPL')
    - Header contains 'JDTDB' before $$SOE
    - Extracts every 2-line record between $$SOE and $$EOE
    - Enforces 6 whitespace tokens on line 1: <jd> = A.D. <date> <time> TDB
    - Enforces 3 float tokens on line 2: <x> <y> <z>
    - Enforces strictly increasing chronological ordering of JD
    - Rejects malformed lines or incomplete record pairs
    """
    lines = [line.strip() for line in hrz_text.splitlines() if line.strip()]

    # Header checks
    soe_idx = None
    eoe_idx = None
    has_target = False
    has_jdtdb = False

    for i, line in enumerate(lines):
        if line == "$$SOE":
            soe_idx = i
            break
        if "Revised" in line or "JPL" in line:
            has_target = True
        if line.startswith("JDTDB"):
            has_jdtdb = True

    if not has_target:
        raise ValueError("Header missing 'Revised' or 'JPL' target marker")
    if not has_jdtdb:
        raise ValueError("Header missing 'JDTDB' vector table marker")
    if soe_idx is None:
        raise ValueError("File missing '$$SOE' marker")

    for i in range(soe_idx + 1, len(lines)):
        if lines[i] == "$$EOE":
            eoe_idx = i
            break
    if eoe_idx is None:
        raise ValueError("File missing '$$EOE' marker")

    data_lines = lines[soe_idx + 1:eoe_idx]
    if len(data_lines) % 2 != 0:
        raise ValueError(f"Odd number of data lines between $$SOE and $$EOE: {len(data_lines)}")

    records = []
    prev_jd = -float("inf")

    for i in range(0, len(data_lines), 2):
        line1 = data_lines[i]
        line2 = data_lines[i + 1]

        # Tokenize line 1
        tokens1 = line1.split()
        if len(tokens1) != 6:
            raise ValueError(f"Malformed timestamp line: expected 6 tokens, got {len(tokens1)} in '{line1}'")
        if tokens1[1] != "=" or tokens1[2] != "A.D." or tokens1[5] != "TDB":
            raise ValueError(f"Malformed timestamp syntax in '{line1}'")

        try:
            jd_val = float(tokens1[0])
        except ValueError:
            raise ValueError(f"Invalid Julian Day number in '{line1}'")

        if jd_val <= prev_jd:
            raise ValueError(f"Non-chronological JD record: {jd_val} <= {prev_jd}")
        prev_jd = jd_val

        # Tokenize line 2
        tokens2 = line2.split()
        if len(tokens2) != 3:
            raise ValueError(f"Malformed position line: expected 3 tokens, got {len(tokens2)} in '{line2}'")

        try:
            pos = [float(c) for c in tokens2]
        except ValueError:
            raise ValueError(f"Invalid floating-point coordinates in '{line2}'")

        records.append({
            "jd": jd_val,
            "date": tokens1[3],
            "time": tokens1[4],
            "pos_km": pos,
        })

    return records


def test_years_to_jd():
    """Verify simulation year to Julian Day conversion at epoch and offsets."""
    assert years_to_jd(0.0) == J2000_JD
    assert years_to_jd(10.0) == J2000_JD + 3652.5
    assert years_to_jd(100.0) == J2000_JD + 36525.0


def test_jd_to_calendar_epoch():
    """Verify J2000.0 (JD 2451545.0) calendar conversion to 2000-Jan-01 12:00:00."""
    year, month, day, hour, minute, second = jd_to_calendar(J2000_JD)
    assert year == 2000
    assert month == 1
    assert day == 1
    assert hour == 12
    assert minute == 0
    assert pytest.approx(second, abs=1e-4) == 0.0

    full_line, date_str, time_str = format_horizons_timestamp(J2000_JD)
    assert date_str == "2000-Jan-01"
    assert time_str == "12:00:00.0000"
    assert full_line.strip() == "2451545.000000000 = A.D. 2000-Jan-01 12:00:00.0000 TDB"


def test_jd_to_calendar_intermediate():
    """Verify intermediate frame timestamp (t = 10.1 yr)."""
    jd = years_to_jd(10.1)
    year, month, day, hour, minute, second = jd_to_calendar(jd)
    assert year == 2010
    assert month == 2
    assert day == 6
    assert hour == 12
    assert minute == 36
    assert pytest.approx(second, abs=1e-4) == 0.0

    _, date_str, time_str = format_horizons_timestamp(jd)
    assert date_str == "2010-Feb-06"
    assert time_str == "12:36:00.0000"


def test_format_spice_timestamp():
    """Verify OpenSpace / SPICE calendar date string format for scene assets."""
    assert format_spice_timestamp(J2000_JD) == "2000 JAN 01 12:00:00"
    assert format_spice_timestamp(years_to_jd(10.1)) == "2010 FEB 06 12:36:00"
    assert format_spice_timestamp(years_to_jd(50.0)) == "2050 JAN 01 00:00:00"
    assert format_spice_timestamp(years_to_jd(8500.0)) == "10500 MAR 05 12:00:00"


def test_years_beyond_9999():
    """Verify calendar conversion and tokenization for years beyond 9999 (A.D. 10000+)."""
    # 8500 years after J2000.0 corresponds to year 10500
    jd = years_to_jd(8500.0)
    year, month, day, hour, minute, second = jd_to_calendar(jd)
    assert year == 10500
    assert month == 3
    assert day == 5

    full_line, date_str, time_str = format_horizons_timestamp(jd)
    assert date_str == "10500-Mar-05"
    assert time_str == "12:00:00.0000"

    # OpenSpace Horizons parser expects 6 whitespace-delimited tokens on line 1:
    # JulianDay = A.D. YYYY-Mon-DD HH:MM:SS TDB
    tokens = full_line.split()
    assert len(tokens) == 6
    assert tokens[1] == "="
    assert tokens[2] == "A.D."
    assert tokens[3] == "10500-Mar-05"
    assert tokens[4] == "12:00:00.0000"
    assert tokens[5] == "TDB"


def test_horizons_vector_full_parsing_and_frames():
    """Verify every record between $$SOE and $$EOE and check first, intermediate, and last frames."""
    with open(FIXTURE_PATH, encoding="utf-8") as f:
        run_data = json.load(f)

    frames = run_data["frames"]
    hrz_text = generate_horizons_vector_text(frames, "earth")

    # Parse using strict OpenSpace Horizons state machine
    records = parse_horizons_vector_records(hrz_text)
    assert len(records) == 3

    # Check chronological ordering
    assert records[0]["jd"] < records[1]["jd"] < records[2]["jd"]

    # 1. First frame (t = 0.0 yr)
    rec0 = records[0]
    assert rec0["jd"] == J2000_JD
    assert rec0["date"] == "2000-Jan-01"
    assert rec0["time"] == "12:00:00.0000"
    expected_pos0 = [
        frames[0]["pos"]["earth"][0] * AU_KM,
        frames[0]["pos"]["earth"][1] * AU_KM,
        frames[0]["pos"]["earth"][2] * AU_KM,
    ]
    assert pytest.approx(rec0["pos_km"][0], rel=1e-5) == expected_pos0[0]
    assert pytest.approx(rec0["pos_km"][1], rel=1e-5) == expected_pos0[1]
    assert pytest.approx(rec0["pos_km"][2], abs=1e-5) == expected_pos0[2]

    # 2. Intermediate frame (t = 10.1 yr)
    rec1 = records[1]
    assert pytest.approx(rec1["jd"], abs=1e-5) == years_to_jd(10.1)
    assert rec1["date"] == "2010-Feb-06"
    assert rec1["time"] == "12:36:00.0000"
    expected_pos1 = [
        frames[1]["pos"]["earth"][0] * AU_KM,
        frames[1]["pos"]["earth"][1] * AU_KM,
        frames[1]["pos"]["earth"][2] * AU_KM,
    ]
    assert pytest.approx(rec1["pos_km"][0], rel=1e-5) == expected_pos1[0]
    assert pytest.approx(rec1["pos_km"][1], rel=1e-5) == expected_pos1[1]
    assert pytest.approx(rec1["pos_km"][2], rel=1e-5) == expected_pos1[2]

    # 3. Last frame (t = 50.0 yr)
    rec2 = records[2]
    assert pytest.approx(rec2["jd"], abs=1e-5) == years_to_jd(50.0)
    assert rec2["date"] == "2050-Jan-01"
    assert rec2["time"] == "00:00:00.0000"
    expected_pos2 = [
        frames[2]["pos"]["earth"][0] * AU_KM,
        frames[2]["pos"]["earth"][1] * AU_KM,
        frames[2]["pos"]["earth"][2] * AU_KM,
    ]
    assert pytest.approx(rec2["pos_km"][0], rel=1e-5) == expected_pos2[0]
    assert pytest.approx(rec2["pos_km"][1], rel=1e-5) == expected_pos2[1]
    assert pytest.approx(rec2["pos_km"][2], rel=1e-5) == expected_pos2[2]


def test_horizons_parser_rejects_malformed_records():
    """Verify parser enforces structure, token counts, and rejects malformed records."""
    valid_header = (
        "*******************************************************************************\n"
        " Revised: Jan 01, 2000 Black Ant Simulation\n"
        " JPL/Horizons Simulation Output Ephemeris\n"
        "JDTDB\n"
        "   X     Y     Z\n"
        "*******************************************************************************\n"
        "$$SOE\n"
    )
    valid_footer = "$$EOE\n*******************************************************************************\n"

    # Missing target in header (neither Revised nor JPL present)
    bad_header = (
        valid_header.replace("Revised: Jan 01, 2000", "Date: Jan 01, 2000")
        .replace("JPL/Horizons", "Custom/Ephemeris")
    )
    with pytest.raises(ValueError, match="missing 'Revised' or 'JPL'"):
        parse_horizons_vector_records(bad_header + valid_footer)

    # Missing JDTDB
    no_jdtdb = valid_header.replace("JDTDB\n", "")
    with pytest.raises(ValueError, match="missing 'JDTDB'"):
        parse_horizons_vector_records(no_jdtdb + valid_footer)

    # Odd number of data lines (timestamp without position)
    odd_data = (
        valid_header
        + "2451545.000000000 = A.D. 2000-Jan-01 12:00:00.0000 TDB\n"
        + valid_footer
    )
    with pytest.raises(ValueError, match="Odd number of data lines"):
        parse_horizons_vector_records(odd_data)

    # Malformed timestamp line (missing TDB token)
    missing_token = (
        valid_header
        + "2451545.000000000 = A.D. 2000-Jan-01 12:00:00.0000\n"
        + "   1.0  2.0  3.0\n"
        + valid_footer
    )
    with pytest.raises(ValueError, match="expected 6 tokens"):
        parse_horizons_vector_records(missing_token)

    # Non-chronological records
    reversed_data = (
        valid_header
        + "2455234.025000000 = A.D. 2010-Feb-06 12:36:00.0000 TDB\n"
        + "   1.0  2.0  3.0\n"
        + "2451545.000000000 = A.D. 2000-Jan-01 12:00:00.0000 TDB\n"
        + "   4.0  5.0  6.0\n"
        + valid_footer
    )
    with pytest.raises(ValueError, match="Non-chronological JD record"):
        parse_horizons_vector_records(reversed_data)


def test_absent_body_handling():
    """Verify that absent bodies raise ValueError and are not fabricated."""
    frames = [
        {"t": 0.0, "pos": {"earth": [1.0, 0.0, 0.0]}},
        {"t": 1.0, "pos": {"earth": [0.0, 1.0, 0.0]}},
    ]
    bodies = get_available_bodies(frames)
    assert bodies == ["earth"]
    assert "mars" not in bodies
    assert "asteroid" not in bodies

    with pytest.raises(ValueError, match="No trajectory frames found for body 'mars'"):
        generate_horizons_vector_text(frames, "mars")


def test_asset_generation_and_tractor_link():
    """Verify black_ant.asset Lua script contains correct scene graph nodes and tractor link."""
    bodies = ["earth", "mars", "asteroid"]
    relative_files = {
        "earth": "earth_trajectory.hrz",
        "mars": "mars_trajectory.hrz",
        "asteroid": "asteroid_trajectory.hrz",
    }
    time_bounds = ("2000 JAN 01 12:00:00", "2050 JAN 01 00:00:00", 864000.0)

    # 1. With tractor link enabled
    asset_with_tow = generate_openspace_asset(
        bodies=bodies,
        relative_trajectory_files=relative_files,
        time_bounds=time_bounds,
        has_tractor_link=True,
    )

    # Heliocentric parenting check
    assert 'Parent = sunAsset.SunCenter.Identifier' in asset_with_tow
    # Trajectory types
    assert 'Type = "RenderableTrailTrajectory"' in asset_with_tow
    assert 'Type = "HorizonsTranslation"' in asset_with_tow
    assert 'Type = "RenderableSphereImageLocal"' in asset_with_tow
    # SPICE-compliant time boundaries
    assert 'StartTime = "2000 JAN 01 12:00:00"' in asset_with_tow
    assert 'EndTime = "2050 JAN 01 00:00:00"' in asset_with_tow
    # Tractor link check
    assert 'Type = "RenderableNodeLine"' in asset_with_tow
    assert 'StartNode = "BlackAnt_Earth"' in asset_with_tow
    assert 'EndNode = "BlackAnt_TowAsteroid"' in asset_with_tow
    # Radii check
    assert f'Size = {BODY_RADII_M["earth"]:.1f}' in asset_with_tow
    assert f'Size = {BODY_RADII_M["mars"]:.1f}' in asset_with_tow

    # 2. Without tractor link (e.g. absent asteroid)
    asset_without_tow = generate_openspace_asset(
        bodies=["earth", "mars"],
        relative_trajectory_files={"earth": "earth.hrz", "mars": "mars.hrz"},
        time_bounds=time_bounds,
        has_tractor_link=False,
    )
    assert 'Type = "RenderableNodeLine"' not in asset_without_tow


def test_export_openspace_bundle(tmp_path):
    """Test full bundle export using sample_run.json fixture."""
    res = export_openspace(FIXTURE_PATH, tmp_path / "openspace_bundle")
    out_dir = Path(res["out_dir"])

    assert out_dir.is_dir()
    asset_path = out_dir / "black_ant.asset"
    assert asset_path.is_file()
    assert (out_dir / "earth_trajectory.hrz").is_file()
    assert (out_dir / "mars_trajectory.hrz").is_file()
    assert (out_dir / "asteroid_trajectory.hrz").is_file()
    assert (out_dir / "jupiter_trajectory.hrz").is_file()
    assert (out_dir / "sphere_texture.png").is_file()

    # Verify PNG texture is valid and exactly 70 bytes
    png_bytes = (out_dir / "sphere_texture.png").read_bytes()
    assert png_bytes == WHITE_PNG_BYTES
    assert png_bytes.startswith(b"\x89PNG\r\n\x1a\n")

    # Verify SPICE StartTime and EndTime inside the generated black_ant.asset
    asset_content = asset_path.read_text(encoding="utf-8")
    assert 'StartTime = "2000 JAN 01 12:00:00"' in asset_content
    assert 'EndTime = "2050 JAN 01 00:00:00"' in asset_content

    # Strict parser verification of all generated trajectory files
    for hrz_file in out_dir.glob("*.hrz"):
        records = parse_horizons_vector_records(hrz_file.read_text(encoding="utf-8"))
        assert len(records) == 3


def test_cli_execution(tmp_path):
    """Test the CLI entry point with --run and --out flags."""
    out_dir = tmp_path / "cli_out"
    exit_code = main(["--run", str(FIXTURE_PATH), "--out", str(out_dir)])
    assert exit_code == 0
    assert (out_dir / "black_ant.asset").is_file()
    assert (out_dir / "earth_trajectory.hrz").is_file()

    # Non-existent run file
    exit_fail = main(["--run", str(tmp_path / "missing.json"), "--out", str(out_dir)])
    assert exit_fail == 1

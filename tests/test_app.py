"""The test bench web app only starts known command lines with checked inputs and serves files from results/ and out/."""

import pytest

from app.server import BY_ID, ROOT, build_command, inside_allowed, parse_pytest


def test_journey_command_uses_the_cli_flags():
    cmd = build_command(BY_ID["journey"], {"years": 300, "no_belt": True, "no_mars_tow": False}, ROOT / "out" / "x")
    assert cmd[2:4] == ["-m", "sim.scenarios.tow"]
    assert ["--years", "300"] == cmd[cmd.index("--years"):cmd.index("--years") + 2]
    assert "--no-belt" in cmd and "--no-mars-tow" not in cmd


@pytest.mark.parametrize("params", [{"years": 1e6}, {"orbits": "square"}, {"dt_days": 0}])
def test_out_of_range_inputs_are_refused(params):
    with pytest.raises(ValueError):
        build_command(BY_ID["journey"], params, ROOT / "out" / "x")


def test_epoch_text_cannot_smuggle_commands():
    with pytest.raises(ValueError):
        build_command(BY_ID["moon_coupled"], {"epochs": "1.0; rm -rf /"}, ROOT / "out" / "x")
    cmd = build_command(BY_ID["moon_coupled"], {"epochs": "1.0 middle 2.7"}, ROOT / "out" / "x")
    assert cmd[cmd.index("--epochs") + 1:cmd.index("--epochs") + 4] == ["1.0", "middle", "2.7"]


def test_paths_outside_results_and_out_are_refused():
    assert inside_allowed("results") == (ROOT / "results").resolve()
    for bad in ("../", "config.yaml", "results/../sim", "/etc"):
        with pytest.raises(ValueError):
            inside_allowed(bad)


def test_pytest_summary_is_parsed():
    out = parse_pytest(["PASSED tests/test_a.py::test_one", "FAILED tests/test_a.py::test_two - assert 1 == 2",
                        "SKIPPED [1] tests/x.py:3: slow", "==== 1 passed, 1 failed in 0.1s ===="])
    assert [t["status"] for t in out["tests"]][:2] == ["PASSED", "FAILED"]
    assert "1 passed" in out["summary"]

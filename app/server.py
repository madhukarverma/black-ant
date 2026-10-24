"""Black Ant test bench: a local web app over the physics core.

The physics stays in sim/ and never imports anything from here. This server only starts the same command-line
runs a person would type, one at a time, and serves their saved results to the browser page in app/static/.

Run from the project root:
    uv run python -m app.server              # then open http://localhost:8765
    uv run python -m app.server --port 9000

Endpoints (all JSON unless noted):
    GET  /api/experiments            what can be run, with parameters, defaults and limits
    POST /api/run                    {"experiment": id, "params": {...}} -> {"job": id}
    GET  /api/jobs/<id>              status, progress lines, and where the result went
    GET  /api/runs                   saved journey runs (results/ and out/*/ with summary.json + run.json)
    GET  /api/run?path=out/x         that run's summary and frames
    GET  /api/file?path=results/baseline.json   any saved result JSON inside results/ or out/
    GET  /api/latest?file=baseline.json         the newest such file in results/ or out/app/*/
    GET  /api/export.csv?path=out/x  the run's frames as CSV (download)
"""

import argparse
import csv
import io
import json
import re
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
STATIC = Path(__file__).resolve().parent / "static"
ALLOWED_ROOTS = (ROOT / "results", ROOT / "out")

# Each experiment is one command line. Parameters are checked against these limits before anything runs.
EXPERIMENTS = [
    {"id": "journey", "label": "Journey", "kind": "journey", "summary": "Earth from 1 AU to 2.7 AU, Mars moved first",
     "question": "Tow Earth from 1 AU to 2.7 AU, Mars first. Does Earth arrive within 10,000 years, safely, with every force booked?",
     "module": "sim.scenarios.tow", "minutes": "1 min per ~700 simulated years without the belt",
     "params": [
         {"group": "Run length", "key": "years", "label": "Simulated years", "type": "number", "default": 500, "min": 10, "max": 10000, "flag": "--years"},
         {"group": "Run length", "key": "dt_days", "label": "Step (days)", "type": "number", "default": 1.0, "min": 0.25, "max": 2.0, "flag": "--dt-days"},
         {"group": "Design", "key": "mars_stop_au", "label": "Mars parks at (AU)", "type": "number", "default": 3.64, "min": 2.9, "max": 4.2, "flag": "--mars-stop-au"},
         {"group": "Starting point", "key": "orbits", "label": "Starting orbits", "type": "choice", "default": "real", "choices": ["real", "circular"], "flag": "--orbits"},
         {"group": "Design", "key": "no_mars_tow", "label": "Leave Mars where it is", "type": "bool", "default": False, "flag": "--no-mars-tow"},
         {"group": "Checks", "key": "no_belt", "label": "Skip the asteroid-belt sample (faster)", "type": "bool", "default": True, "flag": "--no-belt"},
     ]},
    {"id": "baseline", "label": "Baseline", "kind": "baseline", "summary": "Real solar system with the Moon, no push",
     "question": "Sun, planets, Earth and Moon from their real J2000 positions with no push. Do energy and momentum hold, and does the Moon behave?",
     "module": "sim.scenarios.baseline", "minutes": "about 15 s for 10 years",
     "params": [
         {"group": "Run length", "key": "years", "label": "Simulated years", "type": "number", "default": 10, "min": 1, "max": 100, "flag": "--years"},
         {"group": "Bodies", "key": "bodies", "label": "Bodies", "type": "choice", "default": "planets", "choices": ["planets", "sem"], "flag": "--bodies"},
         {"group": "Run length", "key": "dt_hours", "label": "Step (hours)", "type": "number", "default": 0.25, "min": 0.05, "max": 2.0, "flag": "--dt-hours"},
     ]},
    {"id": "moon_coupled", "label": "Moon beside the tow", "kind": "moon_coupled", "summary": "Moon as a full body next to the live tow",
     "question": "The Moon as a full body next to the live tow. Does it stay with Earth, and how much extra beam power does its pull on the asteroid cost?",
     "module": "sim.scenarios.moon_coupled", "minutes": "about 45 s for 3-year windows",
     "params": [
         {"group": "Run length", "key": "years", "label": "Years per window", "type": "number", "default": 1, "min": 0.1, "max": 10, "flag": "--years"},
         {"group": "Where Earth is", "key": "epochs", "label": "Earth orbit sizes (AU, or 'middle')", "type": "text", "default": "1.0 middle 2.7", "flag": "--epochs"},
     ]},
    {"id": "validation", "label": "Benchmarks", "kind": "validation", "summary": "Official benchmarks 1–10 and our tests",
     "question": "Run the official benchmarks 1-10 and our own tests (quick set). Which pass?",
     "module": "pytest", "minutes": "about 1 min", "params": []},
]
BY_ID = {e["id"]: e for e in EXPERIMENTS}

JOBS: dict[str, dict] = {}
LOCK = threading.Lock()


def inside_allowed(rel: str) -> Path:
    """Resolve a user-given path and refuse anything outside results/ or out/."""
    p = (ROOT / rel).resolve()
    if not any(p == r or r in p.parents for r in ALLOWED_ROOTS):
        raise ValueError(f"path must be inside results/ or out/: {rel}")
    return p


def build_command(exp: dict, params: dict, out_dir: Path) -> list[str]:
    if exp["id"] == "validation":
        return [sys.executable, "-m", "pytest", "-m", "not slow", "-q", "-rA", "-p", "no:cacheprovider"]
    cmd = [sys.executable, "-u", "-m", exp["module"]]
    for p in exp["params"]:
        v = params.get(p["key"], p["default"])
        if p["type"] == "bool":
            if bool(v):
                cmd.append(p["flag"])
            continue
        if p["type"] == "number":
            v = float(v)
            if not (p["min"] <= v <= p["max"]):
                raise ValueError(f"{p['label']} must be between {p['min']} and {p['max']}")
            cmd += [p["flag"], f"{v:g}"]
        elif p["type"] == "choice":
            if v not in p["choices"]:
                raise ValueError(f"{p['label']} must be one of {p['choices']}")
            cmd += [p["flag"], v]
        elif p["type"] == "text":
            parts = str(v).split()
            if not parts or not all(re.fullmatch(r"middle|\d+(\.\d+)?", x) for x in parts):
                raise ValueError(f"{p['label']}: numbers in AU or the word middle, separated by spaces")
            cmd += [p["flag"], *parts]
    cmd += ["--out", str(out_dir)]
    return cmd


def start_job(exp_id: str, params: dict) -> str:
    exp = BY_ID.get(exp_id)
    if exp is None:
        raise ValueError(f"unknown experiment {exp_id!r}")
    with LOCK:
        if any(j["status"] == "running" for j in JOBS.values()):
            raise RuntimeError("another run is still going; wait for it or stop it")
        job_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
        out_dir = ROOT / "out" / "app" / f"{exp_id}-{job_id}"
        cmd = build_command(exp, params, out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        job = {"id": job_id, "experiment": exp_id, "params": params, "status": "running", "lines": [],
               "out": str(out_dir.relative_to(ROOT)), "started": time.time(), "ended": None, "returncode": None,
               "command": " ".join(Path(c).name if i == 0 else c for i, c in enumerate(cmd))}
        JOBS[job_id] = job
    threading.Thread(target=_run, args=(job, cmd, out_dir), daemon=True).start()
    return job_id


def _run(job: dict, cmd: list[str], out_dir: Path) -> None:
    proc = subprocess.Popen(cmd, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    job["pid"] = proc.pid
    job["_proc"] = proc
    for line in proc.stdout:
        job["lines"].append(line.rstrip("\n"))
        del job["lines"][:-400]  # keep the tail
    proc.wait()
    job["returncode"] = proc.returncode
    job["ended"] = time.time()
    if job["experiment"] == "validation":
        (out_dir / "validation.json").write_text(json.dumps(parse_pytest(job["lines"]), indent=2), encoding="utf-8")
    job["status"] = "stopped" if job.get("stop_requested") else ("done" if proc.returncode == 0 else "failed")


def parse_pytest(lines: list[str]) -> dict:
    """Turn pytest's -rA short summary into a list of tests with PASS/FAIL/SKIP."""
    tests = []
    for line in lines:
        m = re.match(r"^(PASSED|FAILED|SKIPPED|ERROR)\s+(\S+)(?:\s+-\s+(.*))?", line)
        if m:
            tests.append({"status": m.group(1), "test": m.group(2), "note": m.group(3) or ""})
    summary = next((l for l in reversed(lines) if re.search(r"\d+ (passed|failed)", l)), "")
    return {"tests": tests, "summary": summary.strip("= ")}


def list_runs() -> list[dict]:
    """Saved journeys: any folder in results/ or out/ (one level, or out/app/*) with summary.json and run.json."""
    found = []
    candidates = [ROOT / "results"] + sorted((ROOT / "out").glob("*")) + sorted((ROOT / "out" / "app").glob("*"))
    for d in candidates:
        if d.is_dir() and (d / "summary.json").exists() and (d / "run.json").exists():
            try:
                s = json.loads((d / "summary.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            arrival = (s.get("tows", {}).get("earth-tow") or {}).get("arrival")
            mars = (s.get("tows", {}).get("mars-tow") or {}).get("arrival")
            found.append({"path": str(d.relative_to(ROOT)), "modified": d.stat().st_mtime,
                          "years": s.get("settings", {}).get("years"), "earth_arrival": arrival, "mars_arrival": mars,
                          "unresolved_flags": s.get("flags", {}).get("unresolved"),
                          "end_year": (s.get("end") or {}).get("year")})
    found.sort(key=lambda r: -r["modified"])
    return found


def frames_csv(run_dir: Path) -> str:
    frames = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))["frames"]
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["year", "earth_x_au", "earth_y_au", "earth_z_au", "mars_x_au", "mars_y_au", "mars_z_au", "asteroid_x_au",
                "asteroid_y_au", "asteroid_z_au", "earth_a_au", "earth_e", "mars_a_au", "beam_power_w", "energy_error",
                "momentum_error", "earth_tow_active", "flags"])
    for f in frames:
        p = f["pos"]
        w.writerow([f["t"], *p["earth"], *p["mars"], *p["asteroid"], f["earth_orbit_au"], f["earth_eccentricity"],
                    f["mars_orbit_au"], f["beam_power_w"], f["energy_error"], f["momentum_error"], f["earth_tow_active"],
                    "; ".join(f["flags"])])
    return buf.getvalue()


def finite(obj):
    """Browsers cannot parse Infinity or NaN in JSON; saved runs may hold them (e.g. a flag never met). Send null."""
    if isinstance(obj, float):
        return obj if obj == obj and obj not in (float("inf"), float("-inf")) else None
    if isinstance(obj, dict):
        return {k: finite(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [finite(v) for v in obj]
    return obj


class Handler(BaseHTTPRequestHandler):
    server_version = "BlackAnt/1"

    def log_message(self, fmt, *args):  # quiet console
        pass

    def _send(self, code: int, body, ctype: str = "application/json", extra: dict | None = None):
        data = body if isinstance(body, bytes) else (json.dumps(finite(body), allow_nan=False) if ctype == "application/json" else body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith(("text", "application/json")) else ""))
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def _error(self, code: int, msg: str):
        self._send(code, {"error": msg})

    def do_GET(self):
        url = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        try:
            if url.path in ("/", "/index.html"):
                return self._static("index.html")
            if url.path.startswith("/static/"):
                return self._static(url.path[len("/static/"):])
            if url.path == "/api/experiments":
                return self._send(200, EXPERIMENTS)
            if url.path.startswith("/api/jobs/"):
                job = JOBS.get(url.path.rsplit("/", 1)[-1])
                if not job:
                    return self._error(404, "no such job")
                return self._send(200, {k: v for k, v in job.items() if not k.startswith("_")})
            if url.path == "/api/jobs":
                return self._send(200, [{k: v for k, v in j.items() if k not in ("lines",) and not k.startswith("_")}
                                        for j in sorted(JOBS.values(), key=lambda j: -j["started"])])
            if url.path == "/api/runs":
                return self._send(200, list_runs())
            if url.path == "/api/run":
                d = inside_allowed(q.get("path", "results"))
                summary = json.loads((d / "summary.json").read_text(encoding="utf-8"))
                frames = json.loads((d / "run.json").read_text(encoding="utf-8"))["frames"]
                return self._send(200, {"path": str(d.relative_to(ROOT)), "summary": summary, "frames": frames})
            if url.path == "/api/file":
                p = inside_allowed(q.get("path", ""))
                if p.suffix != ".json" or not p.is_file():
                    return self._error(404, "no such result file")
                return self._send(200, json.loads(p.read_text(encoding="utf-8")))
            if url.path == "/api/latest":
                name = q.get("file", "")
                if not re.fullmatch(r"[a-z_]+\.json", name):
                    return self._error(400, "file must be a plain .json name")
                found = [p for p in [ROOT / "results" / name, *(ROOT / "out" / "app").glob(f"*/{name}")] if p.is_file()]
                if not found:
                    return self._error(404, f"no {name} saved yet")
                newest = max(found, key=lambda p: p.stat().st_mtime)
                data = json.loads(newest.read_text(encoding="utf-8"))
                return self._send(200, {"path": str(newest.relative_to(ROOT)), "data": data})
            if url.path == "/api/export.csv":
                d = inside_allowed(q.get("path", "results"))
                name = d.name + "_frames.csv"
                return self._send(200, frames_csv(d), "text/csv", {"Content-Disposition": f'attachment; filename="{name}"'})
            return self._error(404, "not found")
        except FileNotFoundError:
            return self._error(404, "file not found")
        except ValueError as e:
            return self._error(400, str(e))

    def do_POST(self):
        url = urlparse(self.path)
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0)) or 0) or b"{}")
            if url.path == "/api/run":
                return self._send(200, {"job": start_job(body.get("experiment", ""), body.get("params", {}))})
            if url.path.startswith("/api/jobs/") and url.path.endswith("/stop"):
                job = JOBS.get(url.path.split("/")[3])
                if not job or job["status"] != "running":
                    return self._error(404, "no running job with that id")
                job["stop_requested"] = True
                job["_proc"].terminate()
                return self._send(200, {"stopping": job["id"]})
            return self._error(404, "not found")
        except (ValueError, RuntimeError) as e:
            return self._error(400, str(e))

    def _static(self, rel: str):
        p = (STATIC / rel).resolve()
        if STATIC not in p.parents or not p.is_file():
            return self._error(404, "not found")
        ctype = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml",
                 ".png": "image/png"}.get(p.suffix, "application/octet-stream")
        self._send(200, p.read_bytes(), ctype)


def main() -> None:
    parser = argparse.ArgumentParser(description="Black Ant test bench (local web app).")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1", help="127.0.0.1 keeps it on this laptop only")
    args = parser.parse_args()
    httpd = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Black Ant test bench: http://localhost:{args.port}  (Ctrl+C to stop)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for j in JOBS.values():
            if j["status"] == "running":
                j["_proc"].terminate()


if __name__ == "__main__":
    main()

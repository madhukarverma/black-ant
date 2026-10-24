// Black Ant Workbench. Reads what the Python core saved; computes no physics of its own.
"use strict";
const AU_KM = 149597870.7;
const R_KM = { sun: 695700, earth: 6371, mars: 3389.5, jupiter: 69911, asteroid: 335, moon: 1737.4 };
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const store = { get(k, d) { try { return JSON.parse(localStorage.getItem("ba." + k)) ?? d; } catch (e) { return d; } },
                set(k, v) { try { localStorage.setItem("ba." + k, JSON.stringify(v)); } catch (e) { /* storage off */ } } };

const S = { experiments: [], runs: [], job: null, jobData: null, cache: {} };

/* ---------- formatting ---------- */
const SUP = { "-": "⁻", "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹" };
function sci(x, d = 2) {
  if (x === 0) return "0"; if (x == null || !isFinite(x)) return "—";
  const e = Math.floor(Math.log10(Math.abs(x)));
  if (e >= -2 && e < 5) return (+x.toPrecision(d + 2)).toLocaleString("en-US");
  return (x / 10 ** e).toFixed(d) + "×10" + String(e).split("").map(c => SUP[c]).join("");
}
const fix = (x, d) => (x == null ? "—" : Number(x).toFixed(d));
const year = (t) => (t == null ? "—" : "Year " + Math.round(t).toLocaleString("en-US"));
const when = (s) => new Date(s * 1000).toLocaleString([], { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const state = (ok, text) => `<span class="state ${ok == null ? "none" : ok === "note" ? "note" : ok ? "pass" : "fail"}">${text ?? (ok == null ? "Not checked" : ok === "note" ? "Note" : ok ? "Pass" : "Fail")}</span>`;
const runHref = (path, tab = "trajectory") => `#/run/${encodeURIComponent(path)}/${tab}`;

/* ---------- api ---------- */
async function api(path, opts) {
  const r = await fetch(path, opts);
  const body = r.headers.get("content-type")?.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error(body.error || r.statusText);
  return body;
}
async function latest(name) {
  try { const r = await api("/api/latest?file=" + name); r.data._path = r.path; return r.data; } catch (e) { return null; }
}
async function runData(path) {
  if (!S.cache[path]) S.cache[path] = await api("/api/run?path=" + encodeURIComponent(path));
  return S.cache[path];
}
async function refreshRuns() { S.runs = await api("/api/runs").catch(() => []); return S.runs; }

/* ---------- router ---------- */
const ROUTES = {
  overview: { title: "Overview", render: pageOverview },
  experiments: { title: "Experiments", render: pageExperiments },
  runs: { title: "Runs", render: pageRuns },
  run: { title: "Run", parent: ["Runs", "#/runs"], render: pageRun },
  validation: { title: "Validation", render: pageValidation },
  moon: { title: "Moon and baseline", render: pageMoon },
  compare: { title: "Compare runs", render: pageCompare },
};
let scopeStop = null;
async function route() {
  const parts = (location.hash.replace(/^#\/?/, "") || "overview").split("/");
  const key = ROUTES[parts[0]] ? parts[0] : "overview";
  const r = ROUTES[key];
  if (scopeStop) { scopeStop(); scopeStop = null; }
  const navKey = key === "run" ? "runs" : key;
  document.querySelectorAll("nav a").forEach(a => (a.dataset.route === navKey ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current")));
  const title = key === "run" ? decodeURIComponent(parts[1] || "") : r.title;
  $("#crumbs").innerHTML = (r.parent ? `<a href="${r.parent[1]}">${r.parent[0]}</a><span class="sep">/</span>` : "") + `<h1>${esc(title)}</h1>`;
  const main = $("#main");
  main.innerHTML = `<p class="lede">Loading…</p>`;
  try { await r.render(main, parts.slice(1)); } catch (e) { main.innerHTML = `<div class="sheet"><div class="empty"><strong>This page could not load</strong>${esc(e.message)}</div></div>`; }
  main.focus({ preventScroll: true });
}
window.addEventListener("hashchange", route);

/* ---------- shared pieces ---------- */
function sheet(title, sub, body, cls = "s12", flush = false, actions = "") {
  return `<section class="sheet ${cls}"><header><div><h2>${title}</h2>${sub ? `<p>${sub}</p>` : ""}</div>${actions}</header><div class="body${flush ? " flush" : ""}">${body}</div></section>`;
}
function table(head, rows, numCols = []) {
  return `<div class="scroll"><table><thead><tr>${head.map((h, i) => `<th class="${numCols.includes(i) ? "num" : ""}">${h}</th>`).join("")}</tr></thead><tbody>${rows.map(r => `<tr${r.href ? ` class="link" data-href="${r.href}"` : ""}>${r.cells.map((c, i) => `<td class="${numCols.includes(i) ? "num" : ""}">${c}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
}
function wireRowLinks(el) { el.querySelectorAll("tr[data-href]").forEach(tr => tr.onclick = () => (location.hash = tr.dataset.href)); }
function facts(items) { return `<dl class="facts">${items.map(([k, v, s]) => `<div><dt>${k}</dt><dd>${v}${s ? `<small>${s}</small>` : ""}</dd></div>`).join("")}</dl>`; }
const empty = (title, text, action = "") => `<div class="empty"><strong>${title}</strong>${text}${action ? `<p>${action}</p>` : ""}</div>`;

function runSide(path, s) {
  const a = s.tows["earth-tow"]?.arrival, m = s.tows["mars-tow"]?.arrival, st = s.settings;
  const row = (k, v, sub = "") => `<div><dt>${k}</dt><dd>${v}${sub ? `<small>${sub}</small>` : ""}</dd></div>`;
  const tows = (st.tows || []).map(t => row(t.name === "earth-tow" ? "Earth tow asteroid" : "Mars tow asteroid", `${sci(t.asteroid_mass_kg)} kg`,
    `${Math.round(t.distance_km).toLocaleString("en-US")} km from its planet, stops at ${t.stop_au} AU`)).join("");
  return `<aside class="runside">
    <section class="sheet"><header><div><h2>Outcome</h2></div></header><dl class="sidefacts">
      ${row("Earth arrives", a ? year(a.year) : "Not yet", a ? `${a.a_au} AU, eccentricity ${a.eccentricity}` : `ends at ${fix(s.end?.earth?.a_au, 3)} AU`)}
      ${row("Mars", m ? "Parked" : "Not parked", m ? `${year(m.year)}, ${m.a_au} AU, eccentricity ${m.eccentricity}` : `ends at ${fix(s.end?.mars?.a_au, 2)} AU, eccentricity ${fix(s.end?.mars?.eccentricity, 2)}`)}
      ${row("Closest Earth–Mars", `${s.mars_closest.au} AU`, year(s.mars_closest.year))}
      ${row("Unresolved flags", s.flags.unresolved ? state(false, String(s.flags.unresolved)) : state(true, "0"), `${s.flags.covered_by_enablers} covered by enablers`)}
      ${row("Peak beam power", `${sci(s.total_beam_max_w)} W`, `limit ${sci(st.beam_limit_w)} W (enabler E1)`)}
    </dl></section>
    <section class="sheet"><header><div><h2>Run settings</h2></div></header><dl class="sidefacts">
      ${row("Simulated years asked", Number(st.years).toLocaleString("en-US"))}
      ${row("Step", `${st.dt_days} day${st.dt_days === 1 ? "" : "s"}`)}
      ${row("Starting orbits", st.start_orbits === "real" ? "Real J2000 orbits" : "Flat circles")}
      ${row("Mars moved first", st.mars_tow ? "Yes" : "No")}
      ${row("Bodies", String(st.bodies?.length ?? "—"), "Earth carries the Moon's mass")}
      ${tows}
      ${row("Run time", `${Math.round(s.run_seconds)} s`)}
    </dl></section>
    <section class="sheet"><header><div><h2>Files</h2></div></header><div class="body sidelinks">
      <a href="/api/export.csv?path=${encodeURIComponent(path)}">Frames as CSV</a>
      <a href="/api/file?path=${encodeURIComponent(path + "/summary.json")}" target="_blank">summary.json</a>
      <span class="help">${esc(path)}</span>
    </div></section>
  </aside>`;
}

function runFacts(s) {
  const a = s.tows["earth-tow"]?.arrival, m = s.tows["mars-tow"]?.arrival;
  return facts([
    ["Earth arrives", a ? year(a.year) : "Not yet", a ? `${a.a_au} AU, eccentricity ${a.eccentricity}` : `ends at ${fix(s.end?.earth?.a_au, 3)} AU`],
    ["Mars", m ? `Parked ${year(m.year).toLowerCase()}` : "Not parked", m ? `${m.a_au} AU, eccentricity ${m.eccentricity}` : `ends at ${fix(s.end?.mars?.a_au, 2)} AU, eccentricity ${fix(s.end?.mars?.eccentricity, 2)}`],
    ["Closest Earth–Mars", `${s.mars_closest.au} AU`, year(s.mars_closest.year)],
    ["Unresolved flags", String(s.flags.unresolved), `${s.flags.covered_by_enablers} covered by enablers`],
    ["Peak beam power", `${sci(s.total_beam_max_w)} W`, `limit ${sci(s.settings.beam_limit_w)} W`],
  ]);
}

function conditions(s, validation) {
  const a = s.tows["earth-tow"]?.arrival, m = s.tows["mars-tow"]?.arrival, L = s.ledger;
  const marsLimit = 0.05;
  const vt = validation?.tests || [];
  const failed = vt.filter(t => t.status === "FAILED" || t.status === "ERROR").length;
  return [
    ["Earth reaches 2.7 AU within 10,000 years", a ? `${year(a.year)} at ${a.a_au} AU` : "Earth did not arrive in this run", "Journey", !!a && a.year <= 10000],
    ["Mars is parked clear of Earth", m ? `Parked at ${m.a_au} AU; closest pass ${s.mars_closest.au} AU` : `Not parked; closest pass ${s.mars_closest.au} AU`, "Journey", (!!m || s.settings.mars_tow === false) && s.mars_closest.au >= marsLimit],
    ["Every force booked with its reaction", `Momentum error ${sci(L.momentum_error_max)}`, "Ledger", L.momentum_error_max < 1e-9],
    ["Energy conserved", `Energy error ${sci(L.energy_error_max_of_total)}; work mismatch ${sci(L.work_mismatch_share)}`, "Ledger", L.energy_error_max_of_total < 1e-5],
    ["No unresolved flags", `${s.flags.unresolved} unresolved, ${s.flags.covered_by_enablers} covered by enablers`, "Checks every 100 days", s.flags.unresolved === 0],
    ["Every applicable benchmark passes", validation ? `${vt.length - failed} of ${vt.length} tests pass` : "Run the benchmarks to check", "Validation", validation ? failed === 0 : null],
  ];
}

/* ---------- Overview ---------- */
async function pageOverview(main) {
  await refreshRuns();
  if (!S.runs.length) {
    main.innerHTML = `<div class="pagehead"><div><h2>Mission status</h2><p class="lede">Run a journey to see whether the plan meets every winning condition.</p></div></div>` +
      sheet("No runs yet", "", empty("Nothing to show yet", "A journey run saves its results to <code>out/</code>. Start one from Experiments.", `<a class="btn primary" href="#/experiments/journey">Set up a journey</a>`), "s12", true);
    return;
  }
  const fallback = (S.runs.find(r => r.earth_arrival) || S.runs[0]).path; // newest run that got Earth there
  let ref = store.get("reference", fallback);
  if (!S.runs.find(r => r.path === ref)) ref = fallback;
  const run = await runData(ref), s = run.summary, v = await latest("validation.json");
  const jobs = await api("/api/jobs").catch(() => []);
  main.innerHTML = `
    <div class="pagehead">
      <div><h2>Mission status</h2><p class="lede">Checked against the brief's winning conditions, using one reference run. Thresholds are the team's stand-ins in <code>config.yaml</code> until the rulebook appendix is published.</p></div>
      <div class="actions"><label for="ref">Reference run</label><select id="ref" class="input">${S.runs.map(r => `<option ${r.path === ref ? "selected" : ""}>${esc(r.path)}</option>`).join("")}</select>
      <a class="btn" href="${runHref(ref)}">Open run</a></div>
    </div>
    <section class="sheet">${runFacts(s)}</section>
    <div class="grid">
      ${sheet("Winning conditions", "Each line names where its evidence comes from.", table(["Condition", "Evidence", "Source", ""], conditions(s, v).map(([c, e, src, ok]) => ({ cells: [c, esc(e), src, state(ok)] })), [3]), "s8", true)}
      ${sheet("Recent runs from this app", jobs.length ? "" : "Runs started here appear in this list.", jobs.length ? table(["Experiment", "Started", ""], jobs.slice(0, 8).map(j => ({ cells: [esc(labelOf(j.experiment)), when(j.started), state(j.status === "done" ? true : j.status === "running" ? null : false, j.status[0].toUpperCase() + j.status.slice(1))], href: j.experiment === "journey" && j.status === "done" ? runHref(j.out) : j.experiment === "validation" ? "#/validation" : j.experiment === "journey" ? "#/experiments/journey" : "#/moon" })), [2]) : empty("No runs yet", "Start one from Experiments."), "s4", true)}
    </div>`;
  $("#ref").onchange = (e) => { store.set("reference", e.target.value); route(); };
  wireRowLinks(main);
}
const labelOf = (id) => S.experiments.find(e => e.id === id)?.label || id;

/* ---------- Experiments ---------- */
async function pageExperiments(main, [id]) {
  const exp = S.experiments.find(e => e.id === id) || S.experiments[0];
  const running = S.jobData?.status === "running";
  const groups = [...new Set(exp.params.map(p => p.group))];
  const field = (p) => {
    const fid = `p-${p.key}`;
    if (p.type === "bool") return `<label class="check"><input type="checkbox" id="${fid}" ${p.default ? "checked" : ""}><span>${esc(p.label)}</span></label>`;
    if (p.type === "choice") return `<div class="field"><label for="${fid}">${esc(p.label)}</label><select id="${fid}">${p.choices.map(c => `<option ${c === p.default ? "selected" : ""}>${c}</option>`).join("")}</select></div>`;
    if (p.type === "text") return `<div class="field"><label for="${fid}">${esc(p.label)}</label><input type="text" id="${fid}" value="${esc(p.default)}"></div>`;
    return `<div class="field"><label for="${fid}">${esc(p.label)}</label><input type="number" id="${fid}" value="${p.default}" min="${p.min}" max="${p.max}" step="any"><span class="help">${p.min} to ${p.max}</span></div>`;
  };
  const form = groups.length ? groups.map(g => `<fieldset class="fieldset"><legend>${esc(g)}</legend><div class="formgrid">${exp.params.filter(p => p.group === g).map(field).join("")}</div></fieldset>`).join("") : `<p class="lede">No inputs. This runs the quick test set with <code>pytest</code>.</p>`;
  main.innerHTML = `
    <div class="grid">
      <section class="sheet s4"><header><div><h2>Experiments</h2><p>One run at a time</p></div></header>
        <div class="catalog">${S.experiments.map(e => `<button data-id="${e.id}" aria-current="${e.id === exp.id}"><strong>${esc(e.label)}</strong><span>${esc(e.summary)}</span></button>`).join("")}</div>
      </section>
      <section class="sheet s8"><header><div><h2>${esc(exp.label)}</h2><p>${esc(exp.minutes)}</p></div></header>
        <div class="body" style="display:grid;gap:20px">
          <p class="lede">${esc(exp.question)}</p>
          ${form}
          <div class="actions"><button class="btn primary" id="go" ${running ? "disabled" : ""}>Run ${esc(exp.label.toLowerCase())}</button>
            <button class="btn quiet" id="reset">Restore defaults</button><span id="err" class="error" role="alert"></span></div>
          ${running ? `<p class="help">Another run is in progress. Its log is below.</p>` : ""}
        </div>
      </section>
      <div class="s12" id="jobbox"></div>
    </div>`;
  main.querySelectorAll(".catalog button").forEach(b => b.onclick = () => (location.hash = "#/experiments/" + b.dataset.id));
  $("#reset").onclick = () => route();
  $("#go").onclick = async () => {
    const params = {};
    for (const p of exp.params) { const el = $("#p-" + p.key); params[p.key] = p.type === "bool" ? el.checked : p.type === "number" ? Number(el.value) : el.value; }
    try {
      const { job } = await api("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ experiment: exp.id, params }) });
      S.job = job; S.jobData = { status: "running", experiment: exp.id, lines: [], params };
      $("#go").disabled = true; renderJobBox(); poll();
    } catch (e) { $("#err").textContent = e.message; }
  };
  renderJobBox();
}

function renderJobBox() {
  const box = $("#jobbox"); if (!box) return;
  const j = S.jobData; if (!j) { box.innerHTML = ""; return; }
  const yrs = Number(j.params?.years) || null;
  const lastYear = [...(j.lines || [])].reverse().map(l => l.match(/year\s+(\d+)/)).find(Boolean);
  const pct = j.status !== "running" ? 100 : (j.experiment === "journey" && yrs && lastYear ? Math.min(99, 100 * lastYear[1] / yrs) : null);
  const done = j.status === "done";
  const link = done ? (j.experiment === "journey" ? `<a class="btn primary" href="${runHref(j.out)}">Open this run</a>` : j.experiment === "validation" ? `<a class="btn primary" href="#/validation">See results</a>` : `<a class="btn primary" href="#/moon">See results</a>`) : "";
  box.innerHTML = `<section class="sheet"><header><div><h2>${esc(labelOf(j.experiment))}: ${esc(j.status)}</h2><p>${esc(j.command || "")}</p></div>
    <div class="actions">${j.status === "running" ? `<button class="btn" id="stop">Stop run</button>` : link}</div></header>
    ${pct != null ? `<div class="body" style="padding-bottom:0"><div class="progress"><span style="width:${pct}%"></span></div></div>` : ""}
    <pre class="log">${esc((j.lines || []).join("\n")) || "Starting…"}</pre></section>`;
  const st = $("#stop"); if (st) st.onclick = () => api(`/api/jobs/${S.job}/stop`, { method: "POST" });
  const pre = $("pre.log", box); pre.scrollTop = pre.scrollHeight;
}

async function poll() {
  if (!S.job) return;
  const j = await api("/api/jobs/" + S.job).catch(() => null);
  if (!j) return;
  S.jobData = j;
  const pill = $("#jobpill"); pill.hidden = false; pill.dataset.state = j.status;
  const last = (j.lines.filter(l => l.trim()).slice(-1)[0] || "starting").trim();
  pill.textContent = j.status === "running" ? `${labelOf(j.experiment)} running: ${last}` : `${labelOf(j.experiment)} ${j.status} in ${Math.round(j.ended - j.started)} s`;
  pill.onclick = () => (location.hash = "#/experiments/" + j.experiment);
  renderJobBox();
  if (j.status === "running") { setTimeout(poll, 1000); return; }
  S.cache = {}; await refreshRuns();
  const btn = $("#go"); if (btn) btn.disabled = false;
}

/* ---------- Runs ---------- */
async function pageRuns(main) {
  await refreshRuns();
  main.innerHTML = `<div class="pagehead"><div><h2>Saved journeys</h2><p class="lede">Every journey saved in <code>results/</code> or <code>out/</code>, newest first. <code>results/</code> holds the official numbers.</p></div>
    <a class="btn primary" href="#/experiments/journey">New journey</a></div>` +
    sheet("Runs", `${S.runs.length} saved`, S.runs.length ? table(["Run", "Saved", "Earth", "Mars", "Unresolved flags"], S.runs.map(r => ({
      href: runHref(r.path),
      cells: [`<strong>${esc(r.path)}</strong>`, when(r.modified), r.earth_arrival ? `${year(r.earth_arrival.year)}, ${r.earth_arrival.a_au} AU` : "Not arrived",
        r.mars_arrival ? state(true, "Parked") : state(false, "Not parked"), r.unresolved_flags ? state(false, String(r.unresolved_flags)) : state(true, "0")] })), [4])
      : empty("No saved journeys", "Run a journey from Experiments."), "s12", true);
  wireRowLinks(main);
}

/* ---------- Run detail ---------- */
const RUN_TABS = [["trajectory", "Trajectory"], ["orbit", "Orbit"], ["ledger", "Forces and ledger"], ["safety", "Earth safety"], ["export", "Export"]];
async function pageRun(main, [encPath, tab = "trajectory"]) {
  const path = decodeURIComponent(encPath || "");
  const run = await runData(path), s = run.summary, F = run.frames;
  main.innerHTML = `<div class="runlayout"><div class="runmain">
    <nav class="tabs" aria-label="Run views">${RUN_TABS.map(([k, l]) => `<a href="${runHref(path, k)}" ${k === tab ? 'aria-current="page"' : ""}>${l}</a>`).join("")}</nav>
    <div id="tabbody"></div></div>${runSide(path, s)}</div>`;
  const body = $("#tabbody");
  if (tab === "trajectory") return mountScope(body, run);
  if (tab === "orbit") {
    body.innerHTML = `<div class="grid">${sheet("Orbit size", "Semi-major axis of Earth and Mars, AU", `<canvas class="chart" id="c1"></canvas>`, "s12")}
      ${sheet("Earth's eccentricity", "How oval Earth's orbit is", `<canvas class="chart" id="c2"></canvas>`, "s6")}
      ${sheet("Where Mars stands", "", table(["", "Value"], [
        { cells: ["Mars tow arrival", s.tows["mars-tow"]?.arrival ? `${year(s.tows["mars-tow"].arrival.year)}, ${s.tows["mars-tow"].arrival.a_au} AU` : "Did not arrive"] },
        { cells: ["Mars at the end", `${fix(s.end.mars.a_au, 3)} AU, eccentricity ${fix(s.end.mars.eccentricity, 3)}`] },
        { cells: ["Jupiter's 2:1 resonance", "3.278 AU"] }, { cells: ["Planned parking orbit", "3.64 AU"] }]), "s6", true)}</div>`;
    const t = F.map(f => f.t);
    chart($("#c1"), [{ x: t, y: F.map(f => f.earth_orbit_au), color: css("--c-earth"), label: "Earth" }, { x: t, y: F.map(f => f.mars_orbit_au), color: css("--c-mars"), label: "Mars" }],
      { ymin: 0.9, ymax: 3.9, lines: [{ y: 2.7, label: "Earth target 2.7", color: css("--c-earth") }, { y: 3.64, label: "Mars park 3.64", color: css("--c-mars") }, { y: 3.278, label: "Jupiter 2:1", color: css("--bad") }] });
    chart($("#c2"), [{ x: t, y: F.map(f => f.earth_eccentricity), color: css("--c-earth"), label: "Earth" }], { ymin: 0, ymax: 0.07, lines: [{ y: 0.05, label: "limit 0.05", color: css("--bad") }] });
    return;
  }
  if (tab === "ledger") {
    const L = s.ledger, t = F.map(f => f.t);
    body.innerHTML = `<div class="grid">${sheet("Beam power", "Total of both tows against enabler E1's limit", `<canvas class="chart" id="c1"></canvas>`, "s12")}
      ${sheet("Energy ledger error", "Share of the system's total energy", `<canvas class="chart" id="c2"></canvas>`, "s6")}
      ${sheet("Momentum ledger error", "Bodies + station recoil + light + departed asteroids", `<canvas class="chart" id="c3"></canvas>`, "s6")}
      ${sheet("Ledger totals", "", table(["", "Value"], [
        { cells: ["Work done by the beams", sci(L.beam_work_j) + " J"] }, { cells: ["Orbital energy gained by the bodies", sci(L.bodies_energy_gain_j) + " J"] },
        { cells: ["Mismatch", sci(L.work_mismatch_share)] }, { cells: ["Largest station recoil", sci(s.station_recoil_max_n) + " N"] },
        { cells: ["Largest momentum error", sci(L.momentum_error_max)] }], [1]), "s12", true)}</div>`;
    chart($("#c1"), [{ x: t, y: F.map(f => f.beam_power_w), color: css("--c-beam"), label: "Beam" }], { ymin: 0, ymax: 1.1e26, lines: [{ y: s.settings.beam_limit_w, label: "E1 limit", color: css("--bad") }] });
    chart($("#c2"), [{ x: t, y: F.map(f => Math.abs(f.energy_error)), color: css("--c-ok"), label: "" }], { log: true, ymin: 1e-10, ymax: 1e-5 });
    chart($("#c3"), [{ x: t, y: F.map(f => Math.abs(f.momentum_error)), color: css("--c-earth"), label: "" }], { log: true, ymin: 1e-16, ymax: 1e-8 });
    return;
  }
  if (tab === "safety") {
    body.innerHTML = `<div class="grid">${sheet("Flags", "A check that failed at least once. Flags covered by a declared enabler are allowed by the brief.",
      table(["Check", "Worst", "Limit", "Years", "Status"], s.flags.flags.map(f => ({ cells: [esc(f.check), `${sci(f.worst)} ${esc(f.unit)}`, `${f.kind} ${sci(f.limit)}`, `${Math.round(f.first_year).toLocaleString("en-US")}–${Math.round(f.last_year).toLocaleString("en-US")}`,
        f.covered_by ? state("note", `Covered by ${f.covered_by}`) : state(false, "Unresolved")] })), [1, 2, 4]), "s8", true)}
      ${sheet("Closest passes to Earth", "", table(["Body", "Distance"], Object.entries(s.big_asteroids_closest_au || {}).map(([k, v]) => ({ cells: [k[0].toUpperCase() + k.slice(1), v + " AU"] }))
        .concat([{ cells: ["Mars", s.mars_closest.au + " AU"] }, { cells: ["Jupiter", s.jupiter_closest_au + " AU"] }]), [1]), "s4", true)}</div>`;
    return;
  }
  if (tab === "export") {
    body.innerHTML = sheet("Export", "Files for spreadsheets, the report and OpenSpace", table(["File", "What it holds", ""], [
      { cells: ["Frames as CSV", "One row per saved frame: positions, orbit sizes, beam power, errors, flags", `<a class="btn" href="/api/export.csv?path=${encodeURIComponent(path)}">Download CSV</a>`] },
      { cells: ["summary.json", "Every number and flag the run produced", `<a class="btn" href="/api/file?path=${encodeURIComponent(path + "/summary.json")}" target="_blank">Open</a>`] },
      { cells: ["OpenSpace scene", "Make it from a terminal", `<code>uv run python -m sim.adapters.openspace --run ${esc(path)}/run.json --out out/openspace</code>`] }]), "s12", true);
  }
}

/* ---------- scope (trajectory viewer) ---------- */
// Three views. "solar" and "earth" play the journey's saved frames (one per 10 years; the journey folds the Moon into
// Earth, so the Moon is drawn on its mean orbit and labelled as such). "moon" plays the live Moon from the
// "Moon beside the tow" run, where the Moon is a full body (one frame every 6 hours).
const MOON_KM = 384400, MONTH_D = 27.321661, MOON_L0 = Math.atan2(-1.838126e-3, -1.949282e-3); // J2000 geocentric longitude (Horizons)
async function mountScope(body, run) {
  const F = run.frames;
  let live = await latest("moon_coupled.json");
  if (!live?.epochs?.[0]?.frames?.length) live = null; // older runs saved no frames: run "Moon beside the tow" again
  const v = { i: F.length - 1, j: 0, epoch: 0, view: store.get("view", "solar"), scale: store.get("scale", "enlarged"), yaw: 0, pitch: Math.PI / 2, zoom: 1, playing: false };
  if (v.view === "moon" && !live) v.view = "solar";
  body.innerHTML = `<section class="sheet"><header><div><h2>Trajectory</h2><p id="scopesub"></p></div>
      <div class="actions">
        <div class="seg" role="group" aria-label="View"><button data-view="solar">Solar system</button><button data-view="earth">Earth close-up</button><button data-view="moon">Earth and Moon, live</button></div>
        <div class="seg" role="group" aria-label="Scale"><button data-scale="enlarged">Enlarged</button><button data-scale="true">True scale</button></div>
      </div></header>
    <div class="body"><div class="scope"><canvas></canvas><div class="legend"></div><div class="key"></div></div></div>
    <div class="scopebar"><button class="btn" id="play">Play</button><select id="epoch" class="input" style="width:auto" aria-label="Epoch" hidden></select>
      <input type="range" id="scrub" min="0" value="0" aria-label="Time"><span class="year" id="yr"></span>
      <select id="spd" class="input" style="width:auto" aria-label="Playback speed"></select></div></section>`;
  const cv = $("canvas", body), ctx = cv.getContext("2d"), legend = $(".legend", body), keyBox = $(".key", body);
  const C = {}; ["scope", "s-ink", "s-dim", "s-earth", "s-mars", "s-jupiter", "s-sun", "s-beam", "s-rock", "s-bad", "s-moon"].forEach(k => C[k] = css("--" + k));
  let W = 0, H = 0;
  const fit = () => { const r = cv.getBoundingClientRect(), d = Math.min(devicePixelRatio || 1, 2); cv.width = r.width * d; cv.height = r.height * d; ctx.setTransform(d, 0, 0, d, 0, 0); W = r.width; H = r.height; };
  const proj = (p, sc) => { const c = Math.cos(v.yaw), s = Math.sin(v.yaw), x = c * p[0] - s * p[1], y = s * p[0] + c * p[1]; return [W / 2 + x * sc, H / 2 - (y * Math.sin(v.pitch) + p[2] * Math.cos(v.pitch)) * sc]; };
  const ring = (r, n = 128, c = [0, 0, 0]) => Array.from({ length: n + 1 }, (_, k) => [c[0] + r * Math.cos(k / n * 2 * Math.PI), c[1] + r * Math.sin(k / n * 2 * Math.PI), c[2]]);
  const line = (pts, sc, color, dash = [], alpha = 1, w = 1) => { ctx.save(); ctx.strokeStyle = color; ctx.globalAlpha = alpha; ctx.lineWidth = w; ctx.setLineDash(dash); ctx.beginPath(); pts.forEach((p, k) => { const [x, y] = proj(p, sc); k ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke(); ctx.restore(); };
  const label = (s, x, y, color, align = "left") => { ctx.fillStyle = color; ctx.font = `12px ${css("--font")}`; ctx.textAlign = align; ctx.fillText(s, x, y); ctx.textAlign = "left"; };
  const dot = (p, sc, rView, color, name, minPx = 5) => { const [x, y] = proj(p, sc), tr = rView * sc, r = v.scale === "true" ? Math.max(tr, 0.8) : Math.max(tr, minPx); ctx.fillStyle = color; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill(); if (name) label(name, x + r + 6, y + 4, color); return { k: r / tr, x, y, r }; };
  const bar = (px, text) => { ctx.strokeStyle = C["s-dim"]; ctx.beginPath(); ctx.moveTo(16, H - 18); ctx.lineTo(16 + px, H - 18); ctx.stroke(); label(text, 24 + px, H - 14, C["s-dim"]); };
  const meanMoon = (tYears, rKm) => { const a = MOON_L0 + 2 * Math.PI * tYears * 365.25 / MONTH_D; return [rKm * Math.cos(a), rKm * Math.sin(a), 0]; };
  const E = () => live?.epochs?.[v.epoch];

  function setupBar() {
    const scrub = $("#scrub", body), spd = $("#spd", body), ep = $("#epoch", body);
    if (v.view === "moon") {
      ep.hidden = false; ep.innerHTML = live.epochs.map((e, k) => `<option value="${k}" ${k === v.epoch ? "selected" : ""}>Earth at ${e.earth_au} AU</option>`).join("");
      scrub.max = E().frames.length - 1; v.j = Math.min(v.j, +scrub.max); scrub.value = v.j;
      spd.innerHTML = `<option value="1">6 hours a step</option><option value="4" selected>1 day a step</option><option value="12">3 days a step</option>`;
      $("#scopesub", body).textContent = "The Moon as a full body beside the live tow, one frame every 6 hours.";
      $("#scopesub", body).title = live._path;
    } else {
      ep.hidden = true; scrub.max = F.length - 1; scrub.value = v.i;
      spd.innerHTML = `<option value="1">10 years a step</option><option value="5" selected>50 years a step</option><option value="20">200 years a step</option>`;
      $("#scopesub", body).textContent = "The journey's frames, one per 10 years. Its Moon is folded into Earth, so the Moon is drawn on its mean orbit; the live view shows the simulated Moon.";
      $("#scopesub", body).title = "";
    }
  }

  function draw() {
    ctx.fillStyle = C.scope; ctx.fillRect(0, 0, W, H);
    const k = [];
    let lines = [], keys = [];
    if (v.view === "moon") {
      const ep = E(), f = ep.frames[v.j];
      const moon = f.slice(1, 4), ast = f.slice(4, 7), sun = f.slice(7, 10), P = f[10], inn = f.slice(11, 14), out = f.slice(14, 17), atLimit = f[17];
      const sc = Math.min(W, H) / 2 * 0.9 / 820000 * v.zoom;
      line(ring(420000), sc, C["s-bad"], [5, 5], 0.6); const t2 = proj([0, 420000, 0], sc); label("No beam inside 420,000 km", t2[0], t2[1] - 8, C["s-bad"], "center");
      const from = Math.max(0, v.j - Math.round(MONTH_D * 4)); // last month of the Moon's path
      line(ep.frames.slice(from, v.j + 1).map(g => g.slice(1, 4)), sc, C["s-moon"], [], 0.55, 1.5);
      const sp = proj(sun.map(q => q * 760000), sc), o = proj([0, 0, 0], sc);
      ctx.save(); ctx.strokeStyle = C["s-sun"]; ctx.globalAlpha = 0.35; ctx.beginPath(); ctx.moveTo(o[0], o[1]); ctx.lineTo(sp[0], sp[1]); ctx.stroke(); ctx.restore(); label("Towards the Sun", sp[0] + 6, sp[1], C["s-sun"]);
      if (P > 0) {
        line([ast.map((q, n) => q - inn[n] * 1.2e6), ast], sc, C["s-beam"], [], 0.9, 2);
        line([ast, ast.map((q, n) => q + out[n] * 1.2e6)], sc, C["s-beam"], [6, 4], 0.5, 1.5);
      }
      k.push(["Earth", dot([0, 0, 0], sc, R_KM.earth, C["s-earth"], "Earth").k]);
      k.push(["Moon", dot(moon, sc, R_KM.moon, C["s-moon"], "Moon", 4).k]);
      k.push(["Asteroid", dot(ast, sc, R_KM.asteroid, C["s-rock"], "Tow asteroid", 4).k]);
      bar(100000 * sc, "100,000 km");
      const dm = Math.hypot(...moon), da = Math.hypot(...ast.map((q, n) => q - moon[n]));
      $("#yr", body).textContent = `Day ${fix(f[0], 1)}`;
      lines = [`<b>Day ${fix(f[0], 1)}</b> of the window, Earth at ${ep.earth_au} AU`, `Moon ${Math.round(dm).toLocaleString("en-US")} km from Earth`,
        `Moon ${Math.round(da).toLocaleString("en-US")} km from the asteroid`, `Beam ${sci(P)} W${atLimit ? ` <span class="warn">at E1's limit</span>` : ""}`];
      keys = [["s-earth", "Earth"], ["s-moon", "Moon and its last month"], ["s-rock", "Tow asteroid"], ["s-beam", "Light in (solid), bounced (dashed)"], ["s-bad", "Beam keep-out"]];
    } else {
      const f = F[v.i];
      $("#yr", body).textContent = year(f.t);
      if (v.view === "solar") {
        const sc = Math.min(W, H) / 2 * 0.92 / 4.2 * v.zoom;
        line(ring(2.7), sc, C["s-earth"], [6, 5], 0.55); line(ring(3.64), sc, C["s-mars"], [6, 5], 0.55); line(ring(3.278), sc, C["s-dim"], [2, 4], 0.7);
        line(ring(f.earth_orbit_au), sc, C["s-earth"], [], 0.3); line(ring(f.mars_orbit_au), sc, C["s-mars"], [], 0.3);
        const a = proj([2.7 * 0.71, -2.7 * 0.71, 0], sc); label("Earth target 2.7 AU", a[0] + 6, a[1], C["s-earth"]);
        const b = proj([3.64 * 0.71, -3.64 * 0.71, 0], sc); label("Mars parking 3.64 AU", b[0] + 6, b[1] + 12, C["s-mars"]);
        const j = proj([-3.278 * 0.71, -3.278 * 0.71, 0], sc); label("Jupiter 2:1 resonance 3.28 AU", j[0] - 6, j[1], C["s-dim"], "right");
        for (let n = Math.max(0, v.i - 40); n < v.i; n++) {
          ctx.globalAlpha = 0.15 + 0.5 * (n - v.i + 40) / 40;
          for (const [b2, c] of [["earth", C["s-earth"]], ["mars", C["s-mars"]], ["jupiter", C["s-jupiter"]]]) { const [x, y] = proj(F[n].pos[b2], sc); ctx.fillStyle = c; ctx.fillRect(x - 1, y - 1, 2, 2); }
        }
        ctx.globalAlpha = 1;
        k.push(["Sun", dot([0, 0, 0], sc, R_KM.sun / AU_KM, C["s-sun"]).k]);
        const e = dot(f.pos.earth, sc, R_KM.earth / AU_KM, C["s-earth"], "Earth");
        k.push(["Earth", e.k]);
        // The Moon: its true distance is under a pixel here, so its orbit is drawn enlarged around Earth.
        const trueSep = MOON_KM / AU_KM * sc, sep = v.scale === "true" ? trueSep : Math.max(trueSep, 22);
        const mm = meanMoon(f.t, 1), mx = e.x + mm[0] * sep * Math.cos(v.yaw) - mm[1] * sep * Math.sin(v.yaw), my = e.y - (mm[0] * sep * Math.sin(v.yaw) + mm[1] * sep * Math.cos(v.yaw)) * Math.sin(v.pitch);
        ctx.save(); ctx.strokeStyle = C["s-moon"]; ctx.globalAlpha = 0.5; ctx.beginPath(); ctx.ellipse(e.x, e.y, sep, sep * Math.sin(v.pitch), 0, 0, 7); ctx.stroke(); ctx.restore();
        ctx.fillStyle = C["s-moon"]; ctx.beginPath(); ctx.arc(mx, my, v.scale === "true" ? 0.8 : 3, 0, 7); ctx.fill(); label("Moon", mx + 6, my - 10, C["s-moon"]);
        k.push(["Moon's distance", sep / trueSep]);
        k.push(["Mars", dot(f.pos.mars, sc, R_KM.mars / AU_KM, C["s-mars"], "Mars").k]);
        k.push(["Jupiter", dot(f.pos.jupiter, sc, R_KM.jupiter / AU_KM, C["s-jupiter"], "Jupiter").k]);
        bar(sc, "1 AU");
        keys = [["s-earth", "Earth and its target"], ["s-moon", "Moon on its mean orbit"], ["s-mars", "Mars and its parking orbit"], ["s-jupiter", "Jupiter"]];
      } else {
        const Ea = f.pos.earth, A = f.pos.asteroid, rel = [0, 1, 2].map(q => (A[q] - Ea[q]) * AU_KM), rn = Math.hypot(...Ea), toSun = Ea.map(q => -q / rn);
        const sc = Math.min(W, H) / 2 * 0.9 / 820000 * v.zoom;
        line(ring(MOON_KM), sc, C["s-moon"], [3, 4], 0.5); line(ring(420000), sc, C["s-bad"], [5, 5], 0.65);
        const t2 = proj([0, 420000, 0], sc); label("No beam inside 420,000 km", t2[0], t2[1] - 8, C["s-bad"], "center");
        const sp = proj(toSun.map(q => q * 760000), sc), o = proj([0, 0, 0], sc);
        ctx.save(); ctx.strokeStyle = C["s-sun"]; ctx.globalAlpha = 0.35; ctx.beginPath(); ctx.moveTo(o[0], o[1]); ctx.lineTo(sp[0], sp[1]); ctx.stroke(); ctx.restore(); label("Towards the Sun", sp[0] + 6, sp[1], C["s-sun"]);
        k.push(["Earth", dot([0, 0, 0], sc, R_KM.earth, C["s-earth"], "Earth").k]);
        k.push(["Moon", dot(meanMoon(f.t, MOON_KM), sc, R_KM.moon, C["s-moon"], "Moon (mean orbit)", 4).k]);
        const d = Math.hypot(...rel);
        if (f.earth_tow_active && d < 3e6) {
          line([rel.map((q, n) => q + toSun[n] * 900000), rel], sc, C["s-beam"], [], 0.9, 2);
          k.push(["Asteroid", dot(rel, sc, R_KM.asteroid, C["s-rock"], `Tow asteroid, ${Math.round(d).toLocaleString("en-US")} km`, 4).k]);
        } else label("The tow has finished and the asteroid has been sent away", W / 2, 28, C["s-bad"], "center");
        bar(100000 * sc, "100,000 km");
        keys = [["s-earth", "Earth"], ["s-moon", "Moon on its mean orbit"], ["s-rock", "Tow asteroid"], ["s-beam", "Light from the Sun's side"], ["s-bad", "Beam keep-out"]];
      }
      lines = [`<b>${year(f.t)}</b>`, `Earth orbit ${fix(f.earth_orbit_au, 3)} AU`, `Mars orbit ${fix(f.mars_orbit_au, 3)} AU`];
    }
    lines.push(`<span class="dim">${v.scale === "true" ? "True scale: bodies at real size, often under a pixel" : "Enlarged: " + k.map(([n, x]) => `${n} ×${sci(x, 1)}`).join(", ")}</span>`);
    legend.innerHTML = lines.join("<br>");
    keyBox.innerHTML = keys.map(([c, t]) => `<span><i style="background:var(--${c})"></i>${t}</span>`).join("");
  }
  const setSeg = () => { body.querySelectorAll("[data-view]").forEach(b => { b.setAttribute("aria-pressed", b.dataset.view === v.view); if (b.dataset.view === "moon") b.disabled = !live; });
    body.querySelectorAll("[data-scale]").forEach(b => b.setAttribute("aria-pressed", b.dataset.scale === v.scale)); };
  body.querySelectorAll("[data-view]").forEach(b => b.onclick = () => { stop(); v.view = b.dataset.view; v.zoom = 1; v.yaw = 0; v.pitch = Math.PI / 2; store.set("view", v.view); setSeg(); setupBar(); draw(); });
  body.querySelectorAll("[data-scale]").forEach(b => b.onclick = () => { v.scale = b.dataset.scale; store.set("scale", v.scale); setSeg(); draw(); });
  const scrub = $("#scrub", body);
  scrub.oninput = () => { if (v.view === "moon") v.j = +scrub.value; else v.i = +scrub.value; draw(); };
  $("#epoch", body).onchange = (e) => { v.epoch = +e.target.value; v.j = 0; setupBar(); draw(); };
  cv.onpointerdown = (ev) => { const x0 = ev.clientX, y0 = ev.clientY, a = v.yaw, p = v.pitch; cv.setPointerCapture(ev.pointerId);
    cv.onpointermove = (e) => { v.yaw = a + (e.clientX - x0) * 0.01; v.pitch = Math.min(Math.PI / 2, Math.max(0.05, p - (e.clientY - y0) * 0.01)); draw(); };
    cv.onpointerup = () => { cv.onpointermove = null; }; };
  cv.addEventListener("wheel", (e) => { e.preventDefault(); v.zoom = Math.min(20, Math.max(0.3, v.zoom * (e.deltaY < 0 ? 1.15 : 1 / 1.15))); draw(); }, { passive: false });
  let timer = null;
  function stop() { v.playing = false; clearTimeout(timer); const b = $("#play", body); if (b) b.textContent = "Play"; }
  $("#play", body).onclick = () => {
    if (v.playing) return stop();
    v.playing = true; $("#play", body).textContent = "Pause";
    const max = () => +scrub.max, get = () => (v.view === "moon" ? v.j : v.i), set = (x) => (v.view === "moon" ? (v.j = x) : (v.i = x));
    if (get() >= max()) set(0);
    const tick = () => { if (!v.playing) return; set(Math.min(max(), get() + Number($("#spd", body).value))); scrub.value = get(); draw(); if (get() >= max()) return stop(); timer = setTimeout(tick, 100); };
    tick();
  };
  const ro = new ResizeObserver(() => { fit(); draw(); }); ro.observe(cv);
  setSeg(); setupBar();
  scopeStop = () => { stop(); ro.disconnect(); };
}

/* ---------- charts ---------- */
function chart(canvas, series, o = {}) {
  const d = Math.min(devicePixelRatio || 1, 2), r = canvas.getBoundingClientRect();
  canvas.width = r.width * d; canvas.height = r.height * d; const c = canvas.getContext("2d"); c.setTransform(d, 0, 0, d, 0, 0);
  const w = r.width, h = r.height, L = 70, R = 12, T = 22, B = 24, pw = w - L - R, ph = h - T - B;
  const xs = series[0].x, x0 = xs[0], x1 = xs[xs.length - 1] || 1;
  const tr = (v) => (o.log ? Math.log10(Math.max(v, 1e-300)) : v);
  const y0 = tr(o.ymin), y1 = tr(o.ymax);
  const X = (v) => L + (v - x0) / (x1 - x0 || 1) * pw, Y = (v) => T + ph - (Math.min(Math.max(tr(v), y0), y1) - y0) / ((y1 - y0) || 1) * ph;
  const grid = css("--c-grid"), axis = css("--c-axis"), font = `12px ${css("--font")}`;
  c.font = font; c.lineWidth = 1;
  const ticks = o.log ? Array.from({ length: Math.round(y1 - y0) + 1 }, (_, k) => y0 + k).filter((_, k, a) => a.length < 7 || k % 2 === 0) : [0, 1, 2, 3, 4].map(k => y0 + (y1 - y0) * k / 4);
  for (const t of ticks) { const yy = T + ph - (t - y0) / (y1 - y0) * ph; c.strokeStyle = grid; c.beginPath(); c.moveTo(L, yy); c.lineTo(L + pw, yy); c.stroke(); c.fillStyle = axis; c.textAlign = "right"; c.fillText(o.log ? sci(10 ** t, 0) : sci(t, 2), L - 8, yy + 4); }
  for (let k = 0; k <= 4; k++) { const v = x0 + (x1 - x0) * k / 4; c.fillStyle = axis; c.textAlign = k === 0 ? "left" : k === 4 ? "right" : "center"; c.fillText("Year " + Math.round(v).toLocaleString("en-US"), X(v), h - 6); }
  for (const l of o.lines || []) { c.save(); c.setLineDash([5, 4]); c.strokeStyle = l.color; c.beginPath(); c.moveTo(L, Y(l.y)); c.lineTo(L + pw, Y(l.y)); c.stroke(); c.restore(); c.fillStyle = l.color; c.textAlign = "left"; c.fillText(l.label, L + 6, Y(l.y) - 5); }
  let lx = L + pw;
  for (const s of series) {
    c.strokeStyle = s.color; c.lineWidth = 1.8; c.beginPath(); let on = false;
    s.x.forEach((xv, k) => { const v = s.y[k]; if (v == null || !isFinite(v) || (o.log && v <= 0)) { on = false; return; } const px = X(xv), py = Y(v); on ? c.lineTo(px, py) : c.moveTo(px, py); on = true; });
    c.stroke();
    if (s.label) { c.fillStyle = s.color; c.textAlign = "right"; c.fillText(s.label, lx, 14); lx -= c.measureText(s.label).width + 16; }
  }
  c.textAlign = "left";
}

/* ---------- Validation ---------- */
async function pageValidation(main) {
  const v = await latest("validation.json");
  const rows = (v?.tests || []).map(t => ({ cells: [esc(t.test.replace(/^tests\//, "").replace("::", " › ")), esc(t.note).slice(0, 90), state(t.status === "PASSED" ? true : t.status === "SKIPPED" ? null : false, t.status[0] + t.status.slice(1).toLowerCase())] }));
  const official = (v?.tests || []).filter(t => /test_benchmark_\d+/.test(t.test));
  main.innerHTML = `<div class="pagehead"><div><h2>Validation</h2><p class="lede">The guide's ten benchmarks and our own tests, run as automated tests. Judges may change their inputs, so every run here uses the code as it stands.</p></div>
    <a class="btn primary" href="#/experiments/validation">Run benchmarks</a></div>` +
    (v ? `<section class="sheet">${facts([["Official benchmarks", `${official.filter(t => t.status === "PASSED").length} of ${official.length}`, "pass"], ["All tests", `${v.tests.filter(t => t.status === "PASSED").length} of ${v.tests.length}`, "pass"], ["Last run", esc(v._path.split("/").slice(-2, -1)[0] || v._path), esc(v.summary)]])}</section>` +
      sheet("Tests", "", table(["Test", "Note", "Result"], rows, [2]), "s12", true)
      : sheet("No results yet", "", empty("The benchmarks have not been run from this app", "Running them takes about a minute.", `<a class="btn primary" href="#/experiments/validation">Run benchmarks</a>`), "s12", true));
}

/* ---------- Moon ---------- */
async function pageMoon(main) {
  const base = await latest("baseline.json"), mc = await latest("moon_coupled.json");
  let html = `<div class="pagehead"><div><h2>Moon and baseline</h2><p class="lede">The Moon as its own body. The baseline runs the real solar system with no push; the coupled windows put the Moon next to the live tow.</p></div>
    <div class="actions"><a class="btn" href="#/experiments/baseline">Run baseline</a><a class="btn" href="#/experiments/moon_coupled">Run Moon beside the tow</a></div></div><div class="grid">`;
  if (base) {
    const m = base.measured, c = base.convergence, ck = base.checks;
    html += sheet("Baseline", `${esc(base._path)}, ${base.settings.years} years, ${base.settings.bodies.length} bodies`, table(["Measure", "Result", "Reference", ""], [
      { cells: ["Energy drift", sci(m.energy_error_max), "under 10⁻⁹", state(ck.energy_constant)] },
      { cells: ["Moon distance", `${Math.round(m.moon_closest_km).toLocaleString("en-US")} to ${Math.round(m.moon_farthest_km).toLocaleString("en-US")} km`, "356,400 to 406,700 km", state(ck.moon_bound, ck.moon_bound ? "Bound" : "Escaped")] },
      { cells: ["Moon's month", fix(m.moon_sidereal_month_days, 3) + " days", "27.322 days", state(ck["moon_month_within_0.1_day"])] },
      { cells: ["Earth–Moon year (benchmark 6)", fix(m.earth_moon_year_days, 3) + " days", "365.256 days", state(ck["earth_moon_year_within_0.1_day"])] },
      { cells: ["Step halved: the Moon moves", `${fix(c.moon_offset_change_km, 1)} km`, "under 0.1% of its distance", state(ck["converged_moon_offset_under_0.1pct"])] }], [3]), "s12", true);
  } else html += sheet("Baseline", "", empty("No baseline yet", "It takes about 15 seconds.", `<a class="btn primary" href="#/experiments/baseline">Run baseline</a>`), "s12", true);
  if (mc) {
    html += sheet("Moon beside the tow", `${esc(mc._path)}; Earth tow may use ${sci(mc.settings.earth_tow_power_available_w)} W`, table(["Earth orbit", "Moon distance change", "Extra beam power for the Moon", "Asteroid off its spot", "Time at E1's limit", ""],
      mc.epochs.map(e => ({ cells: [`${e.earth_au} AU`, (e.moon_distance_change * 100).toFixed(3) + "%", "+" + (e.beam_peak_increase_from_moon * 100).toFixed(1) + "%",
        Math.round(e.moon_body_with_tow.spot_error_max_km).toLocaleString("en-US") + " km", e.share_of_time_at_e1_limit != null ? (e.share_of_time_at_e1_limit * 100).toFixed(1) + "%" : "—", state(e.all_pass)] })), [1, 2, 3, 4, 5]), "s12", true);
  } else html += sheet("Moon beside the tow", "", empty("No coupled run yet", "It takes under a minute for short windows.", `<a class="btn primary" href="#/experiments/moon_coupled">Run Moon beside the tow</a>`), "s12", true);
  main.innerHTML = html + `</div>`;
}

/* ---------- Compare ---------- */
async function pageCompare(main) {
  await refreshRuns();
  if (S.runs.length < 2) { main.innerHTML = sheet("Compare runs", "", empty("Two saved journeys are needed", "Run another journey, for example without moving Mars.", `<a class="btn primary" href="#/experiments/journey">Set up a journey</a>`), "s12", true); return; }
  const opts = (sel) => S.runs.map(r => `<option ${r.path === sel ? "selected" : ""}>${esc(r.path)}</option>`).join("");
  const a0 = store.get("cmpA", S.runs[0].path), b0 = store.get("cmpB", S.runs[1].path);
  main.innerHTML = `<div class="pagehead"><div><h2>Compare runs</h2><p class="lede">Two saved journeys side by side.</p></div>
    <div class="actions"><select id="ca" class="input" style="width:auto">${opts(a0)}</select><select id="cb" class="input" style="width:auto">${opts(b0)}</select></div></div><div id="cout"></div>`;
  const go = async () => {
    const A = $("#ca").value, B = $("#cb").value; store.set("cmpA", A); store.set("cmpB", B);
    const [a, b] = await Promise.all([A, B].map(p => api("/api/file?path=" + encodeURIComponent(p + "/summary.json"))));
    const arr = (x) => x.tows["earth-tow"]?.arrival;
    const rows = [
      ["Earth arrives", x => arr(x) ? year(arr(x).year) : "Not arrived"], ["Earth orbit on arrival", x => arr(x) ? `${arr(x).a_au} AU, e ${arr(x).eccentricity}` : "—"],
      ["Mars", x => x.tows["mars-tow"]?.arrival ? `Parked at ${x.tows["mars-tow"].arrival.a_au} AU` : `Not parked; ends ${fix(x.end?.mars?.a_au, 2)} AU, e ${fix(x.end?.mars?.eccentricity, 2)}`],
      ["Closest Earth–Mars", x => x.mars_closest.au + " AU"], ["Unresolved flags", x => String(x.flags.unresolved)],
      ["Peak beam power", x => sci(x.total_beam_max_w) + " W"], ["Momentum error", x => sci(x.ledger.momentum_error_max)], ["Energy error", x => sci(x.ledger.energy_error_max_of_total)],
      ["Moved Mars first", x => x.settings.mars_tow ? "Yes" : "No"], ["Starting orbits", x => x.settings.start_orbits], ["Run time", x => Math.round(x.run_seconds) + " s"]];
    $("#cout").innerHTML = sheet("Side by side", "", table(["", esc(A), esc(B)], rows.map(([l, f]) => ({ cells: [l, esc(f(a)), esc(f(b))] }))), "s12", true);
  };
  $("#ca").onchange = go; $("#cb").onchange = go; go();
}

/* ---------- start ---------- */
(async () => {
  S.experiments = await api("/api/experiments");
  const jobs = await api("/api/jobs").catch(() => []);
  const live = jobs.find(j => j.status === "running");
  if (live) { S.job = live.id; poll(); }
  route();
})();

// Black Ant test bench. Reads what the Python core saved; never computes physics of its own.
"use strict";
const AU_KM = 149597870.7;
const R_KM = { sun: 695700, earth: 6371, mars: 3389.5, jupiter: 69911, asteroid: 335, moon: 1737.4 };
const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const COL = {}; ["void","panel","line","ink","dim","beam","earth","mars","jupiter","rock","sun","ok","warn","bad"].forEach(k => COL[k] = css("--" + k));
const $ = (s) => document.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const S = {
  experiments: [], runs: [], selected: "journey", run: null, i: 0, view: "solar", scale: "enlarged",
  yaw: 0, pitch: Math.PI / 2, zoom: 1, tab: "summary", job: null, jobs: {}, playing: false,
  latest: {}, // experiment id -> output folder of its last finished job
};

/* ---------- numbers ---------- */
const SUP = { "-": "⁻", "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹" };
function sci(x, d = 2) {
  if (x === 0) return "0"; if (x == null || !isFinite(x)) return "—";
  const e = Math.floor(Math.log10(Math.abs(x)));
  if (e >= -2 && e < 5) return (+x.toPrecision(d + 2)).toLocaleString("en-US");
  return (x / 10 ** e).toFixed(d) + "×10" + String(e).split("").map(c => SUP[c]).join("");
}
const fix = (x, d) => (x == null ? "—" : Number(x).toFixed(d));
const yr = (t) => (t == null ? "—" : "year " + Math.round(t).toLocaleString("en-US"));

/* ---------- api ---------- */
async function api(path, opts) {
  const r = await fetch(path, opts);
  const body = r.headers.get("content-type")?.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error(body.error || r.statusText);
  return body;
}

/* ---------- experiments ---------- */
function renderExperiments() {
  const box = $("#experiments"); box.innerHTML = "";
  for (const e of S.experiments) {
    const card = document.createElement("div");
    card.className = "card" + (e.id === S.selected ? " sel" : "");
    const running = S.job && S.jobs[S.job]?.status === "running";
    let form = "";
    if (e.id === S.selected) {
      form = `<div class="form">` + e.params.map(p => {
        const id = `p-${e.id}-${p.key}`;
        if (p.type === "bool") return `<label class="wide"><input type="checkbox" id="${id}" ${p.default ? "checked" : ""}> ${esc(p.label)}</label>`;
        if (p.type === "choice") return `<label for="${id}">${esc(p.label)}</label><select id="${id}">${p.choices.map(c => `<option ${c === p.default ? "selected" : ""}>${c}</option>`).join("")}</select>`;
        if (p.type === "text") return `<label for="${id}" class="wide">${esc(p.label)}</label><input class="wide" type="text" id="${id}" value="${esc(p.default)}">`;
        return `<label for="${id}">${esc(p.label)} <span class="meta">${p.min}–${p.max}</span></label><input type="number" id="${id}" value="${p.default}" min="${p.min}" max="${p.max}" step="any">`;
      }).join("") + `</div><div class="row"><button class="primary" data-run="${e.id}" ${running ? "disabled" : ""}>Run</button><span class="meta">${esc(e.minutes)}</span></div>`;
    }
    card.innerHTML = `<h3>${esc(e.label)}${e.id === S.selected ? "" : `<button data-pick="${e.id}">Set up</button>`}</h3><p>${esc(e.question)}</p>${form}`;
    box.appendChild(card);
  }
  box.querySelectorAll("[data-pick]").forEach(b => b.onclick = () => { S.selected = b.dataset.pick; renderExperiments(); });
  box.querySelectorAll("[data-run]").forEach(b => b.onclick = () => runExperiment(b.dataset.run));
}

async function runExperiment(id) {
  const e = S.experiments.find(x => x.id === id), params = {};
  for (const p of e.params) {
    const el = $(`#p-${e.id}-${p.key}`);
    params[p.key] = p.type === "bool" ? el.checked : p.type === "number" ? Number(el.value) : el.value;
  }
  try {
    const { job } = await api("/api/run", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ experiment: id, params }) });
    S.job = job; S.jobs[job] = { status: "running", experiment: id, lines: [] };
    setTab("log"); renderExperiments(); poll();
  } catch (err) { setJobChip("bad", err.message); }
}

function setJobChip(cls, text) { const c = $("#jobstate"); c.className = "chip " + cls; c.textContent = text; }

async function poll() {
  if (!S.job) return;
  const j = await api("/api/jobs/" + S.job).catch(() => null);
  if (!j) return;
  S.jobs[S.job] = j;
  const last = j.lines.filter(l => l.trim()).slice(-1)[0] || "starting…";
  if (j.status === "running") {
    setJobChip("run", `${j.experiment}: ${last.trim().slice(0, 70)}`);
    if (S.tab === "log") renderPanel();
    setTimeout(poll, 1000);
    return;
  }
  setJobChip(j.status === "done" ? "ok" : "bad", `${j.experiment}: ${j.status} in ${Math.round(j.ended - j.started)} s`);
  S.latest[j.experiment] = j.out;
  renderExperiments();
  if (j.experiment === "journey" && j.status === "done") { await loadRuns(); await loadRun(j.out); setTab("summary"); }
  else if (j.experiment === "baseline" || j.experiment === "moon_coupled") setTab("moon");
  else if (j.experiment === "validation") setTab("validation");
  else renderPanel();
}

/* ---------- saved runs ---------- */
async function loadRuns() {
  S.runs = await api("/api/runs").catch(() => []);
  const box = $("#runs");
  box.innerHTML = S.runs.length ? "" : `<p class="empty">No saved journeys yet. Run one above.</p>`;
  for (const r of S.runs) {
    const c = document.createElement("div");
    c.className = "card" + (S.run?.path === r.path ? " sel" : "");
    const earth = r.earth_arrival ? `Earth ${yr(r.earth_arrival.year)}` : "Earth not arrived";
    const mars = r.mars_arrival ? "Mars parked" : "Mars not parked";
    const flags = r.unresolved_flags ? `<span class="fail">${r.unresolved_flags} unresolved</span>` : `<span class="pass">0 unresolved</span>`;
    c.innerHTML = `<h3><span class="mono">${esc(r.path)}</span><button data-load="${esc(r.path)}">Open</button></h3>
      <span class="meta">${new Date(r.modified * 1000).toLocaleString()} · ${earth} · ${mars} · ${flags}</span>`;
    box.appendChild(c);
  }
  box.querySelectorAll("[data-load]").forEach(b => b.onclick = () => loadRun(b.dataset.load));
}

async function loadRun(path) {
  S.run = await api("/api/run?path=" + encodeURIComponent(path));
  S.i = S.run.frames.length - 1;
  $("#scrub").max = S.run.frames.length - 1; $("#scrub").value = S.i;
  await loadRuns(); draw(); renderPanel();
}

/* ---------- view ---------- */
const cv = $("#cv"), ctx = cv.getContext("2d");
let W = 0, H = 0;
function fit() { const r = cv.getBoundingClientRect(), d = Math.min(devicePixelRatio || 1, 2); cv.width = r.width * d; cv.height = r.height * d; ctx.setTransform(d, 0, 0, d, 0, 0); W = r.width; H = r.height; }
function project(p, scale) { // p = [x, y, z] in view units; yaw about z, then pitch (90° = looking straight down)
  const c = Math.cos(S.yaw), s = Math.sin(S.yaw);
  const x = c * p[0] - s * p[1], y = s * p[0] + c * p[1];
  const sy = y * Math.sin(S.pitch) + p[2] * Math.cos(S.pitch);
  return [W / 2 + x * scale, H / 2 - sy * scale];
}
function ringPts(r, n = 120) { const a = []; for (let k = 0; k <= n; k++) { const t = k / n * 2 * Math.PI; a.push([r * Math.cos(t), r * Math.sin(t), 0]); } return a; }
function poly(pts, scale, color, dash = [], alpha = 1, w = 1) {
  ctx.save(); ctx.strokeStyle = color; ctx.globalAlpha = alpha; ctx.lineWidth = w; ctx.setLineDash(dash); ctx.beginPath();
  pts.forEach((p, k) => { const [x, y] = project(p, scale); k ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke(); ctx.restore();
}
function body(p, scale, rView, color, label) {
  const [x, y] = project(p, scale); const trueR = rView * scale;
  const r = S.scale === "true" ? Math.max(trueR, 0.8) : Math.max(trueR, 5);
  ctx.fillStyle = color; ctx.beginPath(); ctx.arc(x, y, r, 0, 2 * Math.PI); ctx.fill();
  if (label) { ctx.fillStyle = color; ctx.font = `11px ${css("--mono")}`; ctx.fillText(label, x + r + 5, y - r - 2); }
  return r / trueR;
}
function text(s, x, y, color = COL.dim, align = "left") { ctx.fillStyle = color; ctx.font = `11px ${css("--mono")}`; ctx.textAlign = align; ctx.fillText(s, x, y); ctx.textAlign = "left"; }

function draw() {
  ctx.fillStyle = COL.void; ctx.fillRect(0, 0, W, H);
  const note = $("#viewnote");
  if (!S.run) { text("Open a saved journey or run one to see it here.", W / 2, H / 2, COL.dim, "center"); note.textContent = ""; return; }
  const F = S.run.frames, f = F[S.i];
  $("#year").textContent = yr(f.t);
  const factors = [];
  if (S.view === "solar") {
    const sc = Math.min(W, H) / 2 * 0.92 / 4.2 * S.zoom;
    poly(ringPts(2.7), sc, COL.earth, [6, 5], 0.5); poly(ringPts(3.64), sc, COL.mars, [6, 5], 0.5); poly(ringPts(3.28), sc, COL.dim, [2, 4], 0.6);
    poly(ringPts(f.earth_orbit_au), sc, COL.earth, [], 0.35); poly(ringPts(f.mars_orbit_au), sc, COL.mars, [], 0.35);
    const lab = project([2.7 * 0.71, -2.7 * 0.71, 0], sc); text("target 2.7 AU", lab[0] + 4, lab[1], COL.earth);
    const lm = project([3.64 * 0.71, -3.64 * 0.71, 0], sc); text("Mars park 3.64", lm[0] + 4, lm[1], COL.mars);
    const lj = project([-3.28 * 0.71, -3.28 * 0.71, 0], sc); text("Jupiter 2:1 · 3.28", lj[0] - 4, lj[1], COL.dim, "right");
    for (let k = Math.max(0, S.i - 40); k < S.i; k++) { // short trail of saved positions
      const g = F[k], a = 0.15 + 0.5 * (k - S.i + 40) / 40;
      for (const [n, c] of [["earth", COL.earth], ["mars", COL.mars], ["jupiter", COL.jupiter]]) {
        const [x, y] = project(g.pos[n], sc); ctx.globalAlpha = a; ctx.fillStyle = c; ctx.fillRect(x - 1, y - 1, 2, 2);
      }
    }
    ctx.globalAlpha = 1;
    factors.push(["Sun", body([0, 0, 0], sc, R_KM.sun / AU_KM, COL.sun)]);
    factors.push(["Earth", body(f.pos.earth, sc, R_KM.earth / AU_KM, COL.earth, "Earth")]);
    factors.push(["Mars", body(f.pos.mars, sc, R_KM.mars / AU_KM, COL.mars, "Mars")]);
    factors.push(["Jupiter", body(f.pos.jupiter, sc, R_KM.jupiter / AU_KM, COL.jupiter, "Jupiter")]);
    const bar = sc; ctx.strokeStyle = COL.dim; ctx.beginPath(); ctx.moveTo(14, H - 16); ctx.lineTo(14 + bar, H - 16); ctx.stroke(); text("1 AU", 20 + bar, H - 12);
  } else {
    const E = f.pos.earth, A = f.pos.asteroid, rel = [0, 1, 2].map(k => (A[k] - E[k]) * AU_KM);
    const sc = Math.min(W, H) / 2 * 0.9 / 820000 * S.zoom;
    const rn = Math.hypot(E[0], E[1], E[2]), toSun = E.map(v => -v / rn);
    poly(ringPts(384400), sc, COL.rock, [], 0.45); poly(ringPts(420000), sc, COL.bad, [5, 5], 0.6);
    const lk = project([0, 420000, 0], sc); text("no beam inside 420,000 km", lk[0], lk[1] - 6, COL.bad, "center");
    const sunPt = project(toSun.map(v => v * 760000), sc), o = project([0, 0, 0], sc);
    ctx.strokeStyle = COL.sun; ctx.beginPath(); ctx.moveTo(o[0], o[1]); ctx.lineTo(sunPt[0], sunPt[1]); ctx.globalAlpha = 0.35; ctx.stroke(); ctx.globalAlpha = 1; text("to the Sun", sunPt[0], sunPt[1], COL.sun);
    factors.push(["Earth", body([0, 0, 0], sc, R_KM.earth, COL.earth, "Earth")]);
    const dist = Math.hypot(...rel);
    if (f.earth_tow_active && dist < 3e6) {
      const from = rel.map((v, k) => v + toSun[k] * 900000); // the beam arrives from the Sun's side
      poly([from, rel], sc, COL.beam, [], 0.85, 2);
      factors.push(["asteroid", body(rel, sc, R_KM.asteroid, COL.rock, `tow asteroid · ${Math.round(dist).toLocaleString("en-US")} km`)]);
    } else text("Tow finished: the asteroid has been sent away", W / 2, 24, COL.warn, "center");
    const bar = 100000 * sc; ctx.strokeStyle = COL.dim; ctx.beginPath(); ctx.moveTo(14, H - 16); ctx.lineTo(14 + bar, H - 16); ctx.stroke(); text("100,000 km", 20 + bar, H - 12);
  }
  note.textContent = (S.scale === "true" ? "True scale: bodies at real size (may be under 1 px)" :
    "Visualisation scale: bodies enlarged\n" + factors.map(([n, k]) => `${n} ×${sci(k, 1)}`).join("  ")) +
    `\n${yr(f.t)} · Earth a ${fix(f.earth_orbit_au, 3)} AU · Mars a ${fix(f.mars_orbit_au, 3)} AU`;
}

cv.addEventListener("pointerdown", (ev) => {
  const x0 = ev.clientX, y0 = ev.clientY, yaw0 = S.yaw, p0 = S.pitch; cv.setPointerCapture(ev.pointerId);
  const move = (e) => { S.yaw = yaw0 + (e.clientX - x0) * 0.01; S.pitch = Math.min(Math.PI / 2, Math.max(0.05, p0 - (e.clientY - y0) * 0.01)); draw(); };
  const up = () => { cv.removeEventListener("pointermove", move); cv.removeEventListener("pointerup", up); };
  cv.addEventListener("pointermove", move); cv.addEventListener("pointerup", up);
});
cv.addEventListener("wheel", (ev) => { ev.preventDefault(); S.zoom = Math.min(20, Math.max(0.3, S.zoom * (ev.deltaY < 0 ? 1.15 : 1 / 1.15))); draw(); }, { passive: false });
document.querySelectorAll("[data-view]").forEach(b => b.onclick = () => { S.view = b.dataset.view; S.zoom = 1; document.querySelectorAll("[data-view]").forEach(x => x.classList.toggle("on", x === b)); draw(); });
document.querySelectorAll("[data-scale]").forEach(b => b.onclick = () => { S.scale = b.dataset.scale; document.querySelectorAll("[data-scale]").forEach(x => x.classList.toggle("on", x === b)); draw(); });
$("#scrub").oninput = () => { S.i = +$("#scrub").value; draw(); if (["orbit", "ledger"].includes(S.tab)) renderPanel(); };
$("#play").onclick = () => {
  if (!S.run) return;
  S.playing = !S.playing; $("#play").textContent = S.playing ? "Pause" : "Play";
  if (S.playing && S.i >= S.run.frames.length - 1) S.i = 0;
  const tick = () => {
    if (!S.playing) return;
    S.i = Math.min(S.run.frames.length - 1, S.i + Number($("#speed").value)); $("#scrub").value = S.i; draw();
    if (S.i >= S.run.frames.length - 1) { S.playing = false; $("#play").textContent = "Play"; return; }
    setTimeout(tick, 100);
  };
  tick();
};

/* ---------- charts ---------- */
function chart(canvas, series, o = {}) {
  const d = Math.min(devicePixelRatio || 1, 2), r = canvas.getBoundingClientRect();
  canvas.width = r.width * d; canvas.height = r.height * d; const c = canvas.getContext("2d"); c.setTransform(d, 0, 0, d, 0, 0);
  const w = r.width, h = r.height, L = 64, R = 10, T = 18, B = 22, pw = w - L - R, ph = h - T - B;
  const xs = series[0].x, x0 = o.xmin ?? xs[0], x1 = o.xmax ?? xs[xs.length - 1];
  const tr = (v) => (o.log ? Math.log10(Math.max(v, 1e-300)) : v);
  let ys = series.flatMap(s => s.y.filter(v => v != null && isFinite(v) && (!o.log || v > 0)));
  (o.lines || []).forEach(l => ys.push(l.y));
  const y0 = tr(o.ymin ?? Math.min(...ys)), y1 = tr(o.ymax ?? Math.max(...ys)) + (o.ymax == null && !o.log ? 1e-12 : 0);
  const X = (v) => L + (v - x0) / (x1 - x0 || 1) * pw, Y = (v) => T + ph - (tr(v) - y0) / ((y1 - y0) || 1) * ph;
  c.fillStyle = COL.dim; c.font = `10.5px ${css("--mono")}`; c.strokeStyle = COL.line; c.strokeRect(L, T, pw, ph);
  c.fillText(o.title || "", L, 12);
  for (let k = 0; k <= 3; k++) { const v = y0 + (y1 - y0) * k / 3, yy = T + ph - ph * k / 3; c.textAlign = "right"; c.fillText(o.log ? sci(10 ** v, 0) : sci(v, 2), L - 5, yy + 3); }
  c.textAlign = "center"; for (let k = 0; k <= 4; k++) { const v = x0 + (x1 - x0) * k / 4; c.fillText(Math.round(v).toLocaleString("en-US"), X(v), h - 6); }
  c.textAlign = "left";
  for (const l of o.lines || []) { c.save(); c.setLineDash([4, 4]); c.strokeStyle = l.color; c.beginPath(); c.moveTo(L, Y(l.y)); c.lineTo(L + pw, Y(l.y)); c.stroke(); c.restore(); c.fillStyle = l.color; c.textAlign = "right"; c.fillText(l.label, L + pw - 4, Y(l.y) - 3); c.textAlign = "left"; }
  for (const s of series) {
    c.strokeStyle = s.color; c.lineWidth = 1.6; c.beginPath(); let on = false;
    s.x.forEach((xv, k) => { const v = s.y[k]; if (v == null || !isFinite(v) || (o.log && v <= 0)) { on = false; return; } const px = X(xv), py = Y(v); on ? c.lineTo(px, py) : c.moveTo(px, py); on = true; });
    c.stroke();
  }
  if (o.cursor != null) { c.strokeStyle = COL.beam; c.setLineDash([3, 3]); c.beginPath(); c.moveTo(X(o.cursor), T); c.lineTo(X(o.cursor), T + ph); c.stroke(); }
}

/* ---------- results panel ---------- */
function setTab(t) { S.tab = t; document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === t)); renderPanel(); }
document.querySelectorAll("#tabs button").forEach(b => b.onclick = () => setTab(b.dataset.tab));

const table = (rows, head) => `<table>${head ? `<tr>${head.map(h => `<th>${h}</th>`).join("")}</tr>` : ""}${rows.map(r => `<tr>${r.map((c, k) => `<td class="${k ? "num" : ""}">${c}</td>`).join("")}</tr>`).join("")}</table>`;
const mark = (ok) => ok == null ? `<span class="skip">not checked</span>` : ok ? `<span class="pass">PASS</span>` : `<span class="fail">FAIL</span>`;

async function renderPanel() {
  const P = $("#panel"), s = S.run?.summary, F = S.run?.frames;
  const needRun = `<p class="empty">Open a saved journey (left) or run the Journey experiment.</p>`;
  switch (S.tab) {
    case "summary": {
      if (!s) { P.innerHTML = needRun; return; }
      const a = s.tows["earth-tow"]?.arrival, m = s.tows["mars-tow"]?.arrival, L = s.ledger, fl = s.flags;
      P.innerHTML = `<p class="mono">${esc(S.run.path)} · ${s.settings.years} years asked · ran ${Math.round(s.run_seconds)} s</p>` + table([
        ["Earth reaches 2.7 AU within 10,000 yr", a ? `${yr(a.year)} · ${a.a_au} AU · e ${a.eccentricity}` : "not arrived", mark(!!a && a.year <= 10000)],
        ["Mars parks at its orbit", m ? `${yr(m.year)} · ${m.a_au} AU · e ${m.eccentricity}` : `ends ${fix(s.end?.mars?.a_au, 3)} AU · e ${fix(s.end?.mars?.eccentricity, 3)}`, mark(!!m || s.settings.mars_tow === false)],
        ["No unresolved flags", `${fl.unresolved} unresolved · ${fl.covered_by_enablers} by enablers`, mark(fl.unresolved === 0)],
        ["Momentum ledger error", sci(L.momentum_error_max), mark(L.momentum_error_max < 1e-9)],
        ["Energy ledger error", sci(L.energy_error_max_of_total), mark(L.energy_error_max_of_total < 1e-5)],
        ["Closest Earth–Mars", `${s.mars_closest.au} AU · ${yr(s.mars_closest.year)}`, ""],
        ["Peak total beam power", `${sci(s.total_beam_max_w)} W of ${sci(s.settings.beam_limit_w)} W`, ""],
        ["Earth at the end", `${fix(s.end.earth.a_au, 4)} AU · e ${fix(s.end.earth.eccentricity, 4)}`, ""],
      ], ["Condition", "Value", ""]) + `<p class="note">Thresholds are the team's stand-ins in config.yaml until the rulebook appendix is published.</p>`;
      return;
    }
    case "orbit": {
      if (!F) { P.innerHTML = needRun; return; }
      P.innerHTML = `<canvas class="chart" id="c1"></canvas><canvas class="chart" id="c2"></canvas>`;
      const t = F.map(f => f.t);
      chart($("#c1"), [{ x: t, y: F.map(f => f.earth_orbit_au), color: COL.earth }, { x: t, y: F.map(f => f.mars_orbit_au), color: COL.mars }],
        { title: "Orbit size a (AU): Earth blue, Mars orange", ymin: 0.9, ymax: 3.9, cursor: F[S.i].t,
          lines: [{ y: 2.7, label: "target 2.7", color: COL.earth }, { y: 3.64, label: "Mars park 3.64", color: COL.mars }, { y: 3.278, label: "Jupiter 2:1", color: COL.bad }] });
      chart($("#c2"), [{ x: t, y: F.map(f => f.earth_eccentricity), color: COL.earth }],
        { title: "Earth's eccentricity", ymin: 0, cursor: F[S.i].t, lines: [{ y: 0.05, label: "limit 0.05", color: COL.bad }] });
      return;
    }
    case "ledger": {
      if (!F) { P.innerHTML = needRun; return; }
      const L = s.ledger, t = F.map(f => f.t);
      P.innerHTML = `<canvas class="chart" id="c1"></canvas><canvas class="chart" id="c2"></canvas><canvas class="chart" id="c3"></canvas>` + table([
        ["Work done by the beams", sci(L.beam_work_j) + " J"], ["Orbital energy gained by the bodies", sci(L.bodies_energy_gain_j) + " J"],
        ["Mismatch", sci(L.work_mismatch_share)], ["Largest station recoil", sci(s.station_recoil_max_n) + " N"],
        ["Momentum: bodies + station + light + departed", "error " + sci(L.momentum_error_max)]]);
      chart($("#c1"), [{ x: t, y: F.map(f => f.beam_power_w), color: COL.beam }], { title: "Total beam power (W)", ymin: 0, ymax: 1.1e26, cursor: F[S.i].t, lines: [{ y: s.settings.beam_limit_w, label: "E1 limit", color: COL.bad }] });
      chart($("#c2"), [{ x: t, y: F.map(f => Math.abs(f.energy_error)), color: COL.ok }], { title: "Energy ledger error (share of total)", log: true, ymin: 1e-10, ymax: 1e-5, cursor: F[S.i].t });
      chart($("#c3"), [{ x: t, y: F.map(f => Math.abs(f.momentum_error)), color: COL.earth }], { title: "Momentum ledger error", log: true, ymin: 1e-16, ymax: 1e-8, cursor: F[S.i].t });
      return;
    }
    case "safety": {
      if (!s) { P.innerHTML = needRun; return; }
      P.innerHTML = table(s.flags.flags.map(f => [esc(f.check), `${sci(f.worst)} ${esc(f.unit)}`, `${f.kind} ${sci(f.limit)}`,
        f.covered_by ? `<span class="warnc">${f.covered_by}</span>` : `<span class="fail">UNRESOLVED</span>`, `${Math.round(f.first_year)}–${Math.round(f.last_year)}`]),
        ["Check", "Worst", "Limit", "Status", "Years"]) +
        `<h2>Close passes</h2>` + table(Object.entries(s.big_asteroids_closest_au || {}).map(([k, v]) => [k, v + " AU"]).concat([["Mars", s.mars_closest.au + " AU"], ["Jupiter", s.jupiter_closest_au + " AU"]]));
      return;
    }
    case "moon": {
      const base = await latest("baseline.json"), mc = await latest("moon_coupled.json");
      let h = "";
      if (base) {
        const m = base.measured, c = base.convergence;
        h += `<h2>Baseline · ${esc(base._path)}</h2>` + table([
          ["Energy drift", sci(m.energy_error_max), mark(base.checks.energy_constant)],
          ["Moon distance", `${Math.round(m.moon_closest_km).toLocaleString("en-US")}–${Math.round(m.moon_farthest_km).toLocaleString("en-US")} km`, mark(base.checks.moon_bound)],
          ["Moon month (sidereal)", fix(m.moon_sidereal_month_days, 4) + " d", mark(base.checks["moon_month_within_0.1_day"])],
          ["Earth–Moon year (benchmark 6)", fix(m.earth_moon_year_days, 4) + " d", mark(base.checks["earth_moon_year_within_0.1_day"])],
          ["Step halved: Moon moves", `${fix(c.moon_offset_change_km, 1)} km (${sci(c.moon_offset_change_share)})`, mark(base.checks["converged_moon_offset_under_0.1pct"])]]);
      }
      if (mc) {
        h += `<h2>Moon beside the tow · ${esc(mc._path)}</h2>` + table(mc.epochs.map(e => [`${e.earth_au} AU`,
          `Moon change ${(e.moon_distance_change * 100).toFixed(3)}%`, `beam +${(e.beam_peak_increase_from_moon * 100).toFixed(1)}%`,
          `off spot ${Math.round(e.moon_body_with_tow.spot_error_max_km)} km`, mark(e.all_pass)]), ["Epoch", "Moon", "Beam", "Asteroid", ""]) +
          `<p class="note">Earth tow power available: ${sci(mc.settings.earth_tow_power_available_w)} W (${esc(mc.settings.cap_source)}).</p>`;
      }
      P.innerHTML = h || `<p class="empty">No Moon results yet. Run "Baseline" or "Moon beside the tow".</p>`;
      return;
    }
    case "validation": {
      const v = await latest("validation.json");
      if (!v) { P.innerHTML = `<p class="empty">Run "Benchmarks" (left) to run the official benchmarks and our tests here.</p>`; return; }
      P.innerHTML = `<p class="mono">${esc(v._path)} · ${esc(v.summary)}</p>` + table(v.tests.map(t => [esc(t.test.replace(/^tests\//, "")),
        `<span class="${t.status === "PASSED" ? "pass" : t.status === "SKIPPED" ? "skip" : "fail"}">${t.status}</span>`, esc(t.note).slice(0, 80)]), ["Test", "Result", "Note"]);
      return;
    }
    case "compare": {
      const opts = S.runs.map(r => `<option>${esc(r.path)}</option>`).join("");
      P.innerHTML = `<div class="row"><select id="ca">${opts}</select><span>vs</span><select id="cb">${opts}</select><button id="cgo">Compare</button></div><div id="cout"></div>
        <h2>Export</h2>${S.run ? `<p><a href="/api/export.csv?path=${encodeURIComponent(S.run.path)}">Frames of ${esc(S.run.path)} as CSV</a> · <a href="/api/file?path=${encodeURIComponent(S.run.path + "/summary.json")}" target="_blank">summary.json</a></p>` : `<p class="empty">Open a run to export it.</p>`}`;
      if (S.runs[1]) $("#cb").selectedIndex = 1;
      $("#cgo").onclick = async () => {
        const [a, b] = await Promise.all([$("#ca").value, $("#cb").value].map(p => api("/api/file?path=" + encodeURIComponent(p + "/summary.json"))));
        const row = (label, f) => [label, f(a), f(b)];
        const arr = (x) => x.tows["earth-tow"]?.arrival;
        $("#cout").innerHTML = table([
          row("Earth arrives", x => arr(x) ? yr(arr(x).year) : "no"), row("Earth a at arrival", x => arr(x)?.a_au ?? "—"),
          row("Mars parked", x => x.tows["mars-tow"]?.arrival ? "yes" : `no (ends ${fix(x.end?.mars?.a_au, 2)} AU, e ${fix(x.end?.mars?.eccentricity, 2)})`),
          row("Closest Earth–Mars", x => x.mars_closest.au + " AU"), row("Unresolved flags", x => x.flags.unresolved),
          row("Peak beam power", x => sci(x.total_beam_max_w) + " W"), row("Momentum error", x => sci(x.ledger.momentum_error_max)),
          row("Energy error", x => sci(x.ledger.energy_error_max_of_total)), row("Run time", x => Math.round(x.run_seconds) + " s")],
          ["", esc($("#ca").value), esc($("#cb").value)]);
      };
      return;
    }
    case "log": {
      const j = S.job && S.jobs[S.job];
      P.innerHTML = j ? `<p class="mono">${esc(j.command || "")}</p><div class="row">${j.status === "running" ? `<button id="stop">Stop this run</button>` : `<span class="chip">${j.status}</span>`}<span class="meta">output: ${esc(j.out || "")}</span></div><pre class="log">${esc((j.lines || []).join("\n"))}</pre>`
        : `<p class="empty">Nothing has run in this session yet.</p>`;
      const st = $("#stop"); if (st) st.onclick = () => api(`/api/jobs/${S.job}/stop`, { method: "POST" });
      const pre = P.querySelector("pre"); if (pre) pre.scrollTop = pre.scrollHeight;
      return;
    }
  }
}

async function latest(name) { // newest saved copy of a result file, from results/ or this app's runs
  try { const r = await api("/api/latest?file=" + name); r.data._path = r.path; return r.data; } catch (e) { return null; }
}

/* ---------- start ---------- */
new ResizeObserver(() => { fit(); draw(); }).observe(cv);
(async () => {
  S.experiments = await api("/api/experiments");
  renderExperiments();
  await loadRuns();
  if (S.runs[0]) await loadRun(S.runs[0].path); else { fit(); draw(); renderPanel(); }
})();

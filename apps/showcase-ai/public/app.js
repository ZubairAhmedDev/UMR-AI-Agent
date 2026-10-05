"use strict";

const tabs = document.getElementById("run-tabs");
const detail = document.getElementById("run-detail");
const planForm = document.getElementById("plan-form");
const planOutput = document.getElementById("plan-output");
let records = [];

function node(tag, className, value) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (value !== undefined) element.textContent = String(value);
  return element;
}

function metric(value, label) {
  const item = node("div", "metric");
  item.append(node("strong", "", value), node("span", "", label));
  return item;
}

function renderRun(run) {
  tabs.querySelectorAll("button").forEach((button) => {
    const selected = button.dataset.run === run.id;
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  const flagged = [...new Set(run.warnings.flatMap((warning) => warning.frames))].sort((a, b) => a - b);
  const totalFlags = run.warnings.reduce((count, warning) => count + warning.frames.length, 0);
  const head = node("div", "detail-head");
  const heading = node("div");
  heading.append(node("h3", "", run.title), node("p", "", `${run.source} · Attempt ${run.attempt}`));
  head.append(heading, node("span", "state", "Retargeting completed"));

  const body = node("div", "detail-body");
  const metrics = node("div", "metric-row");
  metrics.append(metric(run.frames, "frames"), metric(`${run.fps} Hz`, "source frame rate"),
    metric(`${(run.frames / run.fps).toFixed(2)} s`, "approximate clip duration"),
    metric(`${run.max_hinge_deg_s.toFixed(2)}°/s`, "maximum hinge speed"));
  body.append(metrics);
  const findingHead = node("div", "finding-head");
  findingHead.append(node("h4", "", "Velocity warnings"), node("span", "", `${totalFlags} joint-frame flags`));
  body.append(findingHead);
  const track = node("div", "timeline");
  track.setAttribute("role", "img");
  track.setAttribute("aria-label", `Flagged frame numbers: ${flagged.join(", ")}`);
  flagged.forEach((frame) => {
    const marker = node("i");
    marker.style.left = `${Math.max(1, Math.min(99, 100 * frame / (run.frames - 1)))}%`;
    marker.title = `Frame ${frame}`;
    track.append(marker);
  });
  body.append(track);
  const legend = node("div", "timeline-legend");
  legend.append(node("span", "", "Frame 0"), node("span", "", `Frame ${run.frames - 1}`));
  body.append(legend);
  const findings = node("div", "findings");
  run.warnings.forEach((finding) => findings.append(node("span", "finding", `${finding.joint.replaceAll("_", " ")} · ${finding.frames.length} frame${finding.frames.length === 1 ? "" : "s"}`)));
  body.append(findings);

  const footer = node("div", "detail-footer");
  const result = node("div");
  result.append(node("strong", "", "Output SHA-256"), node("span", "hash", run.result_sha256));
  const plan = node("div");
  plan.append(node("strong", "", "Approved plan SHA-256"), node("span", "hash", run.plan_hash));
  footer.append(result, plan);
  const note = node("div", "detail-note", `${run.provenance_note} Maximum root speed: ${run.max_root_m_s.toFixed(3)} m/s. No reported limit or quaternion errors; contact and skating checks were not run.`);
  detail.replaceChildren(head, body, footer, note);
}

tabs.addEventListener("keydown", (event) => {
  if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
  event.preventDefault();
  const current = records.findIndex((record) => tabs.querySelector('[aria-selected="true"]')?.dataset.run === record.id);
  const next = (current + (event.key === "ArrowRight" ? 1 : -1) + records.length) % records.length;
  tabs.children[next].focus();
  renderRun(records[next]);
});

planForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const selected = records.find((record) => record.id === document.getElementById("motion").value);
  if (!selected) return;
  const steps = node("ol");
  [
    `Select the registered ${selected.source} source for Unitree G1.`,
    "Recheck the source, robot, correspondence slots, and pipeline hashes.",
    "Prepare a new plan with a unique attempt ID and frame limit.",
    "Have an operator review and approve the exact new plan hash.",
    "Run UMR on the private Ubuntu worker; inspect and diagnose its output."
  ].forEach((item) => steps.append(node("li", "", item)));
  planOutput.replaceChildren(node("span", "output-index", "RULE-BASED / NON-EXECUTABLE"),
    node("h3", "", `${selected.title} → Unitree G1`), steps,
    node("p", "disclaimer", "The earlier completed run's hash cannot approve a new attempt. This page does not submit a job."));
});

async function load() {
  try {
    const response = await fetch("./data/runs.json", {cache: "no-store"});
    if (!response.ok) throw new Error("Run records could not be loaded.");
    const data = await response.json();
    if (data.schema_version !== 1 || !Array.isArray(data.runs) || data.runs.length !== 3) throw new Error("Run records have an unexpected format.");
    records = data.runs;
    tabs.replaceChildren();
    records.forEach((record) => {
      const button = node("button", "", record.title);
      button.type = "button";
      button.setAttribute("role", "tab");
      button.dataset.run = record.id;
      button.addEventListener("click", () => renderRun(record));
      tabs.append(button);
    });
    renderRun(records[1]);
  } catch (error) {
    detail.replaceChildren(node("p", "error", "Run records are unavailable."));
    const message = document.getElementById("data-error");
    message.hidden = false;
    message.textContent = error instanceof Error ? error.message : "Unexpected data error.";
    planForm.querySelector("button").disabled = true;
  }
}

load();

const chatForm = document.getElementById("chat-form");
chatForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = chatForm.querySelector("button");
  const output = document.getElementById("chat-response");
  const source = document.getElementById("chat-source");
  button.disabled = true;
  output.textContent = "Reading the completed run…";
  source.textContent = "";
  try {
    const response = await fetch("/api/chat", {
      method: "POST", headers: { "content-type": "application/json" },
      body: JSON.stringify({ motionId: document.getElementById("chat-motion").value,
        question: document.getElementById("chat-question").value })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "The assistant could not answer.");
    output.textContent = result.answer;
    source.textContent = `${result.source} · Attempt ${result.attempt} · SHA-256 ${result.resultSha256.slice(0, 12)}… · ${result.advisory}`;
  } catch (error) {
    output.textContent = error instanceof Error ? error.message : "Assistant unavailable.";
  } finally { button.disabled = false; }
});

const canvas = document.getElementById("robot-canvas");
const overlay = document.getElementById("robot-overlay");
const frameInput = document.getElementById("robot-frame");
const frameLabel = document.getElementById("frame-label");
const motionSelect = document.getElementById("robot-motion");
const playButton = document.getElementById("robot-play");
let motions = null, current = null, frame = 0, playing = true, yaw = -0.4, pitch = 0.12;
let lastTime = 0, pointerX = null;

function drawRobot() {
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const scale = Math.min(devicePixelRatio || 1, 2);
  const width = Math.round(rect.width * scale), height = Math.round(rect.height * scale);
  if (canvas.width !== width || canvas.height !== height) { canvas.width = width; canvas.height = height; }
  const ctx = canvas.getContext("2d");
  ctx.clearRect(0, 0, width, height);
  if (!current) return;
  const points = current.positions[frame];
  const center = current.center;
  const sin = Math.sin(yaw), cos = Math.cos(yaw), sinP = Math.sin(pitch), cosP = Math.cos(pitch);
  const zoom = Math.min(width / 3.2, height / 2.8);
  const projected = points.map(([x,y,z]) => {
    x -= center[0]; y -= center[1]; z -= center[2];
    const side = x * cos - y * sin;
    const depth = x * sin + y * cos;
    return [width / 2 + side * zoom, height / 2 - (z * cosP - depth * sinP) * zoom, depth];
  });
  ctx.lineCap = "round";
  current.links.forEach(([a,b]) => {
    const p = projected[a], q = projected[b];
    if (!p || !q) return;
    ctx.strokeStyle = "#b8e7d7"; ctx.lineWidth = Math.max(3, 8 * scale);
    ctx.beginPath(); ctx.moveTo(p[0],p[1]); ctx.lineTo(q[0],q[1]); ctx.stroke();
    ctx.strokeStyle = "#edf9ef"; ctx.lineWidth = Math.max(1, 2 * scale);
    ctx.beginPath(); ctx.moveTo(p[0],p[1]); ctx.lineTo(q[0],q[1]); ctx.stroke();
  });
  projected.forEach(([x,y]) => { ctx.fillStyle = "#addbca"; ctx.beginPath(); ctx.arc(x,y,2.5*scale,0,Math.PI*2); ctx.fill(); });
  ctx.fillStyle = "#b8e7d7"; ctx.font = `${11 * scale}px sans-serif`;
  ctx.fillText(`G1  /  frame ${frame + 1} of ${current.frames}  /  ${current.fps} Hz`, 18*scale, 25*scale);
}

function selectMotion() {
  current = motions?.runs[motionSelect.value] || null;
  if (!current) return;
  frame = 0; frameInput.max = String(current.frames - 1); frameInput.value = "0";
  frameLabel.textContent = `1 / ${current.frames}`;
  document.getElementById("robot-title").textContent = `G1 / ${current.title}`;
  document.getElementById("robot-provenance").textContent = `Result SHA-256: ${current.result_sha256.slice(0, 16)}… · playback model: ${current.viewer_xml_sha256.slice(0, 16)}…`;
  drawRobot();
}

frameInput.addEventListener("input", () => { frame = Number(frameInput.value); frameLabel.textContent = `${frame + 1} / ${current.frames}`; drawRobot(); });
motionSelect.addEventListener("change", selectMotion);
playButton.addEventListener("click", () => { playing = !playing; playButton.textContent = playing ? "Pause" : "Play"; });
canvas.addEventListener("pointerdown", (event) => { pointerX = event.clientX; canvas.setPointerCapture(event.pointerId); });
canvas.addEventListener("pointermove", (event) => { if (pointerX === null) return; yaw += (event.clientX - pointerX) * 0.008; pointerX = event.clientX; drawRobot(); });
canvas.addEventListener("pointerup", () => { pointerX = null; });
canvas.addEventListener("pointercancel", () => { pointerX = null; });
window.addEventListener("resize", drawRobot);
function tick(time) {
  if (current && playing && time - lastTime >= 1000 / current.fps) {
    frame = (frame + 1) % current.frames;
    frameInput.value = String(frame); frameLabel.textContent = `${frame + 1} / ${current.frames}`;
    lastTime = time; drawRobot();
  }
  requestAnimationFrame(tick);
}
requestAnimationFrame(tick);

async function loadMotions() {
  try {
    const response = await fetch("./data/motions.json", { cache: "no-store" });
    if (!response.ok) throw new Error("Recorded pose export is not installed yet. Run the Ubuntu export command in the release guide, then deploy the site.");
    const data = await response.json();
    if (data.schema_version !== 1 || !data.runs?.run || !data.runs?.["spin-kick"] || !data.runs?.["speed-vault"]) throw new Error("Pose export is incomplete.");
    motions = data; overlay.hidden = true; selectMotion();
  } catch (error) { overlay.textContent = error.message || "Motion data unavailable."; }
}
loadMotions();

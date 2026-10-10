const $ = (s) => document.querySelector(s);
const api = async (method, url, body) => {
  const r = await fetch(url, {method, headers: {"Content-Type": "application/json"}, body: body ? JSON.stringify(body) : undefined});
  const j = await r.json();
  if (!r.ok) throw new Error(j.detail || r.statusText);
  return j;
};
let S = null, scenarios = {}, stepIdx = 0, lastCount = 0, lastDue = null;
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
const fmtArgs = (a) => Object.entries(a || {}).map(([k, v]) => k === "amount" ? "$" + v : v).join(", ");

function render(prev) {
  $("#simnow").textContent = S.sim_now || "-";
  $("#tenant").value = S.tenant.id;
  const steps = scenarios[S.scenario]?.steps || [];
  $("#stepinfo").textContent = S.scenario ? `step ${stepIdx} of ${steps.length}` : "";
  // chat
  const srcIds = {};
  S.items.forEach((it) => { if (it.source_event_id) (srcIds[it.source_event_id] ||= []).push(it.label.split(" (")[0]); });
  $("#chat").innerHTML = S.events.map((e) => {
    if (e.kind === "system") return `<div class="sys ${/6th Reg Z/.test(e.text) ? "trigger" : ""}">Guard · ${esc(e.ts)} · ${esc(e.text)}</div>`;
    if (e.kind === "le_send") return `<div class="lesend">${esc(e.ts)} · ${esc(e.text)}</div>`;
    const who = e.role === "penny" ? "Penny (agent)" : e.role === "lo" ? "Loan officer" : "Borrower";
    const tags = (srcIds[e.id] || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("");
    return `<div class="m ${e.role} ${srcIds[e.id] ? "src" : ""}"><div class="meta">#${e.id} ${who} · ${esc(e.ts)}${tags}</div>${esc(e.text)}</div>`;
  }).join("");
  $("#chat").scrollTop = 1e9;
  // items
  $("#count").textContent = `${S.count} / 6`;
  $("#count").classList.toggle("full", S.count === 6);
  const trig = S.clock.trigger_event_id;
  $("#items").innerHTML = S.items.map((it) => `<div class="it ${it.value ? "on" : ""} ${it.value && trig && it.source_event_id === trig ? "last" : ""}">
    <div class="ck">${it.value ? "✓" : "○"}</div><div class="lbl">${esc(it.label)}</div>
    <div class="val">${it.value ? esc(it.value) : '<span class="prov">not captured</span>'}
    ${it.value ? `<div class="prov">from msg #${it.source_event_id}, ${esc(it.captured_at)}: "${esc(it.quote)}" · ${esc(it.method)}${it.note ? " · " + esc(it.note) : ""}</div>` : ""}</div></div>`).join("");
  // clock
  const c = S.clock, el = $("#clock");
  if (!c.application_received) {
    el.className = "clock";
    el.innerHTML = `<b>No application yet.</b> ${S.count} of 6 items on file. The Loan Estimate clock starts when the 6th lands.
      <div class="cite">Comment 2(a)(3)-1: once the creditor has these six pieces of information, it has an application.</div>`;
  } else {
    el.className = "clock live";
    const days = (arr) => `<div class="days">${arr.map((d, i) => `<span class="day ${d.skipped ? "s" : "c"}" title="${esc(d.skipped || "counts")}">${esc(d.label)}${d.skipped ? " · " + esc(d.skipped.replace("office closed ", "closed ")) : " ✓" + (arr.slice(0, i + 1).filter((x) => !x.skipped).length)}</span>`).join("")}</div>`;
    const status = {running: "Clock running", due_today: "Due today", overdue: "OVERDUE", le_sent_on_time: "LE sent on time", le_sent_late: "LE sent late", withdrawn: "Withdrawn, clock stopped"}[c.status] || "";
    el.innerHTML = `<div class="sub">Application received ${esc(c.application_received_at)} · ${esc(status)}</div>
      <div class="big" id="due">Loan Estimate due ${esc(c.le_due_short)}</div>
      <div class="sub">${esc(S.tenant.name)}: ${esc(S.tenant.note)}. Counting 3 general business days, 1026.19(e)(1)(iii)(A):</div>
      ${days(c.le_due_days)}
      <div class="kv">
        <div>LE sent</div><div>${c.le_sent_at ? esc(c.le_sent_at + " by " + c.le_method.replace("_", " ")) : "not yet"}</div>
        ${c.le_sent_at ? `<div>Considered received</div><div>${esc(c.deemed_receipt)}${c.receipt_evidence_at ? " (borrower confirmed " + esc(c.receipt_evidence_at) + ")" : ""} <span class="cite">1026.19(e)(1)(iv), specific business days</span></div>
        <div>Earliest consummation</div><div>${esc(c.earliest_consummation)} <span class="cite">1026.19(e)(1)(iii)(B)</span></div>` : ""}
        <div>Intent to proceed</div><div>${c.intent_at ? esc(c.intent_at) + ': "' + esc(c.intent_quote) + '"' : "none on file (silence does not count)"}</div>
        <div>Fee tools</div><div>${c.intent_at && !c.withdrawn_at ? "unlocked" : "locked except credit report fee"}</div>
      </div>`;
    if (prev && prev.clock.le_due_short && prev.clock.le_due_short !== c.le_due_short) $("#due").classList.add("flash");
    if (prev && !prev.clock.application_received) el.classList.add("flash");
  }
  // audit
  $("#audit").innerHTML = S.audit.slice().reverse().map((a, i) => `<div class="a ${a.decision} ${i === 0 && prev && prev.audit.length < S.audit.length ? "flash" : ""}">
    <div class="hd"><span>${esc(a.tool)}(${esc(fmtArgs(a.args))})</span><span class="badge">${a.decision.toUpperCase()}</span></div>
    <div class="rs">${esc(a.reason)}</div><div class="cite">${esc(a.ts)} · ${esc(a.cite)}</div></div>`).join("") || '<div class="cite">No tool calls yet.</div>';
}

async function load(id) { const prev = S; S = await api("GET", `/api/files/${id}`); render(prev); }
async function newFile(scenario, playUntil) {
  S = await api("POST", "/api/files", {scenario, play_until: playUntil || null});
  stepIdx = playUntil || 0;
  history.replaceState(null, "", `?file=${S.id}&step=${stepIdx}`);
  render(null);
}
async function post(ev) {
  const prev = S;
  const r = await api("POST", `/api/files/${S.id}/events`, ev);
  S = r.state; render(prev); return r.result;
}
function nowIso() {
  // sim clock as ISO; fall back to last scripted step time
  const steps = scenarios[S.scenario]?.steps || [];
  return window.__simIso || (steps[Math.max(0, stepIdx - 1)] || steps[0] || {ts: new Date().toISOString()}).ts;
}
async function next() {
  const steps = scenarios[S.scenario]?.steps || [];
  if (stepIdx >= steps.length) return false;
  const st = steps[stepIdx++];
  window.__simIso = st.ts;
  await post(st);
  history.replaceState(null, "", `?file=${S.id}&step=${stepIdx}`);
  return true;
}
window.tcg = {next, post, newFile, nowIso, setCaption: (t) => { const c = $("#caption"); c.hidden = !t; c.textContent = t || ""; },
  switchTenant: async (t) => { const prev = S; S = await api("PUT", `/api/files/${S.id}/tenant`, {tenant: t}); render(prev); }};

async function init() {
  scenarios = await api("GET", "/api/scenarios");
  const tenants = await api("GET", "/api/tenants");
  $("#tenant").innerHTML = tenants.map((t) => `<option value="${t.id}">${esc(t.name)}</option>`).join("");
  $("#scenario").innerHTML = Object.entries(scenarios).map(([k, v]) => `<option value="${k}">${esc(v.title)}</option>`).join("");
  const q = new URLSearchParams(location.search);
  if (q.get("file")) {
    try { await load(q.get("file")); stepIdx = +q.get("step") || 0; $("#scenario").value = S.scenario; render(null);
      const st = scenarios[S.scenario]?.steps[stepIdx - 1]; if (st) window.__simIso = st.ts; } catch { await newFile("maya", 0); }
  } else await newFile(q.get("scenario") || "maya", +q.get("step") || 0);
  $("#scenario").value = S.scenario;
  $("#next").onclick = () => next();
  $("#play").onclick = async () => { while (await next()) await new Promise((r) => setTimeout(r, 700)); };
  $("#reset").onclick = () => { window.__simIso = null; newFile($("#scenario").value, 0); };
  $("#scenario").onchange = () => { window.__simIso = null; newFile($("#scenario").value, 0); };
  $("#tenant").onchange = () => window.tcg.switchTenant($("#tenant").value);
  $("#compose").onsubmit = async (e) => { e.preventDefault(); const t = $("#msg").value.trim(); if (!t) return; $("#msg").value = ""; await post({kind: "message", role: "borrower", ts: nowIso(), text: t}); };
  document.querySelectorAll("[data-tool]").forEach((b) => b.onclick = () => post({kind: "tool", ts: nowIso(), tool: b.dataset.tool,
    args: b.dataset.fee ? {fee_type: b.dataset.fee, amount: +b.dataset.amt} : {purpose: "card on file"}}));
  document.querySelectorAll("[data-le]").forEach((b) => b.onclick = () => post({kind: "le_send", ts: nowIso(), method: b.dataset.le}));
  $("#advance").onclick = async () => { const d = new Date(nowIso()); d.setUTCDate(d.getUTCDate() + 1);
    const off = nowIso().slice(-6); const local = new Date(d.getTime() + (parseInt(off) * 60 + Math.sign(parseInt(off)) * +off.slice(-2)) * 60000);
    window.__simIso = local.toISOString().slice(0, 19) + off; await post({kind: "advance", ts: window.__simIso}); };
}
init();

/* The Activity page (E3-F3-01): what this repository's Claude sessions do now. Per session the orchestrator (the main
   thread) with its latest step and since when, and every agent it started, running first, each with its own latest
   step. It asks activity.json (lib/serve.py → lib/activity.py state()) every two seconds while it is open; the times
   count on between two answers. Only what Claude sent to its tools is shown, never what came back. */
(() => {
  const $ = sel => document.querySelector(sel);
  const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const badge = (status, text) => `<span class="badge ${esc(status)}">${esc(text ?? status)}</span>`;
  const KIND = { read: "reads", change: "changes", run: "runs", ask: "asks you", agent: "starts an agent", other: "uses" };
  const ICON = { read: "R", change: "W", run: "$", ask: "?", agent: "◆", other: "·" };
  const age = iso => {
    if (!iso) return "";
    const s = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000));
    return s < 60 ? `${s} s` : s < 3600 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${Math.floor(s / 3600)} h ${Math.floor((s % 3600) / 60)} min`;
  };

  function step(x, running) {
    if (!x || !x.tool) return `<span class="muted">${running ? "starting…" : "no step recorded"}</span>`;
    return `<span class="act-icon k-${esc(x.kind)}" title="${esc(x.tool)}">${esc(ICON[x.kind] || "·")}</span>
      <span class="act-what"><span class="muted">${esc(KIND[x.kind] || "uses")}</span> <b>${esc(x.text || x.tool)}</b></span>
      <span class="act-since muted" data-since="${esc(x.since || "")}">${running ? "for " : ""}${age(x.since)}${running ? "" : " ago"}</span>`;
  }

  function agent(a) {
    return `<li class="agent ${a.running ? "running" : "finished"}">
      <div class="agent-head">${a.running ? badge("area", "running") : badge("passed", "finished")}
        <b>${esc(a.name)}</b> <span class="muted small">${esc(a.type)}</span></div>
      <div class="act">${step(a, a.running)}</div></li>`;
  }

  function session(s) {
    const running = s.agents.filter(a => a.running).length;
    return `<article class="card session">
      <header class="session-head"><h2>${esc(s.title || "Session " + s.id.slice(0, 8))}</h2>
        ${s.busy ? badge("area", "busy") : badge("missing", "quiet")}
        <span class="muted small">${s.agents.length ? `${running} of ${s.agents.length} agent${s.agents.length === 1 ? "" : "s"} running` : "no agents"}</span>
        <a class="small" href="/results/sessions/${encodeURIComponent(s.id)}.html">the whole session</a></header>
      ${s.prompt ? `<p class="session-prompt"><span class="muted">Asked:</span> ${esc(s.prompt)}</p>` : ""}
      <div class="orchestrator"><div class="label">Orchestrator · main thread</div><div class="act">${step(s.main, s.busy)}</div></div>
      ${s.agents.length ? `<ul class="agents">${s.agents.map(agent).join("")}</ul>` : ""}
    </article>`;
  }

  function render(d) {
    if (window.Look) Look.brand(d.product, d.monogram, "Activity");
    const busy = d.sessions.filter(s => s.busy).length;
    $("#stamp").textContent = `${busy ? `${busy} session${busy === 1 ? "" : "s"} busy` : "nothing running"} · live`;
    $("#view").innerHTML = d.sessions.length ? d.sessions.map(session).join("")
      : `<div class="card">No Claude session wrote in this repository in the last half hour. Earlier sessions are under <a href="/results/sessions/index.html">Sessions</a>.</div>`;
  }

  let last = "";
  async function poll() {
    if (document.hidden) return;
    try {
      const r = await fetch("activity.json", { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      const text = await r.text();
      if (text !== last) { last = text; render(JSON.parse(text)); }
    } catch {
      if (!last) $("#view").innerHTML = `<div class="card">This page needs the crissp server: <code>crissp dashboard</code>, then open <code>/activity</code>.</div>`;
    }
  }
  const tick = () => document.querySelectorAll("[data-since]").forEach(el => {
    const since = el.dataset.since, running = el.textContent.startsWith("for ");
    if (since) el.textContent = `${running ? "for " : ""}${age(since)}${running ? "" : " ago"}`;
  });
  poll();
  setInterval(poll, 2000);
  setInterval(tick, 1000);
  document.addEventListener("visibilitychange", poll);
})();

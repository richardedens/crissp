/* The Stages page (F-130): where the work is in the six stages of the agentic SDLC (Discover, Plan, Build, Verify,
   Review, Release), read from the backlog, the release certificate, git and the UX suite (lib/stages.py, the same as
   the crissp tool `stage`). Per stage what is in it and whose move it is, and how to ask Claude Code or Mistral Vibe to
   help with it: the command to start a session with it, or the sentence for a session already open. Discover can
   start the UX team's rounds here, as the UX page does (POST /ux/api/request). It asks stages.json every five seconds
   while it is open. Nothing here starts a check, tags, pushes or publishes. */
(() => {
  const $ = sel => document.querySelector(sel);
  const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const STATUS = { setup: ["missing", "to set up"], work: ["area", "work to do"], yours: ["yours", "waits for you"], clear: ["passed", "clear"] };
  const badge = s => { const [tone, text] = STATUS[s] || ["ver", s]; return `<span class="badge ${tone}">${esc(text)}</span>`; };
  const MORE = 6;

  function flow(d) {
    return `<ol class="flow" aria-label="The six stages">${d.stages.map((s, i) => `<li class="${s.key === d.current ? "on" : ""}">
      <a href="#${esc(s.key)}"${s.key === d.current ? ' aria-current="step"' : ""}><span class="n">${i + 1}</span><b>${esc(s.name)}</b>${badge(s.status)}</a></li>`).join("")}</ol>`;
  }

  function stage(s, i, current) {
    const items = s.items.slice(0, MORE).map(x => `<li>${esc(x)}</li>`).join("")
      + (s.items.length > MORE ? `<li class="muted">and ${s.items.length - MORE} more</li>` : "");
    const actions = s.actions.map(a =>
      `<button class="ghost" data-kind="${esc(a.kind)}" data-walk="${esc(a.walk)}">${esc(a.label)}</button>`).join("");
    return `<article class="card stage${s.key === current ? " on" : ""}" id="${esc(s.key)}">
      <header><span class="n">${i + 1}</span><h3>${esc(s.name)}</h3>${badge(s.status)}${s.key === current ? '<span class="badge area here">the work is here</span>' : ""}</header>
      <p>${esc(s.summary)}</p>
      ${items ? `<ul>${items}</ul>` : ""}
      ${actions ? `<div class="asks">${actions}<span class="muted small">costs tokens: the UX team starts it now</span></div>` : ""}
      <div class="asks">
        <button class="primary" data-copy="${esc(s.claude)}" title="${esc(s.claude)}">Ask Claude</button>
        <button class="ghost" data-copy="${esc(s.vibe)}" title="${esc(s.vibe)}">Ask Vibe</button>
        <button class="ghost" data-copy="${esc(s.ask)}" title="for a session that is already open">Copy the sentence</button>
        <span class="copied" aria-live="polite"></span>
      </div>
      <p class="muted small">Copies <code>${esc(s.claude)}</code> for a terminal; in an open session say <code>${esc(s.ask)}</code>.</p>
      <details><summary>What Claude or Vibe then does</summary><p>${esc(s.prompt)}</p></details>
    </article>`;
  }

  function render(d) {
    if (window.Look) Look.brand(d.product, d.monogram, "Stages");
    const now = d.stages.find(s => s.key === d.current) || d.stages[0];
    $("#stamp").textContent = `The work is in ${now.name} · live`;
    $("#view").innerHTML = `<section class="card now"><div><div class="muted small">The work is in</div><div class="big">${esc(now.name)}</div></div>
        <p>${esc(d.why)}</p></section>
      ${flow(d)}
      <section class="grid stages">${d.stages.map((s, i) => stage(s, i, d.current)).join("")}</section>`;
  }

  async function copy(button) {
    const said = button.parentElement.querySelector(".copied");
    try {
      await navigator.clipboard.writeText(button.dataset.copy);
      said.textContent = `Copied: ${button.dataset.copy}`;
    } catch {
      said.textContent = `Copy this: ${button.dataset.copy}`;
    }
  }

  async function start(button) {
    const said = button.parentElement;
    button.disabled = true;
    try {
      const r = await fetch("/ux/api/request", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ kind: button.dataset.kind, walk: button.dataset.walk }) });
      const answer = await r.json();
      said.insertAdjacentHTML("beforeend", `<span class="small ${r.ok ? "copied" : "muted"}">${esc(r.ok ? (answer.queued ? `queued, place ${answer.queued}: ${answer.why}` : "started: the UX page follows it") : answer.error)}</span>`);
    } catch {
      said.insertAdjacentHTML("beforeend", `<span class="small muted">The UX suite did not answer.</span>`);
    }
  }

  document.addEventListener("click", e => {
    const b = e.target.closest("button[data-copy], button[data-kind]");
    if (!b) return;
    if (b.dataset.copy) copy(b); else start(b);
  });

  let last = "";
  async function poll() {
    if (document.hidden) return;
    try {
      const r = await fetch("stages.json", { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      const text = await r.text();
      if (text !== last) { last = text; render(JSON.parse(text)); }
    } catch {
      if (!last) $("#view").innerHTML = `<div class="card">This page needs the crissp server: <code>crissp dashboard</code>, then open <code>/stages</code>.</div>`;
    }
  }
  poll();
  setInterval(poll, 5000);
  document.addEventListener("visibilitychange", poll);
})();

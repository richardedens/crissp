/* The UX suite's page: reads /ux/api/state (crissp/uxsuite/api.py) and shows the walks, the team's rounds and advice,
   its designs and the product owner's verdicts; writes verdicts and requests back. The look, the theme and the top bar
   are the framework's own (crissp/look). No dependencies, nothing loaded from outside. */
(() => {
  const $ = (sel, el = document) => el.querySelector(sel);
  const { esc, badge } = window.Look;
  let S = null, tab = "overview", query = new URLSearchParams();
  const TABS = [["overview", "Overview"], ["rounds", "Rounds & advice"], ["proposals", "Designs"], ["team", "Team"]];

  const api = async (path, body) => {
    const r = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : { cache: "no-store" });
    const data = await r.json();
    if (!r.ok) throw new Error(data.error || r.statusText);
    return data;
  };
  const ask = (title, hint) => new Promise(done => {
    const d = $("#why");
    $("#why-title").textContent = title; $("#why-hint").textContent = hint || ""; $("#why-text").value = "";
    d.onclose = () => done(d.returnValue === "ok" ? $("#why-text").value.trim() : null);
    d.showModal();
  });
  const say = text => { $("#stamp").textContent = text; };

  const last = list => list[list.length - 1];
  const avg = scores => { const v = Object.values(scores || {}).filter(x => typeof x === "number"); return v.length ? (v.reduce((a, b) => a + b, 0) / v.length).toFixed(1) : "–"; };
  const phase = st => st?.phase === "done" ? badge("passed", "done") : st?.phase === "failed" ? badge("failed", "failed") : badge("missing", st?.phase || "…");
  const name = key => S.personas.find(p => p.key === key)?.name || key;
  const walkOf = id => S.walks.find(w => w.id === id) || S.walks[0];

  function overview() {
    const t = S.team;
    return `<div class="grid kpis" style="margin-bottom:14px">
        <div class="card kpi"><div class="l">Walks</div><div class="v">${S.walks.length}</div><div class="s">${esc(S.url)}</div></div>
        <div class="card kpi"><div class="l">The team</div><div class="v">${t.running.length}<span class="muted small"> / ${t.slots}</span></div><div class="s">${esc(t.text)}</div></div>
        <div class="card kpi"><div class="l">Waiting</div><div class="v">${S.queue.length}</div><div class="s">${S.queue.map(q => esc(q.kind + " " + q.walk)).join(" · ") || "nothing"}</div></div>
        <div class="card kpi"><div class="l">Verdicts</div><div class="v">${Object.keys(S.verdicts).length}</div><div class="s">yours, on advice and designs</div></div></div>
      ${S.about ? `<p class="muted">${esc(S.about)}</p>` : ""}
      <div class="walks-list">${S.walks.map(w => {
        const r = last(w.rounds), p = last(w.proposals), res = r?.result;
        const must = (res?.advice || []).filter(a => a.priority === "must").length;
        return `<article class="card walk"><header><h3>${esc(w.title)}</h3><code class="small muted">${esc(w.id)}</code></header>
          <div class="row small">${w.shots.filter(s => s.url).length} screenshot(s)${w.shots.some(s => s.error) ? ` · ${badge("failed", "stuck")}` : ""}
            · ${w.rounds.length} round(s)${r ? " " + phase(r.status) : ""} · ${w.proposals.length} design(s)${p ? " " + phase(p.status) : ""}</div>
          ${res ? `<div class="row"><span class="score">average <b>${avg(res.scores)}</b></span>${badge("must", must + " must")}</div><p class="small muted">${esc(res.summary)}</p>` : '<p class="small muted">No round yet.</p>'}
          <div class="row">${w.shots.some(s => s.url) ? "" : `<span class="small muted">Shoot it first: <code>crissp/ux.sh --shoot ${esc(w.id)}</code></span>`}
            <button class="ghost" data-request="round" data-walk="${esc(w.id)}">Ask for a round</button>
            <button class="ghost" data-request="proposal" data-walk="${esc(w.id)}">Ask for a design</button>
            <a href="#rounds?walk=${encodeURIComponent(w.id)}">Advice</a></div></article>`;
      }).join("") || '<div class="card">No walks yet: add one to <code>crissp/uxsuite/walks/</code>.</div>'}</div>`;
  }

  const walkPicker = (w, to) => `<div class="toolbar"><select id="walk" data-to="${to}" aria-label="Walk">${S.walks.map(x => `<option value="${esc(x.id)}" ${x === w ? "selected" : ""}>${esc(x.title)}</option>`).join("")}</select></div>`;

  function shotsOf(w) {
    return `<div class="shots">${w.shots.map(s => s.url ? `<figure><img src="${esc(s.url)}" alt="${esc(s.title)}" loading="lazy"><figcaption>${esc(s.device)} ${s.n} · ${esc(s.title)}</figcaption></figure>`
      : `<p class="small">${badge("failed", s.device)} ${esc(s.error)}</p>`).join("") || '<p class="small muted">No screenshots yet.</p>'}</div>`;
  }

  function verdictButtons(id, options) {
    const held = S.verdicts[id];
    return `<div class="verdicts">${options.map(([v, label]) => `<button class="ghost small" data-verdict="${v}" data-id="${esc(id)}" aria-pressed="${v === "approve-remark" ? held?.verdict === "approve" && !!held?.reason : v === "approve" ? held?.verdict === "approve" && !held?.reason : held?.verdict === v}">${label}</button>`).join("")}
      ${held?.reason ? `<span class="small muted">“${esc(held.reason)}”</span>` : ""}</div>`;
  }

  function rounds() {
    const w = walkOf(query.get("walk"));
    if (!w) return '<div class="card">No walks yet.</div>';
    const list = [...w.rounds].reverse();
    return walkPicker(w, "rounds") + `<div class="card" style="margin-bottom:14px"><div class="label">What the team looked at</div>${shotsOf(w)}</div>` +
      (list.map(r => {
        const res = r.result;
        if (!res) return `<div class="card">Round ${r.version} ${phase(r.status)} <span class="small muted">${esc(r.status.note || "")}</span></div>`;
        return `<article class="card walk"><header><h3>Round ${r.version}</h3>${phase(r.status)}<span class="small muted">${esc(r.request?.at || "")}</span></header>
          <div class="scores"><span class="score">average <b>${avg(res.scores)}</b></span>${Object.entries(res.scores || {}).map(([k, v]) => `<span class="score">${esc(name(k))} <b>${esc(v)}</b></span>`).join("")}</div>
          <p>${esc(res.summary)}</p>
          ${(res.consensus || []).length ? `<details><summary>Everyone agreed (${res.consensus.length})</summary><ul>${res.consensus.map(c => `<li>${esc(c)}</li>`).join("")}</ul></details>` : ""}
          ${(res.disputes || []).length ? `<details><summary>Where they disagree (${res.disputes.length})</summary>${res.disputes.map(d => `<p><b>${esc(d.topic)}</b></p><ul>${(d.positions || []).map(x => `<li>${esc(name(x.persona))}: ${esc(x.position)}</li>`).join("")}</ul>`).join("")}</details>` : ""}
          <div class="label">Advice</div>${(res.advice || []).map((a, i) => `<div class="advice ${esc(a.priority)}">
            <div class="row">${badge(a.priority, a.priority)}${a.effort ? badge("ver", a.effort) : ""}<b>${esc(a.title)}</b></div>
            <p>${esc(a.detail)}</p><p class="small">Asked by ${(a.personas || []).map(name).map(esc).join(", ") || "the team"}${a.shot ? ` · ${esc(a.shot)}` : ""}</p>
            ${verdictButtons(`${w.id}/r${r.version}/a${i}`, [["agree", "Agree"], ["disagree", "Disagree"], ["later", "Later"]])}</div>`).join("") || '<p class="muted small">No advice.</p>'}</article>`;
      }).join("") || '<div class="card">No round yet. <button class="ghost" data-request="round" data-walk="' + esc(w.id) + '">Ask for a round</button></div>');
  }

  function proposals() {
    const w = walkOf(query.get("walk"));
    if (!w) return '<div class="card">No walks yet.</div>';
    const open = query.get("key");
    return walkPicker(w, "proposals") + `<div class="toolbar"><button class="primary" data-request="proposal" data-walk="${esc(w.id)}">Ask for a design</button></div>` +
      ([...w.proposals].reverse().map(p => {
        const res = p.result;
        return `<article class="card walk" id="p-${esc(p.key)}"><header><h3>Design ${p.version}${res?.title ? ": " + esc(res.title) : ""}</h3>${phase(p.status)}
            ${p.verdict ? badge(p.verdict.verdict === "approve" ? "passed" : p.verdict.verdict === "reject" ? "failed" : "missing", p.verdict.verdict) : ""}
            ${p.pbi ? `<a href="../dashboard/#board?q=${encodeURIComponent(p.pbi)}">${badge("area", p.pbi)} on the board</a>` : ""}</header>
          ${p.mockup ? compare(w, p) : ""}
          ${res ? `<div class="decide">${verdictButtons(p.key, [["approve", "Approve"], ["approve-remark", "Approve with a remark…"], ["redo", "Again, with…"], ["reject", "Reject"]])}<span class="small muted">Approve makes it a backlog item (a remark goes with it); Again asks the designer for the next version.</span></div>` : ""}
          ${p.request?.focus ? `<p class="small muted">Focus: ${esc(p.request.focus)}</p>` : ""}
          ${res ? `<p>${esc(res.summary)}</p>${(res.changes || []).length ? `<ol>${res.changes.map(c => `<li>${badge(c.priority || "should", c.priority || "should")} ${esc(c.what)} <span class="small muted">${esc(c.why)}</span></li>`).join("")}</ol>` : ""}
            ${(res.open_questions || []).length ? `<div class="label">Open questions</div><ul>${res.open_questions.map(q => `<li>${esc(q)}</li>`).join("")}</ul>` : ""}` : `<p class="small muted">${esc(p.status.note || "")}</p>`}
</article>`;
      }).join("") || '<div class="card">No design yet.</div>');
  }

  /* Before | After: what people see today (the walk's own screenshot, laptop or phone) next to the design, the same
     size, so a verdict is a look and a click. The mockup is drawn at the laptop size and scaled to fit (fit()). */
  function compare(w, p) {
    const shot = d => (w.shots || []).find(s => s.device === d && s.url);
    const devices = ["laptop", "phone"].filter(shot);
    const d = devices.includes(query.get("device")) ? query.get("device") : devices[0];
    const before = d ? shot(d) : null;
    const pick = devices.length > 1 ? `<span class="seg">${devices.map(x => `<button class="ghost small" data-device="${x}" aria-pressed="${x === d}">${x === "laptop" ? "Laptop" : "Phone"}</button>`).join("")}</span>` : "";
    return `<div class="compare">
        <figure class="pane"><figcaption><b>Before</b> · what people see now ${pick}</figcaption>
          <div class="frame ${d === "phone" ? "tall" : ""}">${before ? `<img src="${esc(before.url)}" alt="Before: ${esc(before.title || "")}">` : '<p class="small muted">No screenshot of this walk yet: crissp ux --shoot ' + esc(w.id) + '</p>'}</div></figure>
        <figure class="pane"><figcaption><b>After</b> · design ${p.version} <a class="small" href="${esc(p.mockup)}" target="_blank" rel="noopener">open full size ↗</a></figcaption>
          <div class="frame fit"><iframe sandbox="allow-scripts" src="${esc(p.mockup)}" title="After: design ${p.version}" tabindex="-1"></iframe></div></figure>
      </div>`;
  }

  /* scale every mockup (drawn 1440 wide) to the width of its pane */
  function fit() {
    document.querySelectorAll(".frame.fit").forEach(f => {
      const i = f.querySelector("iframe");
      if (i) i.style.transform = `scale(${f.clientWidth / 1440})`;
    });
  }
  window.addEventListener("resize", fit);

  function team() {
    return `<div class="walks-list">${S.personas.map(p => `<article class="card persona"><div class="row"><h3>${esc(p.name)}</h3>${p.moderator ? badge("area", "moderator") : ""}${badge("ver", p.device)}</div>
      <div class="small muted">${esc(p.role)}</div><p class="small">${esc(p.brief)}</p></article>`).join("")}</div>
      <p class="small muted">The team, the product and the walks are configured in <code>crissp/uxsuite/team.json</code> and <code>crissp/uxsuite/walks/</code>.</p>`;
  }

  function render() {
    $("#tabs").innerHTML = TABS.map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${k === tab}">${l}</button>`).join("");
    const view = { overview, rounds, proposals, team }[tab] || overview;
    $("#view").innerHTML = view();
    fit();
    if (query.get("key")) $(`[id="p-${CSS.escape(query.get("key"))}"]`)?.scrollIntoView();
  }

  function route() {
    const h = decodeURIComponent(location.hash.slice(1));
    if (h.startsWith("proposal=")) {  // a deep link from the Tests board: /ux/#proposal=<walk>#v<n>
      const key = h.slice(9);
      tab = "proposals"; query = new URLSearchParams({ walk: key.split("#")[0], key });
    } else {
      const [k, q] = location.hash.slice(1).split("?");
      tab = TABS.some(([t]) => t === k) ? k : "overview"; query = new URLSearchParams(q || "");
    }
  }

  let seen = "";
  async function load(force = true) {
    try {
      const next = await api("api/state"), text = JSON.stringify(next);
      if (!force && text === seen) return;  // the poll redraws only what changed: an open mockup stays open
      S = next; seen = text;
    } catch (e) { $("#view").innerHTML = `<div class="card">The UX suite does not answer: ${esc(e.message)}</div>`; return; }
    if (S.error) { $("#view").innerHTML = `<div class="card"><b>The configuration is wrong:</b> ${esc(S.error)}</div>`; return; }
    window.Look.brand(S.product, S.monogram, "UX");
    say(S.team.text);
    render();
  }

  document.addEventListener("click", async e => {
    const dv = e.target.closest("[data-device]");
    if (dv) { query.set("device", dv.dataset.device); render(); return; }  // Before on the laptop or the phone
    const t = e.target.closest("[data-tab]");
    if (t) { location.hash = t.dataset.tab; return; }
    const r = e.target.closest("[data-request]");
    if (r) {
      const focus = r.dataset.request === "proposal" ? await ask("What should the design focus on?", "Leave it empty for the must-advice first.") : "";
      if (focus === null) return;
      try { const out = await api("api/request", { kind: r.dataset.request, walk: r.dataset.walk, focus });
        say(out.started ? `Started: ${out.started.kind} ${out.started.version} of ${out.started.walk}` : `Queued as number ${out.queued}: ${out.why}`);
      } catch (err) { say(err.message); }
      return load();
    }
    const v = e.target.closest("[data-verdict]");
    if (v) {
      const remark = v.dataset.verdict === "approve-remark";  // an approval with the product owner's words for the builder
      const verdict = remark ? "approve" : v.dataset.verdict;
      const needs = remark || ["disagree", "redo", "reject"].includes(verdict);
      const reason = needs ? await ask(remark ? "Your remark with the approval" : verdict === "redo" ? "What should the team do differently?" : "Why?",
        remark ? "It goes into the backlog item, before the changes: the builder reads it first." : "The team reads this next time.") : "";
      if (reason === null || (remark && !reason.trim())) return;
      try { const out = await api("api/verdict", { id: v.dataset.id, verdict, reason });
        say(out.pbi ? `Approved: ${out.pbi} is on the board` : out.started ? "The next design has started" : out.queued ? "The next design waits in the queue" : "Saved");
      } catch (err) { say(err.message); }
      return load();
    }
  });
  document.addEventListener("change", e => {
    if (e.target.id === "walk") location.hash = `${e.target.dataset.to}?walk=${encodeURIComponent(e.target.value)}`;
  });
  window.addEventListener("hashchange", () => { route(); if (S && !S.error) render(); });
  route();
  load();
  setInterval(() => { if (!document.hidden && !document.querySelector("dialog[open]")) load(false); }, 5000);
})();

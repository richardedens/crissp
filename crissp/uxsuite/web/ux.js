/* The UX suite's page: reads /ux/api/state (crissp/uxsuite/api.py) and shows the walks, the team's rounds and advice,
   its designs, the product owner's verdicts, the team and the rules; writes verdicts, requests, personas and rules back. The look, the theme and the top bar
   are the framework's own (crissp/look). No dependencies, nothing loaded from outside. */
(() => {
  const $ = (sel, el = document) => el.querySelector(sel);
  const { esc, badge } = window.Look;
  let S = null, tab = "overview", query = new URLSearchParams();
  const TABS = [["overview", "Overview"], ["rounds", "Rounds & advice"], ["proposals", "Designs"], ["team", "Team"], ["rules", "Rules"]];

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
  let notice = "", noticeAt = 0;  // what an action just said stays in the top bar a while, over the poll's redraws
  const tell = text => { notice = text; noticeAt = Date.now(); say(text); };

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
    return `<div class="shots">${w.shots.map(s => s.url ? `<figure><button class="shot" data-view="shot" data-walk="${esc(w.id)}" data-device="${esc(s.device)}" data-n="${s.n}" title="Enlarge"><img src="${esc(s.url)}" alt="${esc(s.title)}" loading="lazy"></button><figcaption>${esc(s.device)} ${s.n} · ${esc(s.title)}</figcaption></figure>`
      : `<p class="small">${badge("failed", s.device)} ${esc(s.error)}</p>`).join("") || '<p class="small muted">No screenshots yet.</p>'}</div>`;
  }

  /* The debate (F-80): every persona's first look on their own device, then their answers to each other, round by
     round; it fills in live while the round runs (debate.json). A shot a persona points at opens enlarged. */
  const shotRef = (w, ref) => {
    const [device, n] = String(ref || "").split(" ");
    const s = (w.shots || []).find(x => x.device === device && String(x.n) === n && x.url);
    return s ? `<button class="link small" data-view="shot" data-walk="${esc(w.id)}" data-device="${esc(device)}" data-n="${esc(n)}">${esc(ref)} ⤢</button>` : (ref ? `<span class="small muted">${esc(ref)}</span>` : "");
  };
  const persona = key => S.personas.find(p => p.key === key) || { key, name: key, role: "", device: "" };
  const who = key => { const p = persona(key); return `<span class="who"><span class="avatar" aria-hidden="true">${esc((p.name || "?")[0])}</span><b>${esc(p.name)}</b></span>`; };

  function debateOf(w, r) {
    const d = r.debate;
    if (!d) return r.status?.phase === "done" ? "" : '<p class="small muted">The debate appears here as the team writes it.</p>';
    const reviews = (d.reviews || []).map(v => `<article class="look">
        <header><span class="who-role">${who(v.persona)} <span class="small muted">${esc(persona(v.persona).role)}</span></span>${typeof v.score === "number" ? `<span class="score big" title="Their score, 1 to 10">${v.score}</span>` : ""}</header>
        ${(v.good || []).length ? `<div class="label">Good</div><ul class="small">${v.good.map(g => `<li>${esc(g)}</li>`).join("")}</ul>` : ""}
        ${(v.problems || []).length ? `<div class="label">Problems</div>${v.problems.map(x => `<div class="problem">${badge(x.severity === "blocker" ? "failed" : x.severity === "major" ? "must" : "could", x.severity || "minor")} <b>${esc(x.title)}</b> ${shotRef(w, x.shot)}<p class="small">${esc(x.detail || "")}</p></div>`).join("")}` : ""}
        ${(v.ideas || []).length ? `<div class="label">Ideas</div><ul class="small">${v.ideas.map(i => `<li>${esc(typeof i === "string" ? i : i.title || JSON.stringify(i))}</li>`).join("")}</ul>` : ""}
      </article>`).join("");
    const rounds = {};
    (d.rebuttals || []).forEach(a => { (rounds[a.round || 1] = rounds[a.round || 1] || []).push(a); });
    const answers = Object.keys(rounds).sort((a, b) => a - b).map(n => `<div class="label">Answers, round ${esc(n)}</div>` + rounds[n].map(a => `<div class="answer">
        <div class="row">${who(a.persona)}</div>
        ${(a.disagree || []).map(x => `<p class="small"><span class="tag no">disagrees</span> with ${x.with ? `<b>${esc(persona(x.with).name)}</b>` : "the others"} on “${esc(x.point)}”: ${esc(x.why || "")}</p>`).join("")}
        ${(a.agree || []).map(x => `<p class="small"><span class="tag yes">agrees</span> ${esc(typeof x === "string" ? x : `${x.with ? persona(x.with).name + ": " : ""}${x.point || ""}`)}</p>`).join("")}
        ${(a.changed_my_mind || []).map(x => `<p class="small"><span class="tag turn">changed their mind</span> ${esc(typeof x === "string" ? x : JSON.stringify(x))}</p>`).join("")}
      </div>`).join("")).join("");
    return `<details class="debate" open><summary>The debate: ${(d.reviews || []).length} first look(s), ${(d.rebuttals || []).length} answer(s)</summary>
      <div class="looks">${reviews}</div>${answers ? `<div class="answers">${answers}</div>` : ""}</details>`;
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
        if (!res) return `<div class="card walk">Round ${r.version} ${phase(r.status)} <span class="small muted">${esc(r.status.note || "")}</span>${debateOf(w, r)}</div>`;
        return `<article class="card walk"><header><h3>Round ${r.version}</h3>${phase(r.status)}<span class="small muted">${esc(r.request?.at || "")}</span></header>
          <div class="scores"><span class="score">average <b>${avg(res.scores)}</b></span>${Object.entries(res.scores || {}).map(([k, v]) => `<span class="score">${esc(name(k))} <b>${esc(v)}</b></span>`).join("")}</div>
          <p>${esc(res.summary)}</p>
          ${debateOf(w, r)}
          ${(res.consensus || []).length ? `<details><summary>Everyone agreed (${res.consensus.length})</summary><ul>${res.consensus.map(c => `<li>${esc(c)}</li>`).join("")}</ul></details>` : ""}
          ${(res.disputes || []).length ? `<details><summary>Where they disagree (${res.disputes.length})</summary>${res.disputes.map(d => `<p><b>${esc(d.topic)}</b></p><ul>${(d.positions || []).map(x => `<li>${esc(name(x.persona))}: ${esc(x.position)}</li>`).join("")}</ul>`).join("")}</details>` : ""}
          <div class="label">Advice</div>${(res.advice || []).map((a, i) => `<div class="advice ${esc(a.priority)}">
            <div class="row">${badge(a.priority, a.priority)}${a.effort ? badge("ver", a.effort) : ""}<b>${esc(a.title)}</b></div>
            <p>${esc(a.detail)}</p><p class="small">Asked by ${(a.personas || []).map(name).map(esc).join(", ") || "the team"}${a.shot ? ` · ${shotRef(w, a.shot)}` : ""}${a.rule ? ` · rule <code>${esc(a.rule)}</code>` : ""}</p>
            ${verdictButtons(`${w.id}/r${r.version}/a${i}`, [["agree", "Agree"], ["disagree", "Disagree"], ["later", "Later"]])}</div>`).join("") || '<p class="muted small">No advice.</p>'}</article>`;
      }).join("") || '<div class="card">No round yet. <button class="ghost" data-request="round" data-walk="' + esc(w.id) + '">Ask for a round</button></div>');
  }

  /* The moderator's word on a design (check.json, F-11): its verdict, what it found and whether the designer fixed it,
     and what still stands. A finished design without one says so instead of looking complete. */
  function moderatorCheck(p) {
    const c = p.check;
    if (!c) return p.status?.phase === "done" ? '<p class="small muted">The moderator wrote no check of this design.</p>' : "";
    const tone = c.verdict === "ready" ? "passed" : c.verdict === "not-ready" ? "failed" : "missing";
    return `<div class="label">The moderator's check${c.moderator ? " (" + esc(c.moderator) + ")" : ""} ${badge(tone, c.verdict || "?")}</div>
      ${c.summary ? `<p>${esc(c.summary)}</p>` : ""}
      ${(c.found || []).length ? `<ul>${c.found.map(x => `<li>${badge(x.severity || "should", x.severity || "should")} ${esc(x.what)} <span class="small muted">${x.fixed ? "fixed" : "still open"}</span></li>`).join("")}</ul>` : ""}
      ${(c.remaining || []).length ? `<div class="label">Still stands</div><ul>${c.remaining.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}`;
  }

  function proposals() {
    const w = walkOf(query.get("walk"));
    if (!w) return '<div class="card">No walks yet.</div>';
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
            ${(res.open_questions || []).length ? `<div class="label">Open questions</div><ul>${res.open_questions.map(q => `<li>${esc(q)}</li>`).join("")}</ul>` : ""}
            ${moderatorCheck(p)}` : `<p class="small muted">${esc(p.status.note || "")}</p>`}
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
          <div class="frame ${d === "phone" ? "tall" : ""}">${before ? `<button class="shot" data-view="design" data-walk="${esc(w.id)}" data-key="${esc(p.key)}" data-device="${esc(d)}" data-mode="before" title="Enlarge"><img src="${esc(before.url)}" alt="Before: ${esc(before.title || "")}"></button>` : '<p class="small muted">No screenshot of this walk yet: crissp ux --shoot ' + esc(w.id) + '</p>'}</div></figure>
        <figure class="pane"><figcaption><b>After</b> · design ${p.version}</figcaption>
          <div class="frame fit"><iframe sandbox="allow-scripts" src="${esc(p.mockup)}" title="After: design ${p.version}" tabindex="-1"></iframe>
            <button class="cover" data-view="design" data-walk="${esc(w.id)}" data-key="${esc(p.key)}" data-device="${esc(d || "")}" data-mode="after" aria-label="Enlarge the design"></button></div></figure>
      </div>
      <div class="toolbar enlarge"><button class="primary" data-view="design" data-walk="${esc(w.id)}" data-key="${esc(p.key)}" data-device="${esc(d || "")}" data-mode="both">Enlarge: before and after ⤢</button>
        <button class="ghost" data-view="design" data-walk="${esc(w.id)}" data-key="${esc(p.key)}" data-device="${esc(d || "")}" data-mode="after">The design alone</button>
        <a class="small" href="${esc(p.mockup)}" target="_blank" rel="noopener">open in a new tab ↗</a>
      </div>`;
  }

  /* The viewer (F-80): a screenshot or a design enlarged over the whole window, before, after or side by side, at
     fit, 100%, 150% or 200% (keys 1 2 3 for the view, + − 0 for the zoom, Esc closes). The design stays in its sandbox. */
  let view = null;
  function openViewer(v) {
    view = { zoom: "fit", ...v };
    $("#viewer-title").textContent = v.title;
    if (!$("#viewer").open) $("#viewer").showModal();  // first open, so the panes have a width to fit the design to
    drawViewer();
  }
  function drawViewer() {
    const v = view, modes = v.after && v.before ? [["before", "Before"], ["both", "Side by side"], ["after", "After"]] : [];
    $("#viewer-modes").innerHTML = modes.map(([m, l], i) => `<button class="ghost small" data-mode-to="${m}" aria-pressed="${m === v.mode}" title="key ${i + 1}">${l}</button>`).join("");
    document.querySelectorAll("#viewer [data-zoom]").forEach(b => b.setAttribute("aria-pressed", String(b.dataset.zoom === String(v.zoom))));
    const pane = (what, label) => what === "before"
      ? `<figure class="pane"><figcaption>${label || ""}</figcaption><div class="scroll"><img src="${esc(v.before.url)}" alt="${esc(v.before.title || "")}" data-z></div></figure>`
      : `<figure class="pane"><figcaption>${label || ""}</figcaption><div class="scroll"><div class="mock" data-z><iframe sandbox="allow-scripts" src="${esc(v.after)}" title="The design"></iframe></div></div></figure>`;
    const panes = v.mode === "both" ? pane("before", "<b>Before</b> · now") + pane("after", "<b>After</b> · the design") : pane(v.mode === "after" ? "after" : "before");
    $("#viewer-body").className = `viewer-body ${v.mode === "both" ? "two" : "one"}`;
    $("#viewer-body").innerHTML = panes;
    $("#viewer-body").querySelectorAll("img[data-z]").forEach(img => img.complete ? zoomViewer() : img.addEventListener("load", zoomViewer));
    zoomViewer();
  }
  function zoomViewer() {
    if (!view) return;
    document.querySelectorAll("#viewer-body .pane").forEach(pane => {
      const box = pane.querySelector(".scroll"), img = pane.querySelector("img"), mock = pane.querySelector(".mock");
      if (img) {
        img.style.width = view.zoom === "fit" ? "" : `${img.naturalWidth * view.zoom}px`;
        img.classList.toggle("fit", view.zoom === "fit");
      }
      if (mock) {  // the design is drawn 1440 wide; fit scales it to the pane
        const z = view.zoom === "fit" ? Math.min(1, (box.clientWidth - 2) / 1440) : Number(view.zoom);
        mock.style.width = `${1440 * z}px`; mock.style.height = `${900 * z}px`;
        mock.firstElementChild.style.transform = `scale(${z})`;
      }
    });
  }
  window.addEventListener("resize", zoomViewer);
  document.addEventListener("keydown", e => {
    if (!$("#viewer").open || e.target.closest("input, textarea, select")) return;
    const modes = [...document.querySelectorAll("#viewer [data-mode-to]")].map(b => b.dataset.modeTo);
    const zooms = ["fit", 1, 1.5, 2], at = zooms.findIndex(z => String(z) === String(view.zoom));
    if (/^[1-3]$/.test(e.key) && modes[e.key - 1]) { view.mode = modes[e.key - 1]; drawViewer(); }
    else if (e.key === "+" || e.key === "=") { view.zoom = zooms[Math.min(zooms.length - 1, at + 1)]; drawViewer(); }
    else if (e.key === "-") { view.zoom = zooms[Math.max(0, at - 1)]; drawViewer(); }
    else if (e.key === "0") { view.zoom = "fit"; drawViewer(); }
  });
  $("#viewer").addEventListener("close", () => { view = null; $("#viewer-body").innerHTML = ""; });

  /* scale every mockup (drawn 1440 wide) to the width of its pane */
  function fit() {
    document.querySelectorAll(".frame.fit").forEach(f => {
      const i = f.querySelector("iframe");
      if (i) i.style.transform = `scale(${f.clientWidth / 1440})`;
    });
  }
  window.addEventListener("resize", fit);

  /* The Team and Rules tabs (E7-F1-01, E7-F2-01): every persona and rule is a file of the project's own
     (crissp/uxsuite/personas/, rules/); these forms add, change, switch off and remove them. */
  const editing = () => query.get("edit");
  const field = (label, name, value, extra = "") => `<label class="field"><span>${label}</span><input type="text" name="${name}" value="${esc(value ?? "")}" ${extra}></label>`;
  const area = (label, name, value, hint = "") => `<label class="field"><span>${label}${hint ? `<span class="hint muted small">${hint}</span>` : ""}</span><textarea name="${name}">${esc(value ?? "")}</textarea></label>`;
  const choose = (label, name, value, options) => `<label class="field"><span>${label}</span><select name="${name}">${options.map(o => `<option ${o === value ? "selected" : ""}>${o}</option>`).join("")}</select></label>`;
  const tick = (label, name, value) => `<label class="chk"><input type="checkbox" name="${name}" ${value ? "checked" : ""}> ${label}</label>`;

  function personaForm(p) {
    const fresh = !p;
    p = p || { key: "", name: "", role: "", device: "desktop", moderator: false, on: true, brief: "", jobs: [] };
    return `<form class="card edit" data-form="persona" data-key="${esc(p.key)}"><h3>${fresh ? "A new persona" : "Edit " + esc(p.name)}</h3>
      ${field("Name", "name", p.name, "required")}${field("Who they are (one line)", "role", p.role, "required")}
      ${choose("Device", "device", p.device, ["desktop", "mobile", "both"])}
      ${area("Brief", "brief", p.brief, "how they look at a screen, in their own voice")}
      ${area("Jobs", "jobs", p.jobs.join("\n"), "one per line: what they come to do")}
      <div class="row">${tick("Takes part", "on", p.on)}${tick("Moderates", "moderator", p.moderator)}</div>
      <div class="row"><button class="primary">Save</button><a href="#team">Cancel</a></div></form>`;
  }

  function team() {
    const where = S.personas_from === "files" ? "<code>crissp/uxsuite/personas/</code>, one file each"
      : "<code>crissp/uxsuite/team.json</code> for now: the first change here moves them to <code>crissp/uxsuite/personas/</code>, one file each";
    const e = editing();
    return `<div class="toolbar"><button class="primary" data-goto="team?edit=new">Add a persona</button><span class="small muted">The team lives in ${where}.</span></div>
      ${e === "new" ? personaForm(null) : ""}
      <div class="walks-list">${S.personas.map(p => e === p.key ? personaForm(p) : `<article class="card persona ${p.on ? "" : "off"}"><div class="row"><h3>${esc(p.name)}</h3>${p.moderator ? badge("area", "moderator") : ""}${badge("ver", p.device)}${p.on ? "" : badge("missing", "off")}</div>
      <div class="small muted">${esc(p.role)}</div><p class="small">${esc(p.brief)}</p>
      ${p.jobs.length ? `<div class="label">Jobs</div><ul class="small">${p.jobs.map(j => `<li>${esc(j)}</li>`).join("")}</ul>` : ""}
      <div class="row"><a href="#team?edit=${encodeURIComponent(p.key)}">Edit</a>
        <button class="ghost small" data-toggle="persona" data-id="${esc(p.key)}">${p.on ? "Switch off" : "Switch on"}</button>
        <button class="ghost small" data-remove="persona" data-id="${esc(p.key)}">Remove</button></div></article>`).join("")}</div>`;
  }

  function ruleForm(r) {
    const fresh = !r;
    r = r || { id: "", title: "", severity: "should", on: true, text: "" };
    return `<form class="card edit" data-form="rule" data-key="${esc(r.id)}"><h3>${fresh ? "A new rule" : "Edit " + esc(r.title)}</h3>
      ${field("Title", "title", r.title, "required")}${choose("Weight", "severity", r.severity, ["must", "should", "could"])}
      ${area("What it asks", "text", r.text, "in plain words, as the team should judge it")}
      <div class="row">${tick("Holds", "on", r.on)}</div>
      <div class="row"><button class="primary">Save</button><a href="#rules">Cancel</a></div></form>`;
  }

  function rulesTab() {
    const e = editing();
    return `<div class="toolbar"><button class="primary" data-goto="rules?edit=new">Add a rule</button><span class="small muted">Every round judges by the rules that hold, and every design follows them. They live in <code>crissp/uxsuite/rules/</code>, one file each${S.rules_from === "PRINCIPLES.md" ? " (the first change moves them out of PRINCIPLES.md)" : ""}.</span></div>
      ${e === "new" ? ruleForm(null) : ""}
      ${S.rules.map(r => e === r.id ? ruleForm(r) : `<article class="card rule ${r.on ? "" : "off"}"><div class="row">${badge(r.severity, r.severity)}<h3>${esc(r.title)}</h3><code class="small muted">${esc(r.id)}</code>${r.on ? "" : badge("missing", "off")}</div>
        <p class="small">${esc(r.text)}</p>
        <div class="row"><a href="#rules?edit=${encodeURIComponent(r.id)}">Edit</a>
          <button class="ghost small" data-toggle="rule" data-id="${esc(r.id)}">${r.on ? "Switch off" : "Switch on"}</button>
          <button class="ghost small" data-remove="rule" data-id="${esc(r.id)}">Remove</button></div></article>`).join("") || '<div class="card">No rules yet: add the first one.</div>'}`;
  }

  function render() {
    $("#tabs").innerHTML = TABS.map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${k === tab}">${l}</button>`).join("");
    const view = { overview, rounds, proposals, team, rules: rulesTab }[tab] || overview;
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
    say(notice && Date.now() - noticeAt < 10000 ? notice : S.team.text);
    render();
  }

  document.addEventListener("click", async e => {
    const dv = e.target.closest("[data-device]:not([data-view])");
    if (dv) { query.set("device", dv.dataset.device); render(); return; }  // Before on the laptop or the phone
    const vw = e.target.closest("[data-view]");
    if (vw) {
      const w = walkOf(vw.dataset.walk);
      if (vw.dataset.view === "shot") {
        const s = w.shots.find(x => x.device === vw.dataset.device && String(x.n) === vw.dataset.n);
        openViewer({ title: `${w.title} · ${s.device} ${s.n} · ${s.title}`, before: s, after: null, mode: "before" });
      } else {
        const p = w.proposals.find(x => x.key === vw.dataset.key);
        const s = (w.shots || []).find(x => x.device === vw.dataset.device && x.url) || null;
        openViewer({ title: `${w.title} · design ${p.version}${p.result?.title ? ": " + p.result.title : ""}`, before: s, after: p.mockup,
                     mode: s ? vw.dataset.mode : "after" });
      }
      return;
    }
    const mt = e.target.closest("[data-mode-to]");
    if (mt) { view.mode = mt.dataset.modeTo; drawViewer(); return; }
    const zm = e.target.closest("[data-zoom]");
    if (zm) { view.zoom = zm.dataset.zoom === "fit" ? "fit" : Number(zm.dataset.zoom); drawViewer(); return; }
    const go = e.target.closest("[data-goto]");
    if (go) { location.hash = go.dataset.goto; return; }
    const t = e.target.closest("[data-tab]");
    if (t) { location.hash = t.dataset.tab; return; }
    const r = e.target.closest("[data-request]");
    if (r) {
      const focus = r.dataset.request === "proposal" ? await ask("What should the design focus on?", "Leave it empty for the must-advice first.") : "";
      if (focus === null) return;
      try { const out = await api("api/request", { kind: r.dataset.request, walk: r.dataset.walk, focus });
        tell(out.started ? `Started: ${out.started.kind} ${out.started.version} of ${out.started.walk}` : `Queued as number ${out.queued}: ${out.why}`);
      } catch (err) { tell(err.message); }
      return load();
    }
    const tg = e.target.closest("[data-toggle]"), rm = e.target.closest("[data-remove]");
    if (tg || rm) {
      const kind = (tg || rm).dataset.toggle || (tg || rm).dataset.remove, id = (tg || rm).dataset.id;
      if (rm && rm.dataset.sure !== "yes") { rm.dataset.sure = "yes"; rm.textContent = "Remove: sure?"; return; }  // a second click removes
      const held = kind === "persona" ? S.personas.find(p => p.key === id) : S.rules.find(r => r.id === id);
      try {
        await api(`api/${kind}`, rm ? { remove: id } : { [kind]: { ...held, [kind === "persona" ? "key" : "id"]: id, on: !held.on } });
        tell(rm ? `Removed ${id}` : `${id} is ${held.on ? "off" : "on"} now`);
      } catch (err) { tell(err.message); }
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
        tell(out.pbi ? `Approved: ${out.pbi} is on the board` : out.started ? "The next design has started" : out.queued ? "The next design waits in the queue" : "Saved");
      } catch (err) { tell(err.message); }
      return load();
    }
  });
  document.addEventListener("submit", async e => {
    const f = e.target.closest("form[data-form]");
    if (!f) return;
    e.preventDefault();
    const kind = f.dataset.form, data = Object.fromEntries(new FormData(f));
    const body = { ...data, on: !!data.on, ...(kind === "persona" ? { key: f.dataset.key || undefined, moderator: !!data.moderator } : { id: f.dataset.key || undefined }) };
    try { await api(`api/${kind}`, { [kind]: body }); tell(`Saved ${kind === "persona" ? data.name : data.title}`); location.hash = kind === "persona" ? "team" : "rules"; }
    catch (err) { tell(err.message); }
    return load();
  });
  document.addEventListener("change", e => {
    if (e.target.id === "walk") location.hash = `${e.target.dataset.to}?walk=${encodeURIComponent(e.target.value)}`;
  });
  window.addEventListener("hashchange", () => { route(); if (S && !S.error) render(); });
  route();
  load();
  setInterval(() => { if (!document.hidden && !document.querySelector("dialog[open], form.edit")) load(false); }, 5000);  // never under a form being filled in
})();

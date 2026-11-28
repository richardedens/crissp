/* The UX suite's page: reads /ux/api/state (crissp/uxsuite/api.py) and shows the walks, the team's rounds and advice,
   its designs, the product owner's verdicts, the team and the rules; writes verdicts, requests, personas and rules back. The look, the theme and the top bar
   are the framework's own (crissp/look). No dependencies, nothing loaded from outside. */
(() => {
  const $ = (sel, el = document) => el.querySelector(sel);
  const { esc, badge } = window.Look;
  let S = null, tab = "overview", query = new URLSearchParams();
  const TABS = [["overview", "Overview"], ["review", "Review"], ["map", "Map"], ["jobs", "Jobs"], ["rounds", "Rounds & advice"], ["proposals", "Designs"], ["team", "Team"], ["rules", "Rules"]];

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

  /* The map (E7-F3-01): every screen the crawl, the project's own E2E tests and the walks found, by area, with its gaps:
     a screen no link reaches, one the crawl could not open, one no walk looks at. A shot opens enlarged. */
  const REACH = ["no link reaches it", "the crawl could not open it"];
  const unreached = s => s.gaps.some(g => REACH.some(r => g.startsWith(r)));
  function mapTab() {
    const m = S.map;
    if (!m) return `<div class="card"><h3>The product is not mapped yet</h3><p>Run <code>crissp ux --map</code> while the product runs on <code>${esc(S.url)}</code>. It opens home and every walk's pages on the team's devices, follows the product's own links (read-only: it never signs out or deletes), adds the screenshots your E2E tests list in <code>crissp/uxsuite/results/test-shots/screens.json</code>, and the walks' own.</p></div>`;
    const show = query.get("show") || "all", list = m.screens.filter(s => show === "gaps" ? unreached(s) : show === "unwalked" ? !s.walks.length : true);
    const unwalked = m.screens.filter(s => !s.walks.length).length;
    const areas = [...new Set(list.map(s => s.area))];
    const seg = [["all", `All ${m.screens.length}`], ["gaps", `Not reached ${m.gaps}`], ["unwalked", `No walk ${unwalked}`]];
    return `<div class="grid kpis" style="margin-bottom:14px">
        <div class="card kpi"><div class="l">Screens</div><div class="v">${m.screens.length}</div><div class="s">in ${Object.keys(m.areas).length} area(s)</div></div>
        <div class="card kpi"><div class="l">Not reached</div><div class="v">${m.gaps}</div><div class="s">${m.crawled ? "no link gets there, or the crawl could not open it" : "no crawl yet: crissp ux --map"}</div></div>
        <div class="card kpi"><div class="l">No walk</div><div class="v">${unwalked}</div><div class="s">the team never looks at these</div></div>
        <div class="card kpi"><div class="l">Mapped</div><div class="v small">${esc((m.at || "").replace("T", " ").slice(0, 16))}</div><div class="s">${esc(m.url || "")}</div></div></div>
      <div class="toolbar"><span class="seg" role="group" aria-label="Show">${seg.map(([k, l]) => `<button class="ghost small" data-goto="map?show=${k}" aria-pressed="${k === show}">${l}</button>`).join("")}</span>
        <span class="small muted">Map again: <code>crissp ux --map</code></span></div>
      ${(m.skipped || []).length ? `<details class="card"><summary>${m.skipped.length} test screenshot(s) skipped</summary><ul class="small">${m.skipped.map(x => `<li>${esc(x)}</li>`).join("")}</ul></details>` : ""}
      <div class="screens">${areas.flatMap(a => list.filter(s => s.area === a)).map(s => {
          const first = s.shots.find(x => x.device === "laptop") || s.shots[0];
          return `<article class="card screen ${unreached(s) ? "gap" : ""}">
            ${first ? `<button class="shot thumb" data-view="map" data-key="${esc(s.key)}" data-i="${s.shots.indexOf(first)}" title="Enlarge"><img src="${esc(first.url)}" alt="${esc(s.title)}" loading="lazy"></button>` : '<div class="thumb none small muted">no picture</div>'}
            <div class="row"><b>${esc(s.title)}</b>${badge("area", s.area)}</div><code class="small muted">${esc(s.key)}</code>
            <div class="row">${s.found_by.map(f => badge("ver", f === "test" ? "E2E test" : f)).join("")}${s.gaps.map(g => badge(REACH.some(r => g.startsWith(r)) ? "failed" : "missing", g)).join("")}</div>
            ${s.linked_from.length ? `<p class="small muted">Linked from ${s.linked_from.map(esc).join(", ")}</p>` : ""}
            ${s.walks.length ? `<p class="small">Walks: ${s.walks.map(w => `<a href="#rounds?walk=${encodeURIComponent(w)}">${esc(w)}</a>`).join(", ")}</p>` : ""}
            ${s.tests.length ? `<p class="small muted">Tests: ${s.tests.map(esc).join(", ")}</p>` : ""}
            ${s.shots.length > 1 ? `<div class="row">${s.shots.map((x, i) => `<button class="link small" data-view="map" data-key="${esc(s.key)}" data-i="${i}">${esc(x.device)} · ${esc(x.source === "test" ? "E2E test" : x.source)} ⤢</button>`).join("")}</div>` : ""}
          </article>`;
        }).join("") || '<div class="card">Nothing to show here.</div>'}</div>`;
  }

  /* Discovery (E7-F3-02): every persona tries their jobs on the mapped screens: done, hard or impossible, and where they
     gave up. What cannot be done becomes a need; an approved need is a design request (a walk with a brief) whose first
     design starts at once. */
  const JOB = { done: "passed", hard: "missing", impossible: "failed" };
  const screenChip = k => `<a class="chip" href="#map" title="On the map">${esc(k)}</a>`;
  function jobsTab() {
    const list = [...(S.discovery || [])].reverse();
    const top = `<div class="toolbar"><button class="primary" data-request="discovery" data-walk="product" ${S.map ? "" : "disabled"}>Ask for a discovery round</button>
      <span class="small muted">${S.map ? `Every persona tries their own jobs on the ${S.map.screens.length} mapped screens. A run costs tokens.` : "Map the product first: <code>crissp ux --map</code>."}</span></div>`;
    return top + (list.map((d, i) => {
      const res = d.result;
      if (!res) return `<div class="card walk">Discovery ${d.version} ${phase(d.status)} <span class="small muted">${esc(d.status.note || "")}</span></div>`;
      const count = v => (res.jobs || []).filter(j => j.verdict === v).length;
      const people = [...new Set((res.jobs || []).map(j => j.persona))];
      const body = `<p>${esc(res.summary)}</p>
        <div class="row">${["done", "hard", "impossible"].map(v => badge(JOB[v], `${count(v)} ${v}`)).join("")}</div>
        <div class="label">The job map</div>
        ${people.map(k => `<div class="jobs-of">${who(k)}<span class="small muted">${esc(persona(k).role)}</span>
          <table class="jobs"><tbody>${res.jobs.filter(j => j.persona === k).map(j => `<tr>
            <td>${badge(JOB[j.verdict] || "missing", j.verdict)}</td><td><b>${esc(j.job)}</b>${j.inferred ? ' <span class="small muted">(inferred)</span>' : ""}${j.why ? `<div class="small muted">${esc(j.why)}</div>` : ""}</td>
            <td class="small">${(j.screens || []).map(screenChip).join(" → ")}${j.gave_up_at ? ` <span class="gave-up">gave up at ${screenChip(j.gave_up_at)}</span>` : ""}</td></tr>`).join("")}</tbody></table></div>`).join("")}
        <div class="label">What is missing: the needs</div>
        ${(res.needs || []).map((n, ni) => {
          const id = d.needs[ni].id, held = d.needs[ni].verdict, walk = S.walks.find(w => w.need === id);
          return `<div class="advice ${held?.verdict === "approve" ? "could" : "must"}"><div class="row"><b>${esc(n.title)}</b>${held ? badge(held.verdict === "approve" ? "passed" : "failed", held.verdict === "approve" ? "design requested" : "rejected") : ""}</div>
            <p>${esc(n.detail)}</p>
            <p class="small">For ${(n.personas || []).map(name).map(esc).join(", ") || "the team"}${(n.jobs || []).length ? ` · ${n.jobs.map(esc).join("; ")}` : ""}${(n.screens || []).length ? ` · fits at ${n.screens.map(screenChip).join(" ")}` : ""}</p>
            ${walk ? `<p class="small"><a href="#proposals?walk=${encodeURIComponent(walk.id)}">Its designs ${walk.proposals.length ? `(${walk.proposals.length})` : "(starting)"} →</a></p>` : ""}
            ${verdictButtons(id, [["approve", "Approve: ask for a design"], ["reject", "Reject"]])}</div>`;
        }).join("") || '<p class="small muted">Nothing is missing: every job can be done.</p>'}`;
      return i === 0 ? `<article class="card walk"><header><h3>Discovery ${d.version}</h3>${phase(d.status)}<span class="small muted">${esc((d.request?.at || "").replace("T", " ").slice(0, 16))}</span></header>${body}</article>`
        : `<details class="card walk"><summary>Discovery ${d.version} · ${esc((d.request?.at || "").replace("T", " ").slice(0, 16))}</summary>${body}</details>`;
    }).join("") || '<div class="card">No discovery round yet.</div>');
  }

  const walkPicker = (w, to) => `<div class="toolbar"><select id="walk" data-to="${to}" aria-label="Walk">${S.walks.map(x => `<option value="${esc(x.id)}" ${x === w ? "selected" : ""}>${esc(x.title)}</option>`).join("")}</select></div>`;

  function shotsOf(w) {
    return `<div class="shots">${w.shots.map(s => s.url ? `<figure><button class="shot" data-view="shot" data-walk="${esc(w.id)}" data-device="${esc(s.device)}" data-n="${s.n}" title="Enlarge"><img src="${esc(s.url)}" alt="${esc(s.title)}" loading="lazy"></button><figcaption>${esc(s.device)} ${s.n} · ${esc(s.title)}${(s.measured || []).length ? " " + badge("must", `${s.measured.length} measured`) : ""}</figcaption></figure>`
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
          ${p.mockup && !rebuilt(w, p) ? compare(w, p) : ""}
          ${p.verdict?.verdict === "approve" ? builtOf(w, p) : ""}
          ${res ? `<div class="decide">${verdictButtons(p.key, [["approve", "Approve"], ["approve-remark", "Approve with a remark…"], ["redo", "Again, with…"], ["reject", "Reject"]])}<span class="small muted">Approve makes it a backlog item (a remark goes with it); Again asks the designer for the next version.</span></div>` : ""}
          ${p.request?.focus ? `<p class="small muted">Focus: ${esc(p.request.focus)}</p>` : ""}
          ${res ? `<p>${esc(res.summary)}</p>${(res.changes || []).length ? `<ol>${res.changes.map(c => `<li>${badge(c.priority || "should", c.priority || "should")} ${esc(c.what)} <span class="small muted">${esc(c.why)}</span></li>`).join("")}</ol>` : ""}
            ${(res.open_questions || []).length ? `<div class="label">Open questions</div><ul>${res.open_questions.map(q => `<li>${esc(q)}</li>`).join("")}</ul>` : ""}
            ${moderatorCheck(p)}` : `<p class="small muted">${esc(p.status.note || "")}</p>`}
</article>`;
      }).join("") || '<div class="card">No design yet.</div>');
  }

  /* What was built (E7-F5-01): once the walk is shot again after the approval, its new screens sit next to the design;
     accept moves the PBI to review, not good sends it back to doing with the reason as a finding. */
  const rebuilt = (w, p) => p.verdict?.verdict === "approve" && !!w.shot_at && w.shot_at > p.verdict.at;
  function builtOf(w, p) {
    const b = p.built, fresh = rebuilt(w, p);
    const said = b ? badge(b.verdict === "accept" ? "passed" : "failed", b.verdict === "accept" ? "accepted" : "sent back") + (b.reason ? ` <span class="small muted">${esc(b.reason)}</span>` : "") : "";
    if (!fresh) return `<div class="built card"><div class="label">What was built ${said}</div><p class="small muted">Once ${p.pbi ? esc(p.pbi) : "it"} is built, shoot the walk again (<code>crissp ux --shoot ${esc(w.id)}</code>): the new screens show here next to this design, to accept or send back.</p></div>`;
    return `<div class="built card"><div class="label">What was built · shot ${esc(w.shot_at.replace("T", " ").slice(0, 16))} ${said}</div>
      ${compare(w, p, "Built")}
      <div class="decide">${verdictButtons(p.key + "/built", [["accept", "Accept"], ["send-back", "Not good…"]])}<span class="small muted">Accept moves ${p.pbi ? esc(p.pbi) : "the backlog item"} to review; Not good sends it back with your reason.</span></div></div>`;
  }

  /* Before | After: what people see today (the walk's own screenshot, laptop or phone) next to the design, the same
     size, so a verdict is a look and a click. The mockup is drawn at the laptop size and scaled to fit (fit()). */
  function compare(w, p, now = "Before") {
    const shot = d => (w.shots || []).find(s => s.device === d && s.url);
    const devices = ["laptop", "phone"].filter(shot);
    const d = devices.includes(query.get("device")) ? query.get("device") : devices[0];
    const before = d ? shot(d) : null;
    const pick = devices.length > 1 ? `<span class="seg">${devices.map(x => `<button class="ghost small" data-device="${x}" aria-pressed="${x === d}">${x === "laptop" ? "Laptop" : "Phone"}</button>`).join("")}</span>` : "";
    return `<div class="compare">
        <figure class="pane"><figcaption><b>${now}</b> · what people see now ${pick}</figcaption>
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
      ? `<figure class="pane"><figcaption>${label || ""}</figcaption><div class="scroll"><div class="marked">
          <img src="${esc(v.before.url)}" alt="${esc(v.before.title || "")}" data-z>${marks(v.before)}</div></div>${markList(v.before)}</figure>`
      : `<figure class="pane"><figcaption>${label || ""}</figcaption><div class="scroll"><div class="mock" data-z><iframe sandbox="allow-scripts" src="${esc(v.after)}" title="The design"></iframe></div></div></figure>`;
    const panes = v.mode === "both" ? pane("before", "<b>Before</b> · now") + pane("after", "<b>After</b> · the design") : pane(v.mode === "after" ? "after" : "before");
    $("#viewer-body").className = `viewer-body ${v.mode === "both" ? "two" : "one"}`;
    $("#viewer-body").innerHTML = panes;
    $("#viewer-body").querySelectorAll("img[data-z]").forEach(img => img.complete ? zoomViewer() : img.addEventListener("load", zoomViewer));
    zoomViewer();
  }
  /* What the browser measured on a shot (E7-F2-02): a box on the picture where it is, and the list under it. The
     screenshot is the viewport at its CSS size, so a place is a share of the picture's width and height. */
  const SIZE = { laptop: [1440, 900], phone: [390, 844] };
  function marks(s) {
    const [W, H] = SIZE[s.device] || [1440, 900];
    return (s.measured || []).filter(f => f.where).map((f, i) => `<span class="mark" title="${esc(measureName(f.check))}: ${esc(f.detail)}" style="left:${100 * f.where.x / W}%;top:${100 * f.where.y / H}%;width:${100 * f.where.w / W}%;height:${100 * f.where.h / H}%"><b>${i + 1}</b></span>`).join("");
  }
  function markList(s) {
    if (!(s.measured || []).length) return "";
    let n = 0;
    return `<ol class="measured small">${s.measured.map(f => `<li${f.where ? ` value="${++n}"` : ' class="off-screen"'}>${badge("must", measureName(f.check))} ${esc(f.detail)}${f.rule ? ` <code class="muted">${esc(f.rule)}</code>` : ""}${f.where ? "" : ' <span class="muted">(not on the first screen)</span>'}</li>`).join("")}</ol>`;
  }
  function zoomViewer() {
    if (!view) return;
    document.querySelectorAll("#viewer-body .pane").forEach(pane => {
      const box = pane.querySelector(".scroll"), img = pane.querySelector("img"), mock = pane.querySelector(".mock");
      if (img && img.naturalWidth) {  // fit: as large as the pane holds, never larger than the picture
        const z = view.zoom === "fit" ? Math.min(1, (box.clientWidth - 2) / img.naturalWidth, (box.clientHeight - 2) / img.naturalHeight) : Number(view.zoom);
        img.style.width = `${img.naturalWidth * z}px`;
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
  /* What the browser itself checks at every shoot for a rule (E7-F2-02, measure.js). */
  const MEASURES = [["overflow", "Text that overflows"], ["tap-targets", "Tap targets under 44 × 44 (phone)"],
    ["below-fold", "The primary action below the fold"], ["dialog-opaque", "See-through dialogs"], ["focus-visible", "No visible focus"]];
  const measureName = m => (MEASURES.find(x => x[0] === m) || [m, m])[1];
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
      <fieldset class="measures"><legend>Measured by the browser at every shoot</legend><div class="row">${MEASURES.map(([m, l]) => tick(l, "m:" + m, (r.measure || []).includes(m))).join("")}</div></fieldset>
      <div class="row"><button class="primary">Save</button><a href="#rules">Cancel</a></div></form>`;
  }

  function rulesTab() {
    const e = editing();
    return `<div class="toolbar"><button class="primary" data-goto="rules?edit=new">Add a rule</button><span class="small muted">Every round judges by the rules that hold, and every design follows them. They live in <code>crissp/uxsuite/rules/</code>, one file each${S.rules_from === "PRINCIPLES.md" ? " (the first change moves them out of PRINCIPLES.md)" : ""}.</span></div>
      ${e === "new" ? ruleForm(null) : ""}
      ${S.rules.map(r => e === r.id ? ruleForm(r) : `<article class="card rule ${r.on ? "" : "off"}"><div class="row">${badge(r.severity, r.severity)}<h3>${esc(r.title)}</h3><code class="small muted">${esc(r.id)}</code>${r.on ? "" : badge("missing", "off")}</div>
        <p class="small">${esc(r.text)}</p>
        ${(r.measure || []).length ? `<div class="row small"><span class="muted">Measured by the browser:</span>${r.measure.map(m => badge("ver", measureName(m))).join("")}</div>` : ""}
        <div class="row"><a href="#rules?edit=${encodeURIComponent(r.id)}">Edit</a>
          <button class="ghost small" data-toggle="rule" data-id="${esc(r.id)}">${r.on ? "Switch off" : "Switch on"}</button>
          <button class="ghost small" data-remove="rule" data-id="${esc(r.id)}">Remove</button></div></article>`).join("") || '<div class="card">No rules yet: add the first one.</div>'}`;
  }

  /* The review screen (E7-F4-01): one screen at a time, the ones that wait for you first. Its status on the way from
     seen to accepted, the shot with the findings pinned where they are next to the design, the advice must first, and
     one verdict bar that stays in its place: 1 2 3 give the verdict, ← → go to the previous or next screen, ↑ ↓ to the
     previous or next item. Everything can be done with the keyboard alone. */
  const STEP_NAMES = { new: "new", seen: "seen", discussed: "discussed", decided: "decided", designed: "designed", approved: "approved", built: "built", accepted: "accepted" };
  const OPTIONS = { advice: [["agree", "Agree"], ["disagree", "Disagree…"], ["later", "Later"]],
    design: [["approve", "Approve"], ["redo", "Again, with…"], ["reject", "Reject…"]], built: [["accept", "Accept"], ["send-back", "Not good…"]] };
  const stepTone = st => st === "accepted" ? "passed" : st === "new" ? "missing" : "area";
  function reviewItems(w, sc) {
    const r = last(w.rounds.filter(x => x.result)), items = [];
    const order = { must: 0, should: 1, could: 2 };
    if (r) (r.result.advice || []).map((a, i) => ({ a, i })).sort((x, y) => (order[x.a.priority] ?? 3) - (order[y.a.priority] ?? 3) || x.i - y.i)
      .forEach(({ a, i }) => items.push({ kind: "advice", id: `${w.id}/r${r.version}/a${i}`, a, title: a.title }));
    const p = w.proposals.find(x => x.key === sc.design);
    if (p && p.result) items.push({ kind: "design", id: p.key, title: `Design ${p.version}${p.result.title ? ": " + p.result.title : ""}` });
    if (p && ["built", "accepted"].includes(sc.status)) items.push({ kind: "built", id: p.key + "/built", title: "What was built" });
    return items;
  }
  function reviewState() {
    const R = S.review, screens = R.screens;
    const at = Math.max(0, screens.findIndex(x => x.walk === query.get("walk")));
    const sc = screens[at], w = sc && walkOf(sc.walk), items = sc ? reviewItems(w, sc) : [];
    const firstOpen = items.findIndex(x => !S.verdicts[x.id]);
    const i = query.has("i") ? Math.min(items.length - 1, Number(query.get("i"))) : Math.max(0, firstOpen);
    return { R, screens, at, sc, w, items, i, item: items[i] };
  }
  function pinned(w, shot, items) {
    if (!shot) return '<div class="frame none small muted">No screenshot yet.</div>';
    const [W, H] = SIZE[shot.device] || [1440, 900], ref = `${shot.device} ${shot.n}`;
    const pins = items.map((x, k) => ({ x, k })).filter(({ x }) => x.a && x.a.where && x.a.shot === ref)
      .map(({ x, k }) => `<span class="mark pin ${esc(x.a.priority)}" title="${esc(x.title)}" style="left:${100 * x.a.where.x / W}%;top:${100 * x.a.where.y / H}%;width:${100 * x.a.where.w / W}%;height:${100 * x.a.where.h / H}%"><b>${k + 1}</b></span>`).join("");
    return `<div class="marked"><img src="${esc(shot.url)}" alt="${esc(shot.title)}">${pins}${marks(shot).replace(/<b>(\d+)<\/b>/g, "<b>m$1</b>")}</div>`;
  }
  function reviewTab() {
    if (!S.review.screens.length) return '<div class="card">No walks yet: add one to <code>crissp/uxsuite/walks/</code>.</div>';
    const { R, screens, at, sc, w, items, i, item } = reviewState();
    const total = R.total || 1;
    const bar = R.steps.filter(st => R.progress[st]).map(st => `<span class="seg-${esc(st)}" style="flex:${R.progress[st]}" title="${esc(STEP_NAMES[st])}: ${R.progress[st]}">${R.progress[st]} ${esc(STEP_NAMES[st])}</span>`).join("");
    const p = w.proposals.find(x => x.key === sc.design);
    const ref = item?.a?.shot, device = ref ? ref.split(" ")[0] : null;
    const shot = w.shots.find(x => x.url && (ref ? `${x.device} ${x.n}` === ref : true)) || w.shots.find(x => x.url && x.device === device) || w.shots.find(x => x.url);
    const held = item && S.verdicts[item.id];
    return `<div class="progress card"><div class="row"><b>${R.progress.accepted} of ${R.total} screen(s) accepted</b><span class="small muted">${R.waiting} wait for you</span></div>
        <div class="progressbar" role="img" aria-label="${R.steps.map(st => `${R.progress[st]} ${st}`).join(", ")}" style="--total:${total}">${bar}</div></div>
      <div class="review">
        <nav class="review-list" aria-label="Screens">${screens.map((x, k) => `<a href="#review?walk=${encodeURIComponent(x.walk)}" class="${k === at ? "on" : ""}" ${k === at ? 'aria-current="true"' : ""}>
          <span class="row">${badge(stepTone(x.status), STEP_NAMES[x.status])}${x.waits === "you" ? badge("must", "you") : ""}${x.must ? `<span class="small muted">${x.must} must</span>` : ""}</span>
          <b>${esc(x.title)}</b><span class="small muted">${esc(x.next)}</span></a>`).join("")}</nav>
        <section class="review-main">
          <header class="row"><h3>${esc(sc.title)}</h3>${badge(stepTone(sc.status), STEP_NAMES[sc.status])}${badge("ver", sc.area)}<span class="small muted">${sc.waits === "you" ? "Waits for you: " : sc.waits === "team" ? "Waits for the team: " : ""}${esc(sc.next)}</span></header>
          <ol class="steps">${R.steps.slice(1).map(st => `<li class="${R.steps.indexOf(st) <= sc.step ? "done" : ""}">${esc(STEP_NAMES[st])}</li>`).join("")}</ol>
          <div class="compare">
            <figure class="pane"><figcaption><b>${sc.status === "built" || sc.status === "accepted" ? "Built" : "Before"}</b> · ${shot ? esc(`${shot.device} ${shot.n} · ${shot.title}`) : "what people see now"}</figcaption>${pinned(w, shot, items)}${shot ? markList(shot) : ""}</figure>
            <figure class="pane"><figcaption><b>After</b> · ${p ? "design " + p.version : "no design yet"}</figcaption>
              ${p?.mockup ? `<div class="frame fit"><iframe sandbox="allow-scripts" src="${esc(p.mockup)}" title="After: design ${p.version}" tabindex="-1"></iframe>
                <button class="cover" data-view="design" data-walk="${esc(w.id)}" data-key="${esc(p.key)}" data-device="${esc(shot?.device || "")}" data-mode="both" aria-label="Enlarge before and after"></button></div>` : `<div class="frame none small muted">${sc.status === "decided" ? `<button class="ghost" data-request="proposal" data-walk="${esc(w.id)}">Ask for a design</button>` : "Once the advice is decided, ask the team for a design."}</div>`}</figure>
          </div>
          <ol class="items">${items.map((x, k) => {
            const v = S.verdicts[x.id];
            return `<li class="${k === i ? "on" : ""} ${x.a ? esc(x.a.priority) : ""}"><a href="#review?walk=${encodeURIComponent(w.id)}&i=${k}">
              <span class="row">${x.a ? badge(x.a.priority, x.a.priority) : badge("area", x.kind === "design" ? "design" : "built")}<b>${esc(x.title)}</b>${v ? badge(v.verdict === "agree" || v.verdict === "approve" || v.verdict === "accept" ? "passed" : v.verdict === "later" ? "missing" : "failed", v.verdict) : ""}</span>
              ${k === i && x.a ? `<span class="small">${esc(x.a.detail || "")}${x.a.rule ? ` · rule <code>${esc(x.a.rule)}</code>` : ""}</span>` : ""}</a></li>`;
          }).join("") || '<li class="small muted">Nothing to decide on this screen yet.</li>'}</ol>
        </section>
      </div>
      <div class="verdict-bar" role="region" aria-label="Your verdict">
        ${item ? `<span class="what"><b>${i + 1}/${items.length}</b> ${esc(item.title)}${held ? ` · now: ${esc(held.verdict)}` : ""}</span>
          <span class="keys">${OPTIONS[item.kind].map(([v, l], k) => `<button class="${k ? "ghost" : "primary"}" data-verdict="${v}" data-id="${esc(item.id)}" data-key-n="${k + 1}" aria-pressed="${held?.verdict === v}"><kbd>${k + 1}</kbd> ${l}</button>`).join("")}</span>`
          : `<span class="what muted">Nothing to decide here.</span>`}
        <span class="small muted nav">← → screen · ↑ ↓ item</span></div>`;
  }
  document.addEventListener("keydown", e => {
    if (tab !== "review" || !S || S.error || document.querySelector("dialog[open]") || e.target.closest("input, textarea, select") || e.metaKey || e.ctrlKey || e.altKey) return;
    const { screens, at, items, i } = reviewState();
    const go = (k, n) => { location.hash = `review?walk=${encodeURIComponent(screens[k].walk)}${n === undefined ? "" : "&i=" + n}`; };
    if (/^[1-3]$/.test(e.key)) { const b = document.querySelector(`.verdict-bar [data-key-n="${e.key}"]`); if (b) { e.preventDefault(); b.click(); } }
    else if (e.key === "ArrowRight" && at < screens.length - 1) { e.preventDefault(); go(at + 1); }
    else if (e.key === "ArrowLeft" && at > 0) { e.preventDefault(); go(at - 1); }
    else if (e.key === "ArrowDown" && i < items.length - 1) { e.preventDefault(); go(at, i + 1); }
    else if (e.key === "ArrowUp" && i > 0) { e.preventDefault(); go(at, i - 1); }
  });

  function render() {
    $("#tabs").innerHTML = TABS.map(([k, l]) => `<button role="tab" data-tab="${k}" aria-selected="${k === tab}">${l}</button>`).join("");
    const view = { overview, review: reviewTab, map: mapTab, jobs: jobsTab, rounds, proposals, team, rules: rulesTab }[tab] || overview;
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
    if (vw && vw.dataset.view === "map") {
      const sc = S.map.screens.find(x => x.key === vw.dataset.key), s = sc.shots[Number(vw.dataset.i)];
      openViewer({ title: `${sc.title} · ${sc.key} · ${s.device}, ${s.source === "test" ? "E2E test" : s.source}`, before: s, after: null, mode: "before" });
      return;
    }
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
      const needs = remark || ["disagree", "redo", "reject", "send-back"].includes(verdict);
      const reason = needs ? await ask(remark ? "Your remark with the approval" : verdict === "redo" ? "What should the team do differently?" : verdict === "send-back" ? "What is not good?" : "Why?",
        remark ? "It goes into the backlog item, before the changes: the builder reads it first." : "The team reads this next time.") : "";
      if (reason === null || (remark && !reason.trim())) return;
      if (tab === "review") {  // on to the next open item after this one
        const { items, i } = reviewState(), open = items.map((x, k) => k).filter(k => k !== i && !S.verdicts[items[k].id]);
        const to = open.find(k => k > i) ?? open[0];
        if (to === undefined) query.delete("i"); else query.set("i", to);
        history.replaceState(null, "", "#review?" + query);
      }
      try { const out = await api("api/verdict", { id: v.dataset.id, verdict, reason });
        tell(out.moved ? `${out.pbi} moved to ${verdict === "accept" ? "review" : "doing"}${out.finding ? `, ${out.finding} written` : ""}` : out.not_moved ? out.not_moved : out.walk ? `Design requested: ${out.walk}${out.queued ? " (waits in the queue)" : ""}` : out.pbi ? `Approved: ${out.pbi} is on the board` : out.started ? "The next design has started" : out.queued ? "The next design waits in the queue" : "Saved");
      } catch (err) { tell(err.message); }
      return load();
    }
  });
  document.addEventListener("submit", async e => {
    const f = e.target.closest("form[data-form]");
    if (!f) return;
    e.preventDefault();
    const kind = f.dataset.form, data = Object.fromEntries(new FormData(f));
    const measure = Object.keys(data).filter(k => k.startsWith("m:")).map(k => { delete data[k]; return k.slice(2); });
    const body = { ...data, on: !!data.on, ...(kind === "rule" ? { measure } : {}), ...(kind === "persona" ? { key: f.dataset.key || undefined, moderator: !!data.moderator } : { id: f.dataset.key || undefined }) };
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

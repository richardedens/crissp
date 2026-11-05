/* The Tests dashboard: reads window.SUITE (results/data.js, written by crissp/testsuite/lib/collect.py) and renders it.
   What differs per product (its name, steps, texts) comes with the data, from crissp/testsuite/suites.json. The look,
   the theme and the top bar are shared with the UX suite (crissp/look). No dependencies, loads nothing from outside. */
(() => {
  const S = window.SUITE;
  const $ = (sel, el = document) => el.querySelector(sel);
  const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const human = name => esc(String(name).replace(/^test_/, "").replace(/_/g, " "));
  const editor = (abs, line) => `vscode://file/${encodeURI(abs)}${line ? ":" + line : ""}`;
  const where = (file, abs, line) => `<a href="${editor(abs, line)}" title="Open in VS Code"><code>${esc(file)}${line ? ":" + line : ""}</code></a>`;
  const badge = (status, text) => `<span class="badge ${status}">${esc(text ?? status)}</span>`;
  const pct = (a, b) => (b ? Math.round((a / b) * 1000) / 10 : 0);
  const color = p => (p >= 80 ? "var(--green)" : p >= 60 ? "var(--amber)" : "var(--red)");

  // the theme is the shared look's (crissp/look/look.js: dark by default, light remembered); journey shots follow it
  const root = document.documentElement;
  window.addEventListener("themechange", () => {
    document.querySelectorAll(".jshot[data-light]").forEach(i => { i.src = root.dataset.theme === "light" ? i.dataset.light : i.dataset.dark; });
  });

  if (!S) { $("#view").innerHTML = `<div class="card">No results yet. Run <code>crissp/check-all.sh</code>, then <code>crissp/test.sh --dashboard</code>.</div>`; return; }
  $("#stamp").textContent = `Last run ${S.generatedAt} · ${String(S.root || "").split("/").filter(Boolean).pop() || ""}`;
  $("#stamp").title = S.root || "";  /* the folder's name in sight, the whole path only on hover: a screenshot never shows a home folder */
  // live: the server (lib/serve.py) rebuilds the data when the backlog, a change or a run's results changed; the page
  // reloads when it did, on the same tab. Served without it (a plain file server) the page simply stays as it is.
  let seen = null;
  const poll = async () => {
    if (document.hidden) return;
    try {
      const r = await fetch("stamp", { cache: "no-store" });
      if (!r.ok) return;
      const { stamp } = await r.json();
      if (seen !== null && stamp !== seen) { location.reload(); return; }
      if (seen === null) $("#stamp").textContent += " · live";
      seen = stamp;
    } catch { /* the server is gone: keep what is shown */ }
  };
  poll(); setInterval(poll, 3000);
  if (window.Look) Look.brand(S.product, S.monogram, "Tests");
  if (S.sessions) { const a = $("#sessions"); a.href = S.sessions.href; a.textContent = "Sessions"; a.title = `Claude sessions · ${S.sessions.tokens} tokens`; a.hidden = false; }

  const tests = S.tests, unit = tests.filter(t => t.suite !== "e2e" && t.suite !== "journeys"), e2e = tests.filter(t => t.suite === "e2e");
  const journeys = S.journeys || [];
  const failed = tests.filter(t => t.status === "failed").length;
  const proven = S.changes.filter(c => c.verdict === "passed").length;
  const touched = new Set(S.changes.flatMap(c => c.sources.map(s => s.file)));

  const B = S.backlog;
  const pbisOf = e => [...e.features.flatMap(f => f.pbis.map(p => ({ ...p, epic: e, feature: f }))), ...e.items.map(p => ({ ...p, epic: e }))];
  const allPbis = B ? B.epics.flatMap(pbisOf) : [];
  const threatCount = (S.threats?.boundaries || []).reduce((n, b) => n + b.threats.length, 0);
  // a tab for what the product has: capabilities, journeys, threats and E2E only once there is something to show
  const TABS = [["overview", "Overview"], ...(B ? [["board", "Backlog", allPbis.filter(p => p.status !== "done").length]] : []), ["changes", "Changes", S.changes.length], ["tests", "Tests", unit.length], ["coverage", "Coverage"],
    ...((S.capabilities || []).length ? [["capabilities", "Capabilities", S.capabilities.length]] : []), ...(journeys.length ? [["journeys", "Journeys", new Set(journeys.map(j => j.id)).size]] : []),
    ...(threatCount ? [["threats", "Threat model", threatCount]] : []), ...(e2e.length ? [["e2e", "E2E", e2e.length]] : []), ["steps", "Runs & logs", S.steps.length], ["gaps", "Known gaps", S.gaps.length]];
  let tab = (location.hash.slice(1).split("?")[0]) || "overview";
  const nav = $("#tabs");
  const drawTabs = () => {
    nav.innerHTML = TABS.map(([k, l, n]) => `<button role="tab" data-k="${k}" aria-selected="${k === tab}">${l}${n !== undefined ? `<span class="n">${n}</span>` : ""}</button>`).join("");
  };
  nav.onclick = e => { const b = e.target.closest("button"); if (b) go(b.dataset.k); };
  const go = (k, query = "") => { tab = k; location.hash = k + (query ? "?" + query : ""); drawTabs(); render(query); window.scrollTo(0, 0); };
  window.addEventListener("hashchange", () => { const [k, q] = location.hash.slice(1).split("?"); if (k && k !== tab) { tab = k; drawTabs(); render(q || ""); } });

  // ---------------------------------------------------------------- views
  function overview() {
    const keys = S.coverageKeys || [], cov = S.coverage[keys[0]], pcov = S.coverage[keys[1]];
    const named = k => esc(S.suites[k]?.label ?? k);
    const ring = (p, label, c) => `<div class="ring" style="--p:${p};--c:${c}" data-label="${label}"></div>`;
    const totalPass = pct(tests.filter(t => t.status === "passed").length, tests.filter(t => t.status !== "skipped").length);
    const touchedFiles = (cov?.files || []).filter(f => touched.has(f.file));
    const tCov = pct(touchedFiles.reduce((a, f) => a + f.covered, 0), touchedFiles.reduce((a, f) => a + f.statements, 0));
    return `
      <div class="grid kpis">
        <div class="card kpi row">${ring(totalPass, totalPass + "%", failed ? "var(--red)" : "var(--green)")}<div><div class="l">Tests passing</div>
          <div class="v">${tests.length - failed - tests.filter(t => t.status === "skipped").length}<span class="muted small"> / ${tests.length}</span></div>
          <div class="s">${failed ? `<b style="color:var(--red)">${failed} failing</b>` : "none failing"} · ${tests.filter(t => t.status === "skipped").length} skipped</div></div></div>
        ${cov ? `<div class="card kpi row">${ring(cov.linePercent ?? cov.percent, (cov.linePercent ?? cov.percent) + "%", color(cov.linePercent ?? cov.percent))}<div><div class="l">${named(keys[0])} · line coverage</div>
          <div class="v">${cov.linePercent ?? cov.percent}%</div><div class="s">${cov.covered.toLocaleString()} of ${cov.statements.toLocaleString()} lines · ${cov.full ?? "?"} of ${cov.files.length} files at 100%</div></div></div>` : ""}
        ${cov?.branches ? `<div class="card kpi row">${ring(cov.branchPercent, cov.branchPercent + "%", color(cov.branchPercent))}<div><div class="l">${named(keys[0])} · branch coverage</div>
          <div class="v">${cov.branchPercent}%</div><div class="s">${cov.branchesCovered.toLocaleString()} of ${cov.branches.toLocaleString()} decision paths</div></div></div>` : ""}
        ${cov ? `<div class="card kpi row">${ring(tCov, tCov + "%", color(tCov))}<div><div class="l">Coverage of touched files</div>
          <div class="v">${tCov}%</div><div class="s">${touchedFiles.length} Python files changed in these releases</div></div></div>` : ""}
        ${pcov ? `<div class="card kpi row">${ring(pcov.linePercent ?? pcov.percent, (pcov.linePercent ?? pcov.percent) + "%", color(pcov.linePercent ?? pcov.percent))}<div><div class="l">${named(keys[1])} · line coverage</div>
          <div class="v">${pcov.linePercent ?? pcov.percent}%<span class="muted small"> lines</span></div><div class="s">${pcov.branches ? pcov.branchPercent + "% of branches · " : ""}${pcov.full ?? "?"} of ${pcov.files.length} files at 100%</div></div></div>` : ""}
        <div class="card kpi row">${ring(pct(proven, S.changes.length), `${proven}/${S.changes.length}`, proven === S.changes.length ? "var(--green)" : "var(--amber)")}
          <div><div class="l">Changes proven</div><div class="v">${proven}<span class="muted small"> / ${S.changes.length}</span></div><div class="s">every change has passing tests</div></div></div>
        ${S.gate ? `<div class="card kpi row click" data-go="coverage" style="cursor:pointer">${ring(S.gate.ok ? 100 : 0, S.gate.ok ? "✓" : "✗", S.gate.ok ? "var(--green)" : "var(--red)")}
          <div><div class="l">Coverage gate</div><div class="v" style="font-size:22px">${S.gate.ok ? "May only go up" : `${S.gate.problems.length} drop(s)`}</div>
          <div class="s">${S.gate.raised.length} file(s) raised this run · ${S.gate.exceptions.length} exception(s) with a reason${diffLine(S.gate.diff)}</div></div></div>` : ""}
        ${e2e.length ? `<div class="card kpi row">${ring(pct(e2e.filter(t => t.status === "passed").length, e2e.length), `${e2e.filter(t => t.status === "passed").length}/${e2e.length}`, "var(--teal)")}
          <div><div class="l">E2E in a browser</div><div class="v">${e2e.length}</div><div class="s">${S.screenshots.length} screenshots</div></div></div>` : ""}
      </div>
      <h2>Suites</h2>
      <div class="card"><table><thead><tr><th>Suite</th><th>Tests</th><th>Passed</th><th>Failed</th><th>Skipped</th><th>Time</th></tr></thead><tbody>
        ${Object.entries(S.suites).map(([k, s]) => `<tr class="click" data-go="${k === "e2e" ? "e2e" : "tests"}" data-q="${k === "e2e" ? "" : "suite=" + k}">
          <td><b>${esc(s.label)}</b></td><td>${s.tests}</td><td>${badge("passed", s.passed)}</td><td>${s.failed ? badge("failed", s.failed) : "0"}</td>
          <td>${s.skipped}</td><td>${s.time}s</td></tr>`).join("")}
      </tbody></table></div>
      <h2>Steps of this run</h2>
      <div class="card"><table><tbody>${S.steps.map(s => `<tr class="click" data-go="steps"><td>${badge(s.status)}</td><td>${esc(s.label)}</td><td class="muted">${s.seconds}s</td></tr>`).join("")
        || `<tr><td class="muted">No step log (collect.py was run on its own).</td></tr>`}</tbody></table></div>
      <h2>Changes by area</h2>
      <div class="grid kpis">${[...new Set(S.changes.map(c => c.area))].map(a => {
        const cs = S.changes.filter(c => c.area === a), ok = cs.filter(c => c.verdict === "passed").length;
        return `<div class="card click" data-go="changes" data-q="area=${encodeURIComponent(a)}" style="cursor:pointer"><div class="l label">${esc(a)}</div>
          <div class="v" style="font-size:22px;font-weight:700">${ok}/${cs.length}</div><div class="small muted">${cs.map(c => esc(c.title)).join(" · ")}</div></div>`;
      }).join("")}</div>`;
  }

  function changes(query) {
    const params = new URLSearchParams(query);
    const area = params.get("area") || "";
    const areas = [...new Set(S.changes.map(c => c.area))];
    const list = S.changes.filter(c => !area || c.area === area);
    return `<div class="toolbar"><select id="area"><option value="">All areas</option>${areas.map(a => `<option ${a === area ? "selected" : ""}>${esc(a)}</option>`).join("")}</select>
      <span class="muted small">Each change: what was wrong, how it is fixed, where the code is (click to open in VS Code), and the tests that prove it.</span></div>
      <div class="grid">${list.map(change).join("")}</div>`;
  }

  function change(c) {
    const code = s => s.found
      ? s.code.split("\n").map((l, i) => `<span class="ln">${s.line + i}</span>${esc(l)}`).join("\n") : "";
    return `<article class="card change" id="c-${esc(c.id)}">
      <header>${badge(c.verdict, c.verdict === "passed" ? "proven" : c.verdict)}<h3>${esc(c.title)}</h3><span class="badge area">${esc(c.area)}</span><span class="badge ver">${esc(c.version)}</span></header>
      <div class="cols"><div><div class="label">What was wrong</div><p>${esc(c.problem)}</p></div><div><div class="label">How it is fixed</div><p>${esc(c.fix)}</p></div></div>
      <div><div class="label">Where in the source</div><div class="grid" style="gap:8px;margin-top:6px">${c.sources.map(s => `
        <details class="src"><summary>${s.found ? "▸" : "⚠"} ${where(s.file, s.abs, s.line)} <span class="muted small">${esc(s.symbol)}</span>
          ${s.found ? "" : badge("missing", "symbol not found")}</summary>${s.found ? `<pre>${code(s)}</pre>` : ""}</details>`).join("")}</div></div>
      <div class="proof"><div class="label">Proof</div><ul>${c.proof.map(p => `<li>${badge(p.status)} ${p.e2e ? '<span class="badge area">E2E</span>' : ""}
        <a href="#" data-test="${esc(p.e2e ? "e2e:" + p.ref : p.ref)}">${esc(p.ref)}</a>
        <span class="muted small">${p.tests.length > 1 ? p.tests.length + " tests" : ""}</span></li>`).join("")}</ul></div>
      ${c.screenshots.length ? `<div><div class="label">Screenshots (E2E)</div><div class="thumbs" style="margin-top:6px">${c.screenshots.map(s => `<img src="../results/e2e/shots/${esc(s)}" alt="${esc(s)}" data-shot="${esc(s)}">`).join("")}</div></div>` : ""}
      ${c.gaps?.length ? `<div><div class="label">Not covered</div><ul class="small muted">${c.gaps.map(g => `<li>${esc(g)}</li>`).join("")}</ul></div>` : ""}
    </article>`;
  }

  function testsView(query) {
    const p = new URLSearchParams(query);
    return `<div class="toolbar">
      <input type="search" id="q" placeholder="Search tests, files, descriptions…" value="${esc(p.get("q") || "")}">
      <select id="suite"><option value="">All suites</option>${(S.unitSuites || Object.keys(S.suites)).filter(k => S.suites[k]).map(k => `<option value="${k}" ${p.get("suite") === k ? "selected" : ""}>${esc(S.suites[k].label)}</option>`).join("")}</select>
      <select id="status"><option value="">Any status</option>${["passed", "failed", "skipped"].map(s => `<option ${p.get("status") === s ? "selected" : ""}>${s}</option>`).join("")}</select>
      <span id="count" class="muted small"></span></div>
      <div class="card" style="padding:0"><table><thead><tr><th>Status</th><th>Test</th><th>Where</th><th>Time</th></tr></thead><tbody id="rows"></tbody></table></div>`;
  }

  function fillTests(pool, filter) {
    const q = ($("#q")?.value || "").toLowerCase(), suite = $("#suite")?.value || "", status = $("#status")?.value || "";
    const list = pool.filter(t => (!suite || t.suite === suite) && (!status || t.status === status) &&
      (!q || [t.name, t.module, t.doc, t.moduleDoc, t.file].join(" ").toLowerCase().includes(q)) && (!filter || filter(t)));
    $("#count").textContent = `${list.length} of ${pool.length}`;
    $("#rows").innerHTML = list.map((t, i) => `<tr class="click" data-i="${i}"><td>${badge(t.status)}</td>
      <td><b>${human(t.name)}</b><div class="small muted">${esc(t.doc || t.moduleDoc).slice(0, 260)}</div></td>
      <td class="small">${where(t.file, t.abs, t.line)}</td><td class="muted small">${t.time}s</td></tr>
      ${t.status === "failed" ? `<tr class="detail"><td colspan="4"><pre class="log">${esc(t.detail)}</pre></td></tr>` : ""}`).join("")
      || `<tr><td colspan="4" class="muted">Nothing matches.</td></tr>`;
  }

  // E1: diff coverage, every line added or changed since the baseline's commit must be covered
  function diffLine(d) {
    if (!d) return "";
    return d.skipped ? " · diff coverage skipped" : ` · changed code ${d.percent}% covered`;
  }

  function diffBox(d) {
    if (!d) return "";
    const head = `<div class="label" style="margin-top:10px">New and changed code${d.base ? ` since ${esc(d.base.slice(0, 10))}` : ""}</div>`;
    if (d.skipped) return head + `<p class="small muted">Not checked: ${esc(d.skipped)}</p>`;
    const files = Object.entries(d.files || {});
    return head + `<p class="small">${badge(d.uncovered.length ? "failed" : "passed", `${d.percent}%`)}
      ${d.covered_lines} of ${d.lines} changed line(s) and ${d.covered_branches} of ${d.branches} branch(es) covered</p>
      ${d.uncovered.length ? `<ul class="small">${d.uncovered.map(u => `<li>${where(u.file, S.root + "/" + u.file, u.line)} <span class="muted">${esc(u.what)}</span></li>`).join("")}</ul>` : ""}
      ${files.length ? `<details style="margin-top:8px"><summary class="small">${files.length} changed file(s)</summary><ul class="small muted">${files.map(([f, r]) =>
        `<li>${esc(f)}: ${r.covered_lines}/${r.lines} lines, ${r.covered_branches}/${r.branches} branches</li>`).join("")}</ul></details>` : ""}`;
  }

  function gateBox() {
    const g = S.gate;
    if (!g) return "";
    const dropped = g.problems.filter(x => !x.endsWith("(new and changed code is fully covered)"));  // those are listed under the diff
    return `<div class="card" style="margin-bottom:14px"><header style="display:flex;gap:10px;align-items:center">${badge(g.ok ? "passed" : "failed", g.ok ? "gate green" : "gate red")}
      <h3>Coverage may only go up</h3><span class="muted small">baseline: crissp/testsuite/coverage-baseline.json</span></header>
      ${dropped.length ? `<div class="label" style="margin-top:10px">What dropped</div><ul class="small">${dropped.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : ""}
      ${diffBox(g.diff)}
      ${g.raised.length ? `<details style="margin-top:8px"><summary class="small">${g.raised.length} file(s) went up this run (baseline raised)</summary><ul class="small muted">${g.raised.map(x => `<li>${esc(x)}</li>`).join("")}</ul></details>` : ""}
      <div class="label" style="margin-top:10px">Exceptions in the code (# pragma: no cover — reason)</div>
      ${g.exceptions.length ? `<ul class="small">${g.exceptions.map(x => `<li>${where(x.file, S.root + "/" + x.file, x.line)} <span class="muted">no ${esc(x.kind)}:</span> ${esc(x.reason) || '<b style="color:var(--red)">no reason</b>'}</li>`).join("")}</ul>` : '<p class="small muted">None: every line counts.</p>'}
      ${g.accepted?.length ? `<div class="label" style="margin-top:10px">Accepted drops</div><ul class="small">${g.accepted.map(a => `<li>${esc(a.at)} — ${esc(a.reason)}</li>`).join("")}</ul>` : ""}
    </div>`;
  }

  function coverageView(query) {
    const p = new URLSearchParams(query);
    return gateBox() + `<div class="toolbar"><select id="cs">${(S.coverageKeys || []).filter(k => S.coverage[k]).map(k => `<option value="${k}" ${p.get("suite") === k ? "selected" : ""}>${esc(S.suites[k].label)} · ${S.coverage[k].percent}%</option>`).join("")}</select>
      <input type="search" id="cq" placeholder="Filter files…"><label class="chk"><input type="checkbox" id="ct" ${p.get("touched") ? "checked" : ""}> only files touched in these changes</label>
      <select id="sort"><option value="file">Sort by file</option><option value="low">Lowest coverage first</option><option value="missing">Most uncovered lines</option><option value="branches">Lowest branch coverage first</option></select></div>
      <div class="card" style="padding:0"><table><thead><tr><th>File</th><th>Lines</th><th>Branches</th><th style="width:28%">Combined</th></tr></thead><tbody id="crows"></tbody></table></div>
      <p class="small muted">Measured with coverage.py while the tests ran. Lines: was every line run? Branches: did every decision (if/else, loops, conditional expressions)
      go both ways? Combined is coverage.py's total of both. Click a file for what is not covered yet.</p>`;
  }

  function fillCoverage() {
    const cov = S.coverage[$("#cs").value]; if (!cov) return;
    const q = $("#cq").value.toLowerCase(), only = $("#ct").checked, sort = $("#sort").value;
    let files = cov.files.filter(f => (!q || f.file.toLowerCase().includes(q)) && (!only || touched.has(f.file)));
    files = [...files].sort(sort === "low" ? (a, b) => a.percent - b.percent : sort === "missing" ? (a, b) => b.missing - a.missing
      : sort === "branches" ? (a, b) => (a.branchPercent ?? 100) - (b.branchPercent ?? 100) : (a, b) => a.file.localeCompare(b.file));
    $("#crows").innerHTML = files.map((f, i) => `<tr class="click" data-c="${i}"><td>${where(f.file, f.abs, 0)}
      ${touched.has(f.file) ? '<span class="badge area">changed</span>' : ""}</td>
      <td class="small">${f.linePercent ?? f.percent}% <span class="muted">· ${f.missing} of ${f.statements} open</span></td>
      <td class="small">${f.branches ? `${f.branchPercent}% <span class="muted">· ${f.branches - f.branchesCovered} of ${f.branches} open</span>` : '<span class="muted">—</span>'}</td>
      <td><div style="display:flex;gap:10px;align-items:center"><div class="bar" style="flex:1;--c:${color(f.percent)}"><i style="width:${f.percent}%"></i></div><b>${f.percent}%</b></div></td></tr>
      <tr class="detail" hidden data-d="${i}"><td colspan="4"><div class="label">Uncovered lines</div><div class="lines">${ranges(f.missingLines).map(([a, b]) =>
        `<a href="${editor(f.abs, a)}">${a === b ? a : a + "–" + b}</a>`).join(", ") || "none"}</div>
        ${(f.missingBranches || []).length ? `<div class="label" style="margin-top:8px">Untaken decision paths (line → where it would go; exit = leaves the function)</div>
        <div class="lines">${f.missingBranches.map(([a, b]) => `<a href="${editor(f.abs, a)}">${a} → ${b < 0 ? "exit" : b}</a>`).join(", ")}</div>` : ""}</td></tr>`).join("");
    $("#crows").onclick = e => { const r = e.target.closest("tr[data-c]"); if (r && !e.target.closest("a")) { const d = $(`tr[data-d="${r.dataset.c}"]`); d.hidden = !d.hidden; } };
  }

  const ranges = lines => lines.reduce((out, n) => { const last = out[out.length - 1]; if (last && n === last[1] + 1) last[1] = n; else out.push([n, n]); return out; }, []);

  function e2eView() {
    return `<p class="muted">${esc(S.texts?.e2e ?? "The product as it runs, on throwaway data, driven over HTTP and in a browser.")}
      Screenshots are taken at the end of every browser test and at key moments.</p>
      <div class="card" style="padding:0"><table><thead><tr><th>Status</th><th>Test</th><th>Where</th><th>Time</th></tr></thead><tbody id="rows"></tbody></table></div>
      <h2>Screenshots</h2><div class="grid gallery">${S.screenshots.map(s => `<figure><img src="../results/e2e/shots/${esc(s)}" data-shot="${esc(s)}" alt="${esc(s)}"><figcaption>${human(s.replace(/\.png$/, ""))}</figcaption></figure>`).join("")
        || '<p class="muted">No screenshots (E2E skipped?).</p>'}</div>`;
  }

  // the kinds of capability, as the product names them in results/capabilities.json (groupLabel), else their key
  const GROUPS = Object.fromEntries((S.capabilities || []).map(c => [c.group, c.groupLabel || c.group]));

  function capabilitiesView() {
    const all = S.capabilities || [];
    const n = f => all.filter(f).length;
    return `<div class="grid kpis" style="margin-bottom:14px">
        <div class="card kpi"><div class="l">Capabilities</div><div class="v">${all.length}</div><div class="s">from results/capabilities.json</div></div>
        <div class="card kpi"><div class="l">Exercised by a test</div><div class="v" style="color:var(--green)">${n(c => c.tested === "passed")}</div><div class="s">${n(c => c.tested === "untested")} not exercised · ${n(c => c.tested === "failed")} failing</div></div>
        <div class="card kpi"><div class="l">Documented by a journey</div><div class="v" style="color:var(--amber)">${n(c => c.documented !== "missing")}</div><div class="s">a journey shows it in use</div></div>
        <div class="card kpi"><div class="l">Under the threat model</div><div class="v">${n(c => c.threats.length)}</div><div class="s">capabilities a threat applies to</div></div></div>
      <p class="muted small">Measured, not maintained: a capability counts as exercised when a test ran the code that carries it out (coverage per test).</p>
      <div class="toolbar"><input type="search" id="cq2" placeholder="Search capabilities…"><select id="cg"><option value="">All kinds</option>${Object.entries(GROUPS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
        <select id="cs2"><option value="">Any state</option><option value="untested">Not exercised</option><option value="failed">Failing</option><option value="undocumented">Not documented</option></select><span id="ccount" class="muted small"></span></div>
      <div class="card" style="padding:0"><table><thead><tr><th>Capability</th><th style="width:12%">Tested</th><th style="width:12%">Documented</th><th style="width:16%">Threats</th><th style="width:20%">Code</th></tr></thead><tbody id="caprows"></tbody></table></div>`;
  }

  function fillCapabilities() {
    const all = S.capabilities || [];
    const q = $("#cq2").value.toLowerCase(), g = $("#cg").value, st = $("#cs2").value;
    const list = all.filter(c => (!g || c.group === g) && (!q || [c.id, c.name, c.description].join(" ").toLowerCase().includes(q))
      && (!st || (st === "undocumented" ? c.documented === "missing" : c.tested === st)));
    $("#ccount").textContent = `${list.length} of ${all.length}`;
    let last = "";
    $("#caprows").innerHTML = list.map(c => {
      const head = c.group !== last ? `<tr><td colspan="5" style="background:var(--panel2)"><b>${esc(GROUPS[c.group] || c.group)}</b></td></tr>` : "";
      last = c.group;
      const code = c.code[0];
      return head + `<tr><td><b>${esc(c.name)}</b> <code class="small muted">${esc(c.id)}</code>${c.description ? `<div class="small muted">${esc(c.description).slice(0, 160)}</div>` : ""}</td>
        <td>${c.tested === "untested" ? badge("missing", "not exercised") : `<a href="#" data-captests="${esc(c.id)}">${badge(c.tested, `${c.testCount} test${c.testCount === 1 ? "" : "s"}`)}</a>`}</td>
        <td>${c.journeys.length ? `<a href="#journeys">${badge(c.documented, c.journeys.length === 1 ? "journey" : c.journeys.length + " journeys")}</a>` : badge("missing", "not yet")}</td>
        <td class="small">${c.threats.map(t => `<span class="badge area">${esc(t)}</span>`).join(" ") || '<span class="muted">—</span>'}</td>
        <td class="small">${code ? where(code.file, code.abs || S.root + "/" + code.file, code.start) : ""}</td></tr>`;
    }).join("");
    $("#caprows").onclick = e => {
      const a = e.target.closest("[data-captests]");
      if (!a) return;
      e.preventDefault();
      const c = all.find(x => x.id === a.dataset.captests);
      alert(`${c.name}\n\nExercised by:\n${c.tests.join("\n")}`);
    };
  }

  const LEVEL = { beginner: "Beginner", professional: "Professional", advanced: "Advanced", architect: "Architect" };
  const JSTATUS = { verified: ["passed", "verified"], "out-of-date": ["failed", "out of date"], "never-verified": ["missing", "never verified"] };

  function journeysView() {
    if (!journeys.length) return `<div class="card">No journeys recorded yet. They run with <code>crissp/check-all.sh</code> (not in quick mode).</div>`;
    const byId = new Map();
    for (const j of journeys) byId.set(j.id, [...(byId.get(j.id) || []), j]);
    const all = [...byId.values()];
    const n = st => all.filter(langs => langs.every(j => j.status === st)).length;
    const steps = all.reduce((sum, langs) => sum + langs[0].steps.length, 0);
    const shots = journeys.reduce((sum, j) => sum + j.steps.reduce((k, st) => k + st.images.length, 0), 0);
    const levels = Object.keys(LEVEL).map(l => [l, all.filter(langs => langs[0].level === l)]).filter(([, list]) => list.length);
    return `<div class="grid kpis" style="margin-bottom:14px">
        <div class="card kpi"><div class="l">Journeys</div><div class="v">${all.length}</div><div class="s">${steps} steps · ${[...new Set(journeys.map(j => j.lang.toUpperCase()))].join(" + ")}</div></div>
        <div class="card kpi"><div class="l">Verified</div><div class="v" style="color:var(--green)">${n("verified")}</div><div class="s">ran green in every language, screenshots current</div></div>
        <div class="card kpi"><div class="l">Out of date</div><div class="v" style="color:${all.length - n("verified") ? "var(--red)" : "var(--muted)"}">${all.length - n("verified")}</div><div class="s">a screen changed: the page says so</div></div>
        <div class="card kpi"><div class="l">Screenshots</div><div class="v">${shots * 4}</div><div class="s">close-up + full screen, light + dark</div></div></div>
      <p class="muted small">${esc(S.texts?.journeys ?? "A journey is an E2E test of the real interface and its documentation page at the same time:")}
        the pink frame and number mark exactly what the test clicked; the green ✓ marks what it checked.</p>
      ${levels.map(([l, list]) => `<h3 class="level-h">${LEVEL[l]}</h3>` + list.map(langs => journeyCard(langs)).join("")).join("")}`;
  }

  function journeyCard(langs) {
    const j = langs[0];
    const status = langs.map(x => `<span class="badge ver">${x.lang.toUpperCase()}</span> ${badge(...JSTATUS[x.status])}`).join(" &nbsp; ");
    const fail = langs.filter(x => x.status !== "verified").map(x => `<div class="card" style="border-color:var(--red)"><b>${x.lang.toUpperCase()}: ${esc(JSTATUS[x.status][1])}</b>
        ${x.failed_at ? `<span class="muted small"> · failed ${esc(x.failed_at)}</span>` : ""}<pre class="log">${esc(x.error)}</pre>
        ${x.failure ? `<img class="jshot" src="${x.failure}" data-shot="failure" alt="The screen when it failed">` : ""}</div>`).join("");
    return `<details class="card journey"><summary><b>${esc(j.title)}</b> <span class="muted small">${langs.map(x => x.lang !== j.lang ? esc(x.title) : "").join("")}</span>
        <span class="jmeta">${status} <span class="muted small">· ${j.steps.length} steps · verified ${esc(j.verified_at)} · ${esc(j.commit)}</span></span></summary>
      ${fail}<p class="muted">${esc(j.intro)}</p>
      ${j.capabilities.length ? `<p class="small">Documents: ${j.capabilities.map(c => `<code>${esc(c)}</code>`).join(" ")}</p>` : ""}
      <div class="jlang">${langs.map(x => `<button data-jlang="${x.lang}" class="${x === j ? "on" : ""}">${x.lang.toUpperCase()}</button>`).join("")}</div>
      ${langs.map(x => `<div class="jsteps" data-lang="${x.lang}" ${x === j ? "" : "hidden"}>${x.steps.map(st => journeyStep(x, st)).join("")}</div>`).join("")}</details>`;
  }

  function journeyStep(j, st) {
    const theme = () => (root.dataset.theme === "light" ? "light" : "dark");
    const img = im => {
      const view = Object.keys(im.crop).length ? "crop" : "full";
      return `<img class="jshot" loading="lazy" data-light="${j.base + im[view].light}" data-dark="${j.base + im[view].dark}" data-shot="${esc(st.title)}"
        data-full-light="${j.base + im.full.light}" data-full-dark="${j.base + im.full.dark}" src="${j.base + im[view][theme()]}" alt="${esc(st.title)}">`;
    };
    const acts = st.actions.map(a => `<li value="${a.n}">${a.kind === "type" ? "Type" : a.kind === "choose" ? "Choose" : "Click"} <b>${esc(a.label)}</b>${a.value ? `: <code>${esc(a.value)}</code>` : ""}</li>`).join("");
    return `<div class="jstep"><h4>${st.n}. ${esc(st.title)}</h4><p>${esc(st.text)}</p>${acts ? `<ol>${acts}</ol>` : ""}
      <div class="jshots">${st.images.map(img).join("")}</div>${st.see.map(x => `<p class="jsee">✓ ${esc(x)}</p>`).join("")}</div>`;
  }

  // the backlog as a board: a lane per epic (its features as chips), a column per status, a card per PBI
  const COLUMNS = [["todo", "To do"], ["doing", "Doing"], ["review", "In review"], ["done", "Done"], ["parked", "Parked"]];
  function boardView(query) {
    const p = new URLSearchParams(query), count = s => allPbis.filter(x => x.status === s).length;
    return `<div class="grid kpis five" style="margin-bottom:14px">${COLUMNS.map(([s, l]) => `<div class="card kpi"><div class="l">${l}</div>
        <div class="v st-${s}">${count(s)}</div><div class="s">${s === "review" ? "waiting for the product owner" : s === "doing" ? "in progress" : "PBIs"}</div></div>`).join("")}</div>
      <div class="toolbar"><select id="be"><option value="">Every open epic</option>${B.epics.map(e => `<option value="${esc(e.id)}"${p.get("epic") === e.id ? " selected" : ""}>${esc(e.id)} · ${esc(e.title)}${e.done ? " (done)" : ""}</option>`).join("")}</select>
        <input type="search" id="bq" placeholder="Search PBIs…" value="${esc(p.get("q") || "")}"></div>
      <p class="muted small">Epic → feature → PBI, read from crissp/backlog/ by the crissp tool. Only the product owner moves work to done.</p>
      <div class="board-head">${COLUMNS.map(([s, l]) => `<div class="st-${s}">${l}</div>`).join("")}</div><div id="lanes"></div>`;
  }
  function fillBoard() {
    const which = $("#be").value, q = $("#bq").value.trim().toLowerCase();
    const ux = x => x.ux ? `<a class="badge area ux" href="../ux/#proposal=${encodeURIComponent(x.ux)}" title="The approved UX design this PBI came from">UX design</a>` : "";
    const card = x => `<div class="kcard"><div class="kid"><code>${esc(x.id)}</code><span>${ux(x)}${x.size ? `<span class="size">${esc(x.size)}</span>` : ""}</span></div>
      <div class="kt">${esc(x.title)}</div>${x.feature ? `<div class="small muted">${esc(x.feature.id)} · ${esc(x.feature.title)}</div>` : ""}
      <details><summary class="small">details</summary><pre class="kblock">${esc(x.block)}</pre></details></div>`;
    const chip = f => { const n = f.pbis.length, d = f.pbis.filter(x => x.status === "done").length;
      return `<span class="chip st-${f.status}" title="${esc(f.status)}"><b>${esc(f.id)}</b> ${esc(f.title)} <span class="muted">${d}/${n}</span></span>`; };
    const lanes = B.epics.filter(e => (which ? e.id === which : !e.done)).map(e => {
      const mine = pbisOf(e).filter(x => !q || (x.id + " " + x.title + " " + x.block).toLowerCase().includes(q));
      if (q && !mine.length) return "";
      return `<section class="lane"><header><h3>${esc(e.id)} · ${esc(e.title)}</h3><span class="muted small">${esc(e.file)}</span>
        <div class="chips">${e.features.map(chip).join("") || (e.items.length ? '<span class="muted small">no features yet: PBIs from before features</span>' : '<span class="muted small">no features yet</span>')}</div></header>
        <div class="board">${COLUMNS.map(([s]) => `<div class="col">${mine.filter(x => x.status === s).map(card).join("")}</div>`).join("")}</div></section>`;
    }).join("");
    $("#lanes").innerHTML = lanes || '<p class="muted">Nothing matches.</p>';
  }

  function threatsView() {
    const all = (S.threats?.boundaries || []).flatMap(b => b.threats);
    const count = s => all.filter(x => x.status === s).length;
    const label = { passed: "proven", untested: "not tested yet", failed: "failing", missing: "test not found" };
    return `<div class="grid kpis" style="margin-bottom:14px">
        <div class="card kpi"><div class="l">Threats</div><div class="v">${all.length}</div><div class="s">across ${S.threats.boundaries.length} trust boundaries</div></div>
        <div class="card kpi"><div class="l">Proven by a test</div><div class="v" style="color:var(--green)">${count("passed")}</div></div>
        <div class="card kpi"><div class="l">Not tested yet</div><div class="v" style="color:var(--amber)">${count("untested") + count("missing")}</div><div class="s">the work list</div></div>
        <div class="card kpi"><div class="l">Failing</div><div class="v" style="color:${count("failed") ? "var(--red)" : "inherit"}">${count("failed")}</div></div></div>
      <p class="muted small">Each threat names the control that should stop it and the tests that prove it does. Source: crissp/testsuite/threats.json.</p>
      ${S.threats.boundaries.map(b => `<h2>${esc(b.id)} · ${esc(b.name)}</h2><div class="card" style="padding:0"><table><thead><tr><th style="width:9%">Status</th><th style="width:31%">Threat</th><th style="width:28%">Control</th><th>Proof</th></tr></thead><tbody>
        ${b.threats.map(x => `<tr><td>${badge(x.status === "untested" ? "missing" : x.status, label[x.status])}</td><td><b>${esc(x.id)}</b> ${esc(x.threat)}${x.note ? `<div class="small muted">${esc(x.note)}</div>` : ""}</td>
          <td class="small">${esc(x.control)}</td><td class="small">${x.proof.map(p => `${badge(p.status)} <a href="#" data-test="${esc(p.ref)}">${esc(p.ref)}</a>`).join("<br>") || '<span class="muted">—</span>'}</td></tr>`).join("")}
      </tbody></table></div>`).join("")}`;
  }

  function stepsView() {
    return S.steps.map(s => `<div class="card" style="margin-bottom:14px"><header style="display:flex;gap:10px;align-items:center">${badge(s.status)}<h3>${esc(s.label)}</h3>
      <span class="muted small">${s.seconds}s · results/${esc(s.key)}.log</span></header><pre class="log">${esc(s.log)}</pre></div>`).join("") || '<p class="muted">No step log.</p>';
  }

  function gapsView() {
    const per = S.changes.filter(c => c.gaps?.length);
    return `<div class="card"><p>What these tests do <b>not</b> prove, so nobody reads more into a green dashboard than is there.</p><ul class="gaps">${S.gaps.map(g => `<li>${esc(g)}</li>`).join("")}
      ${per.map(c => c.gaps.map(g => `<li><b>${esc(c.title)}:</b> ${esc(g)}</li>`).join("")).join("")}</ul></div>`;
  }

  // ---------------------------------------------------------------- render + interactions
  function render(query = (location.hash.split("?")[1] || "")) {
    const v = $("#view");
    if (tab === "overview") v.innerHTML = overview();
    else if (tab === "board" && B) { v.innerHTML = boardView(query); $("#be").onchange = $("#bq").oninput = fillBoard; fillBoard(); }
    else if (tab === "changes") { v.innerHTML = changes(query); $("#area").onchange = e => go("changes", e.target.value ? "area=" + encodeURIComponent(e.target.value) : ""); }
    else if (tab === "tests") {
      v.innerHTML = testsView(query);
      const p = new URLSearchParams(query), ref = p.get("ref");
      const filter = ref ? (t => t.id === ref || t.module === ref) : null;
      const redraw = () => fillTests(unit, filter);
      ["#q", "#suite", "#status"].forEach(s => $(s).oninput = redraw); redraw();
    } else if (tab === "coverage") { v.innerHTML = coverageView(query); ["#cs", "#cq", "#ct", "#sort"].forEach(s => $(s).oninput = fillCoverage); fillCoverage(); }
    else if (tab === "e2e") { v.innerHTML = e2eView(); $("#rows").innerHTML = ""; fillE2e(); }
    else if (tab === "steps") v.innerHTML = stepsView();
    else if (tab === "threats") v.innerHTML = threatsView();
    else if (tab === "journeys") v.innerHTML = journeysView();
    else if (tab === "capabilities") { v.innerHTML = capabilitiesView(query); $("#cq2").oninput = $("#cg").oninput = $("#cs2").oninput = () => fillCapabilities(); fillCapabilities(); }
    else v.innerHTML = gapsView();
  }

  function fillE2e() {
    $("#rows").innerHTML = e2e.map(t => `<tr><td>${badge(t.status)}</td><td><b>${human(t.name)}</b><div class="small muted">${esc(t.doc)}</div></td>
      <td class="small">${where(t.file, t.abs, t.line)}</td><td class="muted small">${t.time}s</td></tr>
      ${t.status === "failed" ? `<tr class="detail"><td colspan="4"><pre class="log">${esc(t.detail)}</pre></td></tr>` : ""}`).join("");
  }

  document.addEventListener("click", e => {
    const lang = e.target.closest("[data-jlang]");
    if (lang) {
      const card = lang.closest(".journey");
      card.querySelectorAll("[data-jlang]").forEach(b => b.classList.toggle("on", b === lang));
      card.querySelectorAll(".jsteps").forEach(d => { d.hidden = d.dataset.lang !== lang.dataset.jlang; });
      return;
    }
    const jshot = e.target.closest(".jshot[data-full-light]");
    if (jshot) { const lb = $("#lightbox"); $("img", lb).src = root.dataset.theme === "light" ? jshot.dataset.fullLight : jshot.dataset.fullDark; $("p", lb).textContent = jshot.alt; lb.hidden = false; return; }
    const shot = e.target.closest("[data-shot]");
    if (shot) { const lb = $("#lightbox"); $("img", lb).src = shot.src; $("p", lb).textContent = human(shot.dataset.shot.replace(/\.png$/, "")).replace(/&amp;/g, "&"); lb.hidden = false; return; }
    if (e.target.closest("#lightbox")) { $("#lightbox").hidden = true; return; }
    const t = e.target.closest("[data-test]");
    if (t) { e.preventDefault(); const ref = t.dataset.test; if (ref.startsWith("e2e:")) go("e2e"); else go("tests", "ref=" + encodeURIComponent(ref)); return; }
    const g = e.target.closest("[data-go]");
    if (g && !e.target.closest("a")) go(g.dataset.go, g.dataset.q || "");
  });
  document.addEventListener("keydown", e => { if (e.key === "Escape") $("#lightbox").hidden = true; });

  drawTabs();
  render();
})();

/* The workers page (E1-F1-04): this machine's CPUs and memory, and per step that runs (or ran) how its tests are spread
   over the workers — what each runs now and since when, what it finished, how busy it was, what failed. It asks
   workers.json (lib/serve.py → lib/workers.py state()) every two seconds while it is open; nothing else, nothing from
   outside. Served without the server (a plain file), it says so. */
(() => {
  const $ = sel => document.querySelector(sel);
  const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const badge = (status, text) => `<span class="badge ${esc(status)}">${esc(text ?? status)}</span>`;
  const gb = mb => (mb == null ? "unknown" : `${(mb / 1024).toFixed(1)} GB`);
  const secs = s => (s == null ? "" : s >= 90 ? `${Math.floor(s / 60)} min ${s % 60} s` : `${s} s`);
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const short = id => { const [file, ...rest] = String(id || "").split("::"); return { file, name: rest.join("::") }; };
  const TONE = { running: "area", passed: "passed", failed: "failed", stopped: "missing" };

  function machine(s) {
    const m = s.machine, w = s.would;
    return `<section class="grid kpis">
      <div class="card kpi"><div class="l">CPUs</div><div class="v">${m.cpus}</div><div class="s">${esc(m.cpu_from)}</div></div>
      <div class="card kpi"><div class="l">Memory</div><div class="v">${gb(m.memory_mb)}</div><div class="s">${gb(m.available_mb)} available · ${esc(m.memory_from)}</div></div>
      <div class="card kpi"><div class="l">A parallel step gets</div><div class="v">${plural(w.workers, "worker")}</div><div class="s">${esc(w.why)}</div></div>
    </section>`;
  }

  function lane(l, step) {
    const share = step.elapsed ? Math.min(100, Math.round((l.busy / step.elapsed) * 100)) : 0;
    const cur = l.now ? short(l.now) : l.last ? short(l.last) : null;
    const what = l.now
      ? `<b>${esc(cur.name)}</b> <span class="muted">${esc(cur.file)} · ${secs(l.since)}</span>${l.quiet ? " " + badge("missing", "quiet") : ""}`
      : cur ? `<span class="muted">last: ${esc(cur.name)} · ${esc(cur.file)}</span>` : `<span class="muted">nothing yet</span>`;
    return `<tr><td><code>${esc(l.worker)}</code></td>
      <td><div class="lane-busy"><div class="bar" style="--c:var(--accent)"><i style="width:${share}%"></i></div><span class="muted">${share}%</span></div></td>
      <td>${l.done} ${l.failed ? badge("failed", l.failed) : ""} ${l.skipped ? badge("skipped", l.skipped) : ""}</td>
      <td class="lane-now">${what}</td></tr>`;
  }

  function step(st) {
    const pct = st.collected ? Math.round((st.done / st.collected) * 100) : st.status === "running" ? 0 : 100;
    const o = st.outcomes;
    const time = `${secs(st.elapsed)}${st.left == null ? "" : st.left < 1 ? " · almost done" : ` · about ${secs(st.left)} left`}`;
    return `<article class="card step">
      <header class="step-head"><h2>${esc(st.label)}</h2>${badge(TONE[st.status] || "ver", st.status)}
        <span class="muted">${plural(st.workers, "worker")}${st.why ? ` · ${esc(st.why)}` : ""}</span></header>
      <div class="step-progress"><div class="bar" style="--c:${st.outcomes.failed ? "var(--red)" : "var(--green)"}"><i style="width:${pct}%"></i></div>
        <span>${st.done}${st.collected ? ` of ${st.collected}` : ""} tests · ${time}</span>
        ${badge("passed", `${o.passed} passed`)} ${o.failed ? badge("failed", `${o.failed} failed`) : ""} ${o.skipped ? badge("skipped", `${o.skipped} skipped`) : ""}</div>
      ${st.lanes.length ? `<table class="lanes"><thead><tr><th>Worker</th><th>Busy</th><th>Done</th><th>${st.status === "running" ? "Now" : "Last"}</th></tr></thead>
        <tbody>${st.lanes.map(l => lane(l, st)).join("")}</tbody></table>` : `<p class="muted">No test has finished yet.</p>`}
      ${st.failed.length ? `<details><summary>${plural(st.failed.length, "failed test")}</summary><ul class="lines">${st.failed.map(f => `<li>${esc(f)}</li>`).join("")}</ul></details>` : ""}
    </article>`;
  }

  function render(s) {
    if (window.Look) Look.brand(s.product, s.monogram, "Workers");
    $("#stamp").textContent = `${new Date(s.now * 1000).toLocaleTimeString()} · live`;
    const steps = s.steps.length ? s.steps.map(step).join("")
      : `<div class="card">No run yet. Start <code>crissp check</code> or <code>crissp check-all</code>: a parallel step's workers fill in here while it runs.</div>`;
    $("#view").innerHTML = machine(s) + steps;
  }

  let last = "";
  async function poll() {
    if (document.hidden) return;
    try {
      const r = await fetch("workers.json", { cache: "no-store" });
      if (!r.ok) throw new Error(String(r.status));
      const text = await r.text();
      if (text !== last) { last = text; render(JSON.parse(text)); }
    } catch {
      if (!last) $("#view").innerHTML = `<div class="card">This page needs the crissp server: <code>crissp dashboard</code>, then open <code>/workers</code>.</div>`;
    }
  }
  poll();
  setInterval(poll, 2000);
  document.addEventListener("visibilitychange", poll);
})();

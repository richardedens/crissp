/* The C.R.I.S.S.P. look, the part that runs: the theme (dark by default, light when the viewer chooses it, remembered
   per viewer in this browser) and the helpers every page of the framework shares. Load it in <head>, so the page never
   flashes in the wrong theme. Loads nothing, needs nothing. */
(() => {
  const KEY = "crissp.theme", root = document.documentElement;
  try { const t = localStorage.getItem(KEY); if (t === "light" || t === "dark") root.dataset.theme = t; } catch { /* storage off */ }
  if (root.dataset.theme !== "light") root.dataset.theme = "dark";
  const set = theme => {
    root.dataset.theme = theme;
    try { localStorage.setItem(KEY, theme); } catch { /* storage off */ }
    window.dispatchEvent(new CustomEvent("themechange", { detail: theme }));
  };
  document.addEventListener("click", e => { if (e.target.closest("#theme")) set(root.dataset.theme === "light" ? "dark" : "light"); });
  const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  window.Look = {
    esc,
    theme: () => root.dataset.theme,
    setTheme: set,
    badge: (status, text) => `<span class="badge ${esc(status)}">${esc(text ?? status)}</span>`,
    /* the product's name in the top bar and the tab title: "<product> · <section>" */
    brand(product, monogram, section) {
      if (!product) return;
      document.title = `${product} · ${section}`;
      const h1 = document.querySelector(".top h1"), logo = document.querySelector(".top .logo");
      if (h1) h1.textContent = `${product} · ${section}`;
      if (logo) logo.textContent = monogram || product[0];
    },
  };
})();

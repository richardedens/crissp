/* The measured rules (E7-F2-02): what the browser itself checks on the screen at every shot, so the team does not spend
   tokens finding it in a picture. ux_shoot.py and ux_map.py add this file to the page and call
   window.crisspMeasure(checks, touch); each finding says which check, where on the screen (the viewport's CSS pixels,
   null when it is off the screen) and what it found. It only reads the page; focus is moved and given back. */
window.crisspMeasure = function (checks, touch) {
  const MAX = 20, out = [];
  const box = el => {
    const r = el.getBoundingClientRect();
    return { x: Math.round(r.left), y: Math.round(r.top), w: Math.round(r.width), h: Math.round(r.height) };
  };
  const onScreen = b => b.w > 0 && b.h > 0 && b.y < innerHeight && b.y + b.h > 0 && b.x < innerWidth && b.x + b.w > 0;
  const shown = el => {
    const s = getComputedStyle(el);
    return s.display !== "none" && s.visibility !== "hidden" && Number(s.opacity) > 0 && el.getClientRects().length > 0;
  };
  const label = el => (el.getAttribute("aria-label") || el.textContent || el.getAttribute("value") || el.tagName).trim().replace(/\s+/g, " ").slice(0, 60);
  const add = (check, el, detail, where) => {
    if (out.filter(f => f.check === check).length < MAX) out.push({ check, where: where === undefined ? box(el) : where, detail });
  };
  const all = sel => [...document.querySelectorAll(sel)].filter(shown);
  const CONTROLS = "a[href], button, input:not([type=hidden]), select, textarea, [role=button], [role=link], [tabindex]:not([tabindex='-1'])";

  if (checks.includes("overflow")) {
    for (const el of all("body *")) {
      if (!el.textContent.trim() || el.children.length > 3) continue;
      const s = getComputedStyle(el);
      const cut = el.scrollWidth > el.clientWidth + 2 && ["hidden", "clip"].includes(s.overflowX) && s.textOverflow !== "ellipsis";
      const out_ = box(el).x + box(el).w > innerWidth + 1 && el.children.length === 0;
      if (cut || out_) add("overflow", el, `"${label(el)}" ${cut ? "is cut off" : "runs past the screen's edge"}`);
    }
  }
  if (checks.includes("tap-targets") && touch) {
    for (const el of all(CONTROLS)) {
      const b = box(el);
      const inText = el.tagName === "A" && getComputedStyle(el).display === "inline" && el.parentElement.closest("p, li, td");
      if (!inText && onScreen(b) && (b.w < 44 || b.h < 44)) add("tap-targets", el, `"${label(el)}" is ${b.w} × ${b.h}, under 44 × 44`);
    }
  }
  if (checks.includes("below-fold")) {
    const buttons = all("button, a[href], input[type=submit], [role=button]");
    const primary = buttons.find(el => /primary|cta|main-action/i.test(el.className) || (el.type === "submit" && el.form))
      || buttons.map(el => [el, box(el).w * box(el).h]).sort((a, b) => b[1] - a[1]).map(x => x[0])[0];
    if (primary && box(primary).y >= innerHeight) add("below-fold", primary, `"${label(primary)}" starts ${box(primary).y - innerHeight} px below the first screen`, null);
  }
  if (checks.includes("dialog-opaque")) {
    for (const el of all("dialog[open], [role=dialog], [aria-modal=true], [role=menu]")) {
      const s = getComputedStyle(el), alpha = s.backgroundColor.match(/rgba?\(([^)]+)\)/);
      const a = alpha ? Number((alpha[1].split(/[,/ ]+/)[3] ?? "1")) : 0;
      if (a < 1 && s.backdropFilter === "none" && s.backgroundImage === "none") add("dialog-opaque", el, `a dialog's surface is ${a === 0 ? "transparent" : "see-through (" + a + ")"}`);
    }
  }
  if (checks.includes("focus-visible")) {
    const before = document.activeElement;
    for (const el of all(CONTROLS).slice(0, 30)) {
      const plain = getComputedStyle(el), was = [plain.outlineStyle, plain.outlineWidth, plain.boxShadow, plain.borderColor, plain.backgroundColor].join("|");
      el.focus({ preventScroll: true });
      if (document.activeElement !== el) continue;
      const s = getComputedStyle(el);
      const ring = s.outlineStyle !== "none" && parseFloat(s.outlineWidth) > 0;
      const now = [s.outlineStyle, s.outlineWidth, s.boxShadow, s.borderColor, s.backgroundColor].join("|");
      if (!ring && now === was && onScreen(box(el))) add("focus-visible", el, `"${label(el)}" shows no focus`);
    }
    if (before && before.focus) before.focus({ preventScroll: true }); else document.activeElement?.blur();
  }
  return out;
};

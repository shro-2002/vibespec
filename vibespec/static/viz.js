/* Influence section: anchor lens, evidence map, accessible table, leave-one-out audit. Only values returned by Qloo are drawn. */
(() => {
  const { el, svg, $ } = VS;
  const W = 920, AX = 175, PX = 640, ROW = 26, HEAD = 34, GAP = 16, TOP = 14;
  const short = (s, n = 36) => (s.length > n ? `${s.slice(0, n - 1)}…` : s);
  const cardId = (d, p) => `card-${d}-${String(p.id).replace(/[^\w-]/g, "_")}`;
  let lens = null;

  const trivial = (dom, anchors) => anchors.length - dom.anchors_ignored.length - Object.keys(dom.anchors_rejected).length <= 1;
  const gapNotes = (dom, names) => [...dom.anchors_ignored.map((a) => `${a}: no signal from Qloo`), ...Object.keys(dom.anchors_rejected).map((a) => `${a}: rejected by Qloo`),
    ...(trivial(dom, names) && dom.selected.length ? ["single usable anchor: share is trivial"] : [])];

  function layout(bp) {
    let y = TOP;
    const groups = VS.DOMAINS.map((d) => {
      const dom = bp.domains[d.key], g = { d, dom, y, picks: [], notes: gapNotes(dom, bp.anchors.map((a) => a.name)) };
      y += HEAD + g.notes.length * 15;
      dom.selected.forEach((p) => { g.picks.push({ p, y: y + ROW / 2 }); y += ROW; });
      if (!dom.selected.length) y += ROW / 2;
      y += GAP;
      return g;
    });
    return { groups, height: y };
  }

  function drawMap(bp) {
    const names = bp.anchors.map((a) => a.name), { groups, height } = layout(bp);
    const ay = (i) => 70 + (i * (height - 140)) / Math.max(names.length - 1, 1);
    const root = svg("svg", { class: "map", viewBox: `0 0 ${W} ${height}`, role: "group", "aria-label": "Influence map: lines connect each anchor to the picks it contributed to, thicker lines mean a larger contribution share" });
    const edges = svg("g"), nodes = svg("g");
    const dimExcept = (fn) => edges.querySelectorAll(".edge").forEach((e) => e.classList.toggle("dim", fn ? !fn(e) : false));
    names.forEach((n, i) => {
      const g = svg("g", { class: "pick", tabindex: "0", role: "button", "aria-label": `Focus on ${n}` });
      g.append(svg("circle", { cx: AX - 24, cy: ay(i), r: 15, fill: VS.ANCHOR_VAR[i] }), svg("text", { x: AX - 46, y: ay(i) + 4, "text-anchor": "end" }, n));
      g.addEventListener("mouseenter", () => dimExcept((e) => e.dataset.anchor === n));
      g.addEventListener("focus", () => dimExcept((e) => e.dataset.anchor === n));
      ["mouseleave", "blur"].forEach((ev) => g.addEventListener(ev, () => dimExcept(null)));
      g.addEventListener("click", () => VS.viz.setLens(lens === n ? null : n));
      nodes.append(g);
    });
    groups.forEach((g) => {
      nodes.append(svg("text", { class: "grp", x: PX - 10, y: g.y + 18 }, g.d.title));
      g.notes.forEach((n, i) => nodes.append(svg("text", { class: "miss", x: PX - 10, y: g.y + 36 + i * 15 }, n)));
      g.picks.forEach(({ p, y }) => {
        const pick = svg("g", { class: "pick", tabindex: "0", role: "button", "aria-label": `${p.name}. Open card` });
        pick.append(svg("circle", { cx: PX, cy: y, r: 4.5, fill: "var(--ink2)" }), svg("text", { x: PX + 14, y: y + 4 }, short(p.name)));
        const mine = () => edges.querySelectorAll(".edge");
        const hi = () => mine().forEach((e) => e.classList.toggle("dim", e.dataset.pick !== p.id));
        pick.addEventListener("mouseenter", hi); pick.addEventListener("focus", hi);
        ["mouseleave", "blur"].forEach((ev) => pick.addEventListener(ev, () => dimExcept(null)));
        pick.addEventListener("click", () => VS.viz.reveal(cardId(g.d.key, p)));
        pick.addEventListener("keydown", (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); VS.viz.reveal(cardId(g.d.key, p)); } });
        nodes.append(pick);
        const triv = trivial(g.dom, names);
        names.forEach((n, i) => {
          const share = p.attribution[n];
          if (!share) return;
          const x0 = AX - 9, x1 = PX - 6, mx = (x0 + x1) / 2;
          edges.append(svg("path", { class: "edge", "data-anchor": n, "data-pick": p.id, d: `M${x0},${ay(i)} C${mx},${ay(i)} ${mx},${y} ${x1},${y}`, stroke: VS.ANCHOR_VAR[i],
            "stroke-width": triv ? 1.6 : Math.max(0.8, share * 11), "stroke-opacity": triv ? 0.5 : 0.62, "stroke-dasharray": triv ? "4 4" : null }));
        });
      });
      if (!g.picks.length) nodes.append(svg("text", { class: "miss", x: PX - 10, y: g.y + HEAD + g.notes.length * 15 + 8 }, "No picks in this section"));
    });
    root.append(edges, nodes);
    return root;
  }

  function table(bp) {
    const names = bp.anchors.map((a) => a.name);
    const rows = VS.DOMAINS.flatMap((d) => bp.domains[d.key].selected.map((p) => el("tr", {}, el("th", { scope: "row" }, p.name), el("td", {}, d.title),
      names.map((n) => el("td", {}, p.attribution[n] != null ? VS.pct(p.attribution[n]) : "no signal")))));
    return el("div", { class: "table-wrap" }, el("table", { class: "maptable" }, el("caption", { class: "sr-only" }, "Contribution share of each anchor to each selected pick"),
      el("thead", {}, el("tr", {}, el("th", { scope: "col" }, "Pick"), el("th", { scope: "col" }, "Section"), names.map((n) => el("th", { scope: "col" }, n)))), el("tbody", {}, rows)));
  }

  function leaveOneOut(bp) {
    const data = bp.anchor_influence.leave_one_out_set_change;
    if (!data || data._skipped) return el("p", { class: "hint" }, "The influence audit was skipped because the call budget ran out.");
    const names = bp.anchors.map((a) => a.name);
    return el("div", { class: "loo" }, VS.DOMAINS.map((d) => el("div", { class: "panel" }, el("h3", {}, d.title),
      names.map((n, i) => {
        const v = (data[d.key] || {})[n], ignored = bp.domains[d.key].anchors_ignored.includes(n);
        const bar = el("div", { class: "meter" }, el("i", {})); bar.firstChild.style.width = `${Math.round((v || 0) * 100)}%`; bar.firstChild.style.background = VS.ANCHOR_VAR[i];
        return el("div", { class: "loo-row" }, el("span", {}, n), bar, el("span", { class: ignored ? "zero" : "" }, v == null ? "n/a" : VS.pct(v)));
      }),
      bp.domains[d.key].anchors_ignored.length ? el("p", { class: "hint" }, `${bp.domains[d.key].anchors_ignored.join(", ")}: removing it changes nothing because Qloo ignored it here.`) : null)));
  }

  VS.viz = {
    section(bp) {
      const names = bp.anchors.map((a) => a.name);
      const bar = el("div", { class: "lens-bar", role: "group", "aria-label": "Focus on an anchor" }, el("button", { type: "button", "aria-pressed": "true", "data-lens": "" }, "All anchors"),
        names.map((n, i) => el("button", { type: "button", "aria-pressed": "false", "data-lens": n }, el("span", { class: "sw" }), n)));
      bar.querySelectorAll(".sw").forEach((s, i) => { s.style.background = VS.ANCHOR_VAR[i]; });
      bar.addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) VS.viz.setLens(b.dataset.lens || null); });
      lens = null;
      return el("section", { class: "lens", id: "influence", "aria-labelledby": "h-lens" }, el("div", { class: "wrap" },
        el("h2", { id: "h-lens" }, "How your anchors shaped this blueprint"),
        el("p", {}, "Lines show the contribution share Qloo reported for each pick. Thicker means a larger share. Dashed lines mean only one anchor was usable there, so the share is always 100% and says nothing."),
        bar, el("a", { class: "skip-map map-only", href: "#soundscape" }, "Skip the map to the recommendations"), el("div", { class: "mapbox map-only" }, drawMap(bp)),
        el("details", { class: "considered" }, el("summary", {}, "View contributions as a table"), el("div", { class: "body" }, table(bp))),
        el("h3", { class: "info-h" }, "If we remove an anchor, how much of the candidate set changes?"),
        el("p", { class: "hint" }, "0% means that anchor had no effect on the candidates. This measures influence on the pool, not the quality of the picks."), leaveOneOut(bp)));
    },
    setLens(name) {
      lens = name;
      document.querySelectorAll(".lens-bar button").forEach((b) => b.setAttribute("aria-pressed", String((b.dataset.lens || null) === name)));
      document.querySelectorAll(".pick-card").forEach((c) => c.classList.toggle("dim", !!name && c.dataset.primary !== name));
      document.querySelectorAll(".map .edge").forEach((e) => e.classList.toggle("dim", !!name && e.dataset.anchor !== name));
    },
    reveal(id) {
      const c = document.getElementById(id);
      if (!c) return;
      c.scrollIntoView({ block: "center" }); c.classList.add("flash"); c.focus({ preventScroll: true }); setTimeout(() => c.classList.remove("flash"), 1600);
    },
    cardId,
  };
})();

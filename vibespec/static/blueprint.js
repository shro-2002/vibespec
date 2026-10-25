/* Blueprint renderer: four sections, each with evidence funnel, picks, uncertainty and rejected alternatives. */
(() => {
  const { el, svg, pct } = VS;
  const ICONS = {
    artist: () => svg("svg", { viewBox: "0 0 32 32", fill: "none", stroke: "currentColor", "stroke-width": "2.2", "stroke-linecap": "round", "aria-hidden": "true" }, ...[4, 9, 14, 19, 24, 29].map((x, i) => svg("path", { d: `M${x},${16 - [3, 8, 5, 11, 6, 3][i]} V${16 + [3, 8, 5, 11, 6, 3][i]}` }))),
    book: () => svg("svg", { viewBox: "0 0 32 32", fill: "none", stroke: "currentColor", "stroke-width": "2.2", "stroke-linejoin": "round", "aria-hidden": "true" }, svg("path", { d: "M16 8c-3-2.5-8-3-12-2v18c4-1 9-.5 12 2 3-2.5 8-3 12-2V6c-4-1-9-.5-12 2zM16 8v18" })),
    brand: () => svg("svg", { viewBox: "0 0 32 32", fill: "none", stroke: "currentColor", "stroke-width": "2.2", "stroke-linejoin": "round", "aria-hidden": "true" }, svg("path", { d: "M13 3h6v4l3 4v17a2 2 0 0 1-2 2h-8a2 2 0 0 1-2-2V11l3-4zM10 16h12" })),
    place: () => svg("svg", { viewBox: "0 0 32 32", fill: "none", stroke: "currentColor", "stroke-width": "2.2", "stroke-linejoin": "round", "aria-hidden": "true" }, svg("path", { d: "M16 29s9-8 9-15a9 9 0 0 0-18 0c0 7 9 15 9 15z" }), svg("circle", { cx: 16, cy: 14, r: 3.2 })),
  };
  const slug = (s) => s.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  const usable = (dom, n) => n - dom.anchors_ignored.length - Object.keys(dom.anchors_rejected).length;

  function facts(domain, p) {
    const pr = p.props, bits = [];
    if (domain === "place") {
      if (pr.address) bits.push(pr.address);
      if (pr.price_level) bits.push("$".repeat(pr.price_level));
      if (pr.business_rating) bits.push(`rated ${Number(pr.business_rating).toFixed(1)}`);
    }
    if (domain === "book") { if (pr.publication_year) bits.push(`published ${pr.publication_year}`); if (pr.page_count) bits.push(`${pr.page_count} pages`); }
    if (domain === "brand" && pr.price_range_usd_min != null) bits.push(`indicative $${pr.price_range_usd_min} to $${pr.price_range_usd_max ?? "?"} (Qloo metadata, not a quote)`);
    if (domain === "brand" && pr.industry) bits.push(pr.industry);
    return bits.join(", ");
  }
  function constraintChips(p) {
    const m = /Constraints met(?: \(where data existed\))?: (.*?)\.(?: |$)/.exec(p.why || "");
    return [...(m ? m[1].split("; ") : []).map((t) => el("span", { class: "st ok" }, t)), ...p.unverified.map((t) => el("span", { class: "st unk" }, t))];
  }
  function attribution(p, names, single) {
    const total = names.reduce((s, n) => s + (p.attribution[n] || 0), 0);
    if (!total) return el("p", { class: "hint" }, "Qloo returned no per-anchor attribution for this pick.");
    const bar = el("div", { class: "attr", role: "img", "aria-label": `Anchor contribution: ${names.filter((n) => p.attribution[n]).map((n) => `${n} ${pct(p.attribution[n])}`).join(", ")}` });
    names.forEach((n, i) => { if (p.attribution[n]) { const seg = el("i", {}); seg.style.width = `${(p.attribution[n] / total) * 100}%`; seg.style.background = VS.ANCHOR_VAR[i]; bar.append(seg); } });
    const shares = el("div", { class: "shares" }, names.filter((n) => p.attribution[n]).map((n) => { const i = names.indexOf(n), sw = el("span", { class: "sw" }); sw.style.background = VS.ANCHOR_VAR[i]; return el("span", {}, sw, `${n} ${pct(p.attribution[n])}`); }));
    return el("div", {}, bar, shares, single ? el("p", { class: "hint" }, "Only one anchor was usable here, so 100% is trivial.") : null);
  }
  function block(title, items, cls, empty, phase) {
    const list = items && items.length ? items : empty ? [empty] : [];
    return list.length ? el("div", { class: `fit-row ${cls}${items && items.length ? "" : " none"}` }, el("b", {}, title, phase ? el("span", { class: "phase ph-fit" }, phase) : null), el("ul", {}, list.map((x) => el("li", {}, x)))) : null;
  }
  function card(domain, p, names, single) {
    const st = p.suitability || { label: "", use: "", fit: [], verified: [], unknowns: p.unverified, gaps: [], verdict: "unverified", next_action: "" };
    const lead = /lead/i.test(st.label);
    return el("article", { class: "pick-card", id: VS.viz.cardId(domain, p), tabindex: "-1", "data-primary": p.primary_anchor || "" },
      el("h4", {}, p.name),
      facts(domain, p) ? el("p", { class: "facts" }, facts(domain, p)) : null,
      el("p", { class: `verdict ${lead ? "lead" : st.verdict}` }, st.label),
      st.use ? el("p", { class: "use" }, el("b", {}, "Use: "), st.use) : null,
      el("div", { class: "fit-row aff" }, el("b", {}, "Why Qloo surfaced it", el("span", { class: "phase ph-discover" }, "Discovery")), p.surfaced ? el("p", { class: "hint" }, p.surfaced) : null, attribution(p, names, single)),
      block("Why it fits your brief", st.fit, "good", "No positive fit evidence yet", "Fit check"),
      block("In Qloo data, not confirmed", st.verified, "ver"),
      block("Missing fit evidence", st.unknowns, "unk"),
      block("Check before using", st.gaps, "gap"),
      el("div", { class: "status" }, constraintChips({ ...p, unverified: [] })),
      st.next_action ? el("p", { class: "next" }, el("b", {}, "Next step: "), st.next_action) : null,
      p.alternative ? el("p", { class: "alt" }, el("b", {}, "If this falls through: "), `${p.alternative.name} (${p.alternative.label.toLowerCase()})`) : null);
  }
  function funnel(dom) {
    const pool = Math.max(dom.pool_size, 1), passed = dom.pool_size - dom.rejected.length, fits = passed - (dom.off_brief || []).length;
    const row = (cls, text, n) => { const m = el("div", { class: "meter" }, el("i", {})); m.firstChild.style.width = `${(n / pool) * 100}%`; return el("div", { class: `fun-row ${cls}` }, m, el("span", {}, text)); };
    return el("div", { class: "funnel", role: "group", "aria-label": "Evidence funnel" }, row("top", `${dom.pool_size} retrieved from Qloo`, dom.pool_size), row("mid", `${passed} met your constraints`, passed), row("mid", `${Math.max(fits, 0)} fit your brief`, Math.max(fits, 0)), row("low", `${dom.selected.length} selected`, dom.selected.length));
  }
  function considered(dom) {
    const off = dom.off_brief || [];
    if (!dom.rejected.length && !dom.outranked.length && !off.length) return null;
    return el("details", { class: "considered", open: off.length ? true : null }, el("summary", {}, `Considered but not chosen (${off.length} off-brief, ${dom.rejected.length} failed constraints, ${dom.outranked.length} backups)`),
      el("div", { class: "body" },
        off.length ? el("div", {}, el("h4", {}, "Did not fit your brief"), el("ul", { class: "rowlist" }, off.slice(0, 10).map((r) => el("li", {}, el("b", {}, r.name), ` ${r.label}`, el("div", { class: "reasons" }, r.reasons.map((x) => el("span", {}, x))))))) : null,
        el("div", {}, el("h4", {}, "Rejected by your constraints"), dom.rejected.length ? el("ul", { class: "rowlist" }, dom.rejected.slice(0, 12).map((r) => el("li", {}, el("b", {}, r.name), el("div", { class: "reasons" }, r.reasons.map((x) => el("span", {}, x)))))) : el("p", { class: "hint" }, "Nothing was rejected."),
          dom.rejected.length > 12 ? el("p", { class: "hint" }, `${dom.rejected.length - 12} more in the JSON export.`) : null),
        el("div", {}, el("h4", {}, "Backups that fit"), dom.outranked.length ? el("ul", { class: "rowlist" }, dom.outranked.map((o) => el("li", {}, el("b", {}, o.name), ` ranked #${o.rank_in_query}`))) : el("p", { class: "hint" }, "None to show."))));
  }
  function section(bp, d) {
    const dom = bp.domains[d.key], names = bp.anchors.map((a) => a.name), single = usable(dom, names.length) <= 1;
    const notices = [...dom.anchors_ignored.map((a) => `${a} was accepted by Qloo but contributed nothing here. These picks reflect ${names.filter((n) => n !== a && !dom.anchors_ignored.includes(n)).join(" and ") || "no anchor"} only.`),
      ...Object.entries(dom.anchors_rejected).map(([a, why]) => `${a}: ${why}.`)];
    return el("section", { class: "bp-sec", id: d.id, "aria-labelledby": `h-${d.id}` }, el("div", { class: "wrap" },
      el("div", { class: `sec-head ${d.cls}` }, el("div", {}, el("h2", { id: `h-${d.id}` }, ICONS[d.key](), d.title), el("p", {}, d.blurb)), funnel(dom)),
      notices.map((n) => el("p", { class: "notice" }, el("b", {}, "Signal gap. "), n)),
      bp.trace.filter((t) => t.tool === "revise_query" && t.arg === d.key).map((t) => el("p", { class: "rev-note" }, el("b", {}, "Agent revision. "), String(t.outcome).replace(/^\w+: /, "").replace(" -> ", ": "))),
      dom.selected.length ? el("div", { class: "picks" }, dom.selected.map((p) => card(d.key, p, names, single)))
        : el("div", { class: "empty" }, dom.anchors_rejected && Object.keys(dom.anchors_rejected).length === names.length ? "Qloo found no usable signal for any of your anchors in this section, so there are no recommendations." : dom.rejected.length ? "Every candidate failed your constraints. Relax them and rebuild." : "No recommendations came back for this section."),
      considered(dom)));
  }
  function download(name, type, text) {
    const url = URL.createObjectURL(new Blob([text], { type }));
    const a = el("a", { href: url, download: name }); document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  function exportRow(bp) {
    const { markdown, ...plain } = bp;
    return el("div", { class: "export", id: "export" }, el("button", { class: "btn", type: "button", onclick: () => download("vibespec-blueprint.md", "text/markdown", markdown) }, "Download Markdown"),
      el("button", { class: "btn ghost", type: "button", onclick: () => download("vibespec-blueprint.json", "application/json", JSON.stringify(plain, null, 2)) }, "Download JSON"),
      el("button", { class: "btn ghost", type: "button", onclick: () => window.print() }, "Print or save as PDF"));
  }

  VS.blueprint = {
    render(bp) {
      const names = bp.anchors.map((a) => a.name), doms = VS.DOMAINS.map((d) => bp.domains[d.key]);
      const sum = (f) => doms.reduce((s, d) => s + f(d), 0), prov = bp.provenance || {};
      const stats = [[sum((d) => d.selected.length), "picks selected"], [sum((d) => d.pool_size), "candidates examined"], [sum((d) => d.rejected.length) + sum((d) => (d.off_brief || []).length), "rejected as unfit or off-brief"],
        [(prov.live_calls || 0) + (prov.cache_hits || 0), `Qloo requests (${prov.live_calls || 0} live)`]];
      const sel = (d) => bp.domains[d.key].selected;
      const lines = VS.DOMAINS.map((d) => {
        const ps = sel(d), fit = ps.filter((p) => (p.suitability || {}).verdict === "aligned").length, leads = ps.filter((p) => /lead/i.test((p.suitability || {}).label || "")).length;
        const rev = bp.trace.filter((t) => t.tool === "revise_query" && t.arg === d.key).length;
        return `${d.title}: ${ps.length} ${ps.length === 1 ? "pick" : "picks"}, ${fit} with positive fit evidence${leads ? `, ${leads} ${leads === 1 ? "lead" : "leads"} to verify` : ""}${rev ? `; the agent revised this section ${rev === 1 ? "once" : `${rev} times`}` : ""}.`;
      });
      const gapCount = {};
      VS.DOMAINS.forEach((d) => sel(d).forEach((p) => ((p.suitability || {}).gaps || []).forEach((g) => { const k = g.split(":")[0]; gapCount[k] = (gapCount[k] || 0) + 1; })));
      const checks = Object.entries(gapCount).sort((x, y) => y[1] - x[1]).slice(0, 5).map(([g, n]) => `${g} (${n} ${n === 1 ? "pick" : "picks"})`);
      const loc = bp.brief.constraints.hotel_lat != null ? `Distances are straight-line from ${bp.brief.constraints.hotel_lat.toFixed(4)}, ${bp.brief.constraints.hotel_lon.toFixed(4)}.` : "No exact hotel location was given, so places are city-level leads with no walking times.";
      const summary = el("section", { class: "summary reveal", "aria-labelledby": "h-sum" }, el("div", { class: "wrap" }, el("div", { class: "cover" },
        el("p", { class: "doc" }, "Cultural experience proposal"),
        el("h1", { id: "h-sum", tabindex: "-1" }, bp.brief.concept || "Boutique hotel"),
        el("p", { class: "meta" }, `${bp.brief.city}. Prepared ${new Date().toLocaleDateString(undefined, { year: "numeric", month: "long", day: "numeric" })} from Qloo data by a rule-based agent. ${loc}`),
        el("div", { class: "anchor-row" }, names.map((n, i) => { const t = el("span", { class: "tag" }, n); t.style.background = VS.ANCHOR_VAR[i]; return t; })),
        el("div", { class: "execsum" },
          el("div", {}, el("h2", {}, "Summary"), el("ul", {}, lines.map((x) => el("li", {}, x)))),
          checks.length ? el("div", { class: "checks" }, el("h2", {}, "Before you act"), el("ul", {}, checks.map((x) => el("li", {}, x)))) : null),
        el("div", { class: "legend", "aria-label": "How to read this proposal" }, el("span", {}, el("span", { class: "phase ph-discover" }, "Discovery"), " what Qloo found"),
          el("span", {}, el("span", { class: "phase ph-fit" }, "Fit check"), " evidence for your brief"), el("span", {}, el("span", { class: "phase ph-revise" }, "Revision"), " where the agent re-queried")),
        el("div", { class: "stats" }, stats.map(([n, l]) => el("div", { class: "stat" }, el("b", {}, n), el("span", {}, l)))), exportRow(bp))));
      const nav = el("nav", { class: "bpnav", "aria-label": "Blueprint sections" }, el("div", { class: "wrap" }, el("a", { href: "#influence" }, "Anchor influence"),
        VS.DOMAINS.map((d) => el("a", { href: `#${d.id}` }, d.title)), el("a", { href: "#notes" }, "Evidence notes"), el("a", { href: "#trace" }, "Agent trace")));
      const budgetRows = bp.budget.indicative_qloo_brand_price_ranges;
      const notes = el("section", { class: "info", id: "notes", "aria-labelledby": "h-notes" }, el("div", { class: "wrap" }, el("h2", { id: "h-notes" }, "What is verified, and what is not"),
        el("p", {}, bp.budget.disclaimer),
        budgetRows.length ? el("div", { class: "table-wrap" }, el("table", { class: "maptable" }, el("caption", { class: "sr-only" }, "Amenity brand price indications"), el("thead", {}, el("tr", {}, ["Brand", "Qloo indicative low", "Qloo indicative high", "Against your assumption"].map((h) => el("th", { scope: "col" }, h)))),
          el("tbody", {}, budgetRows.map((r) => el("tr", {}, el("th", { scope: "row" }, r.brand), el("td", {}, r.qloo_indicative_usd_min != null ? `$${r.qloo_indicative_usd_min}` : "not provided"), el("td", {}, r.qloo_indicative_usd_max != null ? `$${r.qloo_indicative_usd_max}` : "not provided"), el("td", {}, r.fit_vs_user_assumption)))))) : null,
        el("ul", {}, bp.missing_data.map((m) => el("li", {}, m)))));
      const trace = el("section", { class: "info trace", id: "trace", "aria-labelledby": "h-trace" }, el("div", { class: "wrap" }, el("h2", { id: "h-trace" }, "Agent decision trace"),
        el("p", {}, "Each step was chosen by explicit rules from the evidence so far. There is no language model in the loop."),
        el("ol", {}, bp.trace.map((t) => el("li", {}, el("b", {}, `${t.step}. ${t.tool}${t.arg ? ` (${t.arg})` : ""}`), el("span", {}, t.outcome)))),
        el("p", { class: "provenance" }, `Data: ${prov.live_calls || 0} live Qloo calls, ${prov.cache_hits || 0} served from this server's private cache (real earlier Qloo responses).`), exportRow(bp)));
      return [summary, nav, VS.viz.section(bp), ...VS.DOMAINS.map((d) => section(bp, d)), notes, trace];
    },
  };
})();

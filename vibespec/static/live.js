/* Live activity panel. Everything shown is derived from real job events; nothing is simulated. */
(() => {
  const { el, $ } = VS;
  const STAGES = [
    { tool: "resolve_anchor", title: "Resolve anchors", desc: "Match each brand to a Qloo entity", ph: "discover" },
    { tool: "query_domain", title: "Retrieve from Qloo", desc: "Music, books, brands and places in parallel", ph: "discover" },
    { tool: "validate_constraints", title: "Check fit with your brief", desc: "Constraints, then suitability for this hotel", ph: "fit" },
    { tool: "revise_query", title: "Revise from evidence", desc: "Only when too few candidates fit", optional: true, ph: "revise" },
    { tool: "audit_influence", title: "Audit anchor influence", desc: "Re-query without each anchor", ph: "evidence" },
    { tool: "finish", title: "Assemble proposal", desc: "Rank, balance and explain", ph: "evidence" },
  ];
  const PH = { discover: "Discovery", fit: "Fit check", revise: "Revision", evidence: "Evidence" };
  const DOMAIN_NAME = Object.fromEntries(VS.DOMAINS.map((d) => [d.key, d.title]));
  let timer = null, startedAt = 0, logOpen = false;

  const parts = {
    resolved: (o) => /^resolved '(.+?)' -> '(.+?)' \((.+)\)$/.exec(o || ""),
    retrieved: (o) => (o || "").split("; ").map((s) => /^(\w+): (\d+) candidates, effective anchors (\d+)\/(\d+), rejected (\d+), ignored (\d+)/.exec(s)).filter(Boolean),
    validated: (o) => /^(\w+): (\d+) accepted, (\d+) rejected, (\d+) with unverifiable[^,]*(?:, (\d+) off-brief, (\d+) with positive)?/.exec(o || ""),
    revised: (o) => /^(\w+): (.+?); (\d+) new candidates; now (\d+) accepted/.exec(o || ""),
  };

  function stageStates(job) {
    const finished = ["done", "failed", "timeout"].includes(job.status);
    const last = job.steps.length ? job.steps[job.steps.length - 1].tool : null;
    const order = STAGES.map((s) => s.tool);
    return STAGES.map((s) => {
      const mine = job.steps.filter((x) => x.tool === s.tool);
      const running = mine.some((x) => x.phase !== "done");
      const reachedLater = job.steps.some((x) => order.indexOf(x.tool) > order.indexOf(s.tool));
      if (job.status === "failed" || job.status === "timeout") return running || (mine.length && last === s.tool) ? "failed" : mine.length ? "done" : "pending";
      if (running) return "active";
      if (mine.length) return job.status === "queued" || (!finished && last === s.tool && !reachedLater) ? "active" : "done";
      if (s.optional && (reachedLater || finished)) return "skipped";
      return "pending";
    });
  }
  const label = { active: "Working", done: "Done", failed: "Stopped here", pending: "Waiting", skipped: "Not needed: enough candidates passed" };

  function stagesList(job) {
    const states = stageStates(job);
    return el("ol", { class: "stages", "aria-label": "Agent stages" }, STAGES.map((s, i) => el("li", { class: `stage ${states[i] === "skipped" ? "pending" : states[i]}` },
      el("span", { class: "dot", "aria-hidden": "true" }), el("div", {}, el("b", {}, s.title, el("span", { class: `phase ph-${s.ph}` }, PH[s.ph])), el("small", {}, states[i] === "pending" || states[i] === "skipped" ? `${label[states[i]]}${states[i] === "pending" ? `: ${s.desc}` : ""}` : `${label[states[i]]}: ${s.desc}`)))));
  }

  function anchorsPanel(job) {
    const done = job.steps.filter((s) => s.tool === "resolve_anchor" && s.phase === "done");
    if (!done.length) return null;
    return el("section", { class: "panel" }, el("h3", {}, "Resolved anchors"), el("div", { class: "tiles" }, done.map((s) => {
      const m = parts.resolved(s.outcome);
      return m ? el("div", { class: "tile" }, el("b", {}, m[2]), `Matched ${m[3]}${m[1] !== m[2] ? ` from "${m[1]}"` : ""}`) : el("div", { class: "tile" }, el("b", {}, s.arg), s.outcome);
    })));
  }

  function retrievalPanel(job) {
    const step = job.steps.find((s) => s.tool === "query_domain");
    if (!step) return null;
    const rows = step.phase === "done" ? parts.retrieved(step.outcome) : [];
    return el("section", { class: "panel" }, el("h3", {}, "Retrieval from Qloo"), el("div", { class: "tiles" }, VS.DOMAINS.map((d) => {
      const r = rows.find((x) => x[1] === d.key);
      if (!r) return el("div", { class: "tile wait" }, el("b", {}, d.title), step.phase === "done" ? "No result reported" : "Waiting for Qloo");
      const eff = `${r[3]} of ${r[4]} anchors usable`;
      return el("div", { class: "tile" }, el("b", {}, d.title), `${r[2]} candidates, ${eff}${+r[6] ? `, ${r[6]} ignored by Qloo` : ""}`);
    })));
  }

  function validationPanel(job) {
    const done = job.steps.filter((s) => s.tool === "validate_constraints" && s.phase === "done");
    if (!done.length) return null;
    return el("section", { class: "panel" }, el("h3", {}, "Constraint validation"), el("div", { class: "tiles" }, done.map((s) => {
      const m = parts.validated(s.outcome);
      return m ? el("div", { class: "tile" }, el("b", {}, DOMAIN_NAME[m[1]] || m[1]), `${m[2]} fit the brief, ${m[3]} failed constraints${m[5] ? `, ${m[5]} off-brief` : ""}${m[6] ? `, ${m[6]} with positive evidence` : ""}`) : el("div", { class: "tile" }, s.outcome);
    })));
  }

  function revisionPanel(job) {
    const revs = job.steps.filter((s) => s.tool === "revise_query");
    if (!revs.length) return null;
    return el("section", { class: "panel" }, el("h3", {}, "Evidence-triggered revisions"), revs.map((s) => {
      const m = s.phase === "done" ? parts.revised(s.outcome) : null;
      return el("p", { class: "revision" }, m ? `${DOMAIN_NAME[m[1]] || m[1]}: ${m[2]}. Result: ${m[3]} new candidates, ${m[4]} now pass.` : s.phase === "done" ? s.outcome : `Revising ${DOMAIN_NAME[s.arg] || s.arg}…`);
    }));
  }

  function logPanel(job) {
    const d = el("details", { class: "log" }, el("summary", {}, `Every step so far (${job.steps.length})`),
      el("ol", {}, job.steps.map((s) => el("li", {}, `${s.tool}${s.arg ? `(${s.arg})` : ""}, ${s.phase === "done" ? `${s.outcome} (${s.t}s)` : "running"}`))));
    d.open = logOpen;
    d.addEventListener("toggle", () => { logOpen = d.open; });
    return d;
  }

  function render(job) {
    const waiting = job.status === "queued";
    $("#live").replaceChildren(el("div", { class: "wrap" },
      el("div", { class: "live-head" }, el("h2", {}, waiting ? "Waiting for a free slot" : "Building your blueprint"),
        el("span", { class: "badge" }, "Rule-based agent loop, no language model"), el("span", { class: "timer", id: "timer" }, "")),
      waiting ? el("p", {}, `Queued behind ${job.queued_ahead} run(s). It starts automatically.`) : null,
      el("div", { class: "live-grid" }, stagesList(job),
        el("div", { class: "panels" }, anchorsPanel(job), retrievalPanel(job), validationPanel(job), revisionPanel(job), logPanel(job)))));
    tick();
  }
  const tick = () => { const t = $("#timer"); if (t) t.textContent = `${Math.round((Date.now() - startedAt) / 1000)}s elapsed`; };

  VS.live = {
    begin() { startedAt = Date.now(); logOpen = false; clearInterval(timer); timer = setInterval(tick, 1000); render({ status: "queued", steps: [], queued_ahead: 0 }); $("#live h2").textContent = "Submitting"; },
    update: render,
    end() { clearInterval(timer); },
    alert(title, message, actions) {
      clearInterval(timer);
      $("#live").replaceChildren(el("div", { class: "wrap" }, el("div", { class: "alert", role: "alert" }, el("h3", {}, title), el("p", {}, message),
        el("div", { class: "row" }, actions.map((a) => el("button", { class: `btn small${a.ghost ? " ghost" : ""}`, type: "button", onclick: a.run }, a.label))))));
    },
  };
})();

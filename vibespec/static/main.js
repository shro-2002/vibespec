/* Orchestration: views, job submission, polling, confirmation, errors. */
(() => {
  const { el, $ } = VS;
  const setView = (v) => { document.body.dataset.view = v; };
  let busy = false;

  async function api(path, data) {
    const r = await fetch(path, data ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) } : undefined);
    let j = {};
    try { j = await r.json(); } catch (e) { /* non-JSON error page */ }
    return { ok: r.ok, status: r.status, j };
  }
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const toForm = () => { setView("landing"); window.scrollTo(0, $("#compose").offsetTop - 70); };
  const actions = (retry) => [{ label: "Try again", run: retry }, { label: "Edit brief", ghost: true, run: toForm }];

  function confirmView(bp, retry) {
    VS.live.end();
    const groups = bp.confirmations_needed.map((c) => el("fieldset", { class: "step" }, el("legend", {}, `\u201c${c.query}\u201d: ${c.note}`),
      c.candidates.length ? el("div", { class: "choice-list" }, c.candidates.map((cand) => el("label", { class: "tile choice" }, el("input", { type: "radio", name: `c_${c.query}`, value: cand.id }), ` ${cand.name}${cand.disambiguation ? `, ${cand.disambiguation}` : ""}`)))
        : el("p", { class: "hint" }, "Qloo returned no entity. Edit the brief and try a different spelling.")));
    $("#live").replaceChildren(el("div", { class: "wrap" }, el("div", { class: "panel" }, el("h3", {}, "Confirm your anchors"),
      el("p", {}, "These names did not match a Qloo entity exactly, so the agent stopped instead of guessing."), groups,
      el("div", { class: "row" }, el("button", { class: "btn small", type: "button", onclick: () => {
        bp.confirmations_needed.forEach((c) => { const v = document.querySelector(`input[name="c_${CSS.escape(c.query)}"]:checked`); if (v) VS.confirmed[c.query] = v.value; });
        retry();
      } }, "Confirm and rebuild"), el("button", { class: "btn small ghost", type: "button", onclick: toForm }, "Edit brief")))));
  }

  async function run() {
    if (busy || !VS.form.validate()) return;
    busy = true;
    const body = VS.form.body();
    $("#run-title").textContent = body.concept; $("#run-sub").textContent = VS.form.summary();
    $("#result").replaceChildren(); setView("run"); window.scrollTo(0, 0);
    VS.live.begin();
    try {
      const sub = await api("/api/jobs", body);
      if (!sub.ok) return VS.live.alert("The brief could not be submitted", sub.j.error || `The server answered ${sub.status}.`, actions(run));
      let misses = 0;
      for (;;) {
        await sleep(1200);
        let p;
        try { p = await api(`/api/jobs/${sub.j.job_id}`); misses = 0; } catch (e) { if (++misses > 5) return VS.live.alert("Lost connection", "The browser could not reach the server. Check your connection and try again.", actions(run)); continue; }
        if (p.status === 429) { await sleep(2000); continue; }
        if (p.status === 404) return VS.live.alert("The run was lost", "The server restarted or the run expired. Nothing was saved. Try again.", actions(run));
        const job = p.j;
        if (["queued", "running"].includes(job.status)) { VS.live.update(job); continue; }
        VS.live.update(job); VS.live.end();
        if (job.status === "timeout") return VS.live.alert("The run ran out of time", "Qloo may be slow right now. Your brief was not lost; try again in a minute.", actions(run));
        if (job.status === "failed" || !job.result) return VS.live.alert("The run stopped", job.error || "The agent could not finish this brief.", actions(run));
        if (job.result.status === "needs_confirmation") return confirmView(job.result, run);
        if (job.result.status !== "complete") return VS.live.alert("The run stopped", job.result.error || "The agent could not finish this brief.", actions(run));
        $("#result").replaceChildren(...VS.blueprint.render(job.result)); setView("result"); window.scrollTo(0, 0);
        const h = $("#h-sum"); if (h) h.focus({ preventScroll: true });
        return;
      }
    } catch (e) {
      VS.live.alert("Something went wrong", "An unexpected error stopped the run. Try again.", actions(run));
    } finally { busy = false; }
  }
  $("#f").addEventListener("submit", (e) => { e.preventDefault(); run(); });
  $("#edit").addEventListener("click", toForm);
})();

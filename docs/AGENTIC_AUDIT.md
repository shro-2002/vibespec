# Agentic eligibility audit (rules read 2026-10-25 at qloo.devpost.com/rules)

## What the rules require
- Build a working application that integrates the Qloo API and either (a) functions as an agentic tool, (b) is built with an agent framework, or (c) integrates Qloo into an existing agent.
- Stage 1 (pass/fail): reasonably fits the theme ("Agents, but with taste") and reasonably applies the required API.
- Stage 2 (equal weights): Technological Implementation (how thoroughly and skillfully Qloo is used; non-trivial working code), Design (complete, coherent product), Potential Impact, Quality of the Idea.
- Submission needs a functional demo link, a public repo with a detectable open-source license (shown in the About section), a text description, and free unrestricted access for judges until judging ends (2026-11-05). The rules also say judging may use automated AI-driven analysis, and that judges need not run the project.
- Not in the rules: a mandatory LLM, a specific framework, or an autonomy threshold.

## What VibeSpec actually is
A bounded, rule-based tool-selection and revision loop. Observable agentic properties (all in code and traced in every blueprint):
1. Goal in, structured deliverable out; the user does not choose tool calls.
2. State-dependent tool selection: resolve anchors -> halt for human confirmation when ambiguous -> query domains -> validate -> revise -> audit -> assemble (`vibespec/agent.py: next_action`).
3. Evidence-triggered revision: the revision type is chosen from why candidates were rejected (price cap -> server-side filter; year -> filter; otherwise next page). Measured live: 0/20 acceptable places became 15 after one revision.
4. Handles tool failure and silent tool misbehaviour (anchor accepted but ignored) by disclosing it, never substituting.
5. Hard bounds: 40 steps, 2 revisions per domain, per-run call budget, job deadline, human confirmation gate.
It is NOT: an LLM planner, autonomous reasoning, open-ended, or learning. The planner has no model; goal text is keyword-parsed for domain emphasis only. Do not describe it otherwise (README, Devpost text, demo).

## Verdict
- Rule (a): credible but at the lenient end. A judge reading "agentic tool" as "takes a goal, chooses and sequences tool calls, observes results, and revises" will accept it. A judge expecting an LLM agent will call it a pipeline with branches. The same finding applied to the earlier Territory project's audit.
- Stage 1: likely PASS if the demo shows the live decision trace and a revision happening. Weakest moment: a brief where no revision is triggered looks like a fixed sequence of four queries. Demo brief should include constraints that force a revision (the demo preset does).
- Stage 2 Technological Implementation: strong on Qloo depth (search + insights, four entity types, multi-anchor signals, location, server-side filters, explainability, leave-one-out influence audit, detection of silently ignored anchors). Unused Qloo features: tags/audiences/demographics/heatmaps.
- Risk that matters more than "LLM or not": the human preference evaluation is still pending. Do not claim quality gains.

## Smallest improvements that would strengthen the claim (recommendations only, none implemented)
1. **Disclose precisely** (zero code): call it a "bounded, policy-driven agent loop"; show the trace in the demo; state no LLM planner.
2. **Evidence-driven anchor fallback** (≈½ day, uses Qloo more deeply): when an anchor is ignored in a domain (Aesop in books), retry that domain with the anchor's own Qloo tags as `signal.interests.tags` and disclose the substitution. A 1-call probe returned 200 with 10 results for Aesop's brand tags on books; whether the results are meaningful is untested. This is a genuine new decision branch driven by Qloo evidence and fixes the known weakness.
3. **Optional LLM interpreter behind the same legal-action gate** (≈1 day, only if an LLM is available to judges at no cost to you): one structured call turns free-text goals/constraints into the existing `Constraints` + domain emphasis (schema-validated, keyword parser as fallback), optionally letting the model rank which legal next action to take. Keep disabled by default: it needs an LLM key, adds latency/cost, and the demo must not depend on it.
4. Not recommended: adopting an agent framework or multi-agent setup. It adds dependencies and risk without changing what judges can verify.

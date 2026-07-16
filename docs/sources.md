# Sources & honest research map

Every claim in this repo is grounded in the work below. Primary/authoritative sources are marked
**[P]**; secondary/commentary or preprints-not-yet-reviewed are marked **[S]**. Where the
literature is thin or contested, this file says so — the point of the repo is an honest frame, not a
novelty claim.

## Classical organizational theory (the top-down side)

- **[P] Mintzberg — organizational configurations & coordination mechanisms.**
  https://www.myorganisationalbehaviour.com/mintzbergs-organizational-configurations/ ·
  https://www.mindtools.com/apfv1rk/mintzbergs-organizational-configurations/
- **[P] Span of control.** https://en.wikipedia.org/wiki/Span_of_control
- **[P] Conway's law.** https://en.wikipedia.org/wiki/Conway%27s_law
- **[P] Separation of duties (SoD) / internal control (SOX/COSO lineage).**
  https://en.wikipedia.org/wiki/Separation_of_duties · https://www.techtarget.com/whatis/definition/segregation-of-duties-SoD
- **[P] Goodhart's law / metric gaming.** https://kpitree.co/guides/frameworks/goodharts-law ·
  https://explainx.ai/blog/specification-gaming-goodharts-law-ai-metrics
- **[P] Burns & Stalker — mechanistic vs organic (contingency theory).**
  https://www.valuebasedmanagement.net/methods_burns_mechanistic_organic_systems.html
- **[P] Greiner — growth stages / the crisis at each phase.** https://www.mindtools.com/aks7u4n/the-greiner-curve/ ·
  https://mbaknol.com/strategic-management/greiners-model-of-organizational-growth-phases-of-organizational-growth-and-crisis/
- **[P] McChrystal — Team of Teams (shared consciousness + empowered execution).**
  https://www.mcchrystalgroup.com/about/team-of-teams/empowered-execution
- **[P] Galbraith Star Model; Drucker MBO / OKR; RACI.**
  https://strategicmanagementinsight.com/tools/galbraiths-star-model-explained/ ·
  https://mooncamp.com/glossary/management-by-objectives-mbo · https://en.wikipedia.org/wiki/Responsibility_assignment_matrix

## Agent engineering (the bottom-up side the industry named)

- **[P] Context engineering.** Anthropic — Effective context engineering for AI agents.
  https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents
- **[P] Harness engineering.** Birgitta Böckeler (Thoughtworks), on martinfowler.com, 2026-04-02.
  https://martinfowler.com/articles/harness-engineering.html
- **[S] Loop engineering** (term named 2026-06 by Addy Osmani; lineage Boris Cherny / Peter
  Steinberger). Overview: https://www.codecentric.de/en/knowledge-hub/blog/loop-harness-context-engineering-explained ·
  https://datasciencedojo.com/blog/agentic-loops-explained-from-react-to-loop-engineering-2026-guide/
- **[P] AIOS — LLM Agent Operating System** (Mei et al., COLM 2025). https://arxiv.org/abs/2403.16971
- **[P] CoALA — Cognitive Architectures for Language Agents** (Sumers/Yao et al., TMLR 2024).
  https://arxiv.org/abs/2309.02427
- **[P] Anthropic multi-agent research system** (orchestrator-worker; the ~15× token cost).
  https://www.anthropic.com/engineering/multi-agent-research-system
- **[S] awesome-harness-engineering** (community field-list). https://github.com/ai-boost/awesome-harness-engineering
- **[S] LangGraph durable execution / agent middleware.** https://www.langchain.com/blog/langchain-langgraph-1dot0

## "Agents as an organization / company" — advocates

- **[P] Minsky — The Society of Mind** (intelligence from many simple agents in agencies).
  https://en.wikipedia.org/wiki/Society_of_Mind
- **[P] MetaGPT** — "Code = SOP(Team)"; encodes a software company. https://arxiv.org/abs/2308.00352
- **[P] ChatDev** — a virtual chat-driven software company. https://arxiv.org/abs/2307.07924 ·
  https://github.com/OpenBMB/ChatDev
- **[P] CrewAI** — declarative role/goal/backstory + hierarchical process with a manager.
  https://docs.crewai.com/en/learn/hierarchical-process
- **[P] Generative Agents (Stanford, Smallville)** — emergent social coordination. https://arxiv.org/abs/2304.03442
- **[S] Andrew Ng — agentic design patterns** (multi-agent collaboration as one of four).
  https://www.deeplearning.ai/the-batch/
- **[S] Industry "AI-native org" writing** — Sequoia/Dorsey ("company as mini-AGI");
  Hoffman *Superagency*; Salesforce Agentforce / Lindy ("digital workforce").
  https://sequoiacap.com/article/from-hierarchy-to-intelligence/ · https://www.superagency.ai/

## The nearest prior work to a three/four-way synthesis — and its gap

- **[S] Organizational Control Layer** (arXiv 2606.04306) — governance/roles enforced at the runtime
  execution boundary with feedback control. **Closest to org × harness × loop**, but its
  organizational side draws on MAS-institutional theory (Ferber/Horling/Hübner), **not** classical
  management theory (Mintzberg/Greiner/span/SoD).
- **[S] "Multi-Agent Systems Should be Treated as Principal-Agent Problems"** (arXiv 2601.23211) —
  the most serious management-theory application, but limited to **agency theory** and it does not
  descend to harness/loop implementation.
- **[S] ADAS / Darwin Gödel Machine** (arXiv 2505.22954) — automated design of agentic systems
  (harness + loop), but organizational structure stays an implicit search variable, not theorized.

**Honest assessment.** Harness×loop is an established, crystallizing pair (Context→Harness→Loop). The
organization×agents link exists but is **almost entirely principal-agent theory** — a search for
Mintzberg/Greiner/span/SoD applied to LLM agent design returns essentially nothing. So the specific
node this repo occupies — **classical management theory as the top-down decomposition that places
harness and loop** — is thin-to-empty in the literature. That is an *opportunity to connect existing
parts*, not a claim of blank-slate invention.

## The strongest counter-argument (do not ignore it)

- **[S] "Drop the Hierarchy and Roles: How Self-Organizing LLM Agents Outperform Designed
  Structures"** (arXiv 2603.28990). Argues self-organization beats designed structure on
  task-solving. This repo's answer is the two-layer law (`docs/03-organic-vs-mechanistic.md`):
  self-organize the *exploration*, design only the *control skeleton*. The paper measures the former
  and is silent on the latter, so it constrains — but does not refute — an org-first design.

---

*Preprint note:* arXiv IDs in the 2601–2606 range are 2026 preprints; treat **[S]** arXiv items as
evidence that a claim/term exists and is discussed, not as peer-reviewed settled results. The
load-bearing primary anchors are the classical-theory citations, the Anthropic/Thoughtworks
engineering posts, and the COLM/TMLR papers (AIOS, CoALA).

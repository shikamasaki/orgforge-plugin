# Sources & honest research map

Every claim in this repo is grounded in the work below. Primary/authoritative sources are marked
**[P]**; secondary/commentary or preprints-not-yet-reviewed are marked **[S]**. Where the
literature is thin or contested, this file says so — the point of the repo is an honest frame, not a
novelty claim.

> **Provenance disclosure (2026-07, added on the maintainer's own challenge).** The classical-theory
> citations in this repo were originally written *from the author model's training memory*, not by
> reading the primary texts — a real weakness for a repo whose selling point is source honesty. A
> verification pass has since checked the load-bearing items against external sources (marked
> **[✓ verified 2026-07]** below). The pass **confirmed** the existence and core claims of: arXiv
> 2603.28990 (real — Victoria Dochkina, submitted 2026-03-30), Greiner 1972 (5 phases; crises
> leadership/autonomy/control/red-tape; 5th crisis left open), Graicunas 1933 "Relationship in
> Organization" (the 1,6,18,44,100,244 relationship series), Barnard 1938's definition (verbatim),
> Burns & Stalker 1961, Ashby 1956 requisite variety, Conway 1968 *Datamation* 14(5):28–31 (and that
> **Brooks** named it "Conway's law" in 1975, not Conway), and Penrose 1959 (growth limited by
> *managerial* capacity). It also **corrected** memory errors: see the ⚠ notes inline. Items **not**
> yet independently verified (Mintzberg 1979 configurations, the COSO/SOX SoD lineage details, Galbraith,
> Drucker, Cyert & March, Williamson, Lawrence & Lorsch, March 1991, Tushman, Cohen & Levinthal,
> Nonaka, Polanyi, Parnas, Saltzer & Schroeder, Stinchcombe, Hannan & Freeman, Simon 1971, Becker &
> Murphy) remain **memory-sourced and should be treated as [S]-confidence until checked**, regardless
> of the [P] label on the text. The honest status: the *load-bearing* citations are now verified; the
> long tail is not.

## Classical organizational theory (the top-down side)

For each theory, the primary text is cited as **[P]**; the web links that earlier versions of this
file mislabeled as primary are retained as **[S]** (convenience summary).

- **[P] Mintzberg (1979), *The Structuring of Organizations*, Prentice-Hall** — configurations &
  coordination mechanisms.
  [S] Convenience summaries: https://www.myorganisationalbehaviour.com/mintzbergs-organizational-configurations/ ·
  https://www.mindtools.com/apfv1rk/mintzbergs-organizational-configurations/
- **[P ✓ verified 2026-07] Graicunas (1933), "Relationship in Organization"** (first in the
  *Bulletin of the International Management Institute*, Mar 1933; reprinted in Gulick & Urwick (eds.),
  *Papers on the Science of Administration*, 1937) — span of control. Graicunas's three relationship
  types yield the geometric series **1, 6, 18, 44, 100, 244…** as subordinates grow 1→6, and he
  suggested an optimum of ~**4–5** direct reports. Urwick later (HBR, 1956, "The Manager's Span of
  Control") advocated a practical span of **5**. ⚠ *Memory-error correction:* earlier drafts of this
  repo wrote "Urwick 5–6" and used "5–6, up to 15–20" as if a single classical result; the classical
  number is Graicunas's ~4–5 / Urwick's 5. The "up to 15–20 in high-communication settings" figure is
  a *modern* management-practice claim, not Graicunas/Urwick — treat it as [S]. And note (per the
  docs/03/docs/05 reviews) that what actually transfers to forkable agents is **Ashby's
  requisite-variety-of-checks**, not the human span *number*.
  [S] Convenience summary: https://en.wikipedia.org/wiki/Span_of_control · https://www.nickols.us/graicunas.pdf
- **[P ✓ verified 2026-07] Conway (1968), "How Do Committees Invent?", *Datamation* 14(5):28–31**
  — the thesis that a system's design copies its builder org's communication structure. ⚠ *Correction:*
  the *name* "Conway's law" was coined by **Fred Brooks** in *The Mythical Man-Month* (1975), not by
  Conway; HBR rejected the paper in 1967 before *Datamation* ran it in April 1968.
  [S] Convenience summary: https://en.wikipedia.org/wiki/Conway%27s_law · https://www.melconway.com/research/committees.html
- **Separation of duties (SoD) / internal control.** The authoritative lineage is the COSO
  *Internal Control — Integrated Framework* (1992, rev. 2013) and SOX practice rather than a single
  classic text.
  [S] Convenience summaries: https://en.wikipedia.org/wiki/Separation_of_duties ·
  https://www.techtarget.com/whatis/definition/segregation-of-duties-SoD
- **[P] Goodhart (1975)** — the original formulation: "Any observed statistical regularity will
  tend to collapse once pressure is placed upon it for control purposes." **[P] Strathern (1997),
  "'Improving Ratings': Audit in the British University System", *European Review* 5(3)** — the
  popular phrasing "when a measure becomes a target, it ceases to be a good measure" is Strathern's,
  not Goodhart's.
  [S] Convenience summaries: https://kpitree.co/guides/frameworks/goodharts-law ·
  https://explainx.ai/blog/specification-gaming-goodharts-law-ai-metrics
- **[P ✓ verified 2026-07] Burns & Stalker (1961), *The Management of Innovation*, Tavistock** —
  mechanistic (fits stable environments) vs organic (fits dynamic/uncertain environments); a
  foundational contingency-theory text. Verified: mechanistic = strict roles/vertical communication;
  organic = lateral communication, task redefinition. The repo's *two-layer within one org* reading
  (docs/03) extends B&S beyond their own unit of analysis (the whole firm) — that extension is the
  repo's synthesis, and the docs/03 review flags Lawrence & Lorsch (1967) as the more exact source for
  running different regimes in different subunits.
  [S] Convenience summary: https://www.valuebasedmanagement.net/methods_burns_mechanistic_organic_systems.html
- **[P ✓ verified 2026-07] Greiner (1972), "Evolution and Revolution as Organizations Grow",
  *Harvard Business Review* 50(4):37–46** — growth stages, each ending in a crisis. Verified: 5 phases
  (creativity, direction, delegation, coordination, collaboration); crises leadership → autonomy →
  control → red tape; the 5th crisis Greiner left open. ⚠ *Caveat the docs/05 review raised:* Greiner's
  sequence is *one-way and crisis-driven* (rapid growth shortens the time to the next crisis, slow
  growth delays it — but it does not reverse). docs/05's "bidirectional activation levels" reframing
  keeps Greiner's phase *names* while dropping the one-way-crisis *mechanism* — so under the elastic
  model, Greiner is a lens/taxonomy, not a transferred finding. This is stated in docs/02's caveat and
  should be read as a known limit, not a claim that Greiner's law holds for elastic agent orgs.
  [S] Convenience summaries: https://www.mindtools.com/aks7u4n/the-greiner-curve/ ·
  https://mbaknol.com/strategic-management/greiners-model-of-organizational-growth-phases-of-organizational-growth-and-crisis/
- **[P] McChrystal, Collins, Silverman & Fussell (2015), *Team of Teams*, Portfolio/Penguin** —
  shared consciousness + empowered execution.
  [S] Convenience summary: https://www.mcchrystalgroup.com/about/team-of-teams/empowered-execution
- **[P] Galbraith (1973), *Designing Complex Organizations*, Addison-Wesley; and (1974),
  "Organization Design: An Information Processing View", *Interfaces* 4(3)** — the Star Model and
  the information-processing view.
  [S] Convenience summary: https://strategicmanagementinsight.com/tools/galbraiths-star-model-explained/
- **[P] Drucker (1954), *The Practice of Management*, Harper** — management by objectives. (The
  goal/reward decoupling the repo leans on is modern OKR practice, Doerr/Google — not MBO, which was
  historically coupled to appraisal and pay, per Deming's criticism.)
  [S] Convenience summaries: https://mooncamp.com/glossary/management-by-objectives-mbo ·
  RACI: https://en.wikipedia.org/wiki/Responsibility_assignment_matrix

### Classical theory added in v0.3

- **[P ✓ verified 2026-07] Barnard (1938), *The Functions of the Executive*, Harvard University
  Press** — the definition THEORY.md §1 compresses is verbatim Barnard: "a system of consciously
  coordinated activities or forces of two or more persons." Verified nuance: Barnard *himself* already
  contained both the *bounded-rationality* seed (he "acknowledged bounds on rationality," per
  Williamson) and the *alignment* mechanism (his inducement–contribution equilibrium / zone of
  acceptance, which Simon renamed the zone of acceptance). So THEORY.md §1's move — attributing the
  "bounded capabilities" clause to Simon's bounded rationality and the "imperfect alignment" clause
  separately — is defensible: they are *distinct* clauses in Barnard/Simon, not (as one review
  worried) a fusion of one concept. The clauses are real; whether the *definition entails the specific
  organs* (esp. the three-way SoD split) is the separate, weaker claim the docs/03 review rightly
  challenges — see the "honest assessment" note below.
- **[P ✓ verified 2026-07] Simon (1947), *Administrative Behavior*, Macmillan** — bounded rationality
  (the direct descendant of Barnard's zone of acceptance); **and (1962),
  "The Architecture of Complexity", *Proceedings of the American Philosophical Society* 106(6)** —
  near-decomposability, which supports the latent-modular design in docs/05.
- **[P ✓ verified 2026-07] Penrose (1959), *The Theory of the Growth of the Firm*, Blackwell** —
  verified: growth is limited by *managerial capacity* (the time incumbent managers need to absorb new
  managers), not by market interfaces; limits the *rate* of growth, not firm size per se; foundation of
  the resource-based view. docs/05's "ledger + context-pack nullifies the Penrose effect" is the repo's
  own *argued extension*, flagged there as a claim to test.
- **[P] Lawrence & Lorsch (1967), *Organization and Environment*, Harvard Business School Press** —
  differentiation/integration: the real source for running different regimes in different subunits.
- **[P] March (1991), "Exploration and Exploitation in Organizational Learning", *Organization
  Science* 2(1).**
- **[P] Tushman & O'Reilly (1996), "Ambidextrous Organizations", *California Management Review*
  38(4)** — structural ambidexterity, including its integration-cost findings.
- **[P] Williamson (1975), *Markets and Hierarchies*, Free Press; and (1985), *The Economic
  Institutions of Capitalism*, Free Press** — transaction-cost economics beyond Coase.
- **[P] Starkey, Barnatt & Tempest (2000), "Beyond Networks and Hierarchies: Latent Organizations
  in the U.K. Television Industry", *Organization Science* 11(3)** — the term "latent organization"
  originates here.
- **[P] DeFillippi & Arthur (1998), "Paradox in Project-Based Enterprise: The Case of Film Making",
  *California Management Review* 40(2)** — project-based production, the "Hollywood model" primary.
- **[P] Becker & Murphy (1992), "The Division of Labor, Coordination Costs, and Knowledge",
  *Quarterly Journal of Economics* 107(4).**
- **[P] Stinchcombe (1965), "Social Structure and Organizations", in March (ed.), *Handbook of
  Organizations*, Rand McNally** — imprinting; liability of newness.
- **[P] Whetten (1980), "Organizational Decline: A Neglected Topic in Organizational Science",
  *Academy of Management Review* 5(4).**
- **[P] Hannan & Freeman (1977), "The Population Ecology of Organizations", *American Journal of
  Sociology* 82(5); and (1989), *Organizational Ecology*, Harvard University Press** —
  organizational mortality.
- **[P] Mintzberg & Waters (1985), "Of Strategies, Deliberate and Emergent", *Strategic Management
  Journal* 6(3).**

### Knowledge & doctrine (docs/07)

- **[P] Tushman (1977), "Special Boundary Roles in the Innovation Process", *Administrative Science
  Quarterly* 22(4)** — boundary spanning; the curator role's theoretical basis.
- **[P] Cohen & Levinthal (1990), "Absorptive Capacity: A New Perspective on Learning and
  Innovation", *Administrative Science Quarterly* 35(1).**
- **[P] Nonaka & Takeuchi (1995), *The Knowledge-Creating Company*, Oxford University Press** — the
  SECI knowledge-conversion cycle.
- **[P] Polanyi (1966), *The Tacit Dimension*, Routledge.**
- **[P] Aguilar (1967), *Scanning the Business Environment*, Macmillan** — environmental scanning.
- Mintzberg's **standardization of skills** (professional bureaucracy; see Mintzberg 1979 above) is
  the coordination mechanism that doctrine implements.

### Context economy (docs/08)

- **[P] Parnas (1972), "On the Criteria To Be Used in Decomposing Systems into Modules",
  *Communications of the ACM* 15(12)** — information hiding.
- **[P] Galbraith (1974)** — information-processing view of org design (cited above).
- **[P] Simon (1971), "Designing Organizations for an Information-Rich World", in Greenberger
  (ed.), *Computers, Communications, and the Public Interest*, Johns Hopkins Press** — "a wealth of
  information creates a poverty of attention."
- **[P] Mission command / commander's intent** (Auftragstaktik); US Army ADP 6-0 *Mission Command*
  as the doctrinal reference.
- **[P] Saltzer & Schroeder (1975), "The Protection of Information in Computer Systems",
  *Proceedings of the IEEE* 63(9)** — least privilege / need-to-know.

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
  Note: ~15× refers to tokens vs a chat interaction; single agents ≈4× chat — so multi-agent vs
  single-agent is ≈4×.
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
parts*, not a claim of blank-slate invention. As of v0.3, the classical theories are cited from
their primary texts directly (earlier versions of this file labeled web summaries **[P]**; those
links are now honestly demoted to **[S]** convenience summaries).

## The elastic organization (docs/05 — which constraints transfer, which vanish)

- **[P] Coase (1937), "The Nature of the Firm", *Economica* 4(16)** (firm boundaries set by
  coordination/transaction costs, not capital).
  [S] Convenience summary: https://en.wikipedia.org/wiki/The_Nature_of_the_Firm
- **[P] Brooks (1975), *The Mythical Man-Month*, Addison-Wesley** — Brooks's law (communication
  channels n(n−1)/2).
  [S] Convenience summary: https://en.wikipedia.org/wiki/Brooks%27s_law
- **[P ✓ verified 2026-07] Ashby (1956), *An Introduction to Cybernetics*, Chapman & Hall** — the law
  of requisite variety, "only variety can destroy variety": a regulator must have at least as much
  variety (range of responses) as the disturbances it must counter. ⚠ *Precision the docs/05 review
  demanded:* the correct agent-org application is "the **checker's repertoire of checks** must cover the
  variety of **failure/gaming modes** the makers can produce" — NOT the loose "controller capacity must
  match controlled variety." And this is the result that *actually* transfers to forkable supervisors,
  displacing the human span-of-control *number* (see the Graicunas entry).
  [S] Convenience summary: https://en.wikipedia.org/wiki/Variety_(cybernetics)
- **[P] Cyert & March (1963), *A Behavioral Theory of the Firm*, Prentice-Hall** — organizational
  slack (latent departments are free slack for agent orgs).
  [S] Convenience summary: https://en.wikipedia.org/wiki/A_Behavioral_Theory_of_the_Firm
- **[S] Project-based organization (the "Hollywood model")** — a human precedent for full latent
  capability + per-project activation. https://en.wikipedia.org/wiki/Project-based_organization
  (For primaries, see Starkey/Barnatt/Tempest 2000 and DeFillippi & Arthur 1998 above.)

*The Family A (financial/frictional) vs Family B (coordination) constraint split in docs/05 is
this repo's own synthesis of the above; treat it as a design hypothesis, per the repo's stance.*

## Decision practice (docs/06)

- **[S] 稟議 (ringi)** — Japanese written-proposal approval practice; docs/06 borrows only the
  asynchronous written-proposal aspect (agents propose in writing, authority above decides). Real
  ringi is a consensus-formation system (nemawashi, sequential seals) and is typically slow and
  blocking; the repo's mechanism is closer to a delegation-of-authority (決裁権限) matrix plus an
  approval queue. https://en.wikipedia.org/wiki/Ringi-sho

## The strongest counter-argument (do not ignore it)

- **[S ✓ exists, verified 2026-07] "Drop the Hierarchy and Roles: How Self-Organizing LLM Agents
  Outperform Designed Structures"** (arXiv 2603.28990, Victoria Dochkina, submitted 2026-03-30). The
  paper is **real** (the ID is not fabricated — a prior review rightly asked us to confirm this before
  leaning on it). Its actual result is subtler than "self-organization wins outright": a
  **25,000-task** study (8 models, 4–256 agents, 8 coordination protocols) finds an *endogeneity
  paradox* — a **hybrid** protocol (fixed agent ordering, autonomous role selection) beats both fully
  centralized coordination (+14%) and fully autonomous self-organization (+44%). So the paper actually
  supports a *mixed* stance, not pure self-organization — which, if anything, **strengthens** the
  repo's two-layer law (`docs/03`): design *some* structure (the ordering / the control skeleton),
  self-organize the rest (roles / exploration). The repo's framing of it as "the strongest
  counter-argument" slightly overstates the paper's threat; note this. The paper measures task-solving
  efficiency and is silent on the control layer, so it constrains — but does not refute — an org-first
  design. It remains **[S]** (a 2026 preprint, not peer-reviewed).

---

*Preprint note:* arXiv IDs in the 2601–2606 range are 2026 preprints; treat **[S]** arXiv items as
evidence that a claim/term exists and is discussed, not as peer-reviewed settled results. The
load-bearing primary anchors are the classical-theory citations, the Anthropic/Thoughtworks
engineering posts, and the COLM/TMLR papers (AIOS, CoALA).

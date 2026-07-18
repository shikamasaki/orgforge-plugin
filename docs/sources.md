# Sources & honest research map

Every claim in this repo is grounded in the work below. Primary/authoritative sources are marked
**[P]**; secondary/commentary or preprints are marked **[S]**. Where the literature is thin or
contested, this file says so — the point of the repo is an honest frame, not a novelty claim.

## Classical organizational theory (the top-down side)

For each theory the primary text is cited as **[P]**; convenience web summaries are **[S]**.

- **[P] Mintzberg (1979), *The Structuring of Organizations*, Prentice-Hall** — configurations &
  coordination mechanisms.
  [S] Convenience summaries: https://www.myorganisationalbehaviour.com/mintzbergs-organizational-configurations/ ·
  https://www.mindtools.com/apfv1rk/mintzbergs-organizational-configurations/
- **[P] Graicunas (1933), "Relationship in Organization"** (first in the
  *Bulletin of the International Management Institute*, Mar 1933; reprinted in Gulick & Urwick (eds.),
  *Papers on the Science of Administration*, 1937) — span of control. Graicunas's three relationship
  types yield the geometric series **1, 6, 18, 44, 100, 244…** as subordinates grow 1→6, and he
  suggested an optimum of ~**4–5** direct reports. Urwick later (HBR, 1956, "The Manager's Span of
  Control") advocated a practical span of **5**. The classical number is Graicunas's ~4–5 / Urwick's 5.
  The "up to 15–20 in high-communication settings" figure is a *modern* management-practice claim, not
  Graicunas/Urwick — treat it as [S]. What actually transfers to forkable agents is **Ashby's
  requisite-variety-of-checks**, not the human span *number*.
  [S] Convenience summary: https://en.wikipedia.org/wiki/Span_of_control · https://www.nickols.us/graicunas.pdf
- **[P] Conway (1968), "How Do Committees Invent?", *Datamation* 14(5):28–31**
  — the thesis that a system's design copies its builder org's communication structure. The *name*
  "Conway's law" was coined by **Fred Brooks** in *The Mythical Man-Month* (1975); HBR rejected the
  paper in 1967 before *Datamation* ran it in April 1968.
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
- **[P] Burns & Stalker (1961), *The Management of Innovation*, Tavistock** —
  mechanistic (fits stable environments) vs organic (fits dynamic/uncertain environments); a
  foundational contingency-theory text. Mechanistic = strict roles/vertical communication;
  organic = lateral communication, task redefinition. The repo's *two-layer within one org* reading
  (docs/03) extends B&S beyond their own unit of analysis (the whole firm) — that extension is the
  repo's synthesis. Lawrence & Lorsch (1967) is the more exact source for running different regimes in
  different subunits (see docs/03).
  [S] Convenience summary: https://www.valuebasedmanagement.net/methods_burns_mechanistic_organic_systems.html
- **[P] Greiner (1972), "Evolution and Revolution as Organizations Grow",
  *Harvard Business Review* 50(4):37–46** — growth stages, each ending in a crisis. 5 phases
  (creativity, direction, delegation, coordination, collaboration); crises leadership → autonomy →
  control → red tape; the 5th crisis Greiner left open. Greiner's sequence is *one-way and crisis-driven*
  (rapid growth shortens the time to the next crisis, slow growth delays it — but it does not reverse).
  docs/05's "bidirectional activation levels" reframing keeps Greiner's phase *names* while dropping the
  one-way-crisis *mechanism* — so under the elastic model, Greiner is a lens/taxonomy, not a transferred
  finding. This is a known limit, stated in docs/02.
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

- **[P] Barnard (1938), *The Functions of the Executive*, Harvard University
  Press** — the definition THEORY.md §1 compresses is verbatim Barnard: "a system of consciously
  coordinated activities or forces of two or more persons." Barnard *himself* already contained both
  the *bounded-rationality* seed (he "acknowledged bounds on rationality," per Williamson) and the
  *alignment* mechanism (his inducement–contribution equilibrium / zone of acceptance, which Simon
  adopted). So THEORY.md §1's move — attributing the "bounded capabilities" clause to Simon's bounded
  rationality and the "imperfect alignment" clause separately — is faithful: they are *distinct* clauses
  in Barnard/Simon, not a fusion of one concept. The clauses are real; whether the *definition entails
  the specific organs* (esp. the three-way SoD split) is a separate, weaker claim the repo does not make.
- **[P] Simon (1947), *Administrative Behavior*, Macmillan** — bounded rationality
  (the direct descendant of Barnard's zone of acceptance); **and (1962),
  "The Architecture of Complexity", *Proceedings of the American Philosophical Society* 106(6)** —
  near-decomposability, which supports the latent-modular design in docs/05.
- **[P] Penrose (1959), *The Theory of the Growth of the Firm*, Blackwell** —
  growth is limited by *managerial capacity* (the time incumbent managers need to absorb new
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
parts*, not a claim of blank-slate invention. The classical theories are cited from their primary
texts, with web summaries marked **[S]**.

## The elastic organization (docs/05 — which constraints transfer, which vanish)

- **[P] Coase (1937), "The Nature of the Firm", *Economica* 4(16)** (firm boundaries set by
  coordination/transaction costs, not capital).
  [S] Convenience summary: https://en.wikipedia.org/wiki/The_Nature_of_the_Firm
- **[P] Brooks (1975), *The Mythical Man-Month*, Addison-Wesley** — Brooks's law (communication
  channels n(n−1)/2).
  [S] Convenience summary: https://en.wikipedia.org/wiki/Brooks%27s_law
- **[P] Ashby (1956), *An Introduction to Cybernetics*, Chapman & Hall** — the law
  of requisite variety, "only variety can destroy variety": a regulator must have at least as much
  variety (range of responses) as the disturbances it must counter. The faithful agent-org application
  is that the **checker's repertoire of checks** must cover the variety of **failure/gaming modes** the
  makers can produce (not "controller capacity must match controlled variety"). This is the result that
  transfers to forkable supervisors, displacing the human span-of-control *number* (see the Graicunas
  entry).
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

- **[S] "Drop the Hierarchy and Roles: How Self-Organizing LLM Agents
  Outperform Designed Structures"** (arXiv 2603.28990, Victoria Dochkina, submitted 2026-03-30). The
  paper is **real** and its arXiv ID resolves. Its actual result is subtler than "self-organization
  wins outright": a
  **25,000-task** study (8 models, 4–256 agents, 8 coordination protocols) finds an *endogeneity
  paradox* — a **hybrid** protocol (fixed agent ordering, autonomous role selection) beats both fully
  centralized coordination (+14%) and fully autonomous self-organization (+44%). So the paper actually
  supports a *mixed* stance, not pure self-organization — which, if anything, **strengthens** the
  repo's two-layer law (`docs/03`): design *some* structure (the ordering / the control skeleton),
  self-organize the rest (roles / exploration). Framing it as "the strongest counter-argument"
  overstates the paper's threat: it measures task-solving efficiency and is silent on the control layer,
  so it constrains — but does not refute — an org-first design. It remains **[S]** (a 2026 preprint, not
  peer-reviewed).

### Attention allocation — intra-department work selection (docs/12)

How a single department internally decides what to work on next. There is **no single named
theory** for this; docs/12 synthesizes the organization-theory *attention* tradition with the
operations-management *flow* tradition, and says so. These theories were formulated at the level of
the decision-maker and the firm, not a department's private backlog — applying them at intra-unit
granularity is a **down-scaling synthesis**, flagged as such, not a verbatim claim.

Organization theory (why + how bounded cognition selects):
- **[P] March & Simon (1958), *Organizations*, Wiley** — **sequential attention to goals**: a unit
  attends to competing goals one at a time, in order, rather than jointly optimizing. The authors
  later called the book "less a theory of choice than a theory of attention." The direct anchor for
  taking the backlog as a *prefix* of a ranking.
- **[P] Cyert & March (1963), *A Behavioral Theory of the Firm*, Prentice-Hall** — **problemistic
  search** and **aspiration levels**: effort is triggered by a problem (performance below
  aspiration) and searches locally, near the problem. The anchor for the problemistic-search boost.
  (Also cited above for organizational slack.)
- **[P] Ocasio (1997), "Towards an Attention-Based View of the Firm", *Strategic Management Journal*
  18(S1): 187–206** — **situated attention**: what a decision-locus focuses on depends on the
  situation/channel routing issues to it. The anchor for anchoring local choice to the org-wide
  ranking. Refined in **[P] Ocasio (2011), "Attention to Attention", *Organization Science* 22(5):
  1286–1296**. (Simon 1947 bounded rationality / attention-scarcity is already cited above; it is
  the root of "attention is the scarce resource that forces selection.")
- **[P] Cohen, March & Olsen (1972), "A Garbage Can Model of Organizational Choice", *ASQ* 17(1):
  1–25** — the **contested counter-lens**: real intra-unit "prioritization" is often less deliberate
  than a backlog model assumes; work attaches to whatever is temporally salient. Cited as the
  caution the problemistic-search + situated-attention design is meant to defend against, not as a
  law.

Operations management (the mechanical *how* — a separate register, kept distinct):
- **[S] Goldratt (1984), *The Goal*, North River Press** — **Theory of Constraints**: throughput is
  set by the bottleneck; treat WIP as expense, not asset. Operations management, not org theory.
- **[S] Anderson (2010), *Kanban: Successful Evolutionary Change*, Blue Hole Press** — **WIP limits
  / pull**: cap concurrent work; pull the next item only when capacity frees. The anchor for the
  WIP-limit mechanism. Management practice, not organizational theory of cognition.

*Off-target note:* Mintzberg's coordination mechanisms (cited elsewhere for inter-unit
coordination) do **not** address intra-unit work selection — they govern how interdependent work is
linked, not which of a unit's own items is picked next. Do not cite them for docs/12.

### Proxy-stack, conflict, and precedent (docs/13)

Anchors for the five gaps a theory-coverage sweep found — "is the org still solving the right
problem?" Applied at this repo's granularity as explicit synthesis, flagged, not claimed verbatim.

- **[P] Weick (1979/1995), *The Social Psychology of Organizing* / *Sensemaking in Organizations*** —
  **enactment**: organizations partly create the environment they then respond to; sensing whether the
  premise still holds is an active, ongoing act. Anchor for PREMISE (docs/13 §1).
- **[S] Aguilar (1967), *Scanning the Business Environment*, Macmillan** — environmental scanning; the
  disciplined watch for the external shift that invalidates a strategy. Supports PREMISE.
- **[P] Staw (1976), "Knee-deep in the Big Muddy: A Study of Escalating Commitment to a Chosen Course
  of Action," *Organizational Behavior and Human Performance* 16(1): 27–44** — **escalation of
  commitment**: decision-makers pour resources into a failing course rather than abandon a sunk
  investment. Anchor for SUNK-COURSE (docs/13 §2).
- **[P] Argyris & Schön (1978), *Organizational Learning: A Theory of Action Perspective*,
  Addison-Wesley** — **single- vs double-loop learning**: single-loop corrects actions within a fixed
  frame; double-loop questions the governing goal/assumption itself. Anchor for FRAME-REVIEW
  (docs/13 §3) — a canonical framework the repo previously did not cite anywhere.
- **[P] Follett (1925/1942), "Constructive Conflict," in *Dynamic Administration*** — conflict has
  three settlements: **domination, compromise, integration**; integration (an option honoring both
  parties) is the constructive one. Anchor for MANDATE-CONFLICT's "both satisfiable → integrate"
  branch (docs/13 §4). Paired with **Lawrence & Lorsch (1967)** (already cited) on conflict-resolution
  modes across differentiated units.
- **[P] Nelson & Winter (1982), *An Evolutionary Theory of Economic Change*, Harvard** — **routines as
  organizational memory**: an org's settled ways of doing things are where its operational knowledge
  lives. Anchor for CONVENTIONS (docs/13 §5); reinforced by Cyert & March SOPs (already cited).

---

### Manager accountability (docs/14)

What a manager/dept-head is answerable for across the delegation chain — the four accountabilities
of Organ 6's vertical control facet. Applied at agent-manager granularity as explicit synthesis;
the classical parity/responsibility principles are heuristics to *verify*, not laws (Simon 1946),
so they are design priors the lint checks, not proofs. (Urwick, Mintzberg, Graicunas, Deming,
March & Simon are already cited above — referenced, not duplicated.)

- **[P] Koontz & O'Donnell (1955), *Principles of Management*, McGraw-Hill** — **absoluteness of
  responsibility**: a superior cannot escape responsibility for the activities of subordinates to
  whom authority was delegated; and the **parity principle**: responsibility exacted cannot exceed
  (nor fall short of) the authority delegated. Anchors A1 (roll-up attribution) and A2 (parity).
- **[P] Urwick (1943), *The Elements of Administration*, Harper** (already cited) — the **principle
  of responsibility** ("the responsibility of superiors for the acts of subordinates is absolute")
  and the **principle of correspondence** (authority and responsibility coterminous and coequal).
  A1, A2.
- **[P] Fayol (1916), *Administration Industrielle et Générale*** — Principle 2, authority and
  responsibility as corollaries. A2.
- **[P] Simon (1946), "The Proverbs of Administration," *Public Administration Review* 6(1):
  53–67** — the classical principles are contradictory proverbs, not laws: **verify, don't assume.**
  The honesty anchor for treating parity/span as design priors to test. A2.
- **[S] Simons (2013), "The Entrepreneurial Gap," HBS Working Paper 13-100** — a *bounded* gap
  between accountability and control is a deliberate lever; an *unbounded* one is a defect. Refines
  A2 (parity is a floor, a bounded stretch is allowed).
- **[P] Boehm (1979), "Guidelines for Verifying and Validating Software Requirements and Design
  Specifications," *Euro IFIP*** — **verification** ("are we building it right?" — conformance to
  spec) vs. **validation** ("are we building the right thing?"). Anchors A3: the manager's
  intent-conformance *verification* is categorically distinct from the gate/skeptic's *validation*
  + adversarial admission — which is why A3 does not violate separation of duties.
- **[P] March & Simon (1958), *Organizations*, Wiley** (already cited) — **uncertainty
  absorption**: as information moves up, inferences travel and the evidence is lost, making the
  summarizer an un-auditable premise source. Anchor A4: carry the *basis* up alongside the
  inference.
- **[P] Rosen & Tesser (1970), "On Reluctance to Communicate Undesirable Information: the MUM
  effect," *Sociometry* 33(3): 253–263** — the reluctance to pass bad news upward. Anchor A4: make
  silence a positive assertion (`exceptions_none_asserted`), never an omission.
- **[S] Read (1962) / O'Reilly (1978)** — upward information distortion is *intentional* and tracks
  the reporter's incentives. Anchor A4's `report_fidelity` audit (grade the roll-up against source).

### Decomposition principles — how a manager splits a task (docs/15)

How a manager turns one backlog item into sub-tasks (or keeps it single-threaded). There is **no
single named theory** of intra-unit task decomposition; docs/15 renders four consensus results at the
agent-manager granularity the originals did not reach. The own-domain-vs-cross-domain boundary and its
lint tooth are this repo's synthesis, to be verified against a running system.

- **[P] Parnas (1972), "On the Criteria To Be Used in Decomposing Systems into Modules," *CACM*
  15(12)** (already cited above) — **information hiding**: split so each module hides a decision likely
  to change. The anchor for "cut at the design secret, not the surface" (§2.1).
- **[P] Simon (1962), "The Architecture of Complexity," *Proc. Am. Phil. Soc.* 106(6)** (already cited)
  — **near-decomposability**: dense interaction within a part, sparse between parts. The anchor for
  "cut where coupling is already sparse" (§2.2).
- **[P] Thompson (1967), *Organizations in Action*, McGraw-Hill** — the **interdependence taxonomy**
  (pooled / sequential / reciprocal) and its rising coordination cost. The anchor for "never split
  reciprocal work; pin sequential seams; pooled splits freely" (§2.3), and the theoretical form of
  docs/14's keep-coupled-work-single-threaded.
- **[P] Becker & Murphy (1992), "The Division of Labor, Coordination Costs, and Knowledge," *QJE*
  107(4)** (already cited) — the division of labor is bounded by **coordination cost**, not by how
  finely one could cut. The anchor for "split only while the gain beats the coordination cost" (§2.4).
- **[P] Conway (1968), *Datamation* 14(5)** (already cited, docs/04 §3) — the artifact mirrors the
  decomposition; the split is itself an architectural decision.
- Knowledge-boundary anchors reused from docs/07 §2.1 (role-keyed doctrine) and docs/08 §1.1 (no
  **doctrine capture** — the control layer holds no per-role domain doctrine), which ground §3's
  own-domain-vs-cross-domain rule and §5's lint tooth.

---

*Preprint note:* arXiv IDs in the 2601–2606 range are 2026 preprints; treat **[S]** arXiv items as
evidence that a claim/term exists and is discussed, not as peer-reviewed settled results. The
load-bearing primary anchors are the classical-theory citations, the Anthropic/Thoughtworks
engineering posts, and the COLM/TMLR papers (AIOS, CoALA).

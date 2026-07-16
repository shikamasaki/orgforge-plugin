---
description: Adjudicate a mandate conflict — two departments each acting in-authority whose decisions cannot both stand — against the human-declared precedence in the constitution. Resolves silently by precedence, integrates if both satisfiable, escalates only the un-ordered / mutually-exclusive case.
argument-hint: "<subjectA,subjectB> <contested-decision>"
allowed-tools: Bash(python3 *)
---

Adjudicate a genuine mandate conflict (not a resource grab, not a file collision — two mandates that cannot both stand).

Subjects in conflict: **$1**
Contested decision: **$2**

The precedence ordering is human-authored and agent-unwritable — it lives in `constitution.yaml` under `mandate_precedence.order`. Read it, then adjudicate:

!`python3 -c "import yaml,os; c=yaml.safe_load(open(os.environ['CLAUDE_PLUGIN_ROOT']+'/template/constitution.yaml')); mp=c.get('mandate_precedence',{}); print('precedence:', '>'.join(mp.get('order',[]))); print('both_satisfiable_rule:', mp.get('both_satisfiable_rule'))"`

!`python3 "${CLAUDE_PLUGIN_ROOT}/tools/reconcile.py" mandate "${ORG_LEDGER_ROOT}" --subjects "$1" --decision "$2" --precedence "$(python3 -c "import yaml,os; print('>'.join(yaml.safe_load(open(os.environ['CLAUDE_PLUGIN_ROOT']+'/template/constitution.yaml'))['mandate_precedence']['order']))")"`

Interpret the result:
- **precedence_applies** → the higher mandate governs; the contested decision follows it. Silent, no human page.
- **integrate** → both mandates can be honored at once; find the option that honors both (Follett's integration). No human page.
- **escalate** → either a subject is absent from the declared precedence (the org never decided who governs — only the human may), or the mandates are co-equal and mutually exclusive. Surface to the human with the evidence; do not pick a side yourself.

The whole point: a genuine mandate clash resolves by the human's declared precedence, NOT by whichever agent's cycle merged first.

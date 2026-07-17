# HAND-OFF — you are: cli-worker

## Your slice
cli.js — the entry point. Parses process.argv into a cmd, wires store+api together, prints handle()'s result.

## Boundary contract (FIXED by your manager — do not renegotiate)
- Inputs you receive: createStore from ./store.js and handle from ./api.js. process.argv (argv[2]=op, argv[3]=text-or-id). op in {add,toggle,remove,list}.
- Outputs you MUST produce (the exact interface others depend on): An executable 'node cli.js <op> [arg]'. Builds cmd: add -> {op:'add', text:argv[3]}; toggle -> {op:'toggle', id:argv[3]}; remove -> {op:'remove', id:argv[3]}; list -> {op:'list'}. Calls createStore() then handle(store, cmd) and prints the result in human-readable form (list prints each task as e.g. '[x] <id> <text>' for done / '[ ] <id> <text>' otherwise; add/toggle/remove print a confirmation line). Non-zero exit on ok:false.
- You own: cli.js
- You must NOT touch: store.js,api.js
- Shared invariant: task shape is exactly {id: string, text: string, done: boolean} — read fields, don't invent them
- Shared invariant: cli imports the real store.js and api.js by relative path; it must not reimplement their logic

## Your brain (doctrine scoped to your slice)
- The CLI is the only layer that touches process.argv and stdout; it must not contain business logic.
    (source: prior cli runs; confidence: 0.8; review by 2026-10-17)

## If you split your slice further
- Suggested cut for THIS slice (local advice, your call): layer boundary: cli only does argv parsing + printing; all logic lives in api/store.
- Choose the axis that fits YOUR slice — do not inherit a global one. For EACH child you spawn, emit a Boundary contract the same way (inputs / outputs / owns / forbid), and hand down only the doctrine scoped to that child.
- Do NOT re-split across a boundary your manager fixed above; integrate to the outputs interface exactly.

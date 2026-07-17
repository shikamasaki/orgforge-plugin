# HAND-OFF — you are: api-worker

## Your slice
api.js — the thin command layer. Translates a {op,...} command into a store call and returns a plain result object. HTTP-less.

## Boundary contract (FIXED by your manager — do not renegotiate)
- Inputs you receive: A store instance (from store.js's createStore()) with methods add(text), toggle(id), remove(id), all(). A cmd object {op, ...}. Does NOT import store.js or cli.js; the store is passed in.
- Outputs you MUST produce (the exact interface others depend on): module.exports = { handle }. handle(store, cmd) where cmd.op in {add,toggle,remove,list}. Returns a PLAIN result object (never throws for normal cases): add -> {ok:true, op:'add', task}; toggle -> {ok:true, op:'toggle', task} or {ok:false, op:'toggle', error:'not found'} when store.toggle returns null; remove -> {ok:true, op:'remove', removed:true|false}; list -> {ok:true, op:'list', tasks:[...]}. Unknown op -> {ok:false, error:'unknown op: <op>'}. cmd.text used for add; cmd.id used for toggle/remove.
- You own: api.js
- You must NOT touch: store.js,cli.js
- Shared invariant: task shape is exactly {id: string, text: string, done: boolean} — pass tasks through untouched
- Shared invariant: handle returns a plain object with a boolean ok field; it does not print and does not throw on missing-id — it returns ok:false

## Your brain (doctrine scoped to your slice)
- Design endpoints contract-first; validate input at the boundary; return structured errors with stable codes, never raw stack traces.
    (source: prior api runs; confidence: 0.8; review by 2026-10-17)
- Idempotency keys on any state-changing POST; a retry must never double-charge.
    (source: prior api runs; confidence: 0.8; review by 2026-10-17)
- A command layer is pure dispatch: no I/O, no argv, no printing; return plain result objects the caller renders.
    (source: prior api runs; confidence: 0.8; review by 2026-10-17)

## If you split your slice further
- Suggested cut for THIS slice (local advice, your call): layer boundary: api is pure translation, holds no state, does its own persistence — store does. api receives the store by dependency injection.
- Choose the axis that fits YOUR slice — do not inherit a global one. For EACH child you spawn, emit a Boundary contract the same way (inputs / outputs / owns / forbid), and hand down only the doctrine scoped to that child.
- Do NOT re-split across a boundary your manager fixed above; integrate to the outputs interface exactly.

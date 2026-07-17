# HAND-OFF — you are: login-worker

## Your slice
Implement POST /login only.

## Boundary contract (FIXED by your manager — do not renegotiate)
- Inputs you receive: User record {id,email,password_hash} lookup by email.
- Outputs you MUST produce (the exact interface others depend on): POST /login: 200 {token} else {error,code} — SAME envelope parent fixed.
- You own: auth_api.py::login handler
- You must NOT touch: register/refresh handlers, db/schema.sql
- Shared invariant: errors use the {error,code} envelope (inherited from parent's contract)

## Your brain (doctrine scoped to your slice)
- Rate-limit login attempts; lock after N failures; constant-time password compare to resist timing attacks.
    (source: security review; confidence: 0.9; review by 2026-10-17)

## If you split your slice further
- Choose the axis that fits YOUR slice — do not inherit a global one. For EACH child you spawn, emit a Boundary contract the same way (inputs / outputs / owns / forbid), and hand down only the doctrine scoped to that child.
- Do NOT re-split across a boundary your manager fixed above; integrate to the outputs interface exactly.

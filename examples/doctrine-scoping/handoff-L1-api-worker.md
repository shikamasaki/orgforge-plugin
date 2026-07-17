# HAND-OFF — you are: api-worker

## Your slice
Build the authentication API endpoints.

## Boundary contract (FIXED by your manager — do not renegotiate)
- Inputs you receive: User records {id,email,password_hash} from db-worker's schema.
- Outputs you MUST produce (the exact interface others depend on): POST /login and POST /register -> {token} or {error,code}; documented in openapi.yaml.
- You own: auth_api.py, test_auth_api.py
- You must NOT touch: db/schema.sql, ui/*
- Shared invariant: all errors use the shared {error,code} envelope; never leak stack traces

## Your brain (doctrine scoped to your slice)
- Design endpoints contract-first; validate input at the boundary; return structured errors with stable codes, never raw stack traces.
    (source: prior api runs; confidence: 0.8; review by 2026-10-17)
- Idempotency keys on any state-changing POST; a retry must never double-charge.
    (source: prior api runs; confidence: 0.8; review by 2026-10-17)

## If you split your slice further
- Suggested cut for THIS slice (local advice, your call): cut by endpoint if this grows (login/register/refresh) — each independent
- Choose the axis that fits YOUR slice — do not inherit a global one. For EACH child you spawn, emit a Boundary contract the same way (inputs / outputs / owns / forbid), and hand down only the doctrine scoped to that child.
- Do NOT re-split across a boundary your manager fixed above; integrate to the outputs interface exactly.

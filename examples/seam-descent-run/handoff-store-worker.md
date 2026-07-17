# HAND-OFF — you are: store-worker

## Your slice
store.js — the JSON-file data layer. The single source of truth for the task shape and for persistence to tasks.json.

## Boundary contract (FIXED by your manager — do not renegotiate)
- Inputs you receive: None (leaf layer). Node.js built-ins only (fs, path). No dependency on api.js or cli.js.
- Outputs you MUST produce (the exact interface others depend on): module.exports = { createStore }. createStore(filePath?) returns an object with: add(text)->the created task object {id,text,done:false}; toggle(id)->the updated task or null if not found; remove(id)->true if removed else false; all()->array of task objects. Persists to tasks.json (default path resolved relative to store.js dir, i.e. path.join(__dirname,'tasks.json')) after every mutation; loads existing state on createStore(). id is a unique string; done is boolean; text is the string passed to add.
- You own: store.js
- You must NOT touch: api.js,cli.js
- Shared invariant: task shape is exactly {id: string, text: string, done: boolean} — no extra or renamed fields
- Shared invariant: id must be unique across a store's lifetime and stable across reloads (persisted, not re-indexed)

## Your brain (doctrine scoped to your slice)
- A data layer owns persistence only; never parse argv or format output. Load defensively: corrupt/absent file -> empty state, never crash.
    (source: prior store runs; confidence: 0.8; review by 2026-10-17)

## If you split your slice further
- Suggested cut for THIS slice (local advice, your call): layer boundary: store owns persistence + id generation; nothing above it may touch tasks.json directly
- Choose the axis that fits YOUR slice — do not inherit a global one. For EACH child you spawn, emit a Boundary contract the same way (inputs / outputs / owns / forbid), and hand down only the doctrine scoped to that child.
- Do NOT re-split across a boundary your manager fixed above; integrate to the outputs interface exactly.

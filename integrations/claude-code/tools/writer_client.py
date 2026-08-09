#!/usr/bin/env python3
"""writer_client — ask writerd to write to the ledger.

**With no daemon there is no write.** Never reinterpreting that as "written" is the point of this
layer.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from writerd import call          # noqa: E402


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip() + "\n\n"
              "  writer_client.py <op> [--org NAME] -- <the arguments to pass to ledger.py…>\n\n"
              "  op: append | record-scheduled-check | trip-halt | release-halt | "
              "reserve-exposure | halt-status | derive-admission\n"
              "  **The ledger path cannot be passed** — writerd decides it from the org name.")
        return 0
    op = argv[1]
    rest = argv[2:]
    org = "default"
    if "--org" in rest:
        i = rest.index("--org")
        org = rest[i + 1]
        rest = rest[:i] + rest[i + 2:]
    if "--" in rest:
        rest = rest[rest.index("--") + 1:]
    resp, err = call(op, rest, org=org)
    if err:
        print(json.dumps({"ok": False, "reason": "writer_unreachable", "detail": err},
                         ensure_ascii=False))
        return 4
    if op in ("reserve-exposure", "derive-admission"):
        # **Emit the inner decision as-is.** The hook reads `decision` to settle allow/deny, so
        # wrapping it in the RPC envelope makes it unreadable — back to trusting the exit code
        # alone.
        sys.stdout.write(resp.get("stdout") or "")
        sys.stderr.write(resp.get("stderr") or "")
        if not resp.get("ok") and not (resp.get("stdout") or "").strip().startswith("{"):
            # The writer itself refused (an RPC-layer error). **If the decision cannot be read,
            # it does not pass.**
            print(json.dumps({"decision": "deny", "reason": resp.get("reason"),
                              "detail": resp.get("detail")}, ensure_ascii=False))
        return resp.get("exit_code", 4)
    if op == "halt-status":
        # **Return it in the shape the hook reads.** The exit code (0/10) and stdout pass
        # straight through.
        sys.stdout.write(resp.get("stdout") or "")
        sys.stderr.write(resp.get("stderr") or "")
        return resp.get("exit_code", 4)
    print(json.dumps(resp, ensure_ascii=False))
    if resp.get("stdout"):
        print(resp["stdout"].rstrip(), file=sys.stderr)
    if resp.get("stderr"):
        print(resp["stderr"].rstrip(), file=sys.stderr)
    return 0 if resp.get("ok") else (resp.get("exit_code") or 4)


if __name__ == "__main__":
    sys.exit(main(sys.argv))

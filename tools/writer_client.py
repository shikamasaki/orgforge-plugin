#!/usr/bin/env python3
"""writer_client — writerd に台帳の書き込みを依頼する。

**daemon が居なければ書けない。** それを「書けた」と読み替えないことが、この層の要点である。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from writerd import call          # noqa: E402


def main(argv):
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__.strip() + "\n\n"
              "  writer_client.py <op> [--org NAME] -- <ledger.py に渡す引数…>\n\n"
              "  op: append | trip-halt | release-halt | reserve-exposure | halt-status\n"
              "  **台帳のパスは渡せない** — writerd が org 名から決める。")
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
    if op == "halt-status":
        # **hook が読む形で返す。** exit code（0/10）と stdout をそのまま透過させる。
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

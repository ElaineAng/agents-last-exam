#!/usr/bin/env python3
"""env-branch: branch, commit, merge and delete versions of the task database.

Each branch is a full copy of the application database with its own server URL
("main" is the graded one; `env-branch list` shows every branch and its URL).

  env-branch list                         branches and their Odoo database names
  env-branch create NAME [--from REF]     new branch from main (or REF); NAME: [a-z0-9]{1,20}
  env-branch db NAME                      Odoo database name and login URL for a branch
  env-branch commit REF -m MESSAGE        snapshot a branch (REF@<id> can be reset to later)
  env-branch log [REF]                    commits on a branch
  env-branch diff REF_A REF_B             row-level summary of what differs
  env-branch merge SOURCE [--into main]   merge SOURCE into main (or another branch)
  env-branch reset REF --to COMMIT        move a branch back to one of its commits
  env-branch delete NAME                  drop a branch you no longer need
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

SERVICE = "http://branchsvc:7000/op"
_INFO = {}


def info() -> dict:
    if not _INFO:
        _INFO.update(call("info"))
    return _INFO


def ref(name: str) -> str:
    main = info().get("root", "main")
    return main if name in ("main", main) else name


def call(op: str, **args) -> dict:
    req = urllib.request.Request(SERVICE, data=json.dumps({"op": op, "args": args}).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read() or b"{}") or {"ok": False, "error": str(e)}
    except urllib.error.URLError as e:
        return {"ok": False, "error": f"branch service unreachable: {e.reason}"}


def show(out: dict, keep=("ok", "error")) -> int:
    print(json.dumps({k: v for k, v in out.items() if k in keep or not keep}, indent=1, default=str))
    return 0 if out.get("ok") else 1


def main() -> int:
    p = argparse.ArgumentParser(prog="env-branch", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    c = sub.add_parser("create"); c.add_argument("name"); c.add_argument("--from", dest="src", default="main")
    d = sub.add_parser("db"); d.add_argument("name")
    m = sub.add_parser("commit"); m.add_argument("ref"); m.add_argument("-m", "--message", required=True)
    lg = sub.add_parser("log"); lg.add_argument("ref", nargs="?", default="main"); lg.add_argument("-n", type=int, default=10)
    df = sub.add_parser("diff"); df.add_argument("a"); df.add_argument("b")
    mg = sub.add_parser("merge"); mg.add_argument("source"); mg.add_argument("--into", default="main")
    rs = sub.add_parser("reset"); rs.add_argument("ref"); rs.add_argument("--to", required=True)
    dl = sub.add_parser("delete"); dl.add_argument("name")
    a = p.parse_args()

    if a.cmd == "db":
        out = call("list")
        if not out.get("ok"):
            return show(out)
        name = ref(a.name)
        if name not in out.get("urls", {}):
            print(json.dumps({"ok": False, "error": f"no branch {a.name!r}; branches: {list(out.get('urls', {}))}"}))
            return 1
        print(json.dumps({"ok": True, "branch": a.name, "url": out["urls"][name]}, indent=1))
        return 0
    if a.cmd == "list":
        out = call("list")
        if out.get("ok"):
            out["branches"] = {("main" if b == info().get("root") else b): u for b, u in out.get("urls", {}).items()}
        return show(out, keep=("ok", "error", "branches"))
    if a.cmd == "create":
        out = call("branch", name=a.name, **{"from": ref(a.src)})
        return show(out, keep=("ok", "error", "database", "url", "wall_s"))
    if a.cmd == "commit":
        out = call("commit", ref=ref(a.ref), message=a.message)
        out["commit"] = (out.get("bb") or {}).get("value")
        return show(out, keep=("ok", "error", "commit", "wall_s"))
    if a.cmd == "log":
        out = call("log", ref=ref(a.ref), limit=a.n)
        out["log"] = (out.get("bb") or {}).get("value")
        return show(out, keep=("ok", "error", "log"))
    if a.cmd == "diff":
        out = call("diff", a=ref(a.a), b=ref(a.b))
        out["diff"] = (out.get("bb") or {}).get("value")
        return show(out, keep=("ok", "error", "diff", "wall_s"))
    if a.cmd == "merge":
        out = call("merge", into=ref(a.into), source=ref(a.source), message=f"merge {a.source}")
        out["result"] = (out.get("bb") or {}).get("value")
        return show(out, keep=("ok", "error", "result", "wall_s"))
    if a.cmd == "reset":
        return show(call("reset", ref=ref(a.ref), to=a.to), keep=("ok", "error", "wall_s"))
    if a.cmd == "delete":
        if ref(a.name) == info().get("root"):
            print(json.dumps({"ok": False, "error": "main cannot be deleted"}))
            return 1
        return show(call("delete", ref=a.name), keep=("ok", "error", "wall_s"))
    return 2


if __name__ == "__main__":
    sys.exit(main())

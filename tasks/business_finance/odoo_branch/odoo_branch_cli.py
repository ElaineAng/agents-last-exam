#!/usr/bin/env python3
"""odoo-branch: branch, commit, merge and delete versions of the Odoo task database.

Each branch is a full copy of a database that Odoo serves under its own name
(odoo_compact__<name>); "main" is odoo_compact, the database that is graded.

  odoo-branch list                         branches and their Odoo database names
  odoo-branch create NAME [--from REF]     new branch from main (or REF); NAME: [a-z0-9]{1,20}
  odoo-branch db NAME                      Odoo database name and login URL for a branch
  odoo-branch commit REF -m MESSAGE        snapshot a branch (REF@<id> can be reset to later)
  odoo-branch log [REF]                    commits on a branch
  odoo-branch diff REF_A REF_B             row-level summary of what differs
  odoo-branch merge SOURCE [--into main]   merge SOURCE into main (or another branch)
  odoo-branch reset REF --to COMMIT        move a branch back to one of its commits
  odoo-branch delete NAME                  drop a branch you no longer need
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

SERVICE = "http://branchsvc:7000/op"
MAIN = "odoo_compact"
ODOO = "http://odoo:8069"


def ref(name: str) -> str:
    return MAIN if name in ("main", MAIN) else name


def dbname(name: str) -> str:
    return MAIN if ref(name) == MAIN else f"{MAIN}__{name}"


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
    p = argparse.ArgumentParser(prog="odoo-branch", description=__doc__,
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
        db = dbname(a.name)
        print(json.dumps({"database": db, "login_url": f"{ODOO}/web/login?db={db}",
                          "xmlrpc": {"url": ODOO, "db": db}}, indent=1))
        return 0
    if a.cmd == "list":
        out = call("list")
        if out.get("ok"):
            out["branches"] = {b: dbname(b) for b in out.get("branches", [])}
        return show(out, keep=("ok", "error", "branches"))
    if a.cmd == "create":
        out = call("branch", name=a.name, **{"from": ref(a.src)})
        if out.get("ok"):
            out["database"] = dbname(a.name)
            out["login_url"] = f"{ODOO}/web/login?db={out['database']}"
        return show(out, keep=("ok", "error", "database", "login_url", "wall_s"))
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
        if ref(a.name) == MAIN:
            print(json.dumps({"ok": False, "error": "main cannot be deleted"}))
            return 1
        return show(call("delete", ref=a.name), keep=("ok", "error", "wall_s"))
    return 2


if __name__ == "__main__":
    sys.exit(main())

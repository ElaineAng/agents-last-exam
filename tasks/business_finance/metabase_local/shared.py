"""business_finance/metabase_local: the Metabase BI dashboard task on the local Linux stack.

Port of business_finance/metabase_bi_dashboard_01 (Windows VM) to the compose stack:
Metabase 0.54.3 with its application database on PostgreSQL 18 (``metabase_task``,
reset from ``metabase_template`` which was migrated from the task's shipped H2 app DB),
the task's SQLite "Business Analytics" data, and a Linux desktop sandbox with Chromium.

Two variants of one task, identical except for branching:

  branching  the branch service is enabled and the `env-branch` CLI is staged into
             software/; a branch is a copy of the Metabase application database served
             by its own Metabase instance (http://metabase-<name>:3000). The prompt
             instructs the agent to build each chart on a branch and merge verified work.
  baseline   same Metabase, data, prompt and grader; the branch service rejects requests.

Grading: the official ``score_metrics`` (11 fields, equal weight) on
``output/dashboard_metrics.json`` against ``reference/reference_metrics.json``, which is
computed from the SQLite data (the official reference is in ALE's gated repo). The live
dashboard is checked through the Metabase API and reported alongside; it does not change
the official score.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cua_bench as cb

from tasks.business_finance.metabase_bi_dashboard_01.scripts.evaluate_metrics import score_metrics
from tasks.linux_runtime import LinuxTaskConfig

HERE = Path(__file__).resolve().parent
VARIANTS_ROOT = HERE / "variants"
REFERENCE = HERE / "reference" / "reference_metrics.json"
CLI_SOURCE = HERE / "env_branch_cli.py"
ADMIN_URL = os.environ.get("ODOO_BRANCHSVC_ADMIN_URL", "http://127.0.0.1:17001")
METABASE_HOST_URL = os.environ.get("METABASE_HOST_URL", "http://127.0.0.1:3000")
EVAL_TMP_ROOT = "/tmp/agenthle_eval/metabase_local"
DASHBOARD_NAME = "Business Analytics Overview"

VARIANTS = [("branching", True), ("baseline", False)]

BRANCHING_SECTION = """\
Branching protocol (versioned Metabase) - follow it exactly:
- Metabase's application database (questions, dashboards, collections) is versioned. The branch command is
    {cli}
  (written env-branch below; run it with --help). A branch is a full copy of Metabase served by its own
  instance: `env-branch create s1` returns the URL of that instance (http://metabase-s1:3000); log in
  there with the same credentials. "main" is http://metabase:3000; it is the ONLY instance graded.
- Work stage by stage, one branch per stage, in order: s1..s6 = Chart 1..6 from the requirements,
  s7 = create the dashboard "Business Analytics Overview", add the heading card and all charts, arrange it.
  For each stage N:
    1. env-branch create sN            (a fresh branch from the current main; about 20 s)
    2. Do ALL of stage N's work on the sN instance, nothing else.
    3. Verify it there: open the saved question or dashboard and check the numbers against the data.
    4a. Correct: env-branch merge sN, then env-branch delete sN. Stage N is now on main.
    4b. Wrong in any way (wrong query, wrong chart type, a card you had to delete or redo):
        env-branch delete sN and repeat stage N from step 1 on a new branch (sNb, sNc, ...).
        Never repair on a branch you will merge, and never create or edit anything on main directly:
        a branch is merged only if its stage went right the first time on that branch.
- Merge each stage as soon as it is verified. Work not merged into main when time runs out is lost.
- Reading data, running ad-hoc queries without saving, and reading the requirements may be done on main.
- The metrics JSON is a file, not Metabase state: compute it from queries and write it at the end.
- Before you finish: every stage merged and every branch deleted (env-branch list shows only main).
"""


@dataclass
class MetabaseLocalTaskConfig(LinuxTaskConfig):
    DOMAIN_NAME: str = "business_finance"
    TASK_NAME: str = "metabase_local"
    VARIANT_NAME: str = ""
    BRANCHING: bool = False
    METABASE_URL: str = "http://metabase:3000"

    @property
    def cli_path(self) -> str:
        return f"{self.software_dir}/env-branch"

    @property
    def output_file(self) -> str:
        return f"{self.remote_output_dir}/dashboard_metrics.json"

    @property
    def task_description(self) -> str:
        branching = ("\n" + BRANCHING_SECTION.format(cli=self.cli_path)) if self.BRANCHING else ""
        return f"""\
You are a business analyst building a BI dashboard in Metabase.

## Environment
- Metabase is already running at {self.METABASE_URL} (open it with `{self.software_dir}/launch_metabase.sh`
  or the "Metabase" desktop icon). Its HTTP API is at {self.METABASE_URL}/api.
- Login credentials are in: `{self.input_dir}/metabase_credentials.txt`
- The database "Business Analytics" is already connected in Metabase.
{branching}
## Your Task
1. Read the task requirements at `{self.input_dir}/requirements.md`
2. Read the output schema at `{self.input_dir}/output_schema.json`
3. Log in to Metabase
4. Using Metabase, build the required dashboard with all 6 charts and a heading text card
5. Query the Business Analytics database to extract the required metrics
6. Save the final metrics as a JSON file conforming to the output schema

## Output
- Save your JSON report to: `{self.output_file}`
- The JSON must conform to the schema in `{self.input_dir}/output_schema.json`
- All numerical values must be rounded to 2 decimal places
- Revenue calculations must only include orders with status = 'completed'
"""

    def to_metadata(self) -> dict:
        md = super().to_metadata()
        md.update({"variant_name": self.VARIANT_NAME, "branching": self.BRANCHING, "cli_path": self.cli_path,
                   "output_file": self.output_file, "metabase_url": self.METABASE_URL})
        return md


def cfg_for_variant(name: str, branching: bool) -> MetabaseLocalTaskConfig:
    return MetabaseLocalTaskConfig(VARIANT_NAME=name, BRANCHING=branching)


def build_task(name: str, branching: bool) -> cb.Task:
    cfg = cfg_for_variant(name, branching)
    return cb.Task(description=cfg.task_description, metadata=cfg.to_metadata(),
                   computer={"provider": "computer", "setup_config": {"os_type": "linux"}})


def _admin(method: str, path: str, body: dict | None = None, timeout: float = 600) -> dict:
    token = os.environ.get("ODOO_BRANCHSVC_TOKEN", "")
    if not token:
        raise RuntimeError("ODOO_BRANCHSVC_TOKEN is not set (add it to secret/.env)")
    req = urllib.request.Request(ADMIN_URL + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None,
                                 headers={"X-Admin-Token": token, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def _wait_service(branching: bool, timeout: float = 180) -> None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            with urllib.request.urlopen(ADMIN_URL + "/health", timeout=5) as r:
                h = json.loads(r.read())
            if h.get("ready") and h.get("branching") == branching and h.get("app") == "metabase":
                return
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError("branch service did not come back after reset")


async def start_variant_task(task_cfg, session: cb.DesktopSession) -> None:
    md = task_cfg.metadata
    run = f"{md['variant_name']}_{time.strftime('%Y%m%d_%H%M%S')}"
    out = _admin("POST", "/admin/reset", {"run": run, "branching": md["branching"], "app": "metabase"})
    _wait_service(md["branching"])
    await session.run_command(
        f"rm -rf {shlex.quote(md['remote_output_dir'])} && mkdir -p {shlex.quote(md['remote_output_dir'])} "
        f"{EVAL_TMP_ROOT}", check=False)
    if md["branching"]:
        await session.write_file(md["cli_path"], CLI_SOURCE.read_text())
        await session.run_command(f"chmod +x {shlex.quote(md['cli_path'])}", check=False)
    await session.write_file(f"{EVAL_TMP_ROOT}/RESET_OK.txt",
                             json.dumps({"run": run, "branching": md["branching"], "reset": out}) + "\n")


def _credentials() -> tuple[str, str]:
    text = (VARIANTS_ROOT / "baseline" / "input" / "metabase_credentials.txt").read_text()
    email = re.search(r"[\w.+-]+@[\w.-]+", text).group(0)
    pw = next(m.group(1) for line in text.splitlines() for m in [re.match(r"\s*Password\s*[:=]\s*(\S+)", line, re.IGNORECASE)] if m)
    return email, pw


def _api(path: str, token: str | None = None, data: dict | None = None) -> dict | list:
    req = urllib.request.Request(METABASE_HOST_URL + "/api" + path,
                                 data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json",
                                          **({"X-Metabase-Session": token} if token else {})},
                                 method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def dashboard_checks() -> dict:
    """What was built on main, read through the Metabase API. Reported, not scored."""
    try:
        email, pw = _credentials()
        tok = _api("/session", data={"username": email, "password": pw})["id"]
        dashboards = [d for d in _api("/dashboard", tok) if not d.get("archived")]
        named = [d for d in dashboards if (d.get("name") or "").strip().lower() == DASHBOARD_NAME.lower()]
        detail = _api(f"/dashboard/{named[0]['id']}", tok) if named else {}
        cards = detail.get("dashcards") or detail.get("ordered_cards") or []
        questions = [c for c in cards if c.get("card_id")]
        headings = [c for c in cards if not c.get("card_id")
                    and (c.get("visualization_settings") or {}).get("virtual_card", {}).get("display") in ("heading", "text")]
        return {"dashboards_total": len(dashboards), "dashboard_named_found": bool(named),
                "dashboards_named": len(named), "question_cards": len(questions), "heading_or_text_cards": len(headings),
                "card_names": [((c.get("card") or {}).get("name")) for c in questions],
                "displays": sorted({(c.get("card") or {}).get("display") for c in questions if c.get("card")}),
                "dashboard_complete": bool(named) and len(questions) >= 6 and len(headings) >= 1}
    except (urllib.error.URLError, KeyError, IndexError, ValueError) as e:
        return {"error": repr(e)}


async def evaluate_variant_task(task_cfg, session: cb.DesktopSession) -> list[float]:
    md = task_cfg.metadata
    report = {"task": md["task_name"], "variant": md["variant_name"], "branching": md["branching"],
              "scoring_basis": "official score_metrics on output JSON vs computed reference",
              "dashboard_checks": dashboard_checks()}
    ref_json = REFERENCE.read_text()
    if not await session.file_exists(md["output_file"]):
        report.update({"final_score": 0.0, "error": "output file missing"})
    else:
        try:
            agent_json = (await session.read_bytes(md["output_file"])).decode("utf-8-sig")
            result = score_metrics(agent_json, ref_json)
            report.update({"final_score": float(result["score"]), "details": result.get("details")})
        except Exception as exc:  # noqa: BLE001 - a bad file is a zero, not an evaluation error
            report.update({"final_score": 0.0, "error": repr(exc)})
    payload = json.dumps(report, indent=2, default=str)
    await session.write_file(f"{md['remote_output_dir']}/autograde_report.json", payload)
    await session.write_file(f"{EVAL_TMP_ROOT}/autograde_report.json", payload)
    return [report["final_score"]]

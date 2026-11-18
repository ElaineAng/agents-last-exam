"""business_finance/odoo_branch: the odoo_local workflow on a branchable database.

Two variants of one task, identical except for branching:

  branching  the BranchBench file_copy branch service is enabled and the `odoo-branch` CLI is
             staged into software/; the prompt instructs the agent to branch before actions
             that could damage state, verify on the branch, merge good work into main and
             delete failed branches.
  baseline   same database, Odoo, prompt and grader; the branch service rejects requests
             and no CLI is staged.

Setup resets both through the branch service's admin API (host-only, token in
ODOO_BRANCHSVC_TOKEN): every branch and snapshot database is dropped, odoo_compact is
recreated from AgentService, and the service restarts with this run's branching flag and
operation log. Grading is the official odoo grader on main (odoo_compact), unchanged.
"""
from __future__ import annotations

import json
import os
import shlex
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import cua_bench as cb

from tasks.business_finance.odoo import shared as official
from tasks.business_finance.odoo_local import shared as local

HERE = Path(__file__).resolve().parent
VARIANTS_ROOT = HERE / "variants"
CLI_SOURCE = HERE / "odoo_branch_cli.py"
ADMIN_URL = os.environ.get("ODOO_BRANCHSVC_ADMIN_URL", "http://127.0.0.1:17001")

_SPEC = official.VARIANTS_BY_NAME["odoo_compact"]
VARIANTS = [("branching", True), ("baseline", False)]

BRANCHING_SECTION = """\
Branching protocol (versioned task database) - follow it exactly:
- The task database is versioned. The branch command is
    {cli}
  (written odoo-branch below; run it with --help). Each branch is a full copy of the database
  that Odoo serves under its own name, odoo_compact__<name>: open it in the browser with
  ?db=odoo_compact__<name> (e.g. http://odoo:8069/web/login?db=odoo_compact__s1) or pass that
  name as the XML-RPC db. "main" is the database odoo_compact; it is the ONLY database graded.
- Work stage by stage, one branch per stage. The stages are the numbered steps of the
  workflow (1-11) plus the return/refund as stage 12. For each stage N, in order:
    1. odoo-branch create sN       (a fresh branch from the current main; about 1 s)
    2. Do ALL of stage N's work in database odoo_compact__sN, nothing else.
    3. Verify stage N on odoo_compact__sN against the workflow's required values
       (records, quantities, amounts, states). Read the data back; do not assume.
    4a. Correct: odoo-branch merge sN, then odoo-branch delete sN. Stage N is now on main.
    4b. Wrong in any way (an error, a wrong record, a wrong amount, a step you had to undo):
        odoo-branch delete sN, then repeat stage N from step 1 on a new branch (sNb, sNc, ...).
        Do not repair or undo anything on a branch you will merge, and never write to main
        directly: a branch is merged only if its stage went right the first time on that branch.
- Merge each stage as soon as it is verified. Work that is not merged into main when your
  time runs out is lost and scores nothing.
- Read-only checks (searching, reading records) may be done on main at any time.
- Before you finish: every stage merged and every branch deleted (odoo-branch list shows only main).
"""


@dataclass
class OdooBranchTaskConfig(local.OdooLocalTaskConfig):
    TASK_NAME: str = "odoo_branch"
    BRANCHING: bool = False

    @property
    def cli_path(self) -> str:
        return f"{self.software_dir}/odoo-branch"

    @property
    def task_description(self) -> str:
        prompt_text = (VARIANTS_ROOT / self.VARIANT_NAME / "input" / "prompt.txt").read_text(encoding="utf-8").strip()
        branching = ("\n" + BRANCHING_SECTION.format(cli=self.cli_path)) if self.BRANCHING else ""
        return f"""\
Goal:
Complete the recovered end-to-end Odoo supply-chain workflow and leave the final business state inside the task database.

Variant:
- {self.VARIANT_NAME}
- {self.VARIANT_NOTE}

Recovered prompt:
{prompt_text}

Inputs / Environment:
- The benchmark data for this variant is staged under {self.task_dir}.
- The Odoo web server is at {self.ODOO_URL}. Prepare or restore the environment as needed to complete the task.
- Use {self.launch_script_path} (or the "Odoo" desktop icon) to open the correct database in Chromium.
- Task setup resets database "{self.DEFAULT_DB_NAME}" from template "{self.TEMPLATE_DB_NAME}".
- You must work ONLY inside database "{self.DEFAULT_DB_NAME}"{" and its branches" if self.BRANCHING else ""}.
- Use the run tag "{self.RUN_TAG}" in searchable fields such as Reference / Notes / Customer Ref / Vendor Ref on key documents you create manually.
- The agent-visible task prompt is staged at {self.prompt_path}.
- Odoo web login: {self.ADMIN_LOGIN} / {self.ADMIN_PASSWORD}.
{branching}
Warehouses:
- Inbound warehouse code: "WH" (location tree rooted at "WH/Stock")
- Production & Shipping warehouse code: "My Co" (rooted at "My Co/Stock")

Output:
Save these files into {self.remote_output_dir}
1. lc_split.png
2. invoices.png
3. return_credit.png
4. stock_wh.png
5. submission.txt
"""

    def to_metadata(self) -> dict:
        md = super().to_metadata()
        md.update({"branching": self.BRANCHING, "cli_path": self.cli_path})
        return md


def cfg_for_variant(name: str, branching: bool) -> OdooBranchTaskConfig:
    return OdooBranchTaskConfig(
        VARIANT_NAME=name, BRANCHING=branching, RUN_TAG=_SPEC.run_tag,
        DEFAULT_DB_NAME=_SPEC.db_name, VARIANT_NOTE=_SPEC.variant_note,
    )


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


def _wait_service(branching: bool, timeout: float = 120) -> None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        try:
            with urllib.request.urlopen(ADMIN_URL + "/health", timeout=5) as r:
                h = json.loads(r.read())
            if h.get("ready") and h.get("branching") == branching and h.get("app", "odoo") == "odoo":
                return
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError("branch service did not come back after reset")


async def start_variant_task(task_cfg, session: cb.DesktopSession) -> None:
    md = task_cfg.metadata
    run = f"{md['variant_name']}_{time.strftime('%Y%m%d_%H%M%S')}"
    out = _admin("POST", "/admin/reset", {"run": run, "branching": md["branching"], "app": "odoo"})
    _wait_service(md["branching"])
    await session.run_command(
        f"rm -rf {shlex.quote(md['remote_output_dir'])} && mkdir -p {shlex.quote(md['remote_output_dir'])} "
        f"{local.EVAL_TMP_ROOT}", check=False)
    if md["branching"]:
        await session.write_file(md["cli_path"], CLI_SOURCE.read_text())
        await session.run_command(f"chmod +x {shlex.quote(md['cli_path'])}", check=False)
    await session.write_file(f"{local.EVAL_TMP_ROOT}/RESET_OK.txt",
                             json.dumps({"run": run, "branching": md["branching"], "reset": out}) + "\n")


async def evaluate_variant_task(task_cfg, session: cb.DesktopSession) -> list[float]:
    return await local.evaluate_variant_task(task_cfg, session)

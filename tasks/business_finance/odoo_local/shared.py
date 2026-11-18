"""Linux/Docker port of business_finance/odoo for a local arm64 sandbox.

Topology (see stack/docker-compose.yml): the agent drives a desktop sandbox
container through cua-computer-server; Odoo 19 and PostgreSQL 17 run in sibling
containers reachable from the sandbox as ``odoo:8069`` and ``db:5432``.

Grading reuses the official ``tasks.business_finance.odoo.shared.evaluate_variant_task``
unchanged. ``_LinuxShellSession`` translates its PowerShell + psql.exe commands and
Windows paths into bash + psql inside the sandbox, so the 38 checks are identical.
"""
from __future__ import annotations

import logging
import re
import shlex
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

import cua_bench as cb

from tasks.business_finance.odoo import shared as official
from tasks.linux_runtime import LinuxTaskConfig

logger = logging.getLogger(__name__)

VARIANTS_ROOT = Path(__file__).resolve().parent / "variants"
EVAL_TMP_ROOT = "/tmp/agenthle_eval/odoo_local"
VARIANTS = [official.VARIANTS_BY_NAME["odoo_compact"]]


@dataclass
class OdooLocalTaskConfig(LinuxTaskConfig):
    DOMAIN_NAME: str = "business_finance"
    TASK_NAME: str = "odoo_local"
    VARIANT_NAME: str = ""
    RUN_TAG: str = ""
    DEFAULT_DB_NAME: str = ""
    VARIANT_NOTE: str = ""

    ODOO_URL: str = "http://odoo:8069/web"
    TEMPLATE_DB_NAME: str = "AgentService"
    PG_HOST: str = "db"
    PG_USER: str = "openpg"
    PG_PASSWORD: str = "openpgpwd"
    ADMIN_LOGIN: str = "admin@example.com"
    ADMIN_PASSWORD: str = "admin"

    @property
    def prompt_path(self) -> str:
        return f"{self.input_dir}/prompt.txt"

    @property
    def launch_script_path(self) -> str:
        return f"{self.software_dir}/launch_odoo.sh"

    @property
    def task_description(self) -> str:
        prompt_text = (VARIANTS_ROOT / self.VARIANT_NAME / "input" / "prompt.txt").read_text(encoding="utf-8").strip()
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
- You must work ONLY inside database "{self.DEFAULT_DB_NAME}".
- Use the run tag "{self.RUN_TAG}" in searchable fields such as Reference / Notes / Customer Ref / Vendor Ref on key documents you create manually.
- The agent-visible task prompt is staged at {self.prompt_path}.
- Odoo web login: {self.ADMIN_LOGIN} / {self.ADMIN_PASSWORD}.

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
        md.update({
            "variant_name": self.VARIANT_NAME,
            "run_tag": self.RUN_TAG,
            "db_name": self.DEFAULT_DB_NAME,
            "template_db": self.TEMPLATE_DB_NAME,
            "odoo_url": self.ODOO_URL,
            "pg_host": self.PG_HOST,
            "pg_user": self.PG_USER,
            "pg_password": self.PG_PASSWORD,
            "psql_path": "psql",
            "psql_args": f"-h {self.PG_HOST} -p 5432 -U {self.PG_USER}",
            "odoo_admin_login": self.ADMIN_LOGIN,
            "odoo_admin_password": self.ADMIN_PASSWORD,
            "prompt_path": self.prompt_path,
            "launch_script_path": self.launch_script_path,
        })
        return md


def cfg_for_variant(spec: official.VariantSpec) -> OdooLocalTaskConfig:
    return OdooLocalTaskConfig(
        VARIANT_NAME=spec.variant_name,
        RUN_TAG=spec.run_tag,
        DEFAULT_DB_NAME=spec.db_name,
        VARIANT_NOTE=spec.variant_note,
    )


def build_task(spec: official.VariantSpec) -> cb.Task:
    cfg = cfg_for_variant(spec)
    return cb.Task(
        description=cfg.task_description,
        metadata=cfg.to_metadata(),
        computer={"provider": "computer", "setup_config": {"os_type": "linux"}},
    )


def _linux_path(path: str) -> str:
    """Map a Windows path from the official grader onto the sandbox filesystem."""
    p = PureWindowsPath(path)
    if p.drive:
        return EVAL_TMP_ROOT + "/" + "/".join(p.parts[-2:])
    return str(path).replace("\\", "/")


_PSQL_RE = re.compile(r"-d (\S+) -v ON_ERROR_STOP=1 -t -A -q -f \\\"(.+?)\\\"")


class _LinuxShellSession:
    """Adapter that lets the official (Windows) Odoo grader run against a Linux sandbox."""

    def __init__(self, session, pg_password: str):
        self._s = session
        self._pg_password = pg_password
        self.interface = self

    async def create_dir(self, path):
        await self._s.run_command(f"mkdir -p {shlex.quote(_linux_path(path))}", check=False)

    async def write_file(self, path, content):
        target = _linux_path(path)
        await self._s.run_command(f"mkdir -p {shlex.quote(str(Path(target).parent))}", check=False)
        await self._s.write_file(target, content)

    async def file_exists(self, path):
        return await self._s.file_exists(_linux_path(path))

    async def read_bytes(self, path):
        return await self._s.read_bytes(_linux_path(path))

    async def run_command(self, cmd, check=False):
        if "_resolve_pg.ps1" in cmd:
            return {"stdout": "{}", "stderr": "", "return_code": 0}
        m = _PSQL_RE.search(cmd)
        if not m:
            raise RuntimeError(f"odoo_local adapter: unhandled grader command: {cmd[:160]}")
        db, sql_path = m.group(1), _linux_path(m.group(2))
        bash = (
            f"PGPASSWORD={shlex.quote(self._pg_password)} psql -h db -p 5432 -U openpg -d {shlex.quote(db)} "
            f"-v ON_ERROR_STOP=1 -t -A -q -f {shlex.quote(sql_path)}; "
            "echo __ALE_PSQL_STATUS__=$?"
        )
        return await self._s.run_command(bash, check=False)


async def _psql(session, md: dict, db: str, sql: str) -> dict:
    cmd = (
        f"PGPASSWORD={shlex.quote(md['pg_password'])} psql -h {md['pg_host']} -U {md['pg_user']} "
        f"-d {shlex.quote(db)} -v ON_ERROR_STOP=1 -t -A -q -c {shlex.quote(sql)}"
    )
    return await session.run_command(cmd, check=False)


async def start_variant_task(task_cfg, session: cb.DesktopSession) -> None:
    md = task_cfg.metadata
    db, template, out_dir = md["db_name"], md["template_db"], md["remote_output_dir"]
    await session.run_command(
        f"rm -rf {shlex.quote(out_dir)} && mkdir -p {shlex.quote(out_dir)} {EVAL_TMP_ROOT}", check=False
    )
    steps = [
        ("postgres", (f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                      f"WHERE datname IN ('{db}', '{template}') AND pid <> pg_backend_pid();")),
        ("postgres", f"DROP DATABASE IF EXISTS {db} WITH (FORCE);"),
        ("postgres", f'CREATE DATABASE {db} TEMPLATE "{template}";'),
        (db, f"UPDATE res_users SET login = '{md['odoo_admin_login']}' WHERE id = 2;"),
    ]
    for target_db, sql in steps:
        res = await _psql(session, md, target_db, sql)
        if res.get("return_code", 0) != 0:
            await session.write_file(f"{EVAL_TMP_ROOT}/RESET_FAILED.txt", f"{sql}\n{res.get('stderr')}")
            raise RuntimeError(f"odoo_local setup failed on {sql!r}: {res.get('stderr')}")
    await session.write_file(f"{EVAL_TMP_ROOT}/RESET_OK.txt", f"Reset {db} from {template}.\n")


async def evaluate_variant_task(task_cfg, session: cb.DesktopSession) -> list[float]:
    md = dict(task_cfg.metadata)
    task_cfg.metadata = md
    return await official.evaluate_variant_task(task_cfg, _LinuxShellSession(session, md["pg_password"]))

from __future__ import annotations

import cua_bench as cb

from tasks.business_finance.odoo_branch.shared import VARIANTS, build_task, evaluate_variant_task, start_variant_task
from tasks.common_setup import BaseTaskSetup


class _OdooBranchSetup(BaseTaskSetup):
    """Per-run reset through the branch service: drop branches, recreate the task DB, set the branching flag."""

    async def setup(self, task_cfg, session: cb.DesktopSession) -> None:
        await start_variant_task(task_cfg, session)


_setup = _OdooBranchSetup()


@cb.tasks_config(split="train")
def load():
    return [build_task(name, branching) for name, branching in VARIANTS]


@cb.setup_task(split="train")
async def start(task_cfg, session: cb.DesktopSession):
    await _setup(task_cfg, session)


@cb.evaluate_task(split="train")
async def evaluate(task_cfg, session: cb.DesktopSession):
    return await evaluate_variant_task(task_cfg, session)

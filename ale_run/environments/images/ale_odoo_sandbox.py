"""``ale-odoo-sandbox`` — local desktop sandbox for ``business_finance/odoo_local``.

Built from ``stack/sandbox/Dockerfile`` (bGym repo) (Debian trixie: XFCE on Xvfb, Chromium,
cua-computer-server on 5000, psql, noVNC on 6901) with the task's input/ and software/
baked in at the ``ale-ubuntu22`` path conventions. Odoo and PostgreSQL run as sibling
containers; the docker provider attaches the sandbox to their network (``network:``).

Only host-side harnesses (``ale_claw``) are supported: the image has no node and no
``/opt/ale-run`` venv, so in-sandbox deployers (claude_code, codex, ...) cannot install.
"""
from __future__ import annotations

from . import Image


IMAGE = Image(
    name="ale-odoo-sandbox",
    os="linux",
    work_dir_base="/home/user/.ale",
    task_data_root="/media/user/data/agenthle",
    node="/usr/bin/node",
    python="/opt/cua/bin/python",
    mcp_server_dir="/home/user/cua_mcp_server",
    default_machine_type="e2-standard-4",
    docker_image="odoo-sandbox:local",
    docker_entrypoint="/entrypoint.sh",
    cua_server_port=5000,
)

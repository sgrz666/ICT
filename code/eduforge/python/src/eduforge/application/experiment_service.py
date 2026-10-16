"""模板实例化、版本管理和版本回退服务。

对齐方案 §1.2 和 §6.1。
"""
from __future__ import annotations

import json
from pathlib import Path
import uuid
import asyncpg

from eduforge.domain.contracts import ExperimentCreated
from eduforge.domain.errors import ConflictError, NotFoundError
from eduforge.infrastructure.catalog import CatalogError, load_native


class ExperimentNotFound(NotFoundError):
    pass


class TemplateNotFound(NotFoundError):
    pass


class RevisionNotFound(NotFoundError):
    pass


class ActiveJobConflict(ConflictError):
    pass


class ExperimentService:
    """实验聚合与版本管理服务。"""

    def __init__(self, conn: asyncpg.Connection, templates_dir: Path | None = None) -> None:
        self.conn = conn
        self.templates_dir = templates_dir or (
            Path(__file__).resolve().parents[4] / "catalog" / "templates"
        )

    async def create_from_template(self, *, owner_id: str, template_id: str) -> ExperimentCreated:
        """从可信模板克隆初始实验与基础版本。"""
        try:
            native = load_native(template_id)
        except CatalogError as exc:
            raise TemplateNotFound(f"未知模板: {template_id}") from exc

        exp_id = uuid.uuid4()
        rev_id = uuid.uuid4()

        await self.conn.execute(
            """insert into experiments (id, owner_id, template_id, head_revision_id)
               values ($1, $2, $3, $4)""",
            exp_id, owner_id, template_id, rev_id,
        )
        await self.conn.execute(
            """insert into experiment_revisions (id, experiment_id, parent_id, engine_id, native_data)
               values ($1, $2, NULL, 'ray_optics', $3::jsonb)""",
            rev_id, exp_id, json.dumps(native),
        )
        return ExperimentCreated(experiment_id=exp_id, base_revision=rev_id, template_id=template_id)

    async def instantiate(self, *, owner_id: str, template_id: str) -> dict:
        created = await self.create_from_template(owner_id=owner_id, template_id=template_id)
        return {"experiment_id": created.experiment_id, "base_revision": created.base_revision, "template_id": created.template_id}

    async def rollback(self, *, owner_id: str, experiment_id: uuid.UUID, target_revision_id: uuid.UUID) -> dict:
        """安全回滚当前 head_revision 指针到指定历史版本。"""
        exp = await self.conn.fetchrow(
            "select id, owner_id, template_id, head_revision_id from experiments where id = $1",
            experiment_id,
        )
        if exp is None or exp["owner_id"] != owner_id:
            raise ExperimentNotFound(str(experiment_id))

        rev = await self.conn.fetchrow(
            "select id from experiment_revisions where id = $1 and experiment_id = $2",
            target_revision_id, experiment_id,
        )
        if rev is None:
            raise RevisionNotFound(str(target_revision_id))

        active = await self.conn.fetchrow(
            "select id from jobs where experiment_id = $1 and status in ('queued', 'running')",
            experiment_id,
        )
        if active is not None:
            raise ActiveJobConflict(str(active["id"]))

        await self.conn.execute(
            "update experiments set head_revision_id = $1 where id = $2",
            target_revision_id, experiment_id,
        )

        detail = await ExperimentLookup(self.conn).get(experiment_id)
        assert detail is not None
        return detail


class ExperimentLookup:
    """实验与版本历史查询。"""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self.conn = conn

    async def get(self, experiment_id: uuid.UUID) -> dict | None:
        row = await self.conn.fetchrow(
            "select id, owner_id, template_id, head_revision_id from experiments where id = $1",
            experiment_id,
        )
        if row is None:
            return None
        revs = await self.conn.fetch(
            "select id, created_at from experiment_revisions where experiment_id = $1 order by created_at",
            experiment_id,
        )
        return {
            "experiment_id": str(row["id"]),
            "template_id": row["template_id"],
            "head_revision": str(row["head_revision_id"]) if row["head_revision_id"] else None,
            "revision_count": len(revs),
            "revisions": [str(r["id"]) for r in revs],
        }

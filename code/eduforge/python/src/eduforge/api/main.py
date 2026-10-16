"""业务 API（§6.1）。

owner_id 由入口注入：本地固定开发身份，云端由认证层注入。路由绝不从正文接受它。
"""
from __future__ import annotations

import hashlib
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import asyncpg
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import Response

from eduforge.application.services import (
    ActiveJobConflict,
    ExperimentLookup,
    ExperimentNotFound,
    ExperimentService,
    JobService,
    RevisionNotFound,
    TemplateNotFound,
)
from eduforge.infrastructure.catalog import CatalogError, list_templates
from eduforge.domain.contracts import (
    ApiErrorResponse,
    CreateJobRequest,
    ExperimentCreated,
    ExperimentDetail,
    JobAccepted,
    JobCancelled,
    JobView,
    RevisionArtifacts,
    RevisionList,
    RollbackRequest,
    TemplateList,
)
from eduforge.infrastructure.db.repositories import (
    JOBS_DDL,
    DuplicateIdempotencyKey,
)

LOCAL_DEV_OWNER = "local-dev"

# 错误响应写进 OpenAPI，TS 侧才能生成可判别的 code 联合；
# 这些是文档声明，FastAPI 不会拿它们校验响应体。
NOT_FOUND = {404: {"model": ApiErrorResponse}}
CONFLICT = {409: {"model": ApiErrorResponse}}


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await asyncpg.create_pool(dsn=app.state.dsn, min_size=1, max_size=4)
    async with pool.acquire() as c:
        await c.execute(JOBS_DDL)
    app.state.pool = pool
    yield
    await pool.close()


def create_app(dsn: str, artifact_dir: Path | str) -> FastAPI:
    """artifact_dir 必填：产物字节只有一个可交付来源。

    不给默认值是刻意的——数据库里的 native_data 是 jsonb，渲染形式被 Postgres
    规范化过（空格、键序），拿它当下载体会和登记在 artifacts.sha256 的文件字节
    永远对不上，校验成了假校验。字节只能从 artifact_dir / storage_key 取。
    """
    app = FastAPI(title="EduForge", lifespan=lifespan)
    app.state.dsn = dsn
    app.state.artifact_dir = Path(artifact_dir)

    @app.get("/api/v1/templates", response_model=TemplateList)
    async def templates():
        return {
            "templates": [
                {
                    "template_id": t.template_id,
                    "title": t.title,
                    "engine_id": t.engine_id,
                    "units_per_unit": t.units_per_unit,
                    "routes": t.routes,
                    "views": t.views,
                    "controls": [
                        {
                            "entity_id": c.entity_id,
                            "parameter": c.parameter,
                            "label": c.label,
                            "unit": c.unit,
                            "min": c.min,
                            "max": c.max,
                            "initial": c.initial,
                        }
                        for c in t.controls
                    ],
                    "native_file": str((t.directory / "native.json")) if t.directory else "",
                }
                for t in list_templates()
            ]
        }

    @app.post(
        "/api/v1/experiments", status_code=201,
        response_model=ExperimentCreated, responses=NOT_FOUND,
    )
    async def create_experiment(request: Request, template_id: str):
        async with request.app.state.pool.acquire() as c:
            try:
                return await ExperimentService(
                    c, artifact_dir=request.app.state.artifact_dir
                ).create_from_template(
                    owner_id=request.state.owner_id, template_id=template_id
                )
            except (TemplateNotFound, CatalogError):
                raise HTTPException(404, detail={"code": "TEMPLATE_NOT_FOUND"})

    @app.post(
        "/api/v1/jobs", status_code=202,
        response_model=JobAccepted, responses=CONFLICT,
    )
    async def create_job(
        request: Request,
        body: CreateJobRequest,
        idempotency_key: uuid.UUID = Header(alias="Idempotency-Key"),
    ):
        async with request.app.state.pool.acquire() as c:
            try:
                accepted = await JobService(c).submit(
                    owner_id=request.state.owner_id,
                    idempotency_key=idempotency_key,
                    body=body,
                )
                return accepted
            except DuplicateIdempotencyKey:
                raise HTTPException(409, detail={"code": "IDEMPOTENCY_CONFLICT"})

    @app.get("/api/v1/jobs/{job_id}", response_model=JobView, responses=NOT_FOUND)
    async def get_job(request: Request, job_id: uuid.UUID):
        async with request.app.state.pool.acquire() as c:
            out = await JobService(c).get(job_id)
        if out is None:
            raise HTTPException(404, detail={"code": "JOB_NOT_FOUND"})
        return out

    @app.get(
        "/api/v1/experiments/{experiment_id}",
        response_model=ExperimentDetail, responses=NOT_FOUND,
    )
    async def get_experiment(request: Request, experiment_id: uuid.UUID):
        async with request.app.state.pool.acquire() as c:
            out = await ExperimentLookup(c).get(experiment_id)
        if out is None:
            raise HTTPException(404, detail={"code": "EXPERIMENT_NOT_FOUND"})
        return out

    @app.post(
        "/api/v1/experiments/{experiment_id}/rollback",
        response_model=ExperimentDetail,
        responses={**NOT_FOUND, **CONFLICT},
    )
    async def rollback_experiment(
        request: Request,
        experiment_id: uuid.UUID,
        body: RollbackRequest,
    ):
        async with request.app.state.pool.acquire() as c:
            try:
                return await ExperimentService(c).rollback(
                    owner_id=request.state.owner_id,
                    experiment_id=experiment_id,
                    target_revision_id=body.target_revision_id,
                )
            except ExperimentNotFound:
                raise HTTPException(404, detail={"code": "EXPERIMENT_NOT_FOUND"})
            except RevisionNotFound:
                raise HTTPException(404, detail={"code": "REVISION_NOT_FOUND"})
            except ActiveJobConflict:
                raise HTTPException(409, detail={"code": "ACTIVE_JOB_RUNNING"})

    @app.post(
        "/api/v1/jobs/{job_id}/cancel", status_code=202,
        response_model=JobCancelled, responses={**NOT_FOUND, **CONFLICT},
    )
    async def cancel_job(request: Request, job_id: uuid.UUID):
        """§3.5：取消后禁止继续发布。已成功的任务不被回滚。"""
        async with request.app.state.pool.acquire() as c:
            try:
                status = await JobService(c).cancel(owner_id=request.state.owner_id, job_id=job_id)
            except KeyError:
                raise HTTPException(404, detail={"code": "JOB_NOT_FOUND"})
        if status == "succeeded":
            raise HTTPException(409, detail={"code": "ALREADY_SUCCEEDED"})
        return {"job_id": job_id, "status": status}

    @app.get(
        "/api/v1/experiments/{experiment_id}/revisions",
        response_model=RevisionList,
    )
    async def revisions(request: Request, experiment_id: uuid.UUID):
        async with request.app.state.pool.acquire() as c:
            rows = await c.fetch(
                "select id as revision_id, parent_id, engine_id, created_at "
                "from experiment_revisions where experiment_id = $1 order by created_at",
                experiment_id,
            )
        return {"revisions": [dict(r) for r in rows]}

    @app.get(
        "/api/v1/revisions/{revision_id}/artifacts",
        response_model=RevisionArtifacts,
    )
    async def revision_artifacts(request: Request, revision_id: uuid.UUID):
        async with request.app.state.pool.acquire() as c:
            rows = await c.fetch(
                "select id as artifact_id, media_type, sha256, storage_key from artifacts "
                "where revision_id = $1 order by created_at",
                revision_id,
            )
        return {"revision_id": revision_id, "artifacts": [dict(r) for r in rows]}

    @app.get(
        "/api/v1/artifacts/{artifact_id}/download",
        responses={
            200: {
                "description": "交付的文件原文，不是业务 DTO；x-content-sha256 是这份字节的哈希，"
                "客户端必须先校验再用。",
                "content": {
                    "application/json": {"schema": {"type": "object", "additionalProperties": True}}
                },
                "headers": {
                    "x-content-sha256": {"description": "响应字节的 SHA-256", "schema": {"type": "string"}}
                },
            },
            403: {"model": ApiErrorResponse},
            500: {"model": ApiErrorResponse},
            **NOT_FOUND,
        },
    )
    async def download(request: Request, artifact_id: uuid.UUID):
        async with request.app.state.pool.acquire() as c:
            row = await c.fetchrow(
                "select id, storage_key, sha256, media_type from artifacts where id = $1",
                artifact_id,
            )
        if row is None:
            raise HTTPException(404, detail={"code": "ARTIFACT_NOT_FOUND"})

        root = Path(request.app.state.artifact_dir).resolve()
        target = (root / row["storage_key"]).resolve()
        # storage_key 来自数据库，照样可能是 ../ 或另一个盘的绝对路径
        if target == root or not target.is_relative_to(root):
            raise HTTPException(403, detail={"code": "STORAGE_KEY_OUT_OF_ROOT"})
        try:
            body = target.read_bytes()
        except (FileNotFoundError, IsADirectoryError):
            # 绝不退回 native_data::text：那是另一种序列化，哈希必然不相等
            raise HTTPException(404, detail={"code": "ARTIFACT_FILE_MISSING"})

        digest = hashlib.sha256(body).hexdigest()
        if digest != row["sha256"]:
            raise HTTPException(500, detail={"code": "CONTENT_HASH_MISMATCH"})

        return Response(
            content=body, media_type=row["media_type"],
            headers={"x-content-sha256": digest},
        )

    @app.middleware("http")
    async def inject_owner(request: Request, call_next):
        request.state.owner_id = LOCAL_DEV_OWNER
        return await call_next(request)

    return app

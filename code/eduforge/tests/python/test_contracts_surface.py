"""§6.2 守卫：业务 DTO 只能有一个来源（后端 OpenAPI）。

这一条本来是空话：路由直接 return dict 时 OpenAPI 里没有类型可抽，
生成的 api.d.ts 只剩 CreateJobRequest 一个请求体，前端只能手写第二套 DTO。
所以这里断言的是"每个业务接口的 2xx 都指向一个具名组件"，
而不是"路由注册上了"——后者对裸 dict 返回也成立，抓不住回归。
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path

import httpx

# (方法, 路径, 状态码, 期望的具名组件)
BUSINESS_RESPONSES = [
    ("get", "/api/v1/templates", "200", "TemplateList"),
    ("post", "/api/v1/experiments", "201", "ExperimentCreated"),
    ("get", "/api/v1/experiments/{experiment_id}", "200", "ExperimentDetail"),
    ("get", "/api/v1/experiments/{experiment_id}/revisions", "200", "RevisionList"),
    ("post", "/api/v1/jobs", "202", "JobAccepted"),
    ("get", "/api/v1/jobs/{job_id}", "200", "JobView"),
    ("post", "/api/v1/jobs/{job_id}/cancel", "202", "JobCancelled"),
    ("get", "/api/v1/revisions/{revision_id}/artifacts", "200", "RevisionArtifacts"),
]

DOCUMENTED_ERRORS = [
    ("post", "/api/v1/experiments", "404"),
    ("get", "/api/v1/experiments/{experiment_id}", "404"),
    ("get", "/api/v1/jobs/{job_id}", "404"),
    ("post", "/api/v1/jobs/{job_id}/cancel", "404"),
    ("post", "/api/v1/jobs/{job_id}/cancel", "409"),
    ("get", "/api/v1/artifacts/{artifact_id}/download", "404"),
]


def spec() -> dict:
    """不跑 lifespan：取 OpenAPI 不需要数据库。"""
    from eduforge.api.main import create_app

    async def go():
        app = create_app("postgresql://unused/unused", Path(tempfile.gettempdir()))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get("/openapi.json")
            r.raise_for_status()
            return r.json()

    return asyncio.run(go())


def ref_name(operation: dict, status: str) -> str | None:
    schema = (
        operation.get("responses", {}).get(status, {}).get("content", {})
        .get("application/json", {})
        .get("schema", {})
    )
    return schema.get("$ref", "").split("/")[-1] or None


def generated_text() -> str:
    return (
        Path(__file__).resolve().parents[2]
        / "packages" / "contracts" / "src" / "generated" / "api.ts"
    ).read_text(encoding="utf-8")


def generated_names() -> set[str]:
    out = set()
    for line in generated_text().splitlines():
        if line.startswith("export interface ") or line.startswith("export type "):
            out.add(line.split()[2].rstrip("{").strip())
    return out


def test_every_business_success_response_is_a_named_component():
    document = spec()
    for verb, path, status, model in BUSINESS_RESPONSES:
        ops = document["paths"].get(path)
        assert ops, f"接口不见了：{path}"
        got = ref_name(ops[verb], status)
        assert got == model, (
            f"{verb.upper()} {path} 的 {status} 响应不是具名组件 {model}，实际 {got}。"
            "裸 dict 返回会让 §6.2『类型由后端生成』失效。"
        )


def test_error_codes_are_documented():
    """错误码要能进 TS 类型，否则前端只能对字符串做裸比较。"""
    document = spec()
    for verb, path, status in DOCUMENTED_ERRORS:
        op = document["paths"][path][verb]
        assert status in op.get("responses", {}), f"{verb.upper()} {path} 未声明 {status}"
        assert ref_name(op, status) == "ApiErrorResponse", (
            f"{verb.upper()} {path} 的 {status} 不是 ApiErrorResponse"
        )


def test_post_jobs_body_is_the_contract_not_a_free_object():
    op = spec()["paths"]["/api/v1/jobs"]["post"]
    schema = op["requestBody"]["content"]["application/json"]["schema"]
    assert schema.get("$ref", "").endswith("CreateJobRequest"), schema


def test_download_route_is_not_faked_as_a_dto():
    """下载返回文件原文。给它安一个业务 DTO 就是假装我们有第二种场景格式。"""
    resp = spec()["paths"]["/api/v1/artifacts/{artifact_id}/download"]["get"]["responses"]["200"]
    blob = json.dumps(resp)
    assert "$ref" not in blob, f"下载接口被当成业务 DTO 了：{blob}"
    assert "x-content-sha256" in resp.get("headers", {}), "校验头没写进契约，前端会以为不用校验"


def test_generated_ts_covers_the_live_openapi():
    """生成物不许落后于后端：新增 DTO 没重跑生成器就必须红。"""
    schemas = set(spec().get("components", {}).get("schemas", {}))
    missing = schemas - generated_names()
    assert not missing, f"api.d.ts 落后于后端契约，缺：{missing}"


def test_generated_ts_keeps_enum_and_null_information():
    """枚举与可空必须落成字面量联合和 null。

    状态是前端轮询分支的依据；退化成 string 或 unknown 等于把 DTO 又推回前端手写。
    """
    text = generated_text()
    for lit in ['"queued"', '"running"', '"succeeded"', '"failed"', '"cancelled"']:
        assert lit in text, f"状态枚举字面量丢了：{lit}"
    assert "| unknown" not in text, "生成器把不认识的 schema 写成 unknown 了"
    assert "string | null" in text, "可空字段没落成 null"

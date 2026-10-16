"""从 FastAPI 的 OpenAPI 生成 TS 类型（§6.2：不手写第二套业务 DTO）。

用法：uv run python tools/export_contracts.py
产出：packages/contracts/src/generated/api.ts
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "packages" / "contracts" / "src" / "generated" / "api.ts"


def openapi() -> dict:
    """用 create_app 的 lifespan 起一次，取 /openapi.json。"""
    import asyncio

    import httpx

    from eduforge.api.main import create_app

    async def go():
        # artifact_dir 只为构造 app，取 OpenAPI 不碰文件
        app = create_app("postgresql://unused/unused", Path(tempfile.gettempdir()))
        # 不跑 lifespan：openapi 不需要数据库
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
            r = await c.get("/openapi.json")
            r.raise_for_status()
            return r.json()

    return asyncio.run(go())


PRIMS = {"string": "string", "integer": "number", "number": "number", "boolean": "boolean", "null": "null"}


def ts_type(schema: dict) -> str:
    if "$ref" in schema:
        return schema["$ref"].split("/")[-1]
    if "const" in schema:
        return json.dumps(schema["const"], ensure_ascii=False)
    if schema.get("enum"):
        # 枚举必须落成字面量联合：状态机是前端轮询逻辑的分支依据，
        # 退化成 string 就等于把 §6.2 说的"不手写第二套 DTO"还给前端。
        return " | ".join(json.dumps(v, ensure_ascii=False) for v in schema["enum"])
    if "anyOf" in schema:
        parts = [ts_type(s) for s in schema["anyOf"]]
        return " | ".join(dict.fromkeys(parts))
    if schema.get("type") == "array":
        return f"{ts_type(schema.get('items', {}))}[]"
    if schema.get("type") == "object":
        props = schema.get("properties") or {}
        if not props:
            return "Record<string, unknown>"
        req = set(schema.get("required") or [])
        fields = [
            f'{k}{"?" if k not in req else ""}: {ts_type(v)}' for k, v in props.items()
        ]
        return "{ " + "; ".join(fields) + " }"
    return PRIMS.get(schema.get("type", ""), "unknown")


def main() -> int:
    spec = openapi()
    schemas = spec.get("components", {}).get("schemas", {})
    lines = ["// 由 tools/export_contracts.py 从后端 OpenAPI 生成，不要手改。", ""]
    for name, schema in sorted(schemas.items()):
        if schema.get("type") == "object" and schema.get("properties"):
            req = set(schema.get("required") or [])
            fields = []
            for k, v in schema["properties"].items():
                fields.append(f'  {k}{"?" if k not in req else ""}: {ts_type(v)};')
            lines.append(f"export interface {name} {{")
            lines.extend(fields)
            lines.append("}")
        else:
            lines.append(f"export type {name} = {ts_type(schema)};")
        lines.append("")

    paths = []
    for path, ops in sorted(spec.get("paths", {}).items()):
        for verb, op in ops.items():
            paths.append(
                f'  {json.dumps(f"{verb.upper()} {path}")}: {json.dumps(op.get("operationId") or op.get("summary") or "")};'
            )
    lines.append("/** 接口清单：路径 -> operationId，供客户端封装用。 */")
    lines.append("export interface ApiOperations {")
    lines.extend(paths)
    lines.append("}")
    lines.append("")
    lines.append(f"export const OPENAPI_VERSION = {json.dumps(spec.get('info', {}).get('version', ''))};")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT} ({len(lines)} lines, {len(schemas)} schemas)")

    # 顺带把原始 spec 也存下来，便于 diff 与 TS 侧调试
    (OUT.parent / "openapi.json").write_text(json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

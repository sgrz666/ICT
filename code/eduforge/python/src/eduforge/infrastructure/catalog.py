"""catalog 的唯一读取入口。

清单解析原先散在 Python 服务层、策略层和 TS 适配器三处，同一份量程有两个出处；
路径层数也已在两处各错过一次。收敛到这里，其余只从这里取。

TS 侧的 `adapter.ts` 暂留一份独立解析（跨语言没法共用模块），但它读的也是同一批
manifest 文件——数字仍然只有清单一个家。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

CATALOG = Path(__file__).resolve().parents[4] / "catalog"


class CatalogError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass
class ControlSpec:
    entity_id: str
    parameter: str
    min: float
    max: float
    native_type: str
    # 下面三个是给界面用的教学元数据：没有它们前端只能硬编码量程与标签，
    # 于是同一份量程就有两个出处（清单与代码），漂移不会报错只会骗人。
    label: str = ""
    unit: str = ""
    initial: float | None = None


@dataclass
class TemplateSpec:
    template_id: str
    title: str
    engine_id: str
    units_per_unit: int
    controls: list[ControlSpec] = field(default_factory=list)
    views: list[str] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    directory: Path | None = None

    @property
    def supports_config(self) -> bool:
        return "config" in self.routes

    @property
    def supports_code(self) -> bool:
        return "code" in self.routes


def _scalar(text: str, key: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}:"):
            return stripped.split(":", 1)[1].strip()
    raise CatalogError("MANIFEST_MISSING_KEY", key)


def _maybe_scalar(text: str, key: str) -> str | None:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(f"{key}:"):
            return stripped.split(":", 1)[1].strip()
    return None


def find_template_dir(template_id: str) -> Path:
    """按 template_id 找目录：目录名不能由 id 推导（convex_lens vs convex-lens）。"""
    for manifest in sorted((CATALOG / "templates").glob("**/manifest.yaml")):
        head = manifest.read_text(encoding="utf-8").split("template_id:", 1)
        if len(head) > 1 and head[1].splitlines()[0].strip() == template_id:
            return manifest.parent
    raise CatalogError("TEMPLATE_NOT_FOUND", template_id)


def _block_items(text: str, key: str, stop_keys: tuple[str, ...]) -> list[str]:
    """取 `key:` 段落下的列表项，按行切。

    不用字符串 split：清单里第一个项以 "  - " 开头、前面没有换行，
    split("\n  - ") 会把首项整个漏掉（这个坑实测踩过一次）。
    """
    items: list[str] = []
    current: list[str] | None = None
    inside = False
    for line in text.splitlines():
        if not inside:
            if line.rstrip() == f"{key}:":
                inside = True
            continue
        stripped = line.rstrip()
        if any(stripped == f"{s}:" for s in stop_keys):
            break
        if stripped.startswith("  - "):
            if current is not None:
                items.append("\n".join(current))
            current = [stripped[4:]]
        elif current is not None:
            current.append(line.strip())
    if current is not None:
        items.append("\n".join(current))
    return items


def _list_scalars(text: str, key: str, stop_keys: tuple[str, ...]) -> list[str]:
    out: list[str] = []
    inside = False
    for line in text.splitlines():
        if not inside:
            if line.rstrip() == f"{key}:":
                inside = True
            continue
        stripped = line.rstrip()
        if any(stripped == f"{s}:" for s in stop_keys):
            break
        if stripped.startswith("  - "):
            out.append(stripped[4:].strip())
    return out


def load_template(template_id: str) -> TemplateSpec:
    directory = find_template_dir(template_id)
    text = (directory / "manifest.yaml").read_text(encoding="utf-8")

    status = _maybe_scalar(text, "status")
    if status and status.startswith("pending"):
        return TemplateSpec(
            template_id=_scalar(text, "template_id"),
            title=_scalar(text, "title"),
            engine_id=_scalar(text, "engine_id"),
            units_per_unit=int(_maybe_scalar(text, "units_per_unit") or 1),
            controls=[],
            views=[],
            routes=[],
            directory=directory,
        )

    controls: list[ControlSpec] = []
    for item in _block_items(text, "controls", ("views", "observations")):
        def get(k: str) -> str:
            for line in item.splitlines():
                if line.startswith(f"{k}:"):
                    return line.split(":", 1)[1].strip()
            raise CatalogError("MANIFEST_MISSING_KEY", f"{k} in controls item")

        def maybe(k: str) -> str | None:
            for line in item.splitlines():
                if line.startswith(f"{k}:"):
                    return line.split(":", 1)[1].strip()
            return None

        initial = maybe("initial")
        controls.append(
            ControlSpec(
                entity_id=get("entity_id"),
                parameter=get("parameter"),
                native_type=get("native_type"),
                min=float(get("min")),
                max=float(get("max")),
                label=maybe("label") or "",
                unit=maybe("unit") or "",
                initial=float(initial) if initial is not None else None,
            )
        )

    return TemplateSpec(
        template_id=_scalar(text, "template_id"),
        title=_scalar(text, "title"),
        engine_id=_scalar(text, "engine_id"),
        units_per_unit=int(_scalar(text, "units_per_unit")),
        controls=controls,
        views=_list_scalars(text, "views", ("exports",)),
        routes=_list_scalars(text, "routes", ()),
        directory=directory,
    )


def list_templates(*, include_pending: bool = False) -> list[TemplateSpec]:
    """列出可用模板。清单解析只在这里发生，API 层不再自己拆字符串。"""
    out: list[TemplateSpec] = []
    for manifest in sorted((CATALOG / "templates").glob("**/manifest.yaml")):
        text = manifest.read_text(encoding="utf-8")
        status = _maybe_scalar(text, "status")
        if not include_pending and status and status.startswith("pending"):
            continue
        tid = _scalar(text, "template_id")
        out.append(load_template(tid))
    return out


def load_native(template_id: str) -> dict:
    return json.loads((find_template_dir(template_id) / "native.json").read_text(encoding="utf-8"))

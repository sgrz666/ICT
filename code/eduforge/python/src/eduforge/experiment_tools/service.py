"""实验引擎工具服务（Experiment Tool Services）。

提供 8 项原子工具服务：
1. search_experiments: 检索实验与模板
2. open_experiment: 打开/初始化实验工作区
3. inspect_scene: 探查场景实体、参数与光学指标
4. apply_scene_patch: 应用物理参数修改并执行实时光线仿真
5. configure_teaching_views: 配置教学视图与实验数据记录表
6. run_validation: 物理与规约闭环验证
7. build_package: 构建交付产物与离线运行包
8. publish_revision: 原子发布新版本并推进 head
"""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path
from typing import Any
import uuid
from uuid import UUID

import asyncpg

from eduforge.agent.policy import load_template
from eduforge.domain.contracts import SetParameter, SetView
from eduforge.domain.errors import ConflictError, NotFoundError
from eduforge.experiment_tools.contracts import (
    ApplyScenePatchInput,
    ApplyScenePatchOutput,
    BuildPackageInput,
    BuildPackageOutput,
    ConfigureTeachingViewsInput,
    ConfigureTeachingViewsOutput,
    ExperimentSummary,
    InspectSceneInput,
    OpenExperimentInput,
    OpenExperimentOutput,
    PublishRevisionInput,
    PublishRevisionOutput,
    RunValidationInput,
    RunValidationOutput,
    SceneInspectionOutput,
    SearchExperimentsInput,
    SearchExperimentsOutput,
)
from eduforge.infrastructure.catalog import CatalogError, load_native
from eduforge.infrastructure.clients.engine_client import EngineClient
from eduforge.infrastructure.db.repositories import RevisionConflict
from eduforge.validation.policies import build_report
from eduforge.validation.scientific.optics import thin_lens_reference


def _extract_lens_and_source(native: dict[str, Any], units_per_unit: int = 10) -> dict[str, Any]:
    objs = native.get("objs", [])
    lens = next((o for o in objs if o.get("type") == "IdealLens"), None)
    source = next((o for o in objs if o.get("type") == "PointSource"), None)
    screens = [o for o in objs if o.get("type") == "Screen"]
    rulers = [o for o in objs if o.get("type") == "Ruler"]

    res: dict[str, Any] = {
        "lens": lens,
        "source": source,
        "screens": screens,
        "rulers": rulers,
        "focal_length_cm": None,
        "object_distance_cm": None,
    }
    if lens is not None:
        p1_x = float(lens.get("p1", {}).get("x", 0))
        p2_x = float(lens.get("p2", {}).get("x", 0))
        lens_x = (p1_x + p2_x) / 2
        f = float(lens.get("focalLength", 100)) / units_per_unit
        res["focal_length_cm"] = f
        res["lens_center_x"] = lens_x
        if source is not None:
            src_x = float(source.get("x", 0))
            u = abs(src_x - lens_x) / units_per_unit
            res["object_distance_cm"] = u
    return res


def _make_measurement_record(f: float, u: float, ref: dict[str, Any]) -> dict[str, Any]:
    v = ref.get("image_distance_cm")
    if v is None:
        kind = "不成像"
    elif v > 0:
        if math.isclose(u, 2 * f, rel_tol=1e-4):
            kind = "倒立等大实像 (real)"
        elif u > 2 * f:
            kind = "倒立缩小实像 (real)"
        else:
            kind = "倒立放大实像 (real)"
    else:
        kind = "正立放大虚像 (virtual)"

    mag = round(ref["magnification"], 2) if ref.get("magnification") is not None else None
    v_val = round(v, 2) if v is not None else None
    return {
        "object_distance_cm": round(u, 2),
        "focal_length_cm": round(f, 2),
        "image_distance_cm": v_val,
        "image_kind": kind,
        "magnification": mag,
    }



class ExperimentToolService:
    """实验引擎工具服务核心实现。"""

    def __init__(
        self,
        *,
        engine_client: EngineClient,
        conn: asyncpg.Connection | None = None,
        artifact_dir: Path | None = None,
        templates_dir: Path | None = None,
    ) -> None:
        self.engine_client = engine_client
        self.conn = conn
        self.artifact_dir = artifact_dir or (
            Path(__file__).resolve().parents[4] / "output" / "eduforge" / "artifacts"
        )
        self.templates_dir = templates_dir or (
            Path(__file__).resolve().parents[4] / "code" / "eduforge" / "catalog" / "templates"
        )
        self._sessions: dict[str, dict[str, Any]] = {}

    async def search_experiments(self, input_data: SearchExperimentsInput | dict[str, Any]) -> SearchExperimentsOutput:
        """1. search_experiments: 检索实验与模板。"""
        if isinstance(input_data, dict):
            req = SearchExperimentsInput.model_validate(input_data)
        else:
            req = input_data

        items: list[ExperimentSummary] = []
        # 从 catalog 模板读取
        try:
            convex = load_template("optics.convex_lens")
            items.append(
                ExperimentSummary(
                    template_id=convex.template_id,
                    title="凸透镜成像实验",
                    description=convex.title or "探究凸透镜成像规律及物距像距关系",
                    controls=[asdict(c) for c in convex.controls],
                    views=list(convex.views),
                )

            )
        except Exception:
            pass

        # 若有数据库，也可加入已有实验
        if self.conn is not None:
            try:
                rows = await self.conn.fetch(
                    "select id, template_id from experiments order by id desc limit 20"
                )
                for r in rows:
                    items.append(
                        ExperimentSummary(
                            experiment_id=str(r["id"]),
                            template_id=r["template_id"],
                            title=f"实验实例: {r['template_id']}",
                            description=f"实验ID: {r['id']}",
                        )
                    )
            except Exception:
                pass

        # 过滤
        q = req.query.strip().lower()
        if q:
            filtered = [
                it for it in items
                if q in it.title.lower() or q in it.description.lower() or q in it.template_id.lower()
            ]
        else:
            filtered = items

        if req.template_id:
            filtered = [it for it in filtered if it.template_id == req.template_id]

        capped = filtered[: req.limit]
        return SearchExperimentsOutput(items=capped, total=len(filtered))

    async def open_experiment(self, input_data: OpenExperimentInput | dict[str, Any]) -> OpenExperimentOutput:
        """2. open_experiment: 打开已有实验或由模板创建新实验。"""
        if isinstance(input_data, dict):
            req = OpenExperimentInput.model_validate(input_data)
        else:
            req = input_data

        template_id = req.template_id or "optics.convex_lens"
        template = load_template(template_id)
        native = load_native(template_id)

        exp_id_str = req.experiment_id
        base_rev_str = req.revision_id
        head_rev_str = req.revision_id

        if exp_id_str is None:
            exp_uuid = uuid.uuid4()
            rev_uuid = uuid.uuid4()
            exp_id_str = str(exp_uuid)
            base_rev_str = str(rev_uuid)
            head_rev_str = str(rev_uuid)

            if self.conn is not None:
                await self.conn.execute(
                    """insert into experiments (id, owner_id, template_id, head_revision_id)
                       values ($1, $2, $3, $4)""",
                    exp_uuid, req.owner_id, template_id, rev_uuid,
                )
                await self.conn.execute(
                    """insert into experiment_revisions (id, experiment_id, parent_id, engine_id, native_data)
                       values ($1, $2, NULL, 'ray_optics', $3::jsonb)""",
                    rev_uuid, exp_uuid, json.dumps(native),
                )
        else:
            exp_uuid = UUID(exp_id_str)
            if self.conn is not None:
                exp_row = await self.conn.fetchrow(
                    "select id, template_id, head_revision_id from experiments where id = $1",
                    exp_uuid,
                )
                if exp_row is not None:
                    template_id = exp_row["template_id"]
                    head_rev_str = str(exp_row["head_revision_id"])
                    target_rev_id = UUID(req.revision_id) if req.revision_id else exp_row["head_revision_id"]
                    base_rev_str = str(target_rev_id)
                    rev_row = await self.conn.fetchrow(
                        "select native_data from experiment_revisions where id = $1",
                        target_rev_id,
                    )
                    if rev_row is not None:
                        native = json.loads(rev_row["native_data"])

        # 初始化/更新当前会话工作态
        session = {
            "experiment_id": exp_id_str,
            "template_id": template_id,
            "base_revision": base_rev_str,
            "head_revision": head_rev_str,
            "owner_id": req.owner_id,
            "native_data": json.loads(json.dumps(native)),
            "initial_native": json.loads(json.dumps(native)),
            "edits": [],
            "views_config": {},
            "validation_report": None,
            "engine_result": None,
        }
        self._sessions[exp_id_str] = session

        return OpenExperimentOutput(
            experiment_id=exp_id_str,
            template_id=template_id,
            base_revision=base_rev_str or "",
            head_revision=head_rev_str or "",
            controls=[asdict(c) for c in template.controls],
            views=list(template.views),
            native_summary={"version": native.get("version"), "object_count": len(native.get("objs", []))},
        )


    def _get_session(self, experiment_id: str) -> dict[str, Any]:
        if experiment_id not in self._sessions:
            raise NotFoundError(f"实验会话不存在或未打开: {experiment_id}")
        return self._sessions[experiment_id]

    async def inspect_scene(self, input_data: InspectSceneInput | dict[str, Any]) -> SceneInspectionOutput:
        """3. inspect_scene: 探查场景实体、参数与光学指标。"""
        if isinstance(input_data, dict):
            req = InspectSceneInput.model_validate(input_data)
        else:
            req = input_data

        session = self._get_session(req.experiment_id)
        native = session["native_data"]
        extracted = _extract_lens_and_source(native, units_per_unit=10)

        f = extracted["focal_length_cm"]
        u = extracted["object_distance_cm"]
        optics_metrics: dict[str, Any] = {}
        if f is not None and u is not None:
            optics_metrics = thin_lens_reference(f, u)

        elements = [
            {"type": o.get("type"), "name": o.get("name"), "x": o.get("x")}
            for o in native.get("objs", [])
        ]
        eng_res = session.get("engine_result") or {}
        measurement = eng_res.get("measurement") or {}

        return SceneInspectionOutput(
            experiment_id=req.experiment_id,
            revision_id=session["head_revision"],
            elements=elements,
            parameters={
                "focal_length_cm": f,
                "object_distance_cm": u,
            },
            optics_metrics=optics_metrics,
            ray_count=measurement.get("processedRayCount", 0),
            probes=measurement.get("probes", []),
        )

    async def apply_scene_patch(self, input_data: ApplyScenePatchInput | dict[str, Any]) -> ApplyScenePatchOutput:
        """4. apply_scene_patch: 应用物理参数修改并执行实时光线仿真。"""
        if isinstance(input_data, dict):
            req = ApplyScenePatchInput.model_validate(input_data)
        else:
            req = input_data

        session = self._get_session(req.experiment_id)
        raw_edits = req.edits
        edits_list = raw_edits if isinstance(raw_edits, list) else [raw_edits]

        # 调 engine apply
        try:
            eng_res = await self.engine_client.apply(session["native_data"], edits_list)
            session["native_data"] = eng_res["native"]
            session["engine_result"] = eng_res
        except Exception as exc:
            extracted = _extract_lens_and_source(session["native_data"], units_per_unit=10)
            return ApplyScenePatchOutput(
                experiment_id=req.experiment_id,
                applied_edits=[],
                updated_parameters={
                    "focal_length_cm": extracted["focal_length_cm"],
                    "object_distance_cm": extracted["object_distance_cm"],
                },
                ray_count=0,
                probes=[],
                status=f"rejected: {exc}",
            )

        parsed_edits = [SetParameter.model_validate(e) for e in edits_list]
        session["edits"].extend(parsed_edits)

        extracted = _extract_lens_and_source(session["native_data"], units_per_unit=10)
        measurement = eng_res.get("measurement", {})

        # 如果测量表开启，自动更新/追加最新的测量数据行
        if "measurement_table" in session["views_config"] and session["views_config"]["measurement_table"].get("visible"):
            table = session["views_config"]["measurement_table"]
            u = extracted["object_distance_cm"]
            f = extracted["focal_length_cm"]
            if u is not None and f is not None:
                ref = thin_lens_reference(f, u)
                new_row = _make_measurement_record(f, u, ref)
                existing = table.get("records", [])
                match = next(
                    (r for r in existing
                     if math.isclose(r["object_distance_cm"], new_row["object_distance_cm"], rel_tol=1e-4)
                     and math.isclose(r["focal_length_cm"], new_row["focal_length_cm"], rel_tol=1e-4)),
                    None,
                )
                if not match:
                    existing.append(new_row)
                    table["records"] = existing

        return ApplyScenePatchOutput(
            experiment_id=req.experiment_id,
            applied_edits=[e.model_dump() for e in parsed_edits],
            updated_parameters={
                "focal_length_cm": extracted["focal_length_cm"],
                "object_distance_cm": extracted["object_distance_cm"],
            },
            ray_count=measurement.get("processedRayCount", 0),
            probes=measurement.get("probes", []),
            status="applied",
        )

    async def configure_teaching_views(
        self, input_data: ConfigureTeachingViewsInput | dict[str, Any]
    ) -> ConfigureTeachingViewsOutput:
        """5. configure_teaching_views: 配置教学视图与实验数据记录表。"""
        if isinstance(input_data, dict):
            req = ConfigureTeachingViewsInput.model_validate(input_data)
        else:
            req = input_data

        session = self._get_session(req.experiment_id)
        views = req.views
        view_configs: dict[str, Any] = session["views_config"]

        # 解析规范输入
        if isinstance(views, dict):
            for k, v in views.items():
                if isinstance(v, bool):
                    if k in view_configs and isinstance(view_configs[k], dict):
                        view_configs[k]["visible"] = v
                    else:
                        view_configs[k] = {"visible": v}
                elif isinstance(v, dict):
                    if k in view_configs and isinstance(view_configs[k], dict):
                        view_configs[k].update(v)
                    else:
                        view_configs[k] = v
        elif isinstance(views, list):
            for it in views:
                vid = it.get("view_id") or it.get("id")
                if vid:
                    if vid in view_configs and isinstance(view_configs[vid], dict):
                        view_configs[vid]["visible"] = bool(it.get("visible", True))
                    else:
                        view_configs[vid] = {"visible": bool(it.get("visible", True))}

        # 如果开启数据记录表格，填充列定义与初始/当前实测数据行
        if view_configs.get("measurement_table", {}).get("visible"):
            tbl = view_configs["measurement_table"]
            tbl["columns"] = [
                {"key": "object_distance_cm", "label": "物距 u", "unit": "cm"},
                {"key": "focal_length_cm", "label": "焦距 f", "unit": "cm"},
                {"key": "image_distance_cm", "label": "像距 v", "unit": "cm"},
                {"key": "image_kind", "label": "像的性质", "unit": ""},
                {"key": "magnification", "label": "放大率", "unit": ""},
            ]
            if "records" not in tbl:
                tbl["records"] = []

            extracted = _extract_lens_and_source(session["native_data"], units_per_unit=10)
            u = extracted["object_distance_cm"]
            f = extracted["focal_length_cm"]
            if u is not None and f is not None:
                ref = thin_lens_reference(f, u)
                current_record = _make_measurement_record(f, u, ref)
                if not any(
                    math.isclose(r["object_distance_cm"], current_record["object_distance_cm"], rel_tol=1e-4)
                    and math.isclose(r["focal_length_cm"], current_record["focal_length_cm"], rel_tol=1e-4)
                    for r in tbl["records"]
                ):
                    tbl["records"].append(current_record)


        session["views_config"] = view_configs
        return ConfigureTeachingViewsOutput(
            experiment_id=req.experiment_id,
            views_config=view_configs,
            measurement_table=view_configs.get("measurement_table"),
        )

    async def run_validation(self, input_data: RunValidationInput | dict[str, Any]) -> RunValidationOutput:
        """6. run_validation: 物理与规约闭环验证。"""
        if isinstance(input_data, dict):
            req = RunValidationInput.model_validate(input_data)
        else:
            req = input_data

        session = self._get_session(req.experiment_id)
        template = load_template(session["template_id"])

        # 确保有最新 engine_result
        if session.get("engine_result") is None:
            eng_res = await self.engine_client.apply(session["native_data"], [])
            session["engine_result"] = eng_res

        last_edit = session["edits"][-1] if session["edits"] else None
        view_edits = [
            SetView(view_id=k, visible=bool(v.get("visible", False)))
            for k, v in session["views_config"].items()
        ]

        extracted = _extract_lens_and_source(session["native_data"], units_per_unit=template.units_per_unit)
        u_cm = extracted["object_distance_cm"] or 30.0

        report = build_report(
            job_id=str(uuid.uuid4()),
            edit=last_edit,
            edits=session["edits"],
            view_edits=view_edits,
            engine_result=session["engine_result"],
            object_distance_cm=u_cm,
            units_per_unit=template.units_per_unit,
            allowed_views=template.views,
        )
        session["validation_report"] = report

        passed = report.verdict == "passed"
        return RunValidationOutput(
            experiment_id=req.experiment_id,
            verdict=report.verdict,
            passed=passed,
            checks=[c.as_dict() for c in report.checks],
            physics_summary={
                "focal_length_cm": extracted["focal_length_cm"],
                "object_distance_cm": extracted["object_distance_cm"],
                "sharpest_screen": [p for p in session["engine_result"].get("measurement", {}).get("probes", []) if (p.get("power_fraction") or 0) >= 0.2],
            },
        )

    async def build_package(self, input_data: BuildPackageInput | dict[str, Any]) -> BuildPackageOutput:
        """7. build_package: 构建交付产物与离线运行包。"""
        if isinstance(input_data, dict):
            req = BuildPackageInput.model_validate(input_data)
        else:
            req = input_data

        session = self._get_session(req.experiment_id)
        if not session.get("validation_report") or session["validation_report"].verdict != "passed":
            # 自动执行一次验证
            val = await self.run_validation(RunValidationInput(experiment_id=req.experiment_id))
            if not val.passed:
                raise ConflictError(f"场景未通过科学验证，不得打包: {val.verdict}")

        cand_id = uuid.uuid4()
        session["candidate_revision_id"] = str(cand_id)

        # 写入候选目录
        cand_dir = self.artifact_dir / "revisions" / str(cand_id)
        cand_dir.mkdir(parents=True, exist_ok=True)
        native_file = cand_dir / "native.json"
        native_bytes = (json.dumps(session["native_data"], ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        native_file.write_bytes(native_bytes)
        native_digest = hashlib.sha256(native_bytes).hexdigest()

        artifacts = [{
            "id": str(uuid.uuid4()),
            "storage_key": str(native_file.relative_to(self.artifact_dir)).replace("\\", "/"),
            "sha256": native_digest,
            "media_type": "application/json",
        }]

        # 教学视图
        views_config = session.get("views_config")
        if views_config:
            views_file = cand_dir / "teaching_views.json"
            views_bytes = (json.dumps(views_config, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            views_file.write_bytes(views_bytes)
            views_digest = hashlib.sha256(views_bytes).hexdigest()
            artifacts.append({
                "id": str(uuid.uuid4()),
                "storage_key": str(views_file.relative_to(self.artifact_dir)).replace("\\", "/"),
                "sha256": views_digest,
                "media_type": "application/json",
            })

        offline_pkg_info = None
        if req.export_offline_zip:
            pkg_out_dir = cand_dir / "offline_package"
            pkg_out_dir.mkdir(parents=True, exist_ok=True)
            res = await self.engine_client.export_offline_package(
                session["native_data"],
                out_dir=str(pkg_out_dir),
                options={"title": "EduForge 凸透镜成像实验"},
            )
            # 把教学视图也同步放进离线包
            if views_config:
                pkg_views = pkg_out_dir / "www" / "scene" / "teaching_views.json"
                pkg_views.parent.mkdir(parents=True, exist_ok=True)
                pkg_views.write_bytes(views_bytes)

            offline_pkg_info = {
                "dir": res.get("dir", str(pkg_out_dir)),
                "index_file": res.get("index_file", str(pkg_out_dir / "www" / "index.html")),
                "offline_ready": True,
            }

        session["built_artifacts"] = artifacts
        session["built_package"] = offline_pkg_info

        return BuildPackageOutput(
            experiment_id=req.experiment_id,
            candidate_revision_id=str(cand_id),
            artifacts=artifacts,
            offline_package=offline_pkg_info,
            sha256=native_digest,
        )

    async def publish_revision(self, input_data: PublishRevisionInput | dict[str, Any]) -> PublishRevisionOutput:
        """8. publish_revision: 原子发布新版本并推进 head。"""
        if isinstance(input_data, dict):
            req = PublishRevisionInput.model_validate(input_data)
        else:
            req = input_data

        session = self._get_session(req.experiment_id)
        if not session.get("validation_report") or session["validation_report"].verdict != "passed":
            val = await self.run_validation(RunValidationInput(experiment_id=req.experiment_id))
            if not val.passed:
                raise ConflictError(f"未通过科学验证不得发布: {val.verdict}")

        if not session.get("built_artifacts"):
            await self.build_package(BuildPackageInput(experiment_id=req.experiment_id))

        cand_id_str = session.get("candidate_revision_id") or str(uuid.uuid4())
        cand_uuid = UUID(cand_id_str)
        exp_uuid = UUID(req.experiment_id)
        base_rev_str = req.base_revision or session["head_revision"]
        base_uuid = UUID(base_rev_str)
        artifacts = session.get("built_artifacts", [])

        if self.conn is None and req.base_revision and str(req.base_revision) != str(session["head_revision"]):
            raise RevisionConflict(f"head={session['head_revision']} base={req.base_revision}")

        if self.conn is not None:
            async with self.conn.transaction():
                head = await self.conn.fetchval(
                    "select head_revision_id from experiments where id = $1 for update", exp_uuid
                )
                if head is not None and str(head) != str(base_rev_str):
                    raise RevisionConflict(f"head={head} base={base_rev_str}")

                await self.conn.execute(
                    """insert into experiment_revisions (id, experiment_id, parent_id, engine_id, native_data, lesson)
                       values ($1, $2, $3, 'ray_optics', $4::jsonb, $5::jsonb)""",
                    cand_uuid, exp_uuid, base_uuid,
                    json.dumps(session["native_data"]),
                    json.dumps({"views": session.get("views_config")}) if session.get("views_config") else None,
                )
                for art in artifacts:
                    await self.conn.execute(
                        """insert into artifacts (id, revision_id, storage_key, sha256, media_type)
                           values ($1, $2, $3, $4, $5)""",
                        UUID(art["id"]), cand_uuid, art["storage_key"], art["sha256"], art.get("media_type", "application/json"),
                    )
                await self.conn.execute(
                    "update experiments set head_revision_id = $1 where id = $2",
                    cand_uuid, exp_uuid,
                )

        # 推进会话版本状态（支持连续编辑链）
        session["base_revision"] = cand_id_str
        session["head_revision"] = cand_id_str
        session["candidate_revision_id"] = None
        session["built_artifacts"] = None

        native_digest = artifacts[0]["sha256"] if artifacts else ""
        art_id = artifacts[0]["id"] if artifacts else str(uuid.uuid4())

        return PublishRevisionOutput(
            experiment_id=req.experiment_id,
            head_revision_id=cand_id_str,
            base_revision=base_rev_str,
            artifact_id=art_id,
            sha256=native_digest,
            status="published",
        )

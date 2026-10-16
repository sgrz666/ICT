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

from eduforge.agent.policy import authorize_operation, load_template
from eduforge.application.candidate_service import (
    CandidateFrozen,
    CandidateService,
    CandidateState,
    content_fingerprint,
    native_bytes,
    views_bytes,
)
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
    JobContext,
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
from eduforge.infrastructure.db.candidate_repository import (
    CandidateScopeConflict,
    CandidateVersionConflict,
)
from eduforge.infrastructure.db.repositories import RevisionConflict, derived_id
from eduforge.application.publication import Publisher
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
        job: JobContext | None = None,
    ) -> None:
        self.engine_client = engine_client
        self.conn = conn
        self.job = job
        self.artifact_dir = artifact_dir or (
            Path(__file__).resolve().parents[4] / "output" / "eduforge" / "artifacts"
        )
        self.templates_dir = templates_dir or (
            Path(__file__).resolve().parents[4] / "code" / "eduforge" / "catalog" / "templates"
        )
        # `_sessions` 只是本次进程内的缓存：未发布工作态的真相在 `experiment_candidates`。
        # 以前它是唯一存储，进程一退教师成果就没了，Worker 只好在基线上重放操作。
        self._sessions: dict[str, dict[str, Any]] = {}
        self.candidates = CandidateService(conn, job=job)

    def _require_owner(self, action: str) -> JobContext:
        """任何要确定归属的动作都得有服务端签发的上下文。

        没有 JobContext 就没有归属答案，也就没有「谁能改这个实验」的判据；
        宁可拒绝，不能拿默认身份写库或放行。
        """
        if self.job is None:
            raise ConflictError(f"{action} 需要服务端签发的 JobContext（job_id/owner_id/lease_token）")
        return self.job

    def _require_job(self, action: str) -> JobContext:
        """落库动作必须有执行上下文与库连接。

        连不上库就无法登记版本，此时返回成功就是假成功。
        """
        job = self._require_owner(action)
        if self.conn is None:
            raise ConflictError(f"{action} 需要数据库连接，否则无法落库，也不能声称成功")
        return job

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

        # job 绑定了实验就不允许新建，也不允许改开别的实验：智能体探索的必须就是
        # 这条 job 的目标实验，否则它验得再对也交付到别处去了。
        if self.job is not None and self.job.experiment_id is not None:
            bound = str(self.job.experiment_id)
            if exp_id_str not in (None, bound):
                raise ConflictError(f"SCOPE_MISMATCH: 本任务绑定实验 {bound}，不能打开 {exp_id_str}")
            exp_id_str = bound

        if exp_id_str is None:
            # 不带 experiment_id 的再次打开 = 续用本 job 的候选，不是凭空多开一份实验。
            # 以前这里每次都 uuid4() 新建，接上候选之后会变成换绑冲突：
            # 模型绕一圈回来就看不见自己刚改的东西了。
            resumed = None
            if self.job is not None:
                try:
                    resumed = await self.candidates.load()
                except CandidateFrozen:
                    resumed = None
            if resumed is not None:
                exp_id_str = str(resumed.experiment_id)
                base_rev_str = str(resumed.base_revision)

        if exp_id_str is None:
            job = self._require_owner("创建实验")
            exp_uuid = uuid.uuid4()
            rev_uuid = uuid.uuid4()
            exp_id_str = str(exp_uuid)
            base_rev_str = str(rev_uuid)
            head_rev_str = str(rev_uuid)

            if self.conn is not None:
                await self.conn.execute(
                    """insert into experiments (id, owner_id, template_id, head_revision_id)
                       values ($1, $2, $3, $4)""",
                    exp_uuid, job.owner_id, template_id, rev_uuid,
                )
                await self.conn.execute(
                    """insert into experiment_revisions (id, experiment_id, parent_id, engine_id, native_data)
                       values ($1, $2, NULL, 'ray_optics', $3::jsonb)""",
                    rev_uuid, exp_uuid, json.dumps(native),
                )
        else:
            exp_uuid = UUID(exp_id_str)
            if self.conn is not None:
                job = self._require_owner("打开已有实验")
                exp_row = await self.conn.fetchrow(
                    "select id, template_id, owner_id, head_revision_id from experiments where id = $1",
                    exp_uuid,
                )
                if exp_row is not None:
                    # 归属校验：服务端签发的身份必须与实验行一致。
                    # 「读一下别人的实验」同样是授权决定，不放行无上下文的访问。
                    if str(exp_row["owner_id"]) != job.owner_id:
                        raise ConflictError(f"实验 {exp_id_str} 不属于当前身份")
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

        # 工作态落在候选行上：同一个 job 反复打开，续用的是同一份未发布成果；
        # 换一个进程（崩溃后接管的 Worker）读回来的是同一行、同一个内容哈希。
        # 已存在的候选不会被这次 open 覆盖——未发布的编辑被静默丢掉是教师看不见的损失。
        if not self.candidates.persistent:
            self.candidates.note_experiment(UUID(exp_id_str))
        try:
            state = await self.candidates.open(
                experiment_id=UUID(exp_id_str),
                base_revision=UUID(base_rev_str) if base_rev_str else UUID(int=0),
                owner_id=self.job.owner_id if self.job is not None else "",
                template_id=template_id,
                native=native,
            )
        except (CandidateScopeConflict, CandidateVersionConflict) as exc:
            raise ConflictError(str(exc)) from exc
        session = self._session_from_state(exp_id_str, state)
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


    def _session_from_state(self, experiment_id: str, state: CandidateState) -> dict[str, Any]:
        """由候选行重建工作态缓存条目——重启后的 Worker 靠这一句回到断点。"""
        return {
            "experiment_id": experiment_id,
            "template_id": state.template_id,
            "base_revision": str(state.base_revision),
            "head_revision": str(state.base_revision),
            "owner_id": state.owner_id,
            "native_data": json.loads(json.dumps(state.native_data)),
            "initial_native": json.loads(json.dumps(state.native_data)),
            "edits": [SetParameter.model_validate(e) for e in state.edits],
            "views_config": json.loads(json.dumps(state.teaching_views)),
            "candidate": state,
            "validation_report": None,
            "validated_digest": state.validation_hash,
            "engine_result": None,
        }

    async def _session(self, experiment_id: str) -> dict[str, Any]:
        """取本 job 的工作态：先查进程内缓存，缺失就从候选行重建。

        以前缓存没有就是「会话不存在或未打开」，进程一退教师成果即失联；
        现在候选在库里，新建一个 service 也拿得到同一份工作态。
        """
        # 作用域边界先于会话查找：job 绑定了哪个实验，就只能碰哪个实验。
        if self.job is not None and self.job.experiment_id is not None:
            if str(self.job.experiment_id) != str(experiment_id):
                raise ConflictError(
                    f"SCOPE_MISMATCH: 本任务绑定实验 {self.job.experiment_id}，不能操作 {experiment_id}"
                )
        cached = self._sessions.get(experiment_id)
        if cached is not None:
            return cached
        try:
            state = await self.candidates.load()
        except CandidateFrozen:
            state = None
        if state is None or str(state.experiment_id) != str(experiment_id):
            raise NotFoundError(f"实验会话不存在或未打开: {experiment_id}")
        session = self._session_from_state(experiment_id, state)
        self._sessions[experiment_id] = session
        return session

    async def _persist(self, session: dict[str, Any]) -> CandidateState:
        """把当前缓存内容写穿到候选行；写不进去就不回报成功。"""
        edits = [e.model_dump() for e in session.get("edits", [])]
        base = session.get("candidate")
        expected = base.state_version if base is not None else 0
        try:
            state = await self.candidates.write(
                native=session["native_data"], views=session["views_config"],
                edits=edits, expected_version=expected,
            )
        except (CandidateScopeConflict, CandidateVersionConflict) as exc:
            raise ConflictError(str(exc)) from exc
        session["candidate"] = state
        # 内容变了，之前那份验证结论当场失效（库里也清了，双写只为这一条）
        session["validation_report"] = None
        session["validated_digest"] = None
        return state

    @staticmethod
    def _working_digest(session: dict[str, Any]) -> str:
        """工作态内容的指纹：原生场景 + 教学视图，与候选行的算法完全一致。"""
        return content_fingerprint(session.get("native_data"), session.get("views_config"))

    def _fresh_validation(self, session: dict[str, Any]) -> Any | None:
        """只承认钉在当前候选内容上的验证报告。

        靠「每个写操作记得清标记」会漏；内容指纹与库里的 `validation_hash`
        任一对不上就当没验过，结构上杜绝「改完场景拿旧绿灯发布」。
        """
        report = session.get("validation_report")
        if report is None:
            return None
        digest = self._working_digest(session)
        if session.get("validated_digest") != digest:
            return None
        state = session.get("candidate")
        if state is not None and not state.is_validated:
            return None
        return report

    async def inspect_scene(self, input_data: InspectSceneInput | dict[str, Any]) -> SceneInspectionOutput:
        """3. inspect_scene: 探查场景实体、参数与光学指标。"""
        if isinstance(input_data, dict):
            req = InspectSceneInput.model_validate(input_data)
        else:
            req = input_data

        session = await self._session(req.experiment_id)
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

        session = await self._session(req.experiment_id)
        raw_edits = req.edits
        edits_list = raw_edits if isinstance(raw_edits, list) else [raw_edits]

        # 先过策略层，再碰引擎：未登记的对象/参数、超量程的值应当在清单这一层就拒掉。
        # 这里以前完全不判——模型给什么就交给上游什么，只剩 loadJSON 兜底。
        parsed_edits = [SetParameter.model_validate(e) for e in edits_list]
        template = load_template(session["template_id"])
        for op in parsed_edits:
            authorize_operation(template, op)

        # 调 engine apply
        try:
            eng_res = await self.engine_client.apply(session["native_data"], edits_list)
            session["native_data"] = eng_res["native"]
            session["engine_result"] = eng_res
        except Exception as exc:
            # 引擎拒绝就是失败，不能包成 status 字段返回——调用方一旦漏看这个字符串，
            # 就把没改动的场景当成改好了继续发布。
            raise ConflictError(f"场景修改被引擎拒绝: {exc}") from exc

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

        # 引擎改完、记录表补完，这一版内容就写穿到候选行。
        # 写失败必须让这次工具调用失败：只改内存缓存却回报 applied，
        # 后面 Worker 读到的候选还是旧的，交付出去的东西与模型验过的东西分家。
        await self._persist(session)

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

        session = await self._session(req.experiment_id)
        views = req.views
        view_configs: dict[str, Any] = session["views_config"]

        # 视图也要过清单：模板没登记的视图，模型不能自己造一个出来
        template = load_template(session["template_id"])
        if isinstance(views, dict):
            requested_view_ids = list(views.keys())
        else:
            requested_view_ids = [it.get("view_id") or it.get("id") for it in views]
        for vid in requested_view_ids:
            if vid:
                authorize_operation(template, SetView(view_id=str(vid), visible=True))

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
        await self._persist(session)
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

        session = await self._session(req.experiment_id)
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
        u_cm = extracted["object_distance_cm"]
        if u_cm is None:
            # 兜一个常量会让验证对着伪造的物距通过；提不出物距就是不适用，必须明说。
            raise ConflictError("场景中提不出物距，无法做高斯光学可比性验证")

        report = build_report(
            job_id=str(self.job.job_id) if self.job is not None else str(uuid.uuid4()),
            edit=last_edit,
            edits=session["edits"],
            view_edits=view_edits,
            engine_result=session["engine_result"],
            object_distance_cm=u_cm,
            units_per_unit=template.units_per_unit,
            allowed_views=template.views,
        )
        session["validation_report"] = report
        session["validated_digest"] = self._working_digest(session)

        report_id = uuid.uuid4()
        if self.job is not None and self.conn is not None:
            # 验证结论当场落库。以前只有 Worker 的 validating 阶段会写 validation_reports，
            # 工具路径的「验过了」只是内存里的一句话，事后无从核对 observed/expected。
            report_id = await Publisher(self.conn).record_report(job_id=self.job.job_id, report=report)
        # 报告钉在这份候选的当前内容上：内容再变，绑定就作废（仓储里那条
        # `where content_hash = $3` 是这道保证的唯一实现处）。
        session["candidate"] = await self.candidates.bind_validation(report_id)
        session["validation_id"] = str(report_id)

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

        session = await self._session(req.experiment_id)
        report = self._fresh_validation(session)
        if report is None:
            # 没有与当前内容同指纹的报告——必须重验，不能沿用旧绿灯
            val = await self.run_validation(RunValidationInput(experiment_id=req.experiment_id))
            if not val.passed:
                raise ConflictError(f"场景未通过科学验证，不得打包: {val.verdict}")
        elif report.verdict != "passed":
            raise ConflictError(f"场景未通过科学验证，不得打包: {report.verdict}")

        # 冻结候选：从这里起，字节、验证报告、产物登记都只认这一版内容。
        # 版本与产物 id 由候选内容哈希派生——同一份内容重跑落在同一个 id 上（幂等），
        # 内容变了才是新版本（连续编辑），不会把两次编辑悄悄发布成同一版。
        frozen = await self.candidates.freeze()
        cand_id = self.candidates.revision_id(frozen)
        session["candidate_revision_id"] = str(cand_id)
        session["candidate"] = frozen

        # 写入候选目录
        cand_dir = self.artifact_dir / "revisions" / str(cand_id)
        cand_dir.mkdir(parents=True, exist_ok=True)
        native_file = cand_dir / "native.json"
        native_payload = native_bytes(frozen.native_data)
        native_file.write_bytes(native_payload)
        native_digest = hashlib.sha256(native_payload).hexdigest()

        def art_id(name: str, digest: str) -> str:
            return str(self.candidates.artifact_id(frozen, name, digest))

        artifacts = [{
            "id": art_id("native", native_digest),
            "storage_key": str(native_file.relative_to(self.artifact_dir)).replace("\\", "/"),
            "sha256": native_digest,
            "media_type": "application/json",
        }]

        # 教学视图
        views_config = frozen.teaching_views
        if views_config:
            views_file = cand_dir / "teaching_views.json"
            views_payload = views_bytes(views_config)
            views_file.write_bytes(views_payload)
            views_digest = hashlib.sha256(views_payload).hexdigest()
            artifacts.append({
                "id": art_id("teaching_views", views_digest),
                "storage_key": str(views_file.relative_to(self.artifact_dir)).replace("\\", "/"),
                "sha256": views_digest,
                "media_type": "application/json",
            })

        offline_pkg_info = None
        if req.export_offline_zip:
            pkg_out_dir = cand_dir / "offline_package"
            pkg_out_dir.mkdir(parents=True, exist_ok=True)
            res = await self.engine_client.export_offline_package(
                frozen.native_data,
                out_dir=str(pkg_out_dir),
                options={"title": "EduForge 凸透镜成像实验"},
            )
            # 把教学视图也同步放进离线包
            if views_config:
                pkg_views = pkg_out_dir / "www" / "scene" / "teaching_views.json"
                pkg_views.parent.mkdir(parents=True, exist_ok=True)
                pkg_views.write_bytes(views_payload)

            # 逐文件哈希整包，再落一份 manifest：交付字节必须能被复核，
            # 只记 native.json 的哈希等于没记——离线包真出事时是 www/ 里的资源。
            manifest_entries = []
            for p in sorted(pkg_out_dir.rglob("*")):
                if p.is_file() and p.name != "manifest.json":
                    manifest_entries.append({
                        "path": str(p.relative_to(pkg_out_dir)).replace("\\", "/"),
                        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
                    })
            manifest_bytes = (json.dumps(manifest_entries, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            (pkg_out_dir / "manifest.json").write_bytes(manifest_bytes)
            manifest_digest = hashlib.sha256(manifest_bytes).hexdigest()
            artifacts.append({
                "id": art_id("offline_manifest", manifest_digest),
                "storage_key": str((pkg_out_dir / "manifest.json").relative_to(self.artifact_dir)).replace("\\", "/"),
                "sha256": manifest_digest,
                "media_type": "application/json",
            })

            index_file = Path(res.get("index_file", str(pkg_out_dir / "www" / "index.html")))
            offline_pkg_info = {
                "dir": res.get("dir", str(pkg_out_dir)),
                "index_file": str(index_file),
                # 这里只断言「入口文件已在盘上」；离线可运行性要靠浏览器实测，
                # 本轮没实测就不写 ready。
                "index_present": index_file.is_file(),
                "file_count": len(manifest_entries),
                "manifest_sha256": manifest_digest,
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

    async def publish_revision(
        self,
        input_data: PublishRevisionInput | dict[str, Any],
        *,
        close_job: bool = True,
    ) -> PublishRevisionOutput:
        """8. publish_revision: 原子发布新版本并推进 head。

        发布不走这套服务自己的 SQL，而是复用持久层那条四道闸门事务
        （执行权/取消/验证结论/基础版本一致），否则两条路径会验出两种「已发布」。
        """
        if isinstance(input_data, dict):
            req = PublishRevisionInput.model_validate(input_data)
        else:
            req = input_data

        job = self._require_job("发布版本")
        session = await self._session(req.experiment_id)

        report = self._fresh_validation(session)
        if report is None:
            val = await self.run_validation(RunValidationInput(experiment_id=req.experiment_id))
            if not val.passed:
                raise ConflictError(f"未通过科学验证不得发布: {val.verdict}")
            report = self._fresh_validation(session)
        elif report.verdict != "passed":
            raise ConflictError(f"未通过科学验证不得发布: {report.verdict}")

        if not session.get("built_artifacts"):
            await self.build_package(BuildPackageInput(experiment_id=req.experiment_id))

        cand_id_str = session.get("candidate_revision_id")
        artifacts = session.get("built_artifacts") or []
        if not cand_id_str or not artifacts:
            raise ConflictError("没有已构建的候选与产物登记，不能发布")

        # 发布以库里的候选为准，不以缓存的字符串为准：两者不一致说明缓存在
        # 别处被推进过，这种「发布一份、验证的是另一份」的情形必须挡下来。
        state = await self.candidates.load()
        if state is None:
            raise ConflictError("候选行不存在，无法发布")
        cand_uuid = self.candidates.revision_id(state)
        if str(cand_uuid) != str(cand_id_str):
            raise ConflictError(
                f"候选内容在构建后又变了（构建 {cand_id_str}，当前 {cand_uuid}），必须重新验证与构建"
            )

        exp_uuid = UUID(req.experiment_id)
        base_rev_str = req.base_revision or str(state.base_revision)
        base_uuid = UUID(base_rev_str)

        publisher = Publisher(self.conn)
        # 报告已在 run_validation 当场落库；这里只负责把它交给四道闸门事务
        await publisher.publish(
            job_id=job.job_id,
            lease_token=job.lease_token,
            experiment_id=exp_uuid,
            base_revision=base_uuid,
            candidate_revision_id=cand_uuid,
            native_data=state.native_data,
            report_verdict=report.verdict,
            artifacts=artifacts,
            lesson={"views": state.teaching_views},
            close_job=close_job,
        )

        # 推进会话版本状态（支持连续编辑链）：候选的基线跟着前进到刚发布的那一版，
        # 否则同一 job 的第二次发布还拿最初的 base 去撞乐观并发。
        await self.candidates.rebase(cand_uuid)
        session["base_revision"] = str(cand_uuid)
        session["head_revision"] = str(cand_uuid)
        session["candidate_revision_id"] = None
        session["built_artifacts"] = None
        session["built_package"] = None
        session["candidate"] = await self.candidates.load()

        return PublishRevisionOutput(
            experiment_id=req.experiment_id,
            head_revision_id=cand_id_str,
            base_revision=base_rev_str,
            artifact_id=artifacts[0]["id"],
            sha256=artifacts[0]["sha256"],
            status="published",
        )

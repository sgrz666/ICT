"""规划端口的可离线验证部分（§7 的无密钥子集）。

真实模型调用要 `DEEPSEEK_API_KEY`，本机没有，所以这里只钉四件不依赖网络的事实：
① 没有 key 时 Worker **拒绝启动**，而不是悄悄换成固定提案；
② 静态提案必须由显式开关引入，且启动时打说明横幅；
③ 提示词只交事实、响应必须过结构校验（模型不能靠措辞扩大权限）；
④ 授权节点在 LangGraph 图里，越权提案在规划阶段就被拒。
GATE-6 的模型成功率对照仍然开放，这些用例不构成对它的证明。
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from eduforge.agent.graph import build_planning_graph  # noqa: F401  (确保图可导入)
from eduforge.agent.planners import (
    GraphPlanner,
    MissingApiKey,
    chat_payload,
    parse_proposal_json,
)
from eduforge.agent.policy import Rejected
from eduforge.domain.contracts import EditProposal, PlannerRequest
from eduforge.worker.run import STATIC_BANNER, build_parser, main, select_planner


def make_request(prompt="把焦距改成 15 厘米") -> PlannerRequest:
    return PlannerRequest(
        job_id=uuid.uuid4(), experiment_id=uuid.uuid4(), base_revision=uuid.uuid4(),
        template_id="optics.convex_lens", prompt=prompt,
    )


def args(argv):
    return build_parser().parse_args(argv)


def test_no_key_refuses_to_start(monkeypatch, capsys):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("deepseek", raising=False)
    monkeypatch.delenv("DEEPSEEK", raising=False)
    monkeypatch.delenv("deepseek_api_key", raising=False)
    with pytest.raises(MissingApiKey):
        select_planner(args([]))

    assert main(["--dsn", "x", "--engine-url", "y", "--artifact-dir", "z"]) == 2
    err = capsys.readouterr().err
    assert "DEEPSEEK_API_KEY" in err or "deepseek" in err
    assert "注入固定提案" not in err + capsys.readouterr().out, (
        "无 key 时绝不能自动改用静态提案"
    )


def test_deepseek_env_var_accepted(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("deepseek", "sk-custom-deepseek-key")
    from eduforge.agent.planners import api_key
    assert api_key() == "sk-custom-deepseek-key"


def test_missing_config_reported(monkeypatch, capsys):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-present")
    assert main(["--dsn", "", "--engine-url", "", "--artifact-dir", ""]) == 2
    err = capsys.readouterr().err
    assert "EDUFORGE_DSN" in err and "EDUFORGE_ENGINE_URL" in err


def test_static_planner_is_explicit_and_labeled(monkeypatch, capsys):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    argv = ["--planner-static-focal", "15"]
    assert main(argv) == 2  # 配置没给全，但静态横幅必须先打出来
    err = capsys.readouterr().err
    assert "不构成 Agent 规划能力" in err, "静态开关必须自带说明，否则会被误当成功能"

    planner, kind = select_planner(args(argv))
    assert kind == "static"
    proposal = asyncio.run(planner.plan(make_request()))
    assert proposal.operations[0].value == 15.0


def test_model_planner_selected_when_key_present(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-not-real-only-for-selection")
    _planner, kind = select_planner(args([]))
    assert kind == "model"


def test_chat_prompt_offers_facts_not_permissions():
    evidence = [{"kind": "control", "entity_id": "lens_1", "parameter": "focal_length_cm",
                 "min": 5, "max": 50}]
    payload = chat_payload("把焦距改成 15 厘米", {"template_id": "optics.convex_lens"}, evidence)
    content = payload["messages"][0]["content"]
    assert "lens_1" in content and "focal_length_cm" in content and "50" in content
    assert payload["temperature"] == 0
    assert payload["response_format"] == {"type": "json_object"}
    # 提示词里不出现身份与幂等字段：模型不该有机会自己决定归属
    for forbidden in ("owner", "idempotency", "base_revision"):
        assert forbidden not in content, forbidden


def test_fenced_model_output_still_reaches_structural_validation():
    raw = ('```json\n{"route":"config","operations":[{"op":"set_parameter",'
           '"entity_id":"lens_1","parameter":"focal_length_cm","value":15}]}\n```')
    proposal = EditProposal.model_validate(parse_proposal_json(raw))
    assert proposal.operations[0].entity_id == "lens_1"

    with pytest.raises(ValueError):
        parse_proposal_json("抱歉，我做不到")


def test_graph_authorizes_inside_the_loop():
    """越权提案在规划图内就被拒——不是等 Worker 拿去编辑时才炸。"""

    async def bad_model(prompt, context, evidence):
        return {"route": "config", "operations": [
            {"op": "set_parameter", "entity_id": "lens_1",
             "parameter": "focal_length_cm", "value": 9999}]}

    async def good_model(prompt, context, evidence):
        return {"route": "config", "operations": [
            {"op": "set_parameter", "entity_id": "lens_1",
             "parameter": "focal_length_cm", "value": 15}]}

    bad = GraphPlanner(bad_model, template_of=lambda r: r.template_id)
    with pytest.raises(Rejected) as exc:
        asyncio.run(bad.plan(make_request()))
    assert exc.value.code == "VALUE_OUT_OF_RANGE"

    good = GraphPlanner(good_model, template_of=lambda r: r.template_id)
    proposal = asyncio.run(good.plan(make_request()))
    assert proposal.operations[0].value == 15.0

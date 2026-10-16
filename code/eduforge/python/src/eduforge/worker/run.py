"""Worker 进程入口。

    set EDUFORGE_DSN=... EDUFORGE_ENGINE_URL=... EDUFORGE_ARTIFACT_DIR=...
    python -m eduforge.worker.run

规划默认必须走真实模型：没有 `DEEPSEEK_API_KEY` 就拒绝启动，
绝不静默退化成固定提案——那样 Demo 会把自己骗成"Agent 会规划"。
`--planner-static-focal` 是显式的本机链路验证开关，开启时启动会打一条说明横幅。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import asyncpg

from eduforge.agent.planners import MissingApiKey, planner_from_env
from eduforge.domain.contracts import EditProposal, PlannerRequest, SetParameter
from eduforge.infrastructure.db.migrations import apply_migrations
from eduforge.worker.steps import StaticPlanner, make_worker

STATIC_BANNER = (
    "规划由命令行注入固定提案（--planner-static-focal）。"
    "这条路径只验证链路与交付，不构成 Agent 规划能力的证据。"
)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="eduforge.worker.run")
    p.add_argument("--dsn", default=os.environ.get("EDUFORGE_DSN", ""))
    p.add_argument("--engine-url", default=os.environ.get("EDUFORGE_ENGINE_URL", ""))
    p.add_argument("--artifact-dir", default=os.environ.get("EDUFORGE_ARTIFACT_DIR", ""))
    p.add_argument("--lease-seconds", type=int, default=90)
    p.add_argument("--idle-seconds", type=float, default=1.0)
    p.add_argument("--once", action="store_true", help="处理一个任务后退出（本机调试）")
    p.add_argument("--planner", choices=["model", "deep", "static"], default=None,
                   help="model=四节点单轮提案；deep=Deep Agents 自主循环；static=固定提案（仅链路验证）")
    p.add_argument("--planner-static-focal", type=float, default=None,
                   help="注入焦距提案（厘米）。仅用于链路验证")
    p.add_argument("--planner-static-entity", default="lens_1")
    return p


def select_planner(args: argparse.Namespace) -> tuple[Any, str]:
    """返回 (planner, kind)。kind 只用于日志与测试断言。

    `--planner-static-focal` 仍然优先，保证既有的链路验证用法不被打断；
    但它是一次**显式**选择，脚本不会再替用户做这个决定。
    """
    if args.planner_static_focal is not None:
        proposal = EditProposal(route="config", operations=[SetParameter(
            entity_id=args.planner_static_entity,
            parameter="focal_length_cm",
            value=args.planner_static_focal,
        )])
        return StaticPlanner(proposal), "static"
    if args.planner == "deep":
        # Deep Agents 需要活的数据库连接，真正构造放在连上库之后
        from eduforge.agent.planners import api_key

        api_key()  # 无 key 立刻 MissingApiKey，不带着假配置往下跑
        return None, "deep"
    # 真实模型。缺 key 直接抛 MissingApiKey，由 main 转成退出码
    return planner_from_env(template_of=lambda req: req.template_id), "model"


async def loop(conn, *, engine_url: str, artifact_dir: Path, planner, args) -> int:
    await apply_migrations(conn)
    worker = make_worker(
        conn, engine_url=engine_url, artifact_dir=artifact_dir,
        planner=planner, lease_seconds=args.lease_seconds,
    )
    processed = 0
    while True:
        out = await worker.run_once()
        if out is not None:
            print(json.dumps(out, default=str, ensure_ascii=False), flush=True)
            processed += 1
            if args.once:
                # 处理数只进日志，不能当退出码：返回 1 在 supervisor 眼里就是崩溃
                print(f"processed={processed}", file=sys.stderr, flush=True)
                return 0
        else:
            if args.once:
                return 0
            await asyncio.sleep(args.idle_seconds)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        planner, kind = select_planner(args)
    except MissingApiKey as e:
        print(f"拒绝启动：{e}", file=sys.stderr)
        return 2
    if kind == "static":
        print(f"[警告] {STATIC_BANNER}", file=sys.stderr)

    missing = [n for n, v in (
        ("EDUFORGE_DSN", args.dsn),
        ("EDUFORGE_ENGINE_URL", args.engine_url),
        ("EDUFORGE_ARTIFACT_DIR", args.artifact_dir),
    ) if not v]
    if missing:
        print(f"缺少配置：{', '.join(missing)}", file=sys.stderr)
        return 2

    async def go() -> int:
        conn = await asyncpg.connect(args.dsn)
        chosen = planner
        if kind == "deep":
            # 生产配置走 Runner：模型直接改持久候选，Worker 不再重放第二遍。
            # （旧的 DeepAgentPlanner 仍在仓库里，作为对照基线与迁移期的兼容入口。）
            from eduforge.agent.deepagents_runner import DeepAgentRunner
            from eduforge.infrastructure.clients.engine_client import EngineClient

            chosen = DeepAgentRunner(
                conn=conn, engine=EngineClient(args.engine_url), artifact_dir=Path(args.artifact_dir)
            )
        try:
            return await loop(conn, engine_url=args.engine_url,
                              artifact_dir=Path(args.artifact_dir), planner=chosen, args=args)
        finally:
            await conn.close()

    return asyncio.run(go())


if __name__ == "__main__":
    raise SystemExit(main())

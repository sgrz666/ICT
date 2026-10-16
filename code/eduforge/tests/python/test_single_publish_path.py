"""结构守卫：把「只有一个提交者」这句话变成可执行断言。

这类约束如果不写成测试，下一个人加功能时就会顺手多写一条 SQL，
于是又出现第二套发布语义——这正是本轮要收敛掉的东西。
"""
from __future__ import annotations

import inspect
from pathlib import Path

from eduforge.experiment_tools import service as tool_service
from eduforge.infrastructure.db import repositories as repo_module

SRC_ROOT = Path(inspect.getfile(tool_service)).resolve().parents[1]


def _py_files():
    skip = {"__pycache__"}
    for p in SRC_ROOT.rglob("*.py"):
        if not (skip & set(p.parts)):
            yield p


def test_only_the_gated_transaction_can_publish_a_revision():
    """带租约证明的发布插入只允许存在于持久层那一条事务里。

    head 指针还可以被**回滚**移动（application/experiment_service.py）：那是
    把 head 指回一个已发布过的版本，并按追加式历史补一条派生修订——它不改写
    既有修订，也不需要租约。两种语义必须分开钉，否则守卫不是太宽就是太假。
    """
    lease_gated = [
        p.relative_to(SRC_ROOT).as_posix()
        for p in _py_files()
        if "lease_token = $6" in p.read_text(encoding="utf-8")
    ]
    assert lease_gated == ["infrastructure/db/repositories.py"], f"出现多处租约证明式发布：{lease_gated}"

    # 回滚是追加式的：它可以为新版本插入一条修订，但绝不改写既有修订的内容，
    # 也不能绕过归属与活动任务两项检查
    rollback_src = (SRC_ROOT / "application" / "experiment_service.py").read_text(encoding="utf-8")
    assert "update experiment_revisions" not in rollback_src, "回滚不得改写既有修订的内容"
    assert "ActiveJobConflict" in rollback_src, "回滚必须有活动任务守卫"
    assert "owner_id" in rollback_src, "回滚必须校验归属"


def test_tool_service_does_not_own_publish_sql():
    """工具层的发布必须委托持久层事务，自己不再写版本/产物 SQL。"""
    body = inspect.getsource(tool_service.ExperimentToolService.publish_revision)
    for forbidden in (
        "insert into experiment_revisions",
        "insert into artifacts",
        "update experiments",
        "self.conn.execute",
        "self.conn.transaction",
    ):
        assert forbidden not in body, f"publish_revision 里不该再有 {forbidden}"
    assert "Publisher(" in body, "发布应走 application/publication.py → JobRepository.publish"


def test_ddl_lives_only_in_the_persistence_layer():
    """建表语句只有一个来源，避免三处各跑一份漂移的 schema。"""
    owners = {
        p.relative_to(SRC_ROOT).as_posix()
        for p in _py_files()
        if "create table if not exists jobs" in p.read_text(encoding="utf-8")
    }
    assert owners == {"infrastructure/db/repositories.py"}, owners
    assert hasattr(repo_module.JobRepository, "publish")

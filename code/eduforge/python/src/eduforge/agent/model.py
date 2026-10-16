"""DeepSeek 模型接入入口。

对齐方案 §4.1：
- 关闭供应商重试（max_retries=0），由应用任务层统一记录和限制重试。
- 模型名、base_url、凭证全部配置化：DeepSeek 现在只有 `deepseek-flash` 与
  `deepseek-v4-pro` 两个标识，旧默认名 `deepseek-chat` 仍能请求（服务端映射到
  flash），但把名字写死在代码里迟早会变成第二处要改的地方。

凭证只从环境变量解析（沿用 `infrastructure/settings.get_deepseek_api_key()`
这条既有链），绝不落在仓库文件里。
"""
from __future__ import annotations

import os
from typing import Any

from eduforge.domain.errors import EduForgeError

DEFAULT_MODEL = "deepseek-flash"
DEFAULT_BASE_URL = "https://api.deepseek.com/v1"


def resolve_model_name() -> str:
    """按 EDUFORGE_MODEL → DEEPSEEK_MODEL → 默认值 的顺序取模型标识。"""
    return (os.getenv("EDUFORGE_MODEL") or os.getenv("DEEPSEEK_MODEL") or DEFAULT_MODEL).strip()


def resolve_base_url() -> str:
    return (os.getenv("EDUFORGE_MODEL_BASE_URL") or os.getenv("DEEPSEEK_BASE_URL") or DEFAULT_BASE_URL).strip()


def create_model(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model_name: str | None = None,
    timeout: int = 60,
    **kwargs: Any,
) -> Any:
    """创建接入 DeepSeek（OpenAI 兼容协议）的 ChatModel 实例。"""
    resolved_key = api_key
    if not resolved_key:
        from eduforge.infrastructure.settings import get_deepseek_api_key
        resolved_key = get_deepseek_api_key()
    if not resolved_key:
        raise EduForgeError(
            "DeepSeek API 密钥未配置。请在环境变量 deepseek / DEEPSEEK / DEEPSEEK_API_KEY "
            "中提供有效的 Key，或由调用方显式传入 api_key。",
            code="MODEL_CONFIG_ERROR",
        )

    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise EduForgeError(
            "未检测到 langchain-openai。Deep Agents 路径依赖它走 OpenAI 兼容协议。",
            code="DEPENDENCY_MISSING",
        ) from exc

    return ChatOpenAI(
        api_key=resolved_key,
        base_url=base_url or resolve_base_url(),
        model=model_name or resolve_model_name(),
        timeout=timeout,
        max_retries=0,
        **kwargs,
    )

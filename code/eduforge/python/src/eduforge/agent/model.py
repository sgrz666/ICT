"""DeepSeek 模型接入入口。

对齐方案 §4.1：
- 显式关闭思考模式，聚焦结构化输出与工具调用。
- 关闭供应商重试（max_retries=0），由应用任务层统一记录和限制重试。
- 支持 langchain_deepseek 官方包，或兼容 langchain_openai 协议。
"""
from __future__ import annotations

import os
from typing import Any

from eduforge.domain.errors import EduForgeError


def create_model(
    *,
    api_key: str | None = None,
    base_url: str = "https://api.deepseek.com",
    model_name: str = "deepseek-chat",
    timeout: int = 60,
    **kwargs: Any,
) -> Any:
    """创建接入 DeepSeek 的 ChatModel 实例。"""
    resolved_key = (
        api_key
        or os.getenv("deepseek")
        or os.getenv("DEEPSEEK")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("deepseek_api_key")
    )
    if not resolved_key:
        from eduforge.infrastructure.settings import get_deepseek_api_key
        resolved_key = get_deepseek_api_key()
    if not resolved_key:
        raise EduForgeError(
            "DeepSeek API 密钥未配置。请在环境变量（deepseek 或 DEEPSEEK_API_KEY）或入参中提供有效的 DeepSeek API Key。",
            code="MODEL_CONFIG_ERROR",
        )

    # 优先尝试官方 langchain-deepseek
    try:
        from langchain_deepseek import ChatDeepSeek

        return ChatDeepSeek(
            api_key=resolved_key,
            api_base=base_url,
            model=model_name,
            timeout=timeout,
            max_retries=0,
            extra_body={
                "thinking": {
                    "type": "disabled",
                }
            },
            **kwargs,
        )
    except ImportError:
        pass

    # 次选兼容模式：langchain-openai 驱动 deepseek-chat
    try:
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            api_key=resolved_key,
            base_url=base_url,
            model=model_name,
            timeout=timeout,
            max_retries=0,
            **kwargs,
        )
    except ImportError as exc:
        raise EduForgeError(
            "未检测到 langchain_deepseek 或 langchain_openai。请运行 pip install langchain-deepseek。",
            code="DEPENDENCY_MISSING",
        ) from exc

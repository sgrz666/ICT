"""EduForge 系统配置与环境变量管理。

对齐方案 §1.2：统一读取数据库、Engine Host、Agent 及存储参数。
支持优先读取本机变量名为 deepseek 的环境变量。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def get_deepseek_api_key() -> str | None:
    """获取 DeepSeek API Key。

    优先级：
    1. 进程环境变量：deepseek（用户显式指定的变量名）
    2. 进程环境变量：DEEPSEEK
    3. 进程环境变量：DEEPSEEK_API_KEY
    4. 进程环境变量：deepseek_api_key
    5. 若非测试环境且在 Windows 上，尝试从用户/系统注册表读取 deepseek 兜底
    """
    for key in ("deepseek", "DEEPSEEK", "DEEPSEEK_API_KEY", "deepseek_api_key"):
        val = os.environ.get(key)
        if val is not None and val.strip():
            return val.strip()

    # 如果显式设置为 ""（例如测试中 monkeypatch），不应再走注册表兜底
    explicit_empty = any(
        k in os.environ and not (os.environ[k] or "").strip()
        for k in ("deepseek", "DEEPSEEK", "DEEPSEEK_API_KEY")
    )
    if explicit_empty or "PYTEST_CURRENT_TEST" in os.environ:
        return None

    # Windows 注册表兜底（方便在系统属性添加环境变量后免重启终端直接生效）
    if os.name == "nt":
        try:
            import winreg

            for root, subkey in [
                (winreg.HKEY_CURRENT_USER, r"Environment"),
                (
                    winreg.HKEY_LOCAL_MACHINE,
                    r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment",
                ),
            ]:
                try:
                    with winreg.OpenKey(root, subkey) as hkey:
                        i = 0
                        while True:
                            name, val, _ = winreg.EnumValue(hkey, i)
                            if name.lower() in ("deepseek", "deepseek_api_key") and val:
                                s = str(val).strip()
                                if s:
                                    # 回填至当前进程环境变量，保持全链条一致
                                    os.environ.setdefault("deepseek", s)
                                    os.environ.setdefault("DEEPSEEK_API_KEY", s)
                                    return s
                            i += 1
                except OSError:
                    pass
        except Exception:
            pass

    return None


@dataclass
class Settings:
    """系统运行配置。"""
    database_url: str = os.getenv(
        "DATABASE_URL",
        "postgresql://eduforge:eduforge@127.0.0.1:5432/eduforge",
    )
    engine_host_url: str = os.getenv("ENGINE_HOST_URL", "http://127.0.0.1:4000")
    agent_host_url: str = os.getenv("AGENT_HOST_URL", "http://127.0.0.1:8001")
    artifacts_dir: Path = Path(os.getenv("ARTIFACTS_DIR", "output/eduforge/artifacts"))
    templates_dir: Path = Path(os.getenv("TEMPLATES_DIR", "catalog/templates"))
    deepseek_api_key: str | None = get_deepseek_api_key()
    deepseek_base_url: str = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    deepseek_model: str = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")


settings = Settings()

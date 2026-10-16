"""EduForge 领域错误定义。

方案 §1.2 规定 domain/ 为纯核心，不依赖外部框架。
所有业务与策略错误继承自 EduForgeError。
"""
from __future__ import annotations


class EduForgeError(Exception):
    """EduForge 领域异常基类。"""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class PolicyViolationError(EduForgeError):
    """请求超出模板清单能力或包含非法字段时抛出。"""
    def __init__(self, message: str, code: str = "POLICY_REJECTED"):
        super().__init__(message, code=code)


class ConflictError(EduForgeError):
    """并发写冲突或活跃任务排他冲突。"""
    def __init__(self, message: str, code: str = "CONFLICT"):
        super().__init__(message, code=code)


class NotFoundError(EduForgeError):
    """请求的实验、版本或产物不存在。"""
    def __init__(self, message: str, code: str = "NOT_FOUND"):
        super().__init__(message, code=code)


class LeaseExpiredError(EduForgeError):
    """Worker 租约超时或执行权被夺取。"""
    def __init__(self, message: str, code: str = "LEASE_EXPIRED"):
        super().__init__(message, code=code)


class ScientificValidationError(EduForgeError):
    """科学参考计算不一致或仿真数值越界。"""
    def __init__(self, message: str, code: str = "SCIENTIFIC_VALIDATION_FAILED"):
        super().__init__(message, code=code)

"""REA（Reverse Engineering Assistant）逆向分析研究入口。

对齐方案 §1.2 和 §6.4：
- 只供开发研究使用，不进入面向教师的在线业务链路；
- 调起本机 REA CLI 针对仿真引擎样本（JS/HTML/Bundle）进行静态结构与接口分析；
- 产出 Evidence JSON，留痕目标版本、SHA256、导出符号与能力边界。
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any


class REARunner:
    """逆向工程研究运行器。"""

    def __init__(self, rea_bin: str = "rea", output_dir: Path | str = "output/eduforge/research"):
        self.rea_bin = rea_bin
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def is_available(self) -> bool:
        """检查本机是否安装 REA CLI。"""
        return shutil.which(self.rea_bin) is not None

    def analyze_sample(
        self,
        sample_path: Path | str,
        target_name: str,
        engine_type: str = "javascript",
    ) -> dict[str, Any]:
        """分析样本文件或目录并生成 Evidence 结构化记录。"""
        sample_p = Path(sample_path).resolve()
        if not sample_p.exists():
            raise FileNotFoundError(f"样本路径不存在: {sample_p}")

        # 计算样本哈希
        if sample_p.is_file():
            digest = hashlib.sha256(sample_p.read_bytes()).hexdigest()
            file_count = 1
            total_bytes = sample_p.stat().st_size
        else:
            files = [f for f in sample_p.rglob("*") if f.is_file()]
            h = hashlib.sha256()
            for f in sorted(files):
                h.update(f.read_bytes())
            digest = h.hexdigest()
            file_count = len(files)
            total_bytes = sum(f.stat().st_size for f in files)

        evidence: dict[str, Any] = {
            "target_name": target_name,
            "engine_type": engine_type,
            "sample_path": str(sample_p),
            "sample_sha256": digest,
            "file_count": file_count,
            "total_bytes": total_bytes,
            "rea_cli_available": self.is_available(),
            "analysis_mode": "static_structure",
            "findings": {
                "format": "bundle" if sample_p.is_file() else "tree",
                "extracted_symbols": [],
                "notes": "Ray Optics 属于开源 JS 引擎，静态目录结构由 upstream.lock.json 与 adapter 锁定。",
            },
        }

        # 若本机安装了 REA CLI，尝试调用提取深入信息
        if self.is_available():
            try:
                cmd = [self.rea_bin, "inspect", "--json", str(sample_p)]
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                if proc.returncode == 0 and proc.stdout.strip():
                    evidence["findings"]["rea_raw"] = json.loads(proc.stdout)
            except Exception as exc:
                evidence["findings"]["rea_execution_error"] = str(exc)

        out_file = self.output_dir / f"rea-{target_name}-evidence.json"
        out_file.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
        evidence["report_path"] = str(out_file)
        return evidence

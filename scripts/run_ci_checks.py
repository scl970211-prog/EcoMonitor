#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
本地 CI 检查脚本

模拟 CI 流水线执行：
1. Python 语法检查（py_compile）
2. 运行 pytest

用法：
    python scripts/run_ci_checks.py
"""

import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).parent.parent.resolve()
SRC_DIR = PROJECT_ROOT / "src"


def _ensure_venv_python() -> Path:
    """
    如果当前解释器无法导入 pytest，尝试寻找项目虚拟环境解释器。
    找到后使用该解释器重新执行脚本并退出当前进程。
    """
    try:
        import pytest  # noqa: F401
        return Path(sys.executable)
    except ImportError:
        pass

    candidates = [
        PROJECT_ROOT / ".venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / "venv" / "Scripts" / "python.exe",
        PROJECT_ROOT / ".venv" / "bin" / "python",
        PROJECT_ROOT / "venv" / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            print(f"[CI] 当前解释器缺少 pytest，切换到虚拟环境: {candidate}")
            result = subprocess.run([str(candidate), __file__] + sys.argv[1:])
            sys.exit(result.returncode)

    print(
        "[CI] 错误：当前 Python 环境未安装 pytest，且未找到项目虚拟环境。\n"
        "       请使用项目虚拟环境运行，或执行: pip install pytest"
    )
    sys.exit(1)


PYTHON_EXE = str(_ensure_venv_python())


def run_py_compile() -> bool:
    """递归检查 src 下所有 Python 文件语法。"""
    print("[CI] 开始 Python 语法检查...")
    py_files = list(SRC_DIR.rglob("*.py"))
    if not py_files:
        print("[CI] 未找到 Python 源文件")
        return False

    cmd = [PYTHON_EXE, "-m", "py_compile"] + [str(f) for f in py_files]
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    if result.returncode != 0:
        print("[CI] 语法检查失败")
        return False
    print("[CI] 语法检查通过")
    return True


def run_pytest() -> bool:
    """运行测试套件。"""
    print("[CI] 开始运行测试...")
    result = subprocess.run(
        [PYTHON_EXE, "-m", "pytest", "tests/", "-q"],
        cwd=PROJECT_ROOT,
    )
    if result.returncode != 0:
        print("[CI] 测试运行失败")
        return False
    print("[CI] 测试运行通过")
    return True


def main() -> int:
    """入口。"""
    checks = [
        ("语法检查", run_py_compile),
        ("测试套件", run_pytest),
    ]

    failed = []
    for name, check in checks:
        if not check():
            failed.append(name)

    if failed:
        print(f"\n[CI] 未通过的检查: {', '.join(failed)}")
        return 1

    print("\n[CI] 所有检查通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())

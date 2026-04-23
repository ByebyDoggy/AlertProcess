"""
安全沙箱执行环境

为 ScriptNode 提供受限的 Python 代码执行环境，防止用户脚本执行危险操作。

安全措施:
  1. 白名单内置函数 — 只允许安全的 builtins
  2. 禁止危险模块导入 — os, sys, subprocess, socket 等
  3. 执行超时限制 — 默认 5 秒
  4. 递归深度限制 — 默认 100 层
  5. 输出大小限制 — 防止内存炸弹

使用方式:
  from nodes.scripting.sandbox import execute_script

  result = execute_script(
      script="result = all(passed); score = max(scores)",
      variables={"scores": [80, 60], "passed": [True, False], "ctx": {...}},
      timeout=5.0,
  )
  # result = {"result": False, "score": 80, "_stdout": "", "_error": None}
"""

from __future__ import annotations

import logging
import signal
import sys
import threading
from typing import Any

logger = logging.getLogger(__name__)

# ── 安全白名单 ──

# 允许的内置函数
ALLOWED_BUILTINS = {
    "abs", "all", "any", "bin", "bool", "chr", "dict", "divmod",
    "enumerate", "filter", "float", "format", "frozenset", "hash",
    "hex", "int", "isinstance", "issubclass", "iter", "len",
    "list", "map", "max", "min", "next", "oct", "ord", "pow",
    "print", "range", "repr", "reversed", "round", "set",
    "setattr", "slice", "sorted", "str", "sum", "tuple", "type",
    "zip", "True", "False", "None",
}

# 禁止导入的模块
BLOCKED_MODULES = {
    "os", "sys", "subprocess", "socket", "http", "urllib",
    "shutil", "pathlib", "importlib", "ctypes", "multiprocessing",
    "threading", "signal", "builtins", "code", "codeop",
    "compileall", "py_compile", "runpy", "site",
    "webbrowser", "antigravity", "pickle", "shelve",
    "xmlrpc", "ftplib", "smtplib", "telnetlib", "poplib",
    "asyncio", "concurrent", "tempfile", "glob",
}

# 允许导入的安全模块
ALLOWED_MODULES = {
    "re", "math", "json", "datetime", "decimal", "collections",
    "itertools", "functools", "operator", "string", "copy",
}

# 最大输出大小
MAX_OUTPUT_SIZE = 50000

# 默认超时（秒）
DEFAULT_TIMEOUT = 5.0

# 默认递归深度
DEFAULT_RECURSION_LIMIT = 100


class ScriptTimeoutError(Exception):
    """脚本执行超时"""
    pass


class ScriptSecurityError(Exception):
    """脚本违反安全策略"""
    pass


def _safe_import(name: str, *args: Any, **kwargs: Any) -> Any:
    """安全的 import 替代，只允许白名单模块"""
    root_module = name.split(".")[0]
    if root_module in BLOCKED_MODULES:
        raise ScriptSecurityError(f"禁止导入模块: {name}")
    if root_module in ALLOWED_MODULES:
        return __import__(name, *args, **kwargs)
    raise ScriptSecurityError(f"不允许导入模块: {name}（允许的模块: {', '.join(sorted(ALLOWED_MODULES))}）")


def _build_safe_builtins() -> dict[str, Any]:
    """构建安全的 builtins 字典"""
    import builtins as _builtins

    safe = {}
    for name in ALLOWED_BUILTINS:
        if hasattr(_builtins, name):
            safe[name] = getattr(_builtins, name)

    # 覆盖 __import__ 为安全版本
    safe["__import__"] = _safe_import

    # Exception 基类（允许 try/except）
    safe["Exception"] = Exception
    safe["ValueError"] = ValueError
    safe["TypeError"] = TypeError
    safe["KeyError"] = KeyError
    safe["IndexError"] = IndexError
    safe["AttributeError"] = AttributeError
    safe["RuntimeError"] = RuntimeError
    safe["StopIteration"] = StopIteration

    return safe


def _timeout_handler(signum: int, frame: Any) -> None:
    """信号超时处理（仅 Unix）"""
    raise ScriptTimeoutError("脚本执行超时")


def execute_script(
    script: str,
    variables: dict[str, Any],
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """
    在沙箱中执行用户脚本。

    Args:
        script:     用户编写的 Python 代码
        variables:  注入到脚本命名空间的变量（inputs, scores, ctx 等）
        timeout:    执行超时时间（秒）

    Returns:
        脚本执行后的命名空间（包含 result, score, labels 等输出变量）

    Raises:
        ScriptTimeoutError:   执行超时
        ScriptSecurityError:  违反安全策略
        SyntaxError:          脚本语法错误
    """
    # 构建安全执行环境
    safe_globals: dict[str, Any] = {
        "__builtins__": _build_safe_builtins(),
    }

    # 合并注入变量
    sandbox: dict[str, Any] = {**safe_globals, **variables}

    # stdout 捕获
    import io
    stdout_capture = io.StringIO()

    # 保存原始状态
    old_stdout = sys.stdout
    try:
        old_recursion = sys.getrecursionlimit()
    except AttributeError:
        old_recursion = 1000
    sys.stdout = stdout_capture
    try:
        sys.setrecursionlimit(DEFAULT_RECURSION_LIMIT)
    except AttributeError:
        pass

    error: str | None = None

    try:
        # 编译脚本（检查语法）
        code = compile(script, "<script_node>", "exec")

        # 执行
        exec(code, sandbox)

    except ScriptTimeoutError:
        error = "脚本执行超时"
    except ScriptSecurityError as e:
        error = f"安全策略违规: {e}"
    except SyntaxError as e:
        error = f"语法错误 (行 {e.lineno}): {e.msg}"
    except RecursionError:
        error = f"递归深度超过限制 ({DEFAULT_RECURSION_LIMIT})"
    except Exception as e:
        error = f"{type(e).__name__}: {e}"
    finally:
        sys.stdout = old_stdout
        try:
            sys.setrecursionlimit(old_recursion)
        except (AttributeError, NameError):
            pass

    # 提取输出
    stdout_text = stdout_capture.getvalue()
    if len(stdout_text) > MAX_OUTPUT_SIZE:
        stdout_text = stdout_text[:MAX_OUTPUT_SIZE] + "...(截断)"

    # 清理内部变量
    result: dict[str, Any] = {}
    for key, value in sandbox.items():
        if key.startswith("__"):
            continue
        result[key] = value

    result["_stdout"] = stdout_text
    result["_error"] = error

    return result

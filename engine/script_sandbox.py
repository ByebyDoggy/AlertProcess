"""
脚本沙箱执行引擎 — 安全的 Python 脚本执行环境

提供受限的 Python 执行环境，用于执行用户自定义脚本（如自定义检测逻辑、数据处理等）。

安全特性:
  - 模块白名单: 仅允许 re, json, math, datetime, collections, itertools, functools, typing
  - 禁止危险函数: open, exec, eval, compile, __import__, input, breakpoint, exit, quit
  - 禁止文件系统和网络访问
  - 超时控制: 默认 5 秒
  - 内存限制: 默认 100MB (通过监控实现)
  - 受限的 __builtins__

用法:
  >>> sandbox = ScriptSandbox(timeout=5, memory_limit_mb=100)
  >>> result = await sandbox.execute_async(
  ...     script_code='result = sum([x**2 for x in range(10)])',
  ...     context={'data': [1, 2, 3]}
  ... )
  >>> print(result)
  {'success': True, 'result': 285, 'error': None, 'execution_time_ms': 0.5}
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Any

logger = logging.getLogger(__name__)


# ── 安全的内置函数白名单 ──
_SAFE_BUILTINS: dict[str, Any] = {
    # 基础类型
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "bytes": bytes,
    "bytearray": bytearray,
    # 容器类型
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "frozenset": frozenset,
    # 常量
    "True": True,
    "False": False,
    "None": None,
    "Ellipsis": Ellipsis,
    # 常用函数
    "len": len,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "sorted": sorted,
    "reversed": reversed,
    "round": round,
    "abs": abs,
    "min": min,
    "max": max,
    "sum": sum,
    "any": any,
    "all": all,
    "pow": pow,
    "divmod": divmod,
    # 类型检查
    "isinstance": isinstance,
    "issubclass": issubclass,
    "type": type,
    "hasattr": hasattr,
    "getattr": getattr,
    "setattr": setattr,
    "delattr": delattr,
    # 字符串/字节操作
    "chr": chr,
    "ord": ord,
    "hex": hex,
    "oct": oct,
    "bin": bin,
    "format": format,
    "repr": repr,
    "ascii": ascii,
    # 迭代器
    "iter": iter,
    "next": next,
    # 对象操作
    "id": id,
    "hash": hash,
    "callable": callable,
    "dir": dir,
    "vars": vars,
    "slice": slice,
    # 异常类
    "Exception": Exception,
    "ValueError": ValueError,
    "KeyError": KeyError,
    "TypeError": TypeError,
    "IndexError": IndexError,
    "AttributeError": AttributeError,
    "RuntimeError": RuntimeError,
    "StopIteration": StopIteration,
    "ZeroDivisionError": ZeroDivisionError,
    "AssertionError": AssertionError,
    "NotImplementedError": NotImplementedError,
    # 其他
    "print": print,  # 允许调试输出
    "object": object,
    "property": property,
    "staticmethod": staticmethod,
    "classmethod": classmethod,
}


# ── 允许的模块白名单 ──
_ALLOWED_MODULES = {
    "re",
    "json",
    "math",
    "datetime",
    "collections",
    "itertools",
    "functools",
    "typing",
}


class ScriptExecutionError(Exception):
    """脚本执行错误"""
    pass


class ScriptTimeoutError(ScriptExecutionError):
    """脚本执行超时"""
    pass


class ScriptMemoryError(ScriptExecutionError):
    """脚本内存超限"""
    pass


class ScriptSandbox:
    """
    安全的 Python 脚本沙箱执行环境。

    提供受限的执行环境，防止恶意代码执行危险操作。
    """

    DEFAULT_TIMEOUT = 5  # 默认超时 5 秒
    DEFAULT_MEMORY_LIMIT_MB = 100  # 默认内存限制 100MB
    MAX_SCRIPT_LENGTH = 50000  # 脚本最大长度 50KB

    def __init__(
        self,
        timeout: float | None = None,
        memory_limit_mb: int | None = None,
    ) -> None:
        """
        初始化脚本沙箱。

        Args:
            timeout: 执行超时时间（秒），默认 5 秒
            memory_limit_mb: 内存限制（MB），默认 100MB
        """
        self.timeout = timeout or self.DEFAULT_TIMEOUT
        self.memory_limit_mb = memory_limit_mb or self.DEFAULT_MEMORY_LIMIT_MB
        self.memory_limit_bytes = self.memory_limit_mb * 1024 * 1024
        self._executor = self._create_executor()

    def _create_executor(self) -> ThreadPoolExecutor:
        return ThreadPoolExecutor(max_workers=1, thread_name_prefix="script-sandbox")

    def execute(
        self,
        script_code: str,
        context: dict[str, Any] | None = None,
        return_namespace: bool = False,
    ) -> dict[str, Any]:
        """
        同步执行脚本（阻塞式）。

        Args:
            script_code: 要执行的 Python 脚本代码
            context: 注入到脚本中的上下文变量

        Returns:
            执行结果字典:
            {
                'success': bool,           # 是否成功
                'result': Any,             # 脚本返回值（通过 result 变量）
                'error': str | None,       # 错误信息
                'execution_time_ms': float # 执行时间（毫秒）
            }
        """
        # 使用 asyncio.run 包装异步执行
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # 如果已经在事件循环中，创建新的任务
                return asyncio.create_task(
                    self.execute_async(script_code, context, return_namespace=return_namespace)
                )
            else:
                return loop.run_until_complete(
                    self.execute_async(script_code, context, return_namespace=return_namespace)
                )
        except RuntimeError:
            # 没有事件循环，创建新的
            return asyncio.run(self.execute_async(script_code, context, return_namespace=return_namespace))

    async def execute_async(
        self,
        script_code: str,
        context: dict[str, Any] | None = None,
        return_namespace: bool = False,
    ) -> dict[str, Any]:
        """
        异步执行脚本（非阻塞）。

        Args:
            script_code: 要执行的 Python 脚本代码
            context: 注入到脚本中的上下文变量

        Returns:
            执行结果字典（同 execute）
        """
        start_time = time.monotonic()

        # 1. 基础校验
        if not script_code or not script_code.strip():
            return {
                "success": False,
                "result": None,
                "error": "Script code is empty",
                "execution_time_ms": 0,
            }

        script_code = script_code.strip()

        # 2. 长度限制
        if len(script_code) > self.MAX_SCRIPT_LENGTH:
            return {
                "success": False,
                "result": None,
                "error": f"Script too long ({len(script_code)} > {self.MAX_SCRIPT_LENGTH})",
                "execution_time_ms": 0,
            }

        # 3. 安全检查
        try:
            self._security_check(script_code)
        except ValueError as e:
            return {
                "success": False,
                "result": None,
                "error": f"Security check failed: {e}",
                "execution_time_ms": 0,
            }

        # 4. 构建受限的全局命名空间
        safe_globals = self._build_restricted_globals(context or {})

        # 5. 使用 asyncio.wait_for 实现超时控制
        try:
            result = await asyncio.wait_for(
                self._execute_in_sandbox(script_code, safe_globals, return_namespace=return_namespace),
                timeout=self.timeout,
            )

            execution_time_ms = (time.monotonic() - start_time) * 1000

            return {
                "success": True,
                "result": result,
                "error": None,
                "execution_time_ms": execution_time_ms,
            }

        except asyncio.TimeoutError:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = self._create_executor()
            execution_time_ms = (time.monotonic() - start_time) * 1000
            return {
                "success": False,
                "result": None,
                "error": f"Script execution timeout (>{self.timeout}s)",
                "execution_time_ms": execution_time_ms,
            }
        except ScriptMemoryError as e:
            execution_time_ms = (time.monotonic() - start_time) * 1000
            return {
                "success": False,
                "result": None,
                "error": str(e),
                "execution_time_ms": execution_time_ms,
            }
        except Exception as e:
            execution_time_ms = (time.monotonic() - start_time) * 1000
            error_msg = f"{type(e).__name__}: {e}"
            logger.warning(f"[ScriptSandbox] Execution failed: {error_msg}")
            return {
                "success": False,
                "result": None,
                "error": error_msg,
                "execution_time_ms": execution_time_ms,
            }

    async def _execute_in_sandbox(
        self,
        script_code: str,
        safe_globals: dict[str, Any],
        return_namespace: bool = False,
    ) -> Any:
        """
        在沙箱环境中执行脚本。

        脚本可以通过设置 'result' 变量来返回结果。
        如果没有设置 result，返回 None。

        Args:
            script_code: 脚本代码
            safe_globals: 受限的全局命名空间

        Returns:
            脚本执行结果（通过 result 变量）
        """
        # 在独立的线程中执行，避免阻塞事件循环
        loop = asyncio.get_event_loop()

        def _run_script():
            """在受限环境中执行脚本"""
            try:
                # 编译脚本
                compiled_code = compile(script_code, "<sandbox>", "exec")

                # 执行脚本
                exec(compiled_code, safe_globals, safe_globals)

                # 检查内存使用（执行后）
                self._check_memory_usage()

                if return_namespace:
                    return {
                        key: value
                        for key, value in safe_globals.items()
                        if not key.startswith("__")
                    }

                return safe_globals.get("result", None)

            except MemoryError as e:
                raise ScriptMemoryError(f"Memory limit exceeded: {e}") from e
            except Exception as e:
                # 保留原始异常类型和堆栈
                raise

        # 在线程池中执行（避免阻塞事件循环）
        result = await loop.run_in_executor(self._executor, _run_script)
        return result

    def _build_restricted_globals(
        self,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """
        构建受限的全局命名空间。

        注入:
          - 安全的内置函数（_SAFE_BUILTINS）
          - 白名单模块（re, json, math, datetime, collections, itertools, functools, typing）
          - 用户提供的上下文变量

        Args:
            context: 用户上下文变量

        Returns:
            受限的全局命名空间字典
        """
        # 1. 基础安全内置
        safe_globals = {
            "__builtins__": _SAFE_BUILTINS.copy(),
            "__name__": "<sandbox>",
            "__doc__": None,
        }

        # 2. 注入白名单模块（预先导入，避免脚本中使用 import）
        for module_name in _ALLOWED_MODULES:
            try:
                # 使用 __import__ 导入模块
                module = __import__(module_name)
                safe_globals[module_name] = module

                # 对于某些模块，还需要导入子模块
                if module_name == "datetime":
                    from datetime import datetime, timedelta, timezone, date, time
                    safe_globals["datetime"] = datetime
                    safe_globals["timedelta"] = timedelta
                    safe_globals["timezone"] = timezone
                    safe_globals["date"] = date
                    safe_globals["time"] = time
                elif module_name == "collections":
                    from collections import Counter, defaultdict, OrderedDict, deque
                    safe_globals["Counter"] = Counter
                    safe_globals["defaultdict"] = defaultdict
                    safe_globals["OrderedDict"] = OrderedDict
                    safe_globals["deque"] = deque

            except ImportError:
                logger.warning(f"[ScriptSandbox] Failed to import module: {module_name}")

        # 3. 注入用户上下文（深拷贝以防止修改原始数据）
        if context:
            import copy
            try:
                safe_context = copy.deepcopy(context)
                safe_globals.update(safe_context)
            except Exception as e:
                logger.warning(f"[ScriptSandbox] Failed to deep copy context: {e}")
                # 如果深拷贝失败，使用浅拷贝
                safe_globals.update(context.copy())

        return safe_globals

    def _check_memory_usage(self) -> None:
        """
        检查当前进程的内存使用情况。

        如果超过限制，抛出 ScriptMemoryError。

        注意: 这是一个粗略的检查，无法精确限制单个脚本的内存使用。
        """
        try:
            import psutil
            process = psutil.Process()
            memory_info = process.memory_info()
            current_memory = memory_info.rss  # 常驻内存（字节）

            if current_memory > self.memory_limit_bytes:
                raise ScriptMemoryError(
                    f"Memory usage ({current_memory / 1024 / 1024:.2f}MB) "
                    f"exceeds limit ({self.memory_limit_mb}MB)"
                )
        except ImportError:
            # psutil 未安装，跳过内存检查
            logger.debug("[ScriptSandbox] psutil not available, skipping memory check")
        except Exception as e:
            logger.warning(f"[ScriptSandbox] Memory check failed: {e}")

    # ──────────── 安全检查 ────────────

    # 危险的内置函数（不能作为独立函数调用）
    _FORBIDDEN_BUILTINS = [
        "open",
        "exec",
        "eval",
        "compile",
        "__import__",
        "input",
        "breakpoint",
        "exit",
        "quit",
    ]

    # 危险的模块和操作
    _FORBIDDEN_PATTERNS = [
        # 文件系统
        r'\bfile\s*\(',
        r'\bos\.system\b',
        r'\bos\.popen\b',
        r'\bos\.spawn\b',
        r'\bos\.exec\b',
        r'\bsubprocess\.',
        # 网络
        r'\bsocket\.',
        r'\burllib\.',
        r'\brequests\.',
        r'\bhttp\.',
        r'\bhttpx\.',
        # 反射/元编程
        r'\.__class__\b',
        r'\.__subclasses__\b',
        r'\.__mro__\b',
        r'\.__bases__\b',
        r'\.__globals__\b',
        r'\.__code__\b',
        r'\.__dict__\b',
        r'\.__getattribute__\b',
        r'\.__setattr__\b',
        r'\.__delattr__\b',
        # 模块导入
        r'\bimportlib\.',
        r'\bimp\.',
        # 其他危险操作
        r'\bglobals\s*\(\)',
        r'\blocals\s*\(\)',
    ]

    def _security_check(self, script_code: str) -> None:
        """
        检查脚本代码是否包含危险操作。

        Args:
            script_code: 脚本代码

        Raises:
            ValueError: 如果检测到危险操作
        """
        import re

        # 移除注释后再检查（避免注释中的关键字误报）
        # 移除单行注释
        code_without_comments = re.sub(r'#.*$', '', script_code, flags=re.MULTILINE)
        # 移除多行字符串（可能包含示例代码）
        code_without_comments = re.sub(r'""".*?"""', '', code_without_comments, flags=re.DOTALL)
        code_without_comments = re.sub(r"'''.*?'''", '', code_without_comments, flags=re.DOTALL)

        lowered = code_without_comments.lower()

        # 1. 检查禁止的内置函数（作为独立函数调用，不是方法调用）
        for builtin in self._FORBIDDEN_BUILTINS:
            # 匹配独立函数调用: builtin( 但不匹配 xxx.builtin(
            pattern = r'(?<![.\w])' + re.escape(builtin.lower()) + r'\s*\('
            if re.search(pattern, lowered):
                raise ValueError(
                    f"Forbidden builtin function detected: '{builtin}'. "
                    f"This operation is not allowed in sandbox."
                )

        # 2. 检查禁止的模式
        for pattern in self._FORBIDDEN_PATTERNS:
            if re.search(pattern, lowered, re.IGNORECASE):
                raise ValueError(
                    f"Forbidden pattern detected in script. "
                    f"This operation is not allowed in sandbox."
                )

        # 3. 禁止 import 语句（模块已预先导入，无需在脚本中 import）
        if re.search(r'\bimport\s+', code_without_comments) or re.search(r'\bfrom\s+\w+\s+import\b', code_without_comments):
            raise ValueError(
                f"Import statements are not allowed in sandbox. "
                f"All allowed modules are pre-imported: {', '.join(sorted(_ALLOWED_MODULES))}. "
                f"Use them directly without import statements."
            )

        # 4. 检查双下划线属性访问（可能的反射攻击）
        dunder_pattern = r'__\w+__'
        dangerous_dunders = [
            "__class__", "__subclasses__", "__mro__", "__bases__",
            "__globals__", "__code__", "__dict__", "__getattribute__",
        ]
        for match in re.finditer(dunder_pattern, code_without_comments):
            dunder = match.group(0)
            if dunder.lower() in [d.lower() for d in dangerous_dunders]:
                raise ValueError(
                    f"Access to '{dunder}' is not allowed. "
                    f"Reflection and meta-programming are restricted."
                )

    # ──────────── 辅助方法 ────────────

    @classmethod
    def validate(cls, script_code: str) -> dict[str, Any]:
        """
        验证脚本语法和安全性（不执行）。

        Args:
            script_code: 脚本代码

        Returns:
            验证结果:
            {
                'valid': bool,
                'error': str | None,
                'warnings': list[str]
            }
        """
        warnings = []

        # 1. 基础检查
        if not script_code or not script_code.strip():
            return {
                "valid": False,
                "error": "Script code is empty",
                "warnings": [],
            }

        script_code = script_code.strip()

        # 2. 长度检查
        if len(script_code) > cls.MAX_SCRIPT_LENGTH:
            return {
                "valid": False,
                "error": f"Script too long ({len(script_code)} > {cls.MAX_SCRIPT_LENGTH})",
                "warnings": [],
            }

        # 3. 安全检查
        try:
            sandbox = cls()
            sandbox._security_check(script_code)
        except ValueError as e:
            return {
                "valid": False,
                "error": str(e),
                "warnings": [],
            }

        # 4. 语法检查
        try:
            compile(script_code, "<sandbox>", "exec")
        except SyntaxError as e:
            return {
                "valid": False,
                "error": f"Syntax error at line {e.lineno}: {e.msg}",
                "warnings": [],
            }

        # 5. 检查是否设置了 result 变量（建议）
        if "result" not in script_code:
            warnings.append(
                "Script does not set 'result' variable. "
                "Consider setting 'result = ...' to return a value."
            )

        return {
            "valid": True,
            "error": None,
            "warnings": warnings,
        }

    @classmethod
    def get_allowed_modules(cls) -> list[str]:
        """
        获取允许的模块列表。

        Returns:
            允许的模块名称列表
        """
        return sorted(_ALLOWED_MODULES)

    @classmethod
    def get_allowed_builtins(cls) -> list[str]:
        """
        获取允许的内置函数列表。

        Returns:
            允许的内置函数名称列表
        """
        return sorted(_SAFE_BUILTINS.keys())


# ──────────── 便捷函数 ────────────

async def execute_script(
    script_code: str,
    context: dict[str, Any] | None = None,
    timeout: float | None = None,
    memory_limit_mb: int | None = None,
) -> dict[str, Any]:
    """
    便捷函数: 执行脚本并返回结果。

    Args:
        script_code: 脚本代码
        context: 上下文变量
        timeout: 超时时间（秒）
        memory_limit_mb: 内存限制（MB）

    Returns:
        执行结果字典
    """
    sandbox = ScriptSandbox(timeout=timeout, memory_limit_mb=memory_limit_mb)
    return await sandbox.execute_async(script_code, context)


def validate_script(script_code: str) -> dict[str, Any]:
    """
    便捷函数: 验证脚本语法和安全性。

    Args:
        script_code: 脚本代码

    Returns:
        验证结果字典
    """
    return ScriptSandbox.validate(script_code)

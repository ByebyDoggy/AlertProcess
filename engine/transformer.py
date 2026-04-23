"""
输入转换器引擎 — Edge 级别的数据变换表达式求值器。

支持两种语言模式:
  - python: 受限 eval() 执行 Python 表达式，返回变换后的数据对象
  - javascript: 轻量 JS→Python 语法翻译 + 受限 eval()

安全性:
  - 禁止 import/__import__
  - 禁止访问危险内置函数 (open, exec, eval, compile 等)
  - 仅暴露 json/math/datetime 工具模块
  - 表达式超时保护 (默认 5s)

用法:
  >>> result = InputTransformer.evaluate(
  ...     expression='{"address": input["from_address"], "val": int(input["value"])}',
  ...     language="python",
  ...     input_data={"from_address": "0xabc", "value": "100"}
  ... )
  >>> print(result)
  {"address": "0xabc", "val": 100}
"""

from __future__ import annotations

import logging
import re
import signal
from typing import Any

logger = logging.getLogger(__name__)

# ── 安全的内置白名单 ──
_SAFE_BUILTINS: dict[str, Any] = {
    # 类型
    "int": int,
    "float": float,
    "str": str,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    # 常量
    "True": True,
    "False": False,
    "None": None,
    # 函数
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
    "isinstance": isinstance,
    "type": type,
    "hasattr": hasattr,
    "getattr": getattr,
    "print": print,
    # 异常
    "Exception": Exception,
    "ValueError": ValueError,
    "KeyError": KeyError,
    "TypeError": TypeError,
    "IndexError": IndexError,
    "AttributeError": AttributeError,
}


def _build_safe_globals(input_data: dict[str, Any]) -> dict[str, Any]:
    """
    构建安全的执行环境 globals。

    注入:
      - input: 上游节点输出数据 (只读引用)
      - json: JSON 序列化/反序列化工具
      - math: 数学常量和函数
    """
    import json as _json_module
    import math as _math_module
    from datetime import datetime as _datetime_cls, timezone as _tz

    return {
        **_SAFE_BUILTINS.copy(),
        "__builtins__": _SAFE_BUILTINS,
        "input": input_data if isinstance(input_data, dict) else {},
        "json": _json_module,
        "math": _math_module,
        "datetime": _datetime_cls,
        "timezone": _tz,
    }


class TimeoutError(Exception):
    """表达式执行超时"""


def _timeout_handler(signum, frame):
    raise TimeoutError("Expression execution timed out (>5s)")


class InputTransformer:
    """
    输入转换器 — 在边(Edge)级别对上游数据进行自定义变换。

    用户可编写 JS 或 Python 表达式，将上游 output 数据转换为
    下游节点期望的输入结构。

    支持的语言:
      - python: 标准 Python 字典/对象表达式
      - javascript: 自动翻译为 Python 后执行 (支持箭头函数、=== 等)
    """

    MAX_EXPRESSION_LENGTH = 5000  # 表达式最大长度
    TIMEOUT_SECONDS = 5           # 执行超时(秒)

    @classmethod
    def evaluate(
        cls,
        expression: str,
        language: str = "python",
        input_data: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        """
        执行输入转换表达式并返回结果。

        Args:
            expression: 用户编写的变换表达式
            language: "python" 或 "javascript"
            input_data: 上游节点的输出数据 (作为 'input' 变量注入)
            timeout: 自定义超时(秒)，默认 TIMEOUT_SECONDS

        Returns:
            变换后的数据字典

        Raises:
            ValueError: 表达式语法错误或安全校验失败
            TimeoutError: 执行超时
            Exception: 表达式运行时错误
        """
        if not expression or not expression.strip():
            return {}

        expr = expression.strip()
        timeout = timeout or cls.TIMEOUT_SECONDS

        # 安全检查：禁止危险关键字
        cls._security_check(expr)

        # 长度限制
        if len(expr) > cls.MAX_EXPRESSION_LENGTH:
            raise ValueError(f"Expression too long ({len(expr)} > {cls.MAX_EXPRESSION_LENGTH})")

        # JS → Python 语法翻译
        if language == "javascript":
            expr = cls._translate_js_to_python(expr)

        # 构建 safe globals
        safe_globals = _build_safe_globals(input_data or {})

        # 超时保护 (Unix only; Windows 不支持 SIGALRM)
        try:
            old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
            signal.alarm(int(timeout))
            has_alarm = True
        except (OSError, AttributeError):
            has_alarm = False

        try:
            # 执行表达式
            result = eval(expr, safe_globals, {})

            # 确保返回字典类型
            if result is None:
                return {}
            if isinstance(result, dict):
                return dict(result)
            # 如果返回非字典，包装为 value 字段
            return {"__result__": result}

        except TimeoutError:
            raise
        except SyntaxError as e:
            raise ValueError(f"Expression syntax error: {e}") from e
        except Exception as e:
            logger.warning("[InputTransformer] eval failed: %s", e)
            raise ValueError(f"Execution error: {e}") from e
        finally:
            if has_alarm:
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

    # ──────────── 安全检查 ────────────

    _FORBIDDEN_PATTERNS = [
        r'\bimport\b',
        r'\b__import__\b',
        r'\bexec\b',
        r'\beval\b',
        r'\bcompile\b',
        r'\bopen\s*\(',
        r'\bfile\s*\(',
        r'__class__',
        r'__subclasses__',
        r'__mro__',
        r'__bases__',
        r'__globals__',
        r'__getattribute__',
        r'__dict__',
        r'\bos\b\.',
        r'\bsys\b\.',
        r'\bsubprocess\b',
        r'\bpopen\b',
    ]

    @classmethod
    def _security_check(cls, expression: str) -> None:
        """检查表达式是否包含危险操作。"""
        lowered = expression.lower()
        for pattern in cls._FORBIDDEN_PATTERNS:
            if re.search(pattern, lowered, re.IGNORECASE):
                raise ValueError(
                    f"Forbidden pattern detected in expression: '{pattern}'. "
                    f"Only data transformation expressions are allowed."
                )

    # ──────────── JS → Python 翻译 ────────────

    @classmethod
    def _translate_js_to_python(cls, js_expr: str) -> str:
        """
        将 JavaScript 表达式子集翻译为 Python 可执行的等价形式。
        """
        py = js_expr

        # 1. 移除单行注释 //
        py = re.sub(r'^\s*//.*$', '', py, flags=re.MULTILINE)

        # 2. 处理模板字符串 `${...}` → f-string
        def _replace_template_literal(m):
            content = m.group(1)
            content_py = re.sub(r'\$\{([^}]+)\}', r'{\1}', content)
            return f'f"{content_py}"'

        py = re.sub(r'`([^`]*)`', _replace_template_literal, py)

        # 3. return 语句包裹 → 移除 return，保留表达式
        py = re.sub(r'\breturn\s+', '', py)

        # 4. console.log(...) → pass (移除调试语句)
        py = re.sub(r'console\.(log|warn|info|error|debug)\s*\([^)]*\)\s*;?', '', py)

        # 5. 常量替换 (在对象键处理之前)
        py = re.sub(r':\s*null\b', ': None', py)
        py = re.sub(r':\s*undefined\b', ': None', py)
        py = re.sub(r'\bnull\b', 'None', py)
        py = re.sub(r'\bundefined\b', 'None', py)
        py = re.sub(r':\s*true\b', ': True', py)
        py = re.sub(r':\s*false\b', ': False', py)
        py = re.sub(r'\btrue\b', 'True', py)
        py = re.sub(r'\bfalse\b', 'False', py)

        # 6. 对象字面量键加引号 {key: val} → {"key": val}
        # 匹配不在引号内的标识符后跟冒号
        def _quote_keys(m):
            key = m.group(0).rstrip(':').strip()
            # 跳过已加引号的键或数字键
            if (key.startswith('"') or key.startswith("'") or
                    key.replace('.', '').replace('-', '').isdigit()):
                return m.group(0)
            return f'"{key}":'

        # 在花括号内的上下文处理键
        py = re.sub(r'(?<!["\'\w])\s*([a-zA-Z_]\w*)\s*:', _quote_keys, py)

        # 7. 类型转换函数
        py = re.sub(r'\bNumber\s*\(', 'float(', py)
        py = re.sub(r'\bparseInt\s*\(', 'int(', py)
        py = re.sub(r'\bparseFloat\s*\(', 'float(', py)
        py = re.sub(r'\bString\s*\(', 'str(', py)
        py = re.sub(r'\bBoolean\s*\(', 'bool(', py)

        # 8. JSON 方法
        py = re.sub(r'JSON\.stringify', 'json.dumps', py)
        py = re.sub(r'JSON\.parse', 'json.loads', py)

        # 9. Math.* → math.*
        py = re.sub(r'\bMath\.PI\b', 'math.pi', py)
        py = re.sub(r'\bMath\.E\b', 'math.e', py)
        py = re.sub(r'\bMath\.round\s*\(', 'round(', py)
        py = re.sub(r'\bMath\.floor\s*\(', 'int(math.floor(', py)
        py = re.sub(r'\bMath\.ceil\s*\(', 'int(math.ceil(', py)
        py = re.sub(r'\bMath\.abs\s*\(', 'abs(', py)
        py = re.sub(r'\bMath\.max\s*\(', 'max(', py)
        py = re.sub(r'\bMath\.min\s*\(', 'min(', py)
        py = re.sub(r'\bMath\.pow\s*\(', 'pow(', py)
        py = re.sub(r'\bMath\.sqrt\s*\(', 'math.sqrt(', py)
        py = re.sub(r'\bMath\.\w+\(', lambda m: 'math.' + m.group(0)[5:], py)
        py = re.sub(r'\bMath\.\w+(?!\()\b', lambda m: 'math.' + m.group(0)[5:], py)

        # 10. .length → len()
        py = re.sub(r'(\w+)\.length\b', r'len(\1)', py)

        # 11. .push() → .append()
        py = re.sub(r'\.push\s*\(', '.append(', py)

        # 12. .includes(val) → val in obj
        py = re.sub(
            r'([\w\].]+?)\.includes\s*\(([^)]+)\)',
            r'\2 in \1',
            py,
        )

        # 13. .indexOf(x) >= 0 → x in obj
        py = re.sub(
            r'([\w\].]+?)\.indexOf\s*\(([^)]+)\)\s*>=\s*0',
            r'\2 in \1',
            py,
        )

        # 14. 三元运算符 cond ? true_val : false_val  →  true_val if cond else false_val
        # 迭代替换直到没有更多三元运算符
        max_iter = 10
        for _ in range(max_iter):
            prev = py
            # 优先匹配括号包围的条件: (cond) ? val1 : val2
            # val1/val2 可以是对象字面量、数组字面量或简单表达式
            py = re.sub(
                r'\(([^()?]+?)\)\s*\?\s*(\{[^}]*\}|\[[^\]]*\]|[^,:{}]+?)\s*:\s*(\{[^}]*\}|\[[^\]]*\]|[^,}]+)',
                r'(\2 if \1 else \3)',
                py,
            )
            if py != prev:
                continue
            # 其次匹配无括号的条件: cond ? val1 : val2
            # 条件部分匹配到 ? 前的标识符/下标/比较表达式
            py = re.sub(
                r'([\w\]["\'.\s><=!]+?)\s*\?\s*(\{[^}]*\}|\[[^\]]*\]|[^,:{}]+?)\s*:\s*(\{[^}]*\}|\[[^\]]*\]|[^,}]+)',
                r'(\2 if \1 else \3)',
                py,
            )
            if py == prev:
                break

        # 15. 逻辑运算符
        py = re.sub(r'&&', ' and ', py)
        py = re.sub(r'\|\|', ' or ', py)

        # 16. !== 和 ===
        py = re.sub(r'!==', '!=', py)
        py = re.sub(r'===', '==', py)

        # 17. !expression (非赋值场景的 !) → not expression
        # 排除 != 的情况
        py = re.sub(r'!(?!=)(?=\s*\w)', ' not ', py)
        py = re.sub(r'!(?!=)\s*(\()', ' not \\1', py)

        # 18. typeof x → type(x).__name__
        py = re.sub(r'\btypeof\s+(\w+)', r'type(\1).__name__', py)

        # 19. 清理多余空格
        py = py.strip()
        if not py:
            py = '{}'

        # 20. 点号属性访问 → 字典下标 (核心修复)
        #    input.val / data.address 等 JS 风格的 dict 属性访问
        #    转换为 input["val"] / data["address"]
        py = cls._convert_dot_access_to_subscript(py)

        return py

    @classmethod
    def _convert_dot_access_to_subscript(cls, expr: str) -> str:
        """
        将 JS 风格的点号属性访问转换为 Python 字典下标。

        规则：
          - obj.property → obj["property"]  (property 是小写标识符)
          - 保留：obj.method(  (方法调用)
          - 保留：已知模块引用 math.*, json.*
          - 保留：数字字面量 .0, .5
          - 处理链式: a.b.c.d → a["b"]["c"]["d"]

        注意: 此步骤在其他所有翻译之后执行。
        """

        # 已知的模块/对象名，其点号访问应保留（方法调用）
        _KNOWN_MODULES = {'math', 'json', 'datetime', 'timezone', 're', 'os', 'sys'}

        def _should_convert(match):
            full = match.group(0)
            obj_name = match.group(1)
            prop_name = match.group(2)

            # 1. 数字字面量 .0 .5 等 — 保留
            if re.match(r'^\d+$', prop_name) or prop_name[0].isdigit():
                return False

            # 2. 已知模块引用 — 保留
            if obj_name in _KNOWN_MODULES:
                return False

            # 3. 方法调用 (后跟括号) — 保留
            # 检查匹配之后是否有 (
            end_pos = match.end()
            rest = expr[end_pos:end_pos + 10].lstrip()
            if rest.startswith('('):
                return False

            # 4. 属性名是大写开头（可能是类常量）— 保守保留
            if prop_name[0].isupper():
                # 但 PI/E 这种数学常量还是要转换... 实际上这些已经被上面的规则处理了
                pass  # 允许转换

            return True

        # 迭代处理链式点号访问
        # 匹配模式: 标识符.标识符 (不跟括号的)
        max_iter = 20
        for _ in range(max_iter):
            new_expr = re.sub(
                r'(\w+)\.([a-zA-Z_]\w*)(?!\s*\()',
                lambda m: f'{m.group(1)}["{m.group(2)}"]'
                if _should_convert(m)
                else m.group(0),
                expr,
            )
            if new_expr == expr:
                break
            expr = new_expr

        return expr

    # ──────────── 辅助方法 ────────────

    @classmethod
    def preview(cls, expression: str, language: str = "python",
                sample_input: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        预览模式: 使用示例输入执行表达式并返回结果。
        用于前端实时预览变换效果。

        出错时返回 error 字段而非抛出异常。
        """
        try:
            result = cls.evaluate(expression, language, sample_input)
            return {"success": True, "output": result, "error": None}
        except Exception as e:
            return {"success": False, "output": None, "error": str(e)}

    @classmethod
    def validate(cls, expression: str, language: str = "python") -> dict[str, Any]:
        """
        校验表达式语法但不执行。
        返回 {valid: bool, error: str | None}
        """
        if not expression or not expression.strip():
            return {"valid": True, "error": None}

        try:
            cls._security_check(expression.strip())
            expr = expression.strip()

            if language == "javascript":
                expr = cls._translate_js_to_python(expr)

            # 仅编译不执行
            compile(expr, "<transformer>", "eval")
            return {"valid": True, "error": None}
        except SyntaxError as e:
            return {"valid": False, "error": f"Syntax error: {e}"}
        except ValueError as e:
            return {"valid": False, "error": str(e)}
        except Exception as e:
            return {"valid": False, "error": f"Validation error: {e}"}

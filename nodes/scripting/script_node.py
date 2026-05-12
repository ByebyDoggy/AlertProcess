"""Python 表达式节点 — 用脚本替代逻辑/比较/评分节点

统一的脚本节点，用户编写 Python 代码直接访问上游输入和上下文，
返回判定结果和评分。替代 AND/OR Gate、阈值/区间/正则比较器、
平均/加权/最大评分器等所有逻辑/比较/评分节点。

注入变量:
  - inputs:           上游 NodeOutput 列表
  - scores:           上游 score 列表 [float, ...]
  - passed:           上游 passed 列表 [bool, ...]
  - labels:           上游 labels 列表 [str, ...]
  - ctx:              合并后的上下文字典（可读写，修改后传递给下游）
  - primary_scores:   仅检测结果端口的分数
  - correlation_ctx:  仅关联数据端口的 context

输出变量（脚本中设置）:
  - result:     布尔判定结果（默认 True）
  - score:      0-100 评分（默认 100 if result else 0）
  - labels:     标签列表（默认 []）
  - ctx_output: 显式自定义上下文字典（可选，传递给下游 Memory 节点）

输出端口:
  - true:   result=True 时走此端口
  - false:  result=False 时走此端口
  - output: 评分输出端口（score_output）

配置:
  - script: Python 代码
  - timeout: 执行超时（秒，默认 5）

上下文传递机制:
  脚本中对 ctx 字典的修改会被自动检测并传递到下游节点的
  context 中。用户可通过 ctx["key"] = value 写入任意自定义字段，
  下游的 Memory 节点会接收这些字段并存入全局记忆。
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field, ConfigDict

from nodes.base import BaseNode, NodeCategory, NodeOutput, PortDef, NodeRegistry
from engine.script_context import ScriptContext
from engine.script_sandbox import ScriptSandbox

logger = logging.getLogger(__name__)


class ScriptConfigModel(BaseModel):
    """ScriptNode 配置模型"""
    script: str = Field(
        default='# Python 表达式节点\n# ════════════════════════════════════════\n# 输入变量（只读）：\n#   passed/scores/labels  所有上游输入的聚合列表\n#   ctx                  合并后的上下文字典\n#   primary_scores[0]    仅【检测结果】端口的分数\n#   correlation_ctx       仅【关联数据】端口的上下文\n#\n# 输出变量（脚本中设置）：\n#   result = True/False   控制走"满足"/"不满足"端口\n#   score = 0-100         评分（可选）\n#   labels = ["TAG"]      标签列表（可选）\n#\n# ★ 上下文传递（写入 ctx 会传递给下游 Memory 节点）：\n#   ctx["risk_reason"] = "gas_anomaly"     ← 写入自定义字段\n#   ctx["detected_amount"] = 1000000        ← 下游可读取\n#   # 或用显式输出变量：\n#   ctx_output = {"my_key": "my_value"}      ← 同样传递给下游\n# ════════════════════════════════════════\n\n# ── 示例 1：AND 逻辑 ──\nresult = all(passed)\n\n# ── 示例 2：阈值比较 + 自定义上下文 ──\n# result = scores[0] >= 50\n# if result:\n#     ctx["risk_level"] = "high"\n#     score = 85\n#     labels = ["HIGH_SCORE_RISK"]\n\n# ── 示例 3：结合关联数据，写入记忆 ──\n# if ctx.get("upgraded_contracts"):\n#     result = any(passed)\n#     score = 80\n#     labels = ["UPGRADE_CORRELATED"]\n#     ctx["correlation_source"] = "proxy_upgrade_detected"\n',
        description="Python 脚本代码",
        json_schema_extra={"x-editor": "python"},
    )
    timeout: float = Field(
        default=5.0,
        ge=0.1,
        le=30.0,
        description="执行超时（秒）",
    )


class ScriptNode(BaseNode):
    """
    Python 表达式节点 — 用脚本替代逻辑/比较/评分节点。

    用户编写 Python 代码，直接访问上游输入数据和上下文，
    通过设置 result / score / labels 变量输出判定结果。

    替代: AND/OR Gate, Threshold/Range/Regex Comparator,
          Average/Weighted/MinMax/Constant Scorer
    """

    name: str = "script_node"
    label: str = "Python 表达式"
    description: str = (
        "用 Python 脚本替代逻辑/比较/评分节点。"
        "可用变量: inputs(上游输出列表), scores(分数列表), passed(布尔列表), "
        "labels(标签列表), ctx(合并上下文)。"
        "设置 result(布尔)、score(0-100)、labels(列表) 作为输出。"
    )
    icon: str = "\U0001f40d"
    color: str = "#22c55e"

    category: NodeCategory = NodeCategory.SCRIPTING

    # ── Pydantic 配置模型 ──
    ConfigModel: type = ScriptConfigModel

    @classmethod
    def get_inputs(cls) -> list[PortDef]:
        return [
            PortDef(
                key="primary",
                label="检测结果",
                data_type="detection_output",
                required=True,
                description="上游检测器/节点输出，包含 score、passed、labels、context",
            ),
            PortDef(
                key="correlation",
                label="关联数据（可选）",
                data_type="detection_output",
                required=False,
                description="关联上下文（如 Memory 节点的输出），脚本中通过 ctx 访问",
            ),
        ]

    @classmethod
    def get_outputs(cls) -> list[PortDef]:
        return [
            PortDef(key="true", label="满足", data_type="logic_output"),
            PortDef(key="false", label="不满足", data_type="logic_output"),
            PortDef(key="output", label="评分输出", data_type="score_output"),
        ]

    async def execute(
        self,
        context: dict[str, Any],
        inputs: dict[str, list[NodeOutput]],
    ) -> NodeOutput:
        # ── 收集上游输入（按端口分离） ──
        primary_outputs: list[NodeOutput] = []
        correlation_outputs: list[NodeOutput] = []

        for port_key in (inputs or {}).keys():
            for inp in inputs[port_key]:
                if port_key == "primary":
                    primary_outputs.append(inp)
                elif port_key == "correlation":
                    correlation_outputs.append(inp)
                else:
                    # 兼容旧端口命名
                    primary_outputs.append(inp)

        # 所有输入的聚合（用于 all(passed) 等操作）
        all_outputs = primary_outputs + correlation_outputs
        scores = [o.score for o in all_outputs]
        passed_list = [o.passed for o in all_outputs]
        all_labels = [lbl for o in all_outputs for lbl in (o.labels or [])]

        # 合并上下文：主数据 → 关联数据 → 全局上下文（后者覆盖前者）
        merged_ctx: dict[str, Any] = dict(context)
        for o in primary_outputs:
            if o.context:
                merged_ctx.update(o.context)
        for o in correlation_outputs:
            if o.context:
                merged_ctx.update(o.context)

        # ── 构建注入变量 ──
        primary_scores = [o.score for o in primary_outputs]
        primary_passed = [o.passed for o in primary_outputs]
        correlation_ctx: dict[str, Any] = {}
        for o in correlation_outputs:
            if o.context:
                correlation_ctx.update(o.context)

        script_context = ScriptContext(merged_ctx, inputs)
        variables: dict[str, Any] = {
            "context": script_context,
            "script_context": script_context,
            "tx": script_context.tx_context,
            # 全部输入
            "inputs": all_outputs,
            "scores": scores,
            "passed": passed_list,
            "labels": all_labels,
            "ctx": merged_ctx,
            # 仅主输入（检测结果端口）
            "primary_scores": primary_scores,
            "primary_passed": primary_passed,
            "ps": primary_scores,  # 别名
            "pp": primary_passed,  # 别名
            # 仅关联数据（关联数据端口）
            "correlation_ctx": correlation_ctx,
            "cc": correlation_ctx,  # 别名
            # 便捷别名
            "s": scores,
            "p": passed_list,
            "c": merged_ctx,
        }

        # ── 执行脚本 ──
        script = self.config.get("script", "")
        timeout = self.config.get("timeout", 5.0)

        if not script.strip():
            return NodeOutput(
                node_id=self.node_id,
                node_type=self.category.value,
                score=0.0,
                passed=False,
                context={"error": "脚本为空"},
            )

        try:
            sandbox = ScriptSandbox(timeout=timeout)
            execution_result = await sandbox.execute_async(script, variables, return_namespace=True)
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"[ScriptNode] Execution failed: {error_msg}")
            return NodeOutput(
                node_id=self.node_id,
                node_type=self.category.value,
                score=0.0,
                passed=False,
                context={"error": error_msg, "script": script},
            )

        if not execution_result.get("success"):
            exec_error = execution_result.get("error") or "脚本执行失败"
            logger.warning(f"[ScriptNode] Execution error: {exec_error}")
            return NodeOutput(
                node_id=self.node_id,
                node_type=self.category.value,
                score=0.0,
                passed=False,
                context={"error": exec_error, "script": script},
            )

        script_result = execution_result.get("result")
        if isinstance(script_result, dict) and isinstance(script_result.get("result"), dict):
            result_vars = script_result["result"]
        elif isinstance(script_result, dict) and any(
            key in script_result for key in ("score", "labels", "ctx_output", "passed")
        ):
            result_vars = script_result
        else:
            result_vars = script_result if isinstance(script_result, dict) else {"result": script_result}

        # ── 提取结果 ──
        result_bool = bool(result_vars.get("result", result_vars.get("passed", True)))
        result_score = float(result_vars.get("score", 100.0 if result_bool else 0.0))
        result_labels = result_vars.get("labels", [])
        if not isinstance(result_labels, list):
            result_labels = [str(result_labels)]

        # score 范围校验
        result_score = max(0.0, min(100.0, result_score))

        # stdout（调试用）
        stdout_text = result_vars.get("stdout", result_vars.get("_stdout", ""))
        if not stdout_text:
            stdout_text = str(execution_result.get("execution_time_ms", 0.0)) + "ms"

        # ── 提取脚本对 ctx 的自定义修改 ──
        script_ctx = result_vars.get("ctx")
        custom_ctx: dict[str, Any] = {}
        if isinstance(script_ctx, dict):
            # 找出用户在脚本中新增/修改的 ctx 字段
            original_ctx_keys = set(merged_ctx.keys())
            for k, v in script_ctx.items():
                if v != merged_ctx.get(k) or k not in original_ctx_keys:
                    custom_ctx[k] = v

        # 同时支持用户通过 ctx_output 变量直接输出自定义上下文
        explicit_ctx_output = result_vars.get("ctx_output")
        if isinstance(explicit_ctx_output, dict):
            custom_ctx.update(explicit_ctx_output)

        # ── 构建输出（含自定义上下文传递） ──
        from nodes.base import score_to_severity

        context_output: dict[str, Any] = {
            "script_result": result_bool,
            "script_score": result_score,
            "input_scores": scores,
            "input_passed": passed_list,
            "stdout": stdout_text,
        }
        # 将自定义上下文字段注入输出，供下游 Memory 等节点使用
        if custom_ctx:
            context_output["_custom_context"] = custom_ctx
            context_output.update(custom_ctx)  # 扁平化：直接合并到顶层

        return NodeOutput(
            node_id=self.node_id,
            node_type=self.category.value,
            score=result_score,
            passed=result_bool,
            context=context_output,
            labels=result_labels,
            severity=score_to_severity(result_score),
        )


NodeRegistry.register(ScriptNode)

from __future__ import annotations

import json
from typing import Any


def build_rule_chain_messages(
    prompt: str,
    schema_bundle: dict[str, Any],
    current_chain: dict[str, Any] | None,
    constraints: dict[str, Any],
    mode: str,
) -> list[dict[str, str]]:
    system_prompt = """
你是 AlertProcessor 的规则链生成器。你必须只输出一个 JSON object，不能输出 Markdown 或解释文本。
你只能使用给定 schema 中存在的节点 type、输入端口和输出端口。
边必须使用 sourcePort 和 targetPort，且端口 key 必须真实存在。
生成的规则链必须是有向无环图，并且应该从 input 类节点开始。
不要编造节点、字段、接口或端口。
默认不要使用脚本节点，除非约束中显式允许。
返回 JSON 字段必须包含：name、description、nodes、edges、explanation、assumptions。
每个 node 必须包含 id、type、label、config、position。
每个 edge 必须包含 id、source、sourcePort、target、targetPort。
""".strip()
    user_payload = {
        "user_request": prompt,
        "mode": mode,
        "current_chain": current_chain or {"nodes": [], "edges": []},
        "constraints": constraints,
        "rule_chain_schema": schema_bundle,
        "output_example": {
            "name": "规则链名称",
            "description": "规则链用途",
            "nodes": [
                {
                    "id": "trigger_1",
                    "type": "alert_trigger",
                    "label": "告警触发器",
                    "config": {},
                    "position": {"x": 80, "y": 120},
                }
            ],
            "edges": [],
            "explanation": "为什么这样生成",
            "assumptions": ["使用默认阈值"],
        },
    }
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]

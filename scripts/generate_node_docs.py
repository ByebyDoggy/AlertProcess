#!/usr/bin/env python3
"""
节点文档自动生成脚本

从 NodeRegistry 读取所有已注册节点的 Pydantic 模型信息，
自动生成 Markdown 文档到 docs/node-reference/ 目录。

用法:
    python scripts/generate_node_docs.py

后续新增节点时重新运行即可自动更新文档。
"""

import os
import sys
from pathlib import Path

# 确保项目根目录在 sys.path 中
project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


CATEGORY_LABELS = {
    "input": "输入",
    "provider": "上下文查询",
    "detection": "安全检测",
    "comparison": "比较",
    "scoring": "评分",
    "logic": "逻辑",
    "action": "动作",
    "memory": "记忆",
    "scripting": "脚本",
    "storage": "存储",
}

CATEGORY_ORDER = ["input", "provider", "detection", "comparison", "scoring", "logic", "action", "memory", "scripting", "storage"]


def format_default(val):
    if val is None:
        return "-"
    if isinstance(val, bool):
        return str(val)
    if isinstance(val, (dict, list)):
        import json
        return f"`{json.dumps(val, ensure_ascii=False)}`"
    return f"`{val}`"


def format_constraints(prop: dict) -> str:
    parts = []
    if "minimum" in prop:
        parts.append(f"min: {prop['minimum']}")
    if "maximum" in prop:
        parts.append(f"max: {prop['maximum']}")
    if "enum" in prop:
        parts.append(f"enum: [{', '.join(str(v) for v in prop['enum'])}]")
    return ", ".join(parts) if parts else "-"


def schema_to_md_table(schema: dict, indent: int = 0) -> str:
    """将 Pydantic JSON Schema 转换为 Markdown 表格"""
    if not schema or "properties" not in schema:
        return ""
    props = schema["properties"]
    required = schema.get("required", [])
    lines = []
    prefix = "  " * indent
    lines.append(f"{prefix}| 字段 | 类型 | 必填 | 说明 | 默认值 |")
    lines.append(f"{prefix}|------|------|------|------|--------|")
    for key, val in props.items():
        req = "&#10003;" if key in required else "-"
        desc = val.get("description", "-")
        default = format_default(val.get("default"))
        type_str = val.get("type", "any")
        lines.append(f"{prefix}| `{key}` | {type_str} | {req} | {desc} | {default} |")
    return "\n".join(lines)


def generate_node_doc(node: dict) -> str:
    """生成单个节点的 Markdown 文档"""
    lines = []
    lines.append(f"# {node['label']}")
    lines.append("")
    lines.append(f"- **节点名称**: `{node['name']}`")
    lines.append(f"- **分类**: {node['category_label']} (`{node['category']}`)")
    lines.append(f"- **基类**: `{node['base_class']}`")
    lines.append(f"- **模块**: `{node['module']}`")
    lines.append("")

    # Description
    if node.get("description"):
        lines.append("## 描述")
        lines.append("")
        lines.append(node["description"])
        lines.append("")

    # Required providers
    if node.get("required_providers"):
        lines.append("## 上下文依赖")
        lines.append("")
        lines.append("此节点需要上游连接对应的 Provider 节点来注入上下文数据：")
        lines.append("")
        for p in node["required_providers"]:
            lines.append(f"- `{p}`")
        lines.append("")

    # Provides
    if node.get("provides"):
        lines.append("## 数据注入")
        lines.append("")
        lines.append("此节点向上下文 extra 中注入以下字段，供下游节点使用：")
        lines.append("")
        for p in node["provides"]:
            lines.append(f"- `{p}`")
        lines.append("")

    # Input ports
    if node.get("inputs"):
        lines.append("## 输入端口")
        lines.append("")
        lines.append("| Key | 标签 | 数据类型 | 必填 | 多输入 | 说明 |")
        lines.append("|-----|------|---------|------|--------|------|")
        for port in node["inputs"]:
            req = "&#10003;" if port.get("required") else "-"
            multi = "&#10003;" if port.get("multi") else "-"
            lines.append(
                f"| `{port['key']}` | {port['label']} | `{port['data_type']}` | {req} | {multi} | {port.get('description', '-')} |"
            )
        lines.append("")

        # Input schemas
        for i, schema in enumerate(node.get("input_schemas", [])):
            port_label = node["inputs"][i]["label"] if i < len(node["inputs"]) else f"端口 {i}"
            if schema and schema.get("properties"):
                lines.append(f"### {port_label} 输入模型字段")
                lines.append("")
                lines.append(schema_to_md_table(schema))
                lines.append("")

    # Output ports
    if node.get("outputs"):
        lines.append("## 输出端口")
        lines.append("")
        lines.append("| Key | 标签 | 数据类型 | 说明 |")
        lines.append("|-----|------|---------|------|")
        for port in node["outputs"]:
            lines.append(
                f"| `{port['key']}` | {port['label']} | `{port['data_type']}` | {port.get('description', '-')} |"
            )
        lines.append("")

        # Output schemas
        for i, schema in enumerate(node.get("output_schemas", [])):
            port_label = node["outputs"][i]["label"] if i < len(node["outputs"]) else f"端口 {i}"
            if schema and schema.get("properties"):
                lines.append(f"### {port_label} 输出模型字段")
                lines.append("")
                lines.append(schema_to_md_table(schema))
                lines.append("")

    # Config
    config_props = node.get("config_schema", {}).get("properties", {})
    if config_props:
        lines.append("## 配置参数")
        lines.append("")
        lines.append("| 字段 | 类型 | 默认值 | 约束 | 说明 |")
        lines.append("|------|------|--------|------|------|")
        for key, prop in config_props.items():
            default = format_default(prop.get("default"))
            constraints = format_constraints(prop)
            desc = prop.get("description", "-")
            type_str = prop.get("type", "string")
            lines.append(f"| `{key}` | {type_str} | {default} | {constraints} | {desc} |")
        lines.append("")

    return "\n".join(lines)


def generate_index(docs: list[dict]) -> str:
    """生成索引 README.md"""
    lines = []
    lines.append("# 节点参考文档")
    lines.append("")
    lines.append("> 本文档由 `scripts/generate_node_docs.py` 从 Pydantic 模型自动生成，新增节点后重新运行脚本即可更新。")
    lines.append("")

    # Group by category
    groups = {}
    for d in docs:
        cat = d["category"]
        if cat not in groups:
            groups[cat] = []
        groups[cat].append(d)

    for cat in CATEGORY_ORDER:
        if cat not in groups:
            continue
        cat_label = CATEGORY_LABELS.get(cat, cat)
        lines.append(f"## {cat_label}")
        lines.append("")
        lines.append("| 节点 | 名称 | 描述 |")
        lines.append("|------|------|------|")
        for d in groups[cat]:
            desc = (d.get("description") or "-")[:60]
            lines.append(f"| [{d['label']}](./{d['name']}.md) | `{d['name']}` | {desc} |")
        lines.append("")

    # Other categories
    for cat, nodes in groups.items():
        if cat in CATEGORY_ORDER:
            continue
        cat_label = CATEGORY_LABELS.get(cat, cat)
        lines.append(f"## {cat_label}")
        lines.append("")
        for d in nodes:
            lines.append(f"- [{d['label']}](./{d['name']}.md) — {d.get('description', '-')}")
        lines.append("")

    return "\n".join(lines)


def main():
    # Initialize registry
    from nodes import init_registry
    from nodes.base import NodeRegistry
    init_registry()

    docs = NodeRegistry.get_docs_for_frontend()
    print(f"Loaded {len(docs)} nodes from NodeRegistry")

    # Output directory
    out_dir = project_root / "docs" / "node-reference"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Generate per-node docs
    for d in docs:
        md = generate_node_doc(d)
        out_path = out_dir / f"{d['name']}.md"
        out_path.write_text(md, encoding="utf-8")
        print(f"  Generated: {d['name']}.md")

    # Generate index
    index_md = generate_index(docs)
    (out_dir / "README.md").write_text(index_md, encoding="utf-8")
    print(f"  Generated: README.md (index)")

    print(f"\nDone! {len(docs)} node docs generated in {out_dir}")


if __name__ == "__main__":
    main()

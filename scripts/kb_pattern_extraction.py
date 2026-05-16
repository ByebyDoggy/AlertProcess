"""
KB 元数据模式提取脚本

对每个缺口类别，从 alert_data JSON 中提取 root_cause、project、chain_id 等字段，
按项目/链分布分组，选出代表性样本 tx_hash，供后续验证使用。
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "alerts.db"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_DIR.mkdir(exist_ok=True)

# Chain ID → Name
CHAIN_NAMES: dict[int, str] = {
    1: "Ethereum",
    56: "BNB Chain",
    42161: "Arbitrum",
    8453: "Base",
    10: "Optimism",
    137: "Polygon",
    43114: "Avalanche",
    59144: "Linea",
    146: "Sonic",
    80094: "Berachain",
}

# 缺口类别（gap=2 的）
GAP_CATEGORIES = {
    "unverified_input", "governance_attack", "storage_collision",
    "misconfiguration", "untrusted_input",
}

# 部分类别（gap=1 的，选取部分验证）
PARTIAL_CATEGORIES = {
    "private_key_compromise", "business_logic", "access_control",
    "precision_loss", "arbitrary_call",
}

SELECT_CATEGORIES = GAP_CATEGORIES | PARTIAL_CATEGORIES


def extract_alert_data_field(alert_data_json: str, field: str):
    """从 alert_data JSON 中安全提取字段"""
    try:
        data = json.loads(alert_data_json) if isinstance(alert_data_json, str) else alert_data_json
        return data.get(field) if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def analyze_category(cursor, category: str, max_samples: int = 10) -> dict:
    cursor.execute(
        "SELECT id, alert_data, chain_id, tx_hash, expected_labels, "
        "exploiter_address FROM knowledge_base WHERE source='blocksec' AND category=?",
        (category,),
    )
    rows = cursor.fetchall()

    root_cause_dist = defaultdict(int)
    project_dist = defaultdict(int)
    chain_dist = defaultdict(int)
    loss_dist = []
    samples: list[dict] = []

    for row in rows:
        alert_data_str = row[1] or "{}"
        chain_id = row[2] or 1
        tx_hash = row[3] or ""
        labels_str = row[4] or ""
        exploiter = row[5] or ""

        data = json.loads(alert_data_str) if isinstance(alert_data_str, str) else {}
        root_cause = data.get("root_cause") or data.get("rootCause") or "unknown"
        project = data.get("project") or "unknown"
        loss_usd = data.get("loss_usd") or data.get("loss") or 0

        root_cause_dist[root_cause] += 1
        project_dist[project] += 1
        chain_dist[chain_id] += 1
        loss_dist.append(float(loss_usd) if loss_usd else 0.0)

        if len(samples) < max_samples:
            samples.append({
                "tx_hash": tx_hash,
                "chain_id": chain_id,
                "chain_name": CHAIN_NAMES.get(chain_id, f"chain_{chain_id}"),
                "project": project,
                "root_cause": root_cause,
                "loss_usd": loss_usd,
                "exploiter_address": exploiter,
                "labels": labels_str,
            })

    # 按 loss 排序采样：优先选高损失样本
    samples_sorted = sorted(samples, key=lambda x: x["loss_usd"] or 0, reverse=True)

    avg_loss = sum(loss_dist) / len(loss_dist) if loss_dist else 0
    max_loss = max(loss_dist) if loss_dist else 0

    return {
        "total_count": len(rows),
        "top_root_causes": dict(sorted(root_cause_dist.items(), key=lambda x: -x[1])[:10]),
        "top_projects": dict(sorted(project_dist.items(), key=lambda x: -x[1])[:10]),
        "chain_distribution": {str(k): v for k, v in sorted(chain_dist.items(), key=lambda x: -x[1])},
        "avg_loss_usd": round(avg_loss, 2),
        "max_loss_usd": round(max_loss, 2),
        "validation_samples": samples_sorted[:max_samples],
    }


def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 验证表结构
    cursor.execute("SELECT category FROM knowledge_base WHERE source='blocksec' LIMIT 1")
    print(f"Categories available: {GAP_CATEGORIES | PARTIAL_CATEGORIES}")

    results: dict[str, dict] = {}
    all_samples: dict[str, list] = {}

    for category in sorted(SELECT_CATEGORIES):
        print(f"\nAnalyzing: {category}...")
        result = analyze_category(cursor, category)
        results[category] = result
        all_samples[category] = result["validation_samples"]

        print(f"  Total: {result['total_count']}")
        print(f"  Avg loss: ${result['avg_loss_usd']:,.2f}")
        print(f"  Top projects: {list(result['top_projects'].keys())[:3]}")
        print(f"  Top root causes: {list(result['top_root_causes'].keys())[:3]}")
        print(f"  Chains: {list(result['chain_distribution'].keys())[:5]}")
        print(f"  Sample tx: {result['validation_samples'][0]['tx_hash'][:20]}... "
              f"(loss=${result['validation_samples'][0]['loss_usd']})" if result['validation_samples'] else "  No samples")

    conn.close()

    # 保存报告
    report_path = OUTPUT_DIR / "kb_pattern_report.json"
    report_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nPattern report saved to: {report_path}")

    # 保存验证样本
    samples_path = OUTPUT_DIR / "kb_validation_samples.json"
    samples_path.write_text(json.dumps(all_samples, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Validation samples saved to: {samples_path}")

    # 汇总
    total_samples = sum(len(v) for v in all_samples.values())
    print(f"\nTotal validation samples: {total_samples}")
    print("\nSample counts per category:")
    for cat, samples in all_samples.items():
        print(f"  {cat}: {len(samples)}")


if __name__ == "__main__":
    main()

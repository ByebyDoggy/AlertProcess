"""
KB 批量覆盖分析脚本

从 knowledge_base 表读取所有 source=blocksec 的行，按 category 分组，
映射到现有检测器，计算覆盖评分，输出覆盖矩阵和优先级排序。
"""

from __future__ import annotations

import json
import sqlite3
from collections import defaultdict
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "alerts.db"
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "data"
OUTPUT_DIR.mkdir(exist_ok=True)


# ── 检测器 → 能覆盖的 KB category 映射 ────────────────────────────────────────
# 基于对所有 19 个检测器源码的逐个分析得出
DETECTOR_COVERAGE: dict[str, list[str]] = {
    # fund_drain: 覆盖所有有资金净流出的类别
    "fund_drain": [
        "private_key_compromise", "business_logic", "price_manipulation",
        "access_control", "arbitrary_call", "security_incident",
        "misconfiguration", "slippage_issue", "accounting_error",
        "precision_loss", "unverified_input", "untrusted_input",
    ],
    # economic_anomaly: 覆盖有经济异常特征的类别
    "economic_anomaly": [
        "business_logic", "price_manipulation", "precision_loss",
        "unverified_input", "untrusted_input", "slippage_issue",
        "accounting_error", "flash_loan",
    ],
    # reentrancy / reentrancy_trace: 专门覆盖 reentrancy
    "reentrancy": ["reentrancy"],
    "reentrancy_trace": ["reentrancy"],
    # oracle_manipulation / price_manipulation: 覆盖价格操控
    "oracle_manipulation": ["price_manipulation"],
    "price_manipulation": ["price_manipulation", "slippage_issue"],
    # proxy_upgrade: 覆盖代理升级类 access_control
    "proxy_upgrade": ["access_control", "storage_collision"],
    # privileged_address: 覆盖私钥泄露类
    "privileged_address": ["private_key_compromise"],
    # strategy_drain: 覆盖策略类攻击
    "strategy_drain": ["business_logic", "access_control"],
    # flash_loan_trace: 覆盖闪电贷攻击
    "flash_loan_trace": ["flash_loan"],
    # indirection_layer: 覆盖有代理/间接调用层的攻击
    "indirection_layer": ["arbitrary_call", "business_logic", "access_control"],
    # token_approval: 覆盖授权类攻击（无 KB category 直接对应）
    # gas_price: 覆盖 gas 异常类
    # address_graph / address_age / arkm_label: 外部数据依赖，不直接映射
}


def detect_gap_severity(category: str) -> int:
    """gap 严重度：0=已覆盖, 1=部分覆盖, 2=缺口大"""
    fully_covered = {
        "reentrancy",      # reentrancy + reentrancy_trace 双覆盖
        "flash_loan",      # flash_loan_trace 专门覆盖
        "price_manipulation",  # oracle_manipulation + price_manipulation 双覆盖
    }
    partial = {
        "business_logic",
        "access_control",
        "private_key_compromise",
        "security_incident",
        "precision_loss",
        "arbitrary_call",
        "slippage_issue",
        "accounting_error",
    }
    if category in fully_covered:
        return 0
    if category in partial:
        return 1
    return 2  # 缺口大


def analyze_coverage():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 读所有 blocksec 行
    cursor.execute("""
        SELECT id, category, expected_labels, chain_id, tx_hash,
               exploiter_address, alert_data
        FROM knowledge_base
        WHERE source = 'blocksec'
        ORDER BY category
    """)
    rows = cursor.fetchall()
    conn.close()

    print(f"Total BlockSec events: {len(rows)}")

    # 按 category 分组
    by_category: dict[str, list] = defaultdict(list)
    for row in rows:
        cat = row[1] or "unknown"
        by_category[cat].append(row)

    # 覆盖矩阵
    categories = sorted(by_category.keys(), key=lambda c: len(by_category[c]), reverse=True)

    print("\n" + "=" * 80)
    print(f"{'Category':<30} {'Count':>6}  {'Gap':>3}  Detectors")
    print("-" * 80)

    priority_scores: list[dict] = []
    for cat in categories:
        count = len(by_category[cat])
        covering = [
            det for det, cats in DETECTOR_COVERAGE.items()
            if cat in cats
        ]
        gap = detect_gap_severity(cat)
        score = count * gap if gap > 0 else 0
        print(f"{cat:<30} {count:>6}  {gap:>3}  {', '.join(covering) if covering else 'NONE'}")
        priority_scores.append({
            "category": cat,
            "count": count,
            "gap": gap,
            "score": score,
            "covering_detectors": covering,
        })

    # 优先级排序（gap=2 优先，然后按 score）
    priority_scores.sort(key=lambda x: (-x["gap"], -x["score"]))

    print("\n" + "=" * 80)
    print("Priority ranking (gap=2 first, then score):")
    print("-" * 80)
    for i, p in enumerate(priority_scores, 1):
        tag = "[GAP]" if p["gap"] == 2 else ("[PARTIAL]" if p["gap"] == 1 else "[COVERED]")
        print(f"  {i:2d}. {tag} {p['category']:<30} count={p['count']:>4}  score={p['score']}")

    # 写 JSON 报告
    report = {
        "total_events": len(rows),
        "categories": {
            cat: {
                "count": len(by_category[cat]),
                "gap": detect_gap_severity(cat),
                "covering_detectors": [
                    det for det, cats in DETECTOR_COVERAGE.items()
                    if cat in cats
                ],
            }
            for cat in categories
        },
        "priority_ranking": priority_scores,
        "detector_coverage": DETECTOR_COVERAGE,
    }

    report_path = OUTPUT_DIR / "kb_coverage_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nReport saved to: {report_path}")

    return by_category, priority_scores


if __name__ == "__main__":
    analyze_coverage()

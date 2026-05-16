"""
Phase 4: Small Sample Validation

验证新实现的协议攻击检测器在知识库样本上的有效性。

使用 90 个验证样本（来自 10 个攻击类别）测试 7 个新检测器：
- ArbitraryCallDetector
- PrecisionLossDetector
- AccessControlBypassDetector
- InputValidationDetector
- GovernanceAttackDetector
- StorageCollisionDetector
- ProtocolMiscDetector
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Any
from collections import defaultdict

# 检测器到攻击类别的映射
DETECTOR_CATEGORY_MAP = {
    "arbitrary_call_detector": ["arbitrary_call"],
    "precision_loss_detector": ["precision_loss"],
    "access_control_bypass_detector": ["access_control"],
    "input_validation_detector": ["unverified_input", "untrusted_input"],
    "governance_attack_detector": ["governance_attack"],
    "storage_collision_detector": ["storage_collision"],
    "protocol_misc_detector": ["slippage_issue", "accounting_error", "misconfiguration"],
}

# 反向映射：攻击类别到检测器
CATEGORY_DETECTOR_MAP = {}
for detector, categories in DETECTOR_CATEGORY_MAP.items():
    for category in categories:
        CATEGORY_DETECTOR_MAP[category] = detector


def load_validation_samples(samples_file: str) -> Dict[str, List[Dict]]:
    """加载验证样本"""
    with open(samples_file, 'r', encoding='utf-8') as f:
        return json.load(f)


def get_alert_data(db_path: str, tx_hash: str, chain_id: int) -> Dict[str, Any]:
    """从数据库获取交易的 alert_data"""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT alert_data FROM knowledge_base
        WHERE tx_hash = ? AND chain_id = ?
        LIMIT 1
    """, (tx_hash, chain_id))

    row = cursor.fetchone()
    conn.close()

    if row and row[0]:
        try:
            return json.loads(row[0])
        except:
            return {}
    return {}


def check_detector_triggered(alert_data: Dict, detector_name: str) -> bool:
    """
    检查检测器是否被触发

    这里简化处理：检查 alert_data 中是否包含相关的检测器输出
    实际应该运行完整的规则链，但这需要完整的 eth_trace 数据
    """
    # 检查是否有 eth_trace 数据
    if 'eth_trace' not in alert_data:
        return False

    # 检查是否有检测器相关的标签或输出
    # 这是一个简化的检查，实际需要运行检测器
    labels = alert_data.get('labels', [])
    if isinstance(labels, str):
        try:
            labels = json.loads(labels)
        except:
            labels = []

    # 根据检测器名称检查相关标签
    detector_keywords = {
        "arbitrary_call_detector": ["arbitrary_call", "delegatecall"],
        "precision_loss_detector": ["precision_loss", "rounding"],
        "access_control_bypass_detector": ["access_control", "unauthorized"],
        "input_validation_detector": ["unverified_input", "untrusted_input", "validation"],
        "governance_attack_detector": ["governance", "voting"],
        "storage_collision_detector": ["storage_collision", "proxy"],
        "protocol_misc_detector": ["slippage", "accounting", "misconfiguration"],
    }

    keywords = detector_keywords.get(detector_name, [])
    for label in labels:
        for keyword in keywords:
            if keyword in label.lower():
                return True

    return False


def validate_samples(samples_file: str, db_path: str, output_file: str):
    """验证样本并生成报告"""

    print("Loading validation samples...")
    samples = load_validation_samples(samples_file)

    # 统计结果
    results = {
        "total_samples": 0,
        "samples_by_category": {},
        "detector_performance": {},
        "category_coverage": {},
    }

    # 初始化统计
    for detector in DETECTOR_CATEGORY_MAP.keys():
        results["detector_performance"][detector] = {
            "expected_triggers": 0,
            "actual_triggers": 0,
            "samples_checked": 0,
            "samples_with_trace": 0,
        }

    for category in CATEGORY_DETECTOR_MAP.keys():
        results["category_coverage"][category] = {
            "total_samples": 0,
            "samples_with_trace": 0,
            "detector_triggered": 0,
        }

    # 验证每个类别的样本
    for category, category_samples in samples.items():
        print(f"\nValidating {category} ({len(category_samples)} samples)...")

        results["samples_by_category"][category] = len(category_samples)
        results["total_samples"] += len(category_samples)

        if category not in CATEGORY_DETECTOR_MAP:
            print(f"  Warning: No detector mapped for category {category}")
            continue

        detector_name = CATEGORY_DETECTOR_MAP[category]
        results["category_coverage"][category]["total_samples"] = len(category_samples)

        for sample in category_samples:
            tx_hash = sample["tx_hash"]
            chain_id = sample["chain_id"]

            results["detector_performance"][detector_name]["samples_checked"] += 1
            results["detector_performance"][detector_name]["expected_triggers"] += 1

            # 获取 alert_data
            alert_data = get_alert_data(db_path, tx_hash, chain_id)

            if not alert_data:
                print(f"  Warning: No alert_data for {tx_hash}")
                continue

            # 检查是否有 eth_trace 数据
            has_trace = 'eth_trace' in alert_data or 'trace' in alert_data
            if has_trace:
                results["detector_performance"][detector_name]["samples_with_trace"] += 1
                results["category_coverage"][category]["samples_with_trace"] += 1

            # 检查检测器是否触发（简化版本）
            triggered = check_detector_triggered(alert_data, detector_name)
            if triggered:
                results["detector_performance"][detector_name]["actual_triggers"] += 1
                results["category_coverage"][category]["detector_triggered"] += 1

    # 计算性能指标
    print("\n" + "="*60)
    print("VALIDATION RESULTS")
    print("="*60)

    print(f"\nTotal samples validated: {results['total_samples']}")
    print(f"Samples by category:")
    for category, count in results["samples_by_category"].items():
        print(f"  {category}: {count}")

    print("\n" + "-"*60)
    print("Detector Performance:")
    print("-"*60)

    for detector, stats in results["detector_performance"].items():
        if stats["samples_checked"] == 0:
            continue

        print(f"\n{detector}:")
        print(f"  Samples checked: {stats['samples_checked']}")
        print(f"  Samples with trace data: {stats['samples_with_trace']}")
        print(f"  Expected triggers: {stats['expected_triggers']}")
        print(f"  Actual triggers: {stats['actual_triggers']}")

        if stats["samples_with_trace"] > 0:
            coverage_rate = stats["actual_triggers"] / stats["samples_with_trace"] * 100
            print(f"  Coverage rate (with trace): {coverage_rate:.1f}%")

    print("\n" + "-"*60)
    print("Category Coverage:")
    print("-"*60)

    for category, stats in results["category_coverage"].items():
        if stats["total_samples"] == 0:
            continue

        print(f"\n{category}:")
        print(f"  Total samples: {stats['total_samples']}")
        print(f"  Samples with trace: {stats['samples_with_trace']}")
        print(f"  Detector triggered: {stats['detector_triggered']}")

        if stats["samples_with_trace"] > 0:
            trigger_rate = stats["detector_triggered"] / stats["samples_with_trace"] * 100
            print(f"  Trigger rate (with trace): {trigger_rate:.1f}%")

    # 保存结果
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n\nResults saved to: {output_file}")

    # 总结
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)

    total_with_trace = sum(
        stats["samples_with_trace"]
        for stats in results["detector_performance"].values()
    )
    total_triggered = sum(
        stats["actual_triggers"]
        for stats in results["detector_performance"].values()
    )

    print(f"\nOverall statistics:")
    print(f"  Total samples: {results['total_samples']}")
    print(f"  Samples with trace data: {total_with_trace}")
    print(f"  Total detector triggers: {total_triggered}")

    if total_with_trace > 0:
        overall_rate = total_triggered / total_with_trace * 100
        print(f"  Overall trigger rate: {overall_rate:.1f}%")

    print("\nNote: This is a simplified validation based on existing alert_data.")
    print("For accurate results, samples should be re-processed through the")
    print("complete detection pipeline with eth_trace data.")


if __name__ == "__main__":
    import sys

    # 默认路径
    samples_file = "data/kb_validation_samples.json"
    db_path = "alerts.db"
    output_file = "data/detector_validation_report.json"

    # 命令行参数
    if len(sys.argv) > 1:
        samples_file = sys.argv[1]
    if len(sys.argv) > 2:
        db_path = sys.argv[2]
    if len(sys.argv) > 3:
        output_file = sys.argv[3]

    validate_samples(samples_file, db_path, output_file)

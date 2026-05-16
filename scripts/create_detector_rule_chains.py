"""
Phase 5: Rule Chain Assembly

为新实现的 7 个协议攻击检测器创建规则链。

每个规则链包含：
1. Alert Trigger (触发器)
2. EthTrace Provider (获取调用栈数据)
3. 对应的检测器
4. Set Severity Action (设置严重程度)
5. Add Tag Action (添加标签)
"""

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Dict, List, Any


# 检测器配置
DETECTOR_CONFIGS = {
    "arbitrary_call_detector": {
        "name": "Arbitrary Call Attack Detection",
        "description": "检测任意调用攻击，包括 delegatecall 到未知地址、任意调用入口函数等模式",
        "severity": "critical",
        "tags": ["arbitrary_call", "delegatecall", "protocol_attack"],
    },
    "precision_loss_detector": {
        "name": "Precision Loss Attack Detection",
        "description": "检测精度损失漏洞，包括舍入错误、精度截断等导致的资产损失",
        "severity": "high",
        "tags": ["precision_loss", "rounding_error", "protocol_attack"],
    },
    "access_control_bypass_detector": {
        "name": "Access Control Bypass Detection",
        "description": "检测访问控制绕过攻击，包括特权函数未授权调用、权限检查绕过等",
        "severity": "critical",
        "tags": ["access_control", "unauthorized_access", "protocol_attack"],
    },
    "input_validation_detector": {
        "name": "Input Validation Vulnerability Detection",
        "description": "检测输入验证不足导致的漏洞，包括未验证的用户输入、缺少边界检查等",
        "severity": "high",
        "tags": ["input_validation", "unverified_input", "protocol_attack"],
    },
    "governance_attack_detector": {
        "name": "Governance Attack Detection",
        "description": "检测针对治理机制的攻击，包括恶意提案执行、闪电贷治理攻击等",
        "severity": "critical",
        "tags": ["governance_attack", "dao_attack", "protocol_attack"],
    },
    "storage_collision_detector": {
        "name": "Storage Collision Detection",
        "description": "检测存储槽冲突漏洞，包括代理合约存储冲突、delegatecall 存储覆盖等",
        "severity": "critical",
        "tags": ["storage_collision", "proxy_attack", "protocol_attack"],
    },
    "protocol_misc_detector": {
        "name": "Protocol Miscellaneous Vulnerability Detection",
        "description": "检测协议中的其他常见漏洞，包括滑点保护不足、会计错误、配置问题等",
        "severity": "medium",
        "tags": ["slippage", "accounting_error", "misconfiguration", "protocol_attack"],
    },
}


def generate_rule_chain(detector_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """生成规则链配置"""

    # 生成节点 ID
    trigger_id = f"node_{uuid.uuid4().hex[:16]}"
    provider_id = f"node_{uuid.uuid4().hex[:16]}"
    detector_id = f"node_{uuid.uuid4().hex[:16]}"
    severity_id = f"node_{uuid.uuid4().hex[:16]}"
    tag_id = f"node_{uuid.uuid4().hex[:16]}"

    # 节点配置
    nodes = [
        {
            "id": trigger_id,
            "type": "alert_trigger",
            "label": "Alert Trigger",
            "config": {},
            "position": {"x": 100, "y": 200}
        },
        {
            "id": provider_id,
            "type": "eth_trace_provider",
            "label": "ETH Trace Provider",
            "config": {
                "enable_cache": True,
                "cache_ttl_seconds": 3600,
            },
            "position": {"x": 350, "y": 200}
        },
        {
            "id": detector_id,
            "type": detector_type,
            "label": config["name"],
            "config": {},
            "position": {"x": 650, "y": 200}
        },
        {
            "id": severity_id,
            "type": "set_severity_action",
            "label": "Set Severity",
            "config": {
                "severity": config["severity"],
            },
            "position": {"x": 950, "y": 150}
        },
        {
            "id": tag_id,
            "type": "add_tag_action",
            "label": "Add Tags",
            "config": {
                "tags": config["tags"],
            },
            "position": {"x": 950, "y": 250}
        },
    ]

    # 边配置
    edges = [
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": trigger_id,
            "sourcePort": "output",
            "target": provider_id,
            "targetPort": "input",
            "label": "",
            "fieldMapping": None,
            "inputTransformer": None,
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": provider_id,
            "sourcePort": "output",
            "target": detector_id,
            "targetPort": "input",
            "label": "",
            "fieldMapping": None,
            "inputTransformer": None,
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": detector_id,
            "sourcePort": "output",
            "target": severity_id,
            "targetPort": "input",
            "label": "",
            "fieldMapping": None,
            "inputTransformer": None,
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": detector_id,
            "sourcePort": "output",
            "target": tag_id,
            "targetPort": "input",
            "label": "",
            "fieldMapping": None,
            "inputTransformer": None,
        },
    ]

    return {
        "nodes": nodes,
        "edges": edges,
    }


def create_rule_chains(db_path: str, output_file: str):
    """创建所有新检测器的规则链"""

    print("="*60)
    print("Phase 5: Rule Chain Assembly")
    print("="*60)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    created_chains = []

    for detector_type, config in DETECTOR_CONFIGS.items():
        print(f"\nCreating rule chain for {detector_type}...")

        # 生成规则链配置
        chain_config = generate_rule_chain(detector_type, config)

        # 生成规则链记录
        chain_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        chain_record = {
            "id": chain_id,
            "name": config["name"],
            "description": config["description"],
            "chain_config": json.dumps(chain_config, ensure_ascii=False),
            "enabled": 1,
            "created_at": now,
            "updated_at": now,
        }

        # 插入数据库
        cursor.execute("""
            INSERT INTO rule_chains (id, name, description, chain_config, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            chain_record["id"],
            chain_record["name"],
            chain_record["description"],
            chain_record["chain_config"],
            chain_record["enabled"],
            chain_record["created_at"],
            chain_record["updated_at"],
        ))

        created_chains.append({
            "id": chain_id,
            "name": config["name"],
            "detector": detector_type,
            "severity": config["severity"],
            "tags": config["tags"],
        })

        print(f"  Created: {chain_id}")
        print(f"  Name: {config['name']}")
        print(f"  Severity: {config['severity']}")
        print(f"  Tags: {', '.join(config['tags'])}")

    conn.commit()

    # 验证
    cursor.execute("SELECT COUNT(*) FROM rule_chains")
    total_chains = cursor.fetchone()[0]

    conn.close()

    # 保存摘要
    summary = {
        "created_at": datetime.now().isoformat(),
        "total_chains_created": len(created_chains),
        "total_chains_in_db": total_chains,
        "chains": created_chains,
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # 打印摘要
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"\nRule chains created: {len(created_chains)}")
    print(f"Total rule chains in database: {total_chains}")

    print("\nCreated chains:")
    for chain in created_chains:
        print(f"  - {chain['name']}")
        print(f"    Detector: {chain['detector']}")
        print(f"    Severity: {chain['severity']}")

    print(f"\nSummary saved to: {output_file}")

    print("\n" + "="*60)
    print("NEXT STEPS")
    print("="*60)
    print("""
The rule chains are now created and stored in the database.

To use them:
1. Load the rule chains in the frontend editor
2. Customize node configurations if needed
3. Test with sample transactions
4. Enable the chains for production use

Each chain follows the standard pattern:
  Alert Trigger -> ETH Trace Provider -> Detector -> Actions (Severity + Tags)

The chains are ready for Phase 6: Final Coverage Verification.
""")


if __name__ == "__main__":
    db_path = "alerts.db"
    output_file = "data/rule_chains_created.json"

    create_rule_chains(db_path, output_file)

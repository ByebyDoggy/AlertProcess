"""
跨链消息伪造攻击检测规则链

攻击场景：
1. 攻击者在源链（如 ETH）上伪造或重放跨链消息
2. 跨链桥在目标链（如 BSC）上执行恶意操作
3. 单独看每条链的交易可能都正常，但关联分析可以发现异常

检测策略：
- 在源链上记录所有跨链消息发送事件
- 在目标链上验证跨链消息执行是否有对应的源链记录
- 检测消息重放、消息伪造、消息顺序异常等模式

规则链组合：
1. 源链监控链：记录跨链消息发送
2. 目标链验证链：验证消息合法性
3. 异常检测链：识别伪造/重放模式
"""

import json
import sqlite3
import uuid
from datetime import datetime
from typing import Dict, List, Any


# 跨链桥合约地址（示例）
CROSS_CHAIN_BRIDGE_CONTRACTS = {
    # Multichain (Anyswap)
    "0xc564ee9f21ed8a2d8e7e76c085740d5e4c5fafbe": "Multichain Router",
    "0x6b7a87899490ece95443e979ca9485cbe7e71522": "Multichain V7 Router",

    # Stargate
    "0x8731d54e9d02c286767d56ac03e8037c07e01e98": "Stargate Router",
    "0x150f94b44927f078737562f0fcf3c95c01cc2376": "Stargate Bridge",

    # Celer cBridge
    "0x5427fefa711eff984124bfbb1ab6fbf5e3da1820": "Celer cBridge",

    # Wormhole
    "0x98f3c9e6e3face36baad05fe09d375ef1464288b": "Wormhole Core Bridge",

    # LayerZero
    "0x66a71dcef29a0ffbdbe3c6a460a3b5bc225cd675": "LayerZero Endpoint",
}

# 跨链消息相关的函数签名
CROSS_CHAIN_MESSAGE_SIGNATURES = {
    # 发送消息
    "0x3dbb202b": "send(uint16,bytes,bytes)",  # LayerZero send
    "0x7ff9b596": "sendMessage(bytes)",
    "0x0f5287b0": "sendToken(uint256,address,uint256)",

    # 接收/执行消息
    "0x1a808f91": "receiveMessage(bytes)",
    "0x66ad5c8a": "executeMessage(bytes)",
    "0xc4461834": "lzReceive(uint16,bytes,uint64,bytes)",  # LayerZero receive

    # 验证消息
    "0x8c3152e9": "validateMessage(bytes)",
    "0x5c975abb": "verifySignatures(bytes,bytes[])",
}


def generate_source_chain_monitor() -> Dict[str, Any]:
    """
    规则链 1: 源链跨链消息监控

    功能：
    - 监控跨链桥合约的消息发送事件
    - 记录消息哈希、目标链、发送者、时间戳
    - 发布到 Temporal Store 供目标链验证
    """

    trigger_id = f"node_{uuid.uuid4().hex[:16]}"
    log_parser_id = f"node_{uuid.uuid4().hex[:16]}"
    trace_provider_id = f"node_{uuid.uuid4().hex[:16]}"
    script_filter_id = f"node_{uuid.uuid4().hex[:16]}"
    publisher_id = f"node_{uuid.uuid4().hex[:16]}"

    nodes = [
        {
            "id": trigger_id,
            "type": "alert_trigger",
            "label": "Alert Trigger",
            "config": {},
            "position": {"x": 100, "y": 200}
        },
        {
            "id": log_parser_id,
            "type": "log_parser_provider",
            "label": "Parse Bridge Events",
            "config": {
                "event_signatures": [
                    "SendToChain(address,uint256,bytes32,uint256)",  # 跨链发送事件
                    "MessageSent(bytes32,uint256,address,bytes)",
                ],
            },
            "position": {"x": 300, "y": 200}
        },
        {
            "id": trace_provider_id,
            "type": "eth_trace_provider",
            "label": "ETH Trace Provider",
            "config": {
                "enable_cache": True,
                "cache_ttl_seconds": 3600,
            },
            "position": {"x": 500, "y": 200}
        },
        {
            "id": script_filter_id,
            "type": "script_node",
            "label": "Filter Bridge Messages",
            "config": {
                "script": """
# 过滤跨链桥消息
def process(context):
    logs = context.get('parsed_logs', [])
    trace = context.get('eth_trace', {})

    # 检查是否调用了跨链桥合约
    bridge_contracts = {
        '0xc564ee9f21ed8a2d8e7e76c085740d5e4c5fafbe',
        '0x8731d54e9d02c286767d56ac03e8037c07e01e98',
        # ... 更多桥合约地址
    }

    is_bridge_tx = False
    for entry in trace.get('traces', []):
        to_addr = entry.get('action', {}).get('to', '').lower()
        if to_addr in bridge_contracts:
            is_bridge_tx = True
            break

    if not is_bridge_tx:
        return {'passed': False, 'score': 0}

    # 提取跨链消息信息
    message_info = {
        'tx_hash': context.get('tx_hash'),
        'from_address': context.get('from_address'),
        'timestamp': context.get('timestamp'),
        'chain_id': context.get('chain_id'),
        'bridge_contract': to_addr,
        'message_events': logs,
    }

    context['cross_chain_message'] = message_info
    return {'passed': True, 'score': 100}
"""
            },
            "position": {"x": 700, "y": 200}
        },
        {
            "id": publisher_id,
            "type": "fact_publisher",
            "label": "Publish Message Sent",
            "config": {
                "fact_name": "cross_chain_message_sent",
                "scope_by": "tx_hash",
                "time_field": "timestamp",
                "ttl_minutes": 1440,  # 24小时
                "payload_fields": [
                    "tx_hash",
                    "from_address",
                    "chain_id",
                    "bridge_contract",
                    "cross_chain_message",
                ],
                "publish_condition_field": "passed",
                "tags": ["cross_chain", "message_sent"],
            },
            "position": {"x": 900, "y": 200}
        },
    ]

    edges = [
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": trigger_id,
            "sourcePort": "output",
            "target": log_parser_id,
            "targetPort": "input",
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": log_parser_id,
            "sourcePort": "output",
            "target": trace_provider_id,
            "targetPort": "input",
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": trace_provider_id,
            "sourcePort": "output",
            "target": script_filter_id,
            "targetPort": "input",
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": script_filter_id,
            "sourcePort": "output",
            "target": publisher_id,
            "targetPort": "input",
        },
    ]

    return {"nodes": nodes, "edges": edges}


def generate_target_chain_validator() -> Dict[str, Any]:
    """
    规则链 2: 目标链消息验证

    功能：
    - 检测目标链上的跨链消息执行
    - 查询源链是否有对应的消息发送记录
    - 验证消息的合法性（是否伪造/重放）
    """

    trigger_id = f"node_{uuid.uuid4().hex[:16]}"
    trace_provider_id = f"node_{uuid.uuid4().hex[:16]}"
    script_detect_id = f"node_{uuid.uuid4().hex[:16]}"
    query_source_id = f"node_{uuid.uuid4().hex[:16]}"
    match_id = f"node_{uuid.uuid4().hex[:16]}"
    drain_detector_id = f"node_{uuid.uuid4().hex[:16]}"
    severity_id = f"node_{uuid.uuid4().hex[:16]}"
    tag_id = f"node_{uuid.uuid4().hex[:16]}"

    nodes = [
        {
            "id": trigger_id,
            "type": "alert_trigger",
            "label": "Alert Trigger",
            "config": {},
            "position": {"x": 100, "y": 200}
        },
        {
            "id": trace_provider_id,
            "type": "eth_trace_provider",
            "label": "ETH Trace Provider",
            "config": {
                "enable_cache": True,
                "cache_ttl_seconds": 3600,
            },
            "position": {"x": 300, "y": 200}
        },
        {
            "id": script_detect_id,
            "type": "script_node",
            "label": "Detect Message Execution",
            "config": {
                "script": """
# 检测跨链消息执行
def process(context):
    trace = context.get('eth_trace', {})

    # 检查是否调用了消息接收/执行函数
    message_exec_sigs = {
        '0x1a808f91',  # receiveMessage
        '0x66ad5c8a',  # executeMessage
        '0xc4461834',  # lzReceive
    }

    message_executions = []
    for entry in trace.get('traces', []):
        selector = entry.get('action', {}).get('input', '')[:10]
        if selector in message_exec_sigs:
            message_executions.append({
                'selector': selector,
                'to': entry.get('action', {}).get('to'),
                'from': entry.get('action', {}).get('from'),
                'input': entry.get('action', {}).get('input'),
            })

    if not message_executions:
        return {'passed': False, 'score': 0}

    context['message_executions'] = message_executions
    context['execution_count'] = len(message_executions)

    # 提取可能的源链交易哈希（从 calldata 中）
    # 这需要根据具体桥的实现来解析
    context['source_tx_hash'] = 'unknown'  # 实际需要解析

    return {'passed': True, 'score': 50}
"""
            },
            "position": {"x": 500, "y": 200}
        },
        {
            "id": query_source_id,
            "type": "fact_query",
            "label": "Query Source Chain",
            "config": {
                "fact_name": "cross_chain_message_sent",
                "scope_by": "source_tx_hash",  # 根据源链交易哈希查询
                "lookup_mode": "RECENT",
                "window_minutes": 1440,  # 24小时窗口
                "limit": 10,
            },
            "position": {"x": 700, "y": 200}
        },
        {
            "id": match_id,
            "type": "fact_match",
            "label": "Verify Message Legitimacy",
            "config": {
                "pattern": ["cross_chain_message_sent"],
                "min_matches": 1,
                "match_mode": "ANY",
            },
            "position": {"x": 900, "y": 200}
        },
        {
            "id": drain_detector_id,
            "type": "fund_drain_detector",
            "label": "Check Fund Drain",
            "config": {
                "threshold": 70.0,
            },
            "position": {"x": 1100, "y": 200}
        },
        {
            "id": severity_id,
            "type": "set_severity_action",
            "label": "Set Severity",
            "config": {
                "severity": "critical",
            },
            "position": {"x": 1300, "y": 150}
        },
        {
            "id": tag_id,
            "type": "add_tag_action",
            "label": "Add Tags",
            "config": {
                "tags": [
                    "cross_chain_attack",
                    "message_forgery",
                    "bridge_exploit",
                ],
            },
            "position": {"x": 1300, "y": 250}
        },
    ]

    edges = [
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": trigger_id,
            "sourcePort": "output",
            "target": trace_provider_id,
            "targetPort": "input",
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": trace_provider_id,
            "sourcePort": "output",
            "target": script_detect_id,
            "targetPort": "input",
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": script_detect_id,
            "sourcePort": "output",
            "target": query_source_id,
            "targetPort": "input",
            "label": "Message Execution Detected",
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": query_source_id,
            "sourcePort": "output",
            "target": match_id,
            "targetPort": "input",
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": match_id,
            "sourcePort": "false",  # 没有匹配到源链记录
            "target": drain_detector_id,
            "targetPort": "input",
            "label": "No Source Record Found",
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": drain_detector_id,
            "sourcePort": "output",
            "target": severity_id,
            "targetPort": "input",
            "label": "Fund Loss Confirmed",
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": drain_detector_id,
            "sourcePort": "output",
            "target": tag_id,
            "targetPort": "input",
        },
    ]

    return {"nodes": nodes, "edges": edges}


def generate_replay_attack_detector() -> Dict[str, Any]:
    """
    规则链 3: 消息重放攻击检测

    功能：
    - 检测同一消息被多次执行
    - 识别消息重放攻击模式
    """

    trigger_id = f"node_{uuid.uuid4().hex[:16]}"
    trace_provider_id = f"node_{uuid.uuid4().hex[:16]}"
    query_history_id = f"node_{uuid.uuid4().hex[:16]}"
    script_check_id = f"node_{uuid.uuid4().hex[:16]}"
    drain_detector_id = f"node_{uuid.uuid4().hex[:16]}"
    severity_id = f"node_{uuid.uuid4().hex[:16]}"
    tag_id = f"node_{uuid.uuid4().hex[:16]}"
    publisher_id = f"node_{uuid.uuid4().hex[:16]}"

    nodes = [
        {
            "id": trigger_id,
            "type": "alert_trigger",
            "label": "Alert Trigger",
            "config": {},
            "position": {"x": 100, "y": 200}
        },
        {
            "id": trace_provider_id,
            "type": "eth_trace_provider",
            "label": "ETH Trace Provider",
            "config": {},
            "position": {"x": 300, "y": 200}
        },
        {
            "id": query_history_id,
            "type": "fact_query",
            "label": "Query Message History",
            "config": {
                "fact_name": "message_executed",
                "scope_by": "message_hash",  # 按消息哈希查询
                "lookup_mode": "ALL",
                "window_minutes": 10080,  # 7天
                "limit": 100,
            },
            "position": {"x": 500, "y": 200}
        },
        {
            "id": script_check_id,
            "type": "script_node",
            "label": "Check Replay",
            "config": {
                "script": """
# 检查消息重放
def process(context):
    history = context.get('queried_facts', [])
    current_msg_hash = context.get('message_hash')

    # 检查这个消息是否之前执行过
    execution_count = len([
        f for f in history
        if f.get('payload', {}).get('message_hash') == current_msg_hash
    ])

    if execution_count > 0:
        # 消息重放检测到
        context['is_replay'] = True
        context['previous_executions'] = execution_count
        return {'passed': True, 'score': 95}

    return {'passed': False, 'score': 0}
"""
            },
            "position": {"x": 700, "y": 200}
        },
        {
            "id": drain_detector_id,
            "type": "fund_drain_detector",
            "label": "Verify Fund Drain",
            "config": {
                "threshold": 60.0,
            },
            "position": {"x": 900, "y": 200}
        },
        {
            "id": severity_id,
            "type": "set_severity_action",
            "label": "Set Severity",
            "config": {
                "severity": "critical",
            },
            "position": {"x": 1100, "y": 150}
        },
        {
            "id": tag_id,
            "type": "add_tag_action",
            "label": "Add Tags",
            "config": {
                "tags": [
                    "replay_attack",
                    "cross_chain_attack",
                    "message_replay",
                ],
            },
            "position": {"x": 1100, "y": 250}
        },
        {
            "id": publisher_id,
            "type": "fact_publisher",
            "label": "Record Execution",
            "config": {
                "fact_name": "message_executed",
                "scope_by": "message_hash",
                "ttl_minutes": 10080,  # 7天
                "payload_fields": ["message_hash", "tx_hash", "timestamp"],
            },
            "position": {"x": 1100, "y": 350}
        },
    ]

    edges = [
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": trigger_id,
            "target": trace_provider_id,
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": trace_provider_id,
            "target": query_history_id,
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": query_history_id,
            "target": script_check_id,
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": script_check_id,
            "sourcePort": "output",
            "target": drain_detector_id,
            "label": "Replay Detected",
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": drain_detector_id,
            "target": severity_id,
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": drain_detector_id,
            "target": tag_id,
        },
        {
            "id": f"edge_{uuid.uuid4().hex[:16]}",
            "source": drain_detector_id,
            "target": publisher_id,
        },
    ]

    return {"nodes": nodes, "edges": edges}


def create_cross_chain_detection_chains(db_path: str, output_file: str):
    """创建跨链消息伪造检测规则链"""

    print("="*60)
    print("Creating Cross-Chain Message Forgery Detection Chains")
    print("="*60)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    chains = [
        {
            "name": "Cross-Chain Message Sent Monitor (Source Chain)",
            "description": "监控源链上的跨链消息发送，记录到 Temporal Store",
            "config": generate_source_chain_monitor(),
            "enabled": 1,
        },
        {
            "name": "Cross-Chain Message Validation (Target Chain)",
            "description": "验证目标链上执行的跨链消息是否有对应的源链记录",
            "config": generate_target_chain_validator(),
            "enabled": 1,
        },
        {
            "name": "Cross-Chain Message Replay Detection",
            "description": "检测跨链消息重放攻击",
            "config": generate_replay_attack_detector(),
            "enabled": 1,
        },
    ]

    created_chains = []

    for chain_data in chains:
        chain_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        print(f"\nCreating: {chain_data['name']}")

        cursor.execute("""
            INSERT INTO rule_chains (id, name, description, chain_config, enabled, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            chain_id,
            chain_data["name"],
            chain_data["description"],
            json.dumps(chain_data["config"], ensure_ascii=False),
            chain_data["enabled"],
            now,
            now,
        ))

        created_chains.append({
            "id": chain_id,
            "name": chain_data["name"],
            "description": chain_data["description"],
        })

        print(f"  [OK] Created: {chain_id}")

    conn.commit()

    # 验证
    cursor.execute("SELECT COUNT(*) FROM rule_chains WHERE enabled = 1")
    total_enabled = cursor.fetchone()[0]

    conn.close()

    # 保存摘要
    summary = {
        "created_at": datetime.now().isoformat(),
        "chains_created": len(created_chains),
        "total_enabled_chains": total_enabled,
        "chains": created_chains,
        "detection_capabilities": {
            "message_forgery": "检测目标链上执行的消息是否有源链记录",
            "message_replay": "检测同一消息被多次执行",
            "unauthorized_execution": "检测未授权的跨链消息执行",
        },
    }

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    # 打印摘要
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    print(f"\nChains created: {len(created_chains)}")
    print(f"Total enabled chains: {total_enabled}")

    print("\nCreated chains:")
    for chain in created_chains:
        print(f"  - {chain['name']}")

    print(f"\nSummary saved to: {output_file}")

    print("\n" + "="*60)
    print("DETECTION STRATEGY")
    print("="*60)
    print("""
跨链消息伪造检测策略：

1. 源链监控（Chain 1）
   - 监控所有跨链桥的消息发送事件
   - 记录消息哈希、目标链、发送者等信息
   - 发布到 Temporal Store（TTL: 24小时）

2. 目标链验证（Chain 2）
   - 检测目标链上的消息执行
   - 查询 Temporal Store 验证是否有源链记录
   - 如果没有记录 + 有资金损失 → 报警（消息伪造）

3. 重放攻击检测（Chain 3）
   - 记录每个消息的执行历史
   - 检测同一消息是否被多次执行
   - 如果重复执行 + 有资金损失 → 报警（消息重放）

检测能力：
✅ 消息伪造：目标链执行了不存在的源链消息
✅ 消息重放：同一消息被多次执行
✅ 未授权执行：消息执行导致异常资金流失

限制：
- 需要同时监控源链和目标链
- 依赖 Temporal Store 的数据完整性
- 消息哈希提取需要根据具体桥实现定制
""")

    print("\n" + "="*60)
    print("NEXT STEPS")
    print("="*60)
    print("""
1. 配置跨链桥合约地址
   - 更新 CROSS_CHAIN_BRIDGE_CONTRACTS
   - 添加你关注的桥合约

2. 定制消息解析逻辑
   - 根据具体桥的实现解析消息哈希
   - 提取源链交易哈希

3. 部署规则链
   - 在源链上启用 Chain 1
   - 在目标链上启用 Chain 2 和 Chain 3

4. 测试验证
   - 使用已知的跨链攻击案例测试
   - 验证检测准确性
""")


if __name__ == "__main__":
    db_path = "alerts.db"
    output_file = "data/cross_chain_detection_chains.json"

    create_cross_chain_detection_chains(db_path, output_file)

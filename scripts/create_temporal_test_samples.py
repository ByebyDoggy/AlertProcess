"""
创建时序检测测试样本到知识库

场景：管理员权限转移后 5 分钟内大额资金转出
"""

import requests
import json
from datetime import datetime, timezone

API_BASE = "http://127.0.0.1:8001"
API_KEY = "default_secret_key_change_in_production"

headers = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json"
}

# 测试地址
contract = "0xvictimcontract000000000000000000000000000001"
old_admin = "0xoldadmin0000000000000000000000000000000001"
new_admin = "0xattacker0000000000000000000000000000000001"
receiver = "0xreceiver0000000000000000000000000000000001"

# 样本 1: 管理员权限转移事件
sample1 = {
    "title": "时序测试-管理员权限转移",
    "description": "代理合约管理员权限从旧管理员转移到攻击者地址",
    "category": "temporal_test",
    "tags": ["temporal", "admin_transfer", "test"],
    "chain_id": 1,
    "tx_hash": "0xcontrolchange0001000000000000000000000000000000000000000000000001",
    "attacked_address": contract,
    "exploiter_address": new_admin,
    "alert_data": {
        "tx_hash": "0xcontrolchange0001000000000000000000000000000000000000000000000001",
        "chain_id": 1,
        "from_address": old_admin,
        "to_address": contract,
        "value": 0,
        "gas_price": 50_000_000_000,
        "gas_used": 180000,
        "block_number": 19_000_001,
        "timestamp": "2026-05-10T12:00:00+00:00",
        "logs": [
            {
                "address": contract,
                "topics": [
                    "0x7e644d79422f17c01e4894b5f4f588d331ebfa28653d42ae832dc59e38c9798f",
                ],
                "data": "0x" + old_admin.lower().replace("0x", "").rjust(64, "0") + new_admin.lower().replace("0x", "").rjust(64, "0"),
                "logIndex": "0x1",
                "blockNumber": hex(19_000_001),
                "transactionHash": "0xcontrolchange0001000000000000000000000000000000000000000000000001",
            }
        ],
    },
    "expected_severity": "HIGH",
    "expected_labels": ["admin_transfer", "control_change"],
    "expected_min_score": 70,
    "source": "temporal_test",
    "tx_explorer_url": f"https://etherscan.io/tx/0xcontrolchange0001000000000000000000000000000000000000000000000001"
}

# 样本 2: 5分钟内大额资金转出
sample2 = {
    "title": "时序测试-大额资金转出(3分钟后)",
    "description": "管理员权限转移后3分钟，发生大额ETH转出",
    "category": "temporal_test",
    "tags": ["temporal", "fund_drain", "test"],
    "chain_id": 1,
    "tx_hash": "0xfunddrain0001000000000000000000000000000000000000000000000000001",
    "attacked_address": contract,
    "exploiter_address": receiver,
    "alert_data": {
        "tx_hash": "0xfunddrain0001000000000000000000000000000000000000000000000000001",
        "chain_id": 1,
        "from_address": new_admin,
        "to_address": contract,
        "value": 0,
        "gas_price": 55_000_000_000,
        "gas_used": 420000,
        "block_number": 19_000_002,
        "timestamp": "2026-05-10T12:03:00+00:00",
        "logs": [],
        "transfers": [
            {
                "from": contract,
                "to": receiver,
                "value": 100_000 * 10**18,
                "token": "",
            }
        ],
        "token_prices": {
            "": 3000.0,
        },
    },
    "expected_severity": "CRITICAL",
    "expected_labels": ["fund_drain", "temporal_match"],
    "expected_min_score": 80,
    "source": "temporal_test",
    "tx_explorer_url": f"https://etherscan.io/tx/0xfunddrain0001000000000000000000000000000000000000000000000000001"
}

def create_sample(sample_data):
    """创建知识库样本"""
    response = requests.post(
        f"{API_BASE}/knowledge-base/",
        headers=headers,
        json=sample_data
    )
    if response.status_code == 200:
        result = response.json()
        print(f"[OK] Created: {result['title']} (ID: {result['id'][:8]}...)")
        return result
    else:
        print(f"[FAIL] Status: {response.status_code}")
        print(f"  Error: {response.text}")
        return None

if __name__ == "__main__":
    print("=" * 60)
    print("Creating temporal detection test samples")
    print("=" * 60)

    print("\n[1/2] Creating admin transfer event...")
    result1 = create_sample(sample1)

    print("\n[2/2] Creating fund drain event...")
    result2 = create_sample(sample2)

    if result1 and result2:
        print("\n" + "=" * 60)
        print("[OK] Test samples created successfully")
        print("=" * 60)
        print(f"\nSample 1 ID: {result1['id']}")
        print(f"Sample 2 ID: {result2['id']}")
        print("\nNext steps in frontend:")
        print("1. Open rule chain: temporal detection chain")
        print("2. Click 'Test Run' button")
        print("3. Select these 2 samples from knowledge base")
        print("4. Add them to execution queue in order")
        print("5. Click 'Execute Test' and view results")
    else:
        print("\n[FAIL] Sample creation failed")

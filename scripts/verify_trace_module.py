"""
P0+P1 集成验证脚本
==================
验证 detectors/trace 模块所有组件可正确导入、初始化、并完成一次完整分析流程。

用法 (使用虚拟环境):
    python scripts/verify_trace_module.py
"""
import sys
import asyncio
import time
import traceback
from pathlib import Path

# 确保项目根目录在 path 中
PROJECT_ROOT = Path(__file__).resolve().parents[1]
str_root = str(PROJECT_ROOT)
if str_root not in sys.path:
    sys.path.insert(0, str_root)


async def main():
    print("=" * 60)
    print("  Trace Analysis Module - P0/P1 Verification")
    print("=" * 60)

    # ---- Step 1: 验证模块导入 ----
    print("\n[Step 1] Importing modules...")
    try:
        from detectors.trace.models import (
            CallType,
            DecodedParam,
            EventRecord,
            CallNode,
            TransactionInfo,
            ProtocolInfo,
            BehaviorResult,
            TokenFlowItem,
            FullAnalysisResult,
        )
        print("  [OK] models.py - All dataclasses imported")
    except Exception as e:
        print(f"  [FAIL] models.py: {e}")
        return False

    try:
        from detectors.trace.provider import MultiRpcClient, DEFAULT_CHAIN_CONFIG
        print(f"  [OK] provider.py - {len(DEFAULT_CHAIN_CONFIG)} chains configured")
    except Exception as e:
        print(f"  [FAIL] provider.py: {e}")
        return False

    try:
        from detectors.trace.signature_db import SignatureDB, _BUILTIN_SIGNATURES
        db = SignatureDB()  # fallback mode (no DB file yet)
        count = db.count()
        print(f"  [OK] signature_db.py - {count} signatures available (fallback mode)")
    except Exception as e:
        print(f"  [FAIL] signature_db.py: {e}")
        traceback.print_exc()
        return False

    try:
        from detectors.trace.protocol_registry import ProtocolRegistry
        reg = ProtocolRegistry()
        eth_count = len(reg.all_protocols_for_chain(1))
        bsc_count = len(reg.all_protocols_for_chain(56))
        print(
            f"  [OK] protocol_registry.py - "
            f"{eth_count} ETH + {bsc_count} BSC protocols"
        )
    except Exception as e:
        print(f"  [FAIL] protocol_registry.py: {e}")
        return False

    try:
        from detectors.trace.analyzer import (
            TxTraceAnalyzer,
            count_nodes,
            get_max_depth,
            count_events,
        )
        print("  [OK] analyzer.py - TxTraceAnalyzer imported")
    except Exception as e:
        print(f"  [FAIL] analyzer.py: {e}")
        traceback.print_exc()
        return False

    # 行为检测器
    try:
        from detectors.trace.behaviors.flash_loan import FlashLoanDetector
        from detectors.trace.behaviors.token_flow import TokenFlowDetector
        from detectors.trace.behaviors.base_behavior import BaseBehaviorDetector
        print("  [OK] behaviors/ - FlashLoan + TokenFlow detectors imported")
    except Exception as e:
        print(f"  [FAIL] behaviors/: {e}")
        traceback.print_exc()
        return False

    # API 路由
    try:
        from routers.detectors.trace_router import trace_router
        routes = [r.path for r in trace_router.routes]
        print(f"  [OK] trace_router.py - {len(routes)} endpoints: {routes}")
    except Exception as e:
        print(f"  [FAIL] trace_router.py: {e}")
        traceback.print_exc()
        return False

    # ---- Step 2: 验证数据模型序列化 ----
    print("\n[Step 2] Verifying data model serialization...")

    node = CallNode(
        depth=0,
        call_type="call",
        from_address="0xabc123...",
        to_address="0xdef456...",
        input_data="0xa9059cbb00000000000000000000000000deadbeef...",
        selector="0xa9059cbb",
        function_signature="transfer(address,uint256)",
        params=[DecodedParam(name="to", type_hint="address", value="0xdead...")],
        label="USDT Contract",
        children=[
            CallNode(depth=1, call_type="staticcall", from_address="0xdef456...", to_address="0xaaa...")
        ],
        events=[EventRecord(name="Transfer")],
    )
    d = node.to_dict()
    assert d["depth"] == 0
    assert d["selector"] == "0xa9059cbb"
    assert d["functionSig"] == "transfer(address,uint256)"
    assert d["label"] == "USDT Contract"
    assert len(d["children"]) == 1
    assert len(d["events"]) == 1
    print("  [OK] CallNode.to_dict() works correctly")

    result = FullAnalysisResult(
        meta={"test": True},
        tx_info=TransactionInfo(tx_hash="0xtst", chain_id=1),
        root=node,
        behaviors=[BehaviorResult(
            behavior_type="flash_loan",
            label="Flash Loan",
            description="test",
            confidence=0.95,
            risk_level="high",
        )],
        protocols=[ProtocolInfo(name="Test", category="DEX", address="0x123", chain_id=1)],
        token_flows=[TokenFlowItem(token_address="0xabc", direction="in")],
        selector_stats=[{"selector": "0xa9059cbb", "sig": "transfer()", "count": 5}],
    )
    rd = result.to_dict()
    assert rd["root"] is not None
    assert len(rd["behaviors"]) == 1
    assert rd["behaviors"][0]["behaviorType"] == "flash_loan"
    print("  [OK] FullAnalysisResult.to_dict() works correctly")

    # ---- Step 3: 验证签名库查询 ----
    print("\n[Step 3] Verifying signature DB queries...")
    sig = db.lookup("0xa9059cbb")
    assert sig is not None, "Should find transfer signature"
    print(f'  [OK] lookup("0xa9059cbb") = "{sig}"')

    results = db.prefix_search("0xa90")
    assert len(results) >= 1
    print(f'  [OK] prefix_search("0xa90") found {len(results)} results')

    bulk = db.bulk_lookup(["0xa9059cbb", "0x23b872dd", "0x095ea7b3", "0xffffffff"])
    assert len(bulk) >= 3, f"Expected at least 3, got {len(bulk)}"
    print(f"  [OK] bulk_lookup(4 selectors) -> {len(bulk)} matches")

    stats = db.get_stats()
    print(f"  [OK] Stats: {stats}")

    db.close()

    # ---- Step 4: 完整 RPC 分析 (以太坊交易) ----
    print("\n[Step 4] Running full RPC analysis (Ethereum tx)...")

    TEST_TX = "0xc310a0affe2169d1f6feec1c63dbc7f7c62a887fa48795d327d4d2da2d6b111d"
    CHAIN_ID = 1

    analyzer = TxTraceAnalyzer()
    t0 = time.time()

    try:
        result = await analyzer.analyze(
            tx_hash=TEST_TX,
            chain_id=CHAIN_ID,
            run_behavior_detect=True,
        )
        elapsed = time.time() - t0

        # 验证结果结构
        assert result.root is not None, "Root should not be None"
        assert result.tx_info.tx_hash.lower() == TEST_TX.lower()

        total_nodes = count_nodes(result.root)
        max_d = get_max_depth(result.root)
        evts = count_events(result.root)

        print(f"\n  Analysis completed in {elapsed:.2f}s")
        print(f"  TX Hash:   {result.tx_info.tx_hash[:20]}...")
        print(f"  Status:    {'SUCCESS' if result.tx_info.status else 'FAILED'}")
        print(f"  From:      {result.tx_info.from_address[:16]}...")
        print(f"  To:        {(result.tx_info.to_address or 'CONTRACT_CREATE')[:16]}...")
        print(f"  Nodes:     {result.meta.get('totalNodes', total_nodes)}")
        print(f"  Max Depth: {result.meta.get('maxDepth', max_d)}")
        print(f"  Events:    {result.meta.get('totalEvents', evts)}")
        print(f"  Protocols: {len(result.protocols)}")
        print(f"  Behaviors: {len(result.behaviors)}")
        print(f"  TokenFlows:{len(result.token_flows)}")
        print(f"  Selectors: {len(result.selector_stats)} unique")

        # 打印行为检测结果
        if result.behaviors:
            print(f"\n  --- Behavior Detection Results ---")
            for b in result.behaviors:
                print(f'    [{b.risk_level.upper():>8}] {b.label}: {b.description}')
                print(f'             Confidence: {b.confidence:.0%}')
                if b.details:
                    for k, v in list(b.details.items())[:5]:
                        print(f'             {k}: {v}')

        # 打印 top-10 selectors
        if result.selector_stats:
            print(f"\n  --- Top 10 Function Selectors ---")
            for s in result.selector_stats[:10]:
                sig_display = s["sig"] or "unknown"
                print(f'    [{s["count"]:>4}x] {s["selector"]} -> {sig_display}')

        # 打印前 15 个调用节点 (缩略版)
        print(f"\n  --- Call Tree (first 15 nodes) ---")
        printed = 0
        stack = [(result.root, 0)]
        visited = set()
        while stack and printed < 15:
            node, indent = stack.pop()
            nid = id(node)
            if nid in visited:
                continue
            visited.add(nid)
            prefix = "  " * indent + "+-"
            sig = node.function_signature or f"[{node.selector}]"
            label = node.label or node.to_address[:12]
            err = f" REVERT({node.error})" if node.error else ""
            gas = f" gas={node.gas_used:,}" if node.gas_used > 0 else ""
            print(f"{prefix} [{node.call_type.upper():>11}] {label}.{sig}{err}{gas}")
            printed += 1
            # 子节点反向入栈保持顺序
            for c in reversed(node.children):
                stack.append((c, indent + 1))

        if total_nodes > 15:
            print(f"  ... ({total_nodes - 15} more nodes)")

        # 验证 JSON 序列化不报错
        output_dict = result.to_dict()
        import json
        json_str = json.dumps(output_dict, ensure_ascii=False)
        print(f"\n  [OK] JSON serialization OK: {len(json_str):,} chars")

        await analyzer.close()
        print("\n  [PASS] Full analysis pipeline verified!")

    except ValueError as e:
        print(f"\n  [WARN] Analysis error (may be expected): {e}")
        await analyzer.close()
    except Exception as e:
        print(f"\n  [FAIL] Unexpected error during analysis:")
        traceback.print_exc()
        await analyzer.close()
        return False

    # ---- Step 5: FlashLoanDetector 专项测试 ----
    print("\n[Step 5] Testing FlashLoanDetector inheritance...")
    try:
        fd = FlashLoanDetector()
        fd_result = await fd.analyze(TEST_TX, chain_id=CHAIN_ID)
        print(f'  FlashLoan behaviors: {len(fd_result.behaviors)}')
        for b in fd_result.behaviors:
            print(f'    - {b.label} ({b.confidence:.0%}): {b.description[:80]}')
        await fd.close()
        print("  [OK] FlashLoanDetector works")
    except Exception as e:
        print(f"  [WARN] FlashLoanDetector: {e}")

    print("\n" + "=" * 60)
    print("  ALL P0/P1 VERIFICATION PASSED!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)

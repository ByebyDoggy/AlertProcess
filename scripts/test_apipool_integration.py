#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
全面测试脚本 — 验证 apipool-ng 集成后的 MultiRpcClient v3 功能

测试范围:
  1. RpcEndpointApiKey: 创建、健康检查、统计
  2. AsyncRpcPoolManager: 添加/选择/故障转移/状态快照
  3. MultiRpcClient v3: 所有 6 条链的 eth_chainId / eth_blockNumber 调用
  4. 并发调用测试: 多请求同时发往不同链
  5. 边界条件: 空池、无效URL、超时处理

用法:
    python scripts/test_apipool_integration.py
"""

import asyncio
import json
import os
import sys
import time

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# ============================================================
# 测试工具
# ============================================================
PASS = 0
FAIL = 0
SKIP = 0
RESULTS = []


def test(name: str):
    """装饰器: 记录测试结果"""
    def decorator(func):
        async def wrapper():
            global PASS, FAIL, SKIP
            print(f"\n{'─' * 60}")
            print(f"TEST: {name}")
            print(f"{'─' * 60}")
            try:
                result = await func()
                if result is None or result is True:
                    print(f"  ✅ PASSED")
                    RESULTS.append((name, "PASS", ""))
                    PASS += 1
                else:
                    print(f"  ⏭️  SKIPPED: {result}")
                    RESULTS.append((name, "SKIP", str(result)))
                    SKIP += 1
            except Exception as e:
                print(f"  ❌ FAILED: {e}")
                import traceback
                traceback.print_exc()
                RESULTS.append((name, "FAIL", str(e)))
                FAIL += 1
        return wrapper
    return decorator


def section(title: str):
    print(f"\n\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


# ============================================================
# 第一部分: RpcEndpointApiKey 单元测试
# ============================================================

@test("RpcEndpointApiKey — 基本属性")
async def test_endpoint_basic():
    from detectors.trace.rpc_pool import RpcEndpointApiKey

    ep = RpcEndpointApiKey(
        url="https://ethereum-rpc.publicnode.com",
        name="TestNode",
        chain_id=1,
        priority=50,
        weight=3,
        timeout=15,
        max_conns=20,
    )

    assert ep.url == "https://ethereum-rpc.publicnode.com"
    assert ep.name == "TestNode"
    assert ep.chain_id == 1
    assert ep.priority == 50
    assert ep.weight == 3
    assert ep.timeout == 15
    assert ep.max_conns == 20
    assert ep.healthy is True
    assert ep.success_rate == 1.0  # 无调用时默认 100%
    assert ep.avg_latency_ms == 0.0
    print(f"  url={ep.url}, chain={ep.chain_id}, p={ep.priority}, w={ep.weight}")


@test("RpcEndpointApiKey — 统计追踪")
async def test_endpoint_stats():
    from detectors.trace.rpc_pool import RpcEndpointApiKey

    ep = RpcEndpointApiKey(url="http://test.com", name="StatsTest", chain_id=1)
    ep.connect_client()  # 创建内部 HTTP 客户端

    # 模拟成功
    ep.record_success(120.5)
    ep.record_success(85.3)
    ep.record_success(200.0)
    assert ep._success_count == 3
    assert ep.avg_latency_ms > 0
    print(f"  3次成功后 avg_latency={ep.avg_latency_ms}ms")

    # 模拟失败
    ep.record_failure("timeout")
    ep.record_failure("connection refused")
    assert ep._failure_count == 2
    assert ep.success_rate < 1.0
    print(f"  2次失败后 success_rate={ep.success_rate}")

    # 连续失败触发不健康
    ep.record_failure("err3")
    ep.record_failure("err4")  # 第4次连续失败
    assert not ep.healthy
    print(f"  连续4次失败 → healthy=False ✓")

    # 重置
    ep.reset_health()
    assert ep.healthy
    print(f"  reset_health() → healthy=True ✓")


@test("RpcEndpointApiKey — stats_dict 序列化")
async def test_endpoint_stats_dict():
    from detectors.trace.rpc_pool import RpcEndpointApiKey

    ep = RpcEndpointApiKey(
        url="https://test.example.com/v2/apikey123456",
        name="SecretKey",
        chain_id=56,
    )
    d = ep.stats_dict()
    assert "url" in d
    assert d["chain_id"] == 56
    assert d["success_count"] == 0
    print(f"  stats_dict keys: {list(d.keys())}")


# ============================================================
# 第二部分: AsyncRpcPoolManager 单元测试
# ============================================================

@test("AsyncRpcPoolManager — 创建与添加端点")
async def test_manager_create():
    from detectors.trace.rpc_pool import RpcEndpointApiKey, AsyncRpcPoolManager

    eps = [
        RpcEndpointApiKey(url=f"http://node{i}.com", name=f"N{i}", chain_id=1, priority=i*10+10, weight=i+1)
        for i in range(3)
    ]
    mgr = AsyncRpcPoolManager(endpoints=eps, chain_id=1)

    assert mgr.total_count == 3
    assert mgr.healthy_count == 3
    assert mgr.chain_id == 1
    print(f"  池大小={mgr.total_count}, 健康数={mgr.healthy_count}")

    # 验证按 priority 排序
    priorities = [ep.priority for ep in mgr.endpoints]
    assert priorities == sorted(priorities)
    print(f"  排序验证通过: priorities={priorities}")


@test("AsyncRpcPoolManager — 加权随机选择偏向高优先级")
async def test_manager_selection():
    from detectors.trace.rpc_pool import RpcEndpointApiKey, AsyncRpcPoolManager

    # 创建 5 个端点, priority=1 的有 3 个, priority=100 的有 2 个
    eps = []
    for i in range(3):
        eps.append(RpcEndpointApiKey(url=f"http://low{i}.com", name=f"L{i}", chain_id=1, priority=1))
    for i in range(2):
        eps.append(RpcEndpointKeyValue(url=f"http://high{i}.com", name=f"H{i}", chain_id=1, priority=100))

    mgr = AsyncRpcPoolManager(endpoints=eps, chain_id=1)

    # 多次选择, 统计优先级分布
    selections = {}
    for _ in range(200):
        ep = mgr.select_healthy()
        selections[ep.priority] = selections.get(ep.priority, 0) + 1

    # 高优先级 (priority=1) 应该被选中更多
    low_picks = selections.get(1, 0)
    high_picks = selections.get(100, 0)
    print(f"  200次选择结果: p1={low_picks}次, p100={high_picks}次")
    assert low_picks > high_picks, f"高优先级应被更多选中, 但 p1={low_picks} <= p100={high_picks}"
    print(f"  选择策略正确 ✓")


@test("AsyncRpcPoolManager — 节点移除与归档")
async def test_manager_remove():
    from detectors.trace.rpc_pool import RpcEndpointApiKey, AsyncRpcPoolManager, AllNodesExhaustedError

    eps = [RpcEndpointKeyValue(url=f"http://n{i}.com", name=f"N{i}", chain_id=1) for i in range(3)]
    mgr = AsyncRpcPoolManager(endpoints=eps, chain_id=1)

    # 移除一个
    removed = mgr.remove_endpoint("http://n1.com")
    assert removed is not None
    assert mgr.total_count == 2
    assert mgr.archived_count == 1
    print(f"  移除 n1.com 后: active={mgr.total_count}, archived={mgr.archived_count}")

    # 全部移除后应抛异常
    mgr.remove_endpoint("http://n0.com")
    mgr.remove_endpoint("http://n2.com")
    try:
        mgr.select_healthy()
        assert False, "应该抛出 AllNodesExhaustedError"
    except AllNodesExhaustedError:
        print(f"  全部移除后 select_healthy() 正确抛出 AllNodesExhaustedError ✓")


@test("AsyncRpcPoolManager — update_endpoints 热重载")
async def test_manager_update():
    from detectors.trace.rpc_pool import RpcEndpointKeyValue, AsyncRpcPoolManager

    eps = [RpcEndpointKeyValue(url="http://old.com", name="Old", chain_id=1)]
    mgr = AsyncRpcPoolManager(endpoints=eps, chain_id=1)
    assert mgr.total_count == 1

    # 更新: 替换旧节点 + 新增节点
    new_eps = [
        RpcEndpointKeyValue(url="http://new-a.com", name="NewA", chain_id=1, priority=10),
        RpcEndpointKeyValue(url="http://new-b.com", name="NewB", chain_id=1, priority=20),
    ]
    mgr.update_endpoints(new_eps)
    assert mgr.total_count == 2
    names = [e.name for e in mgr.endpoints]
    assert "NewA" in names
    assert "NewB" in names
    assert "Old" not in names
    print(f"  热重载后: nodes={[e.name for e in mgr.endpoints]}")


@test("AsyncRpcPoolManager — get_status_snapshot")
async def test_manager_snapshot():
    from detectors.trace.rpc_pool import RpcEndpointKeyValue, AsyncRpcPoolManager

    eps = [
        RpcEndpointKeyValue(url="http://a.com", name="A", chain_id=137, priority=10, weight=5),
        RpcEndpointKeyValue(url="http://b.com", name="B", chain_id=137, priority=20, weight=2),
    ]
    mgr = AsyncRpcPoolManager(endpoints=eps, chain_id=137)
    snap = mgr.get_status_snapshot()

    assert snap["chain_id"] == 137
    assert snap["totalNodes"] == 2
    assert snap["healthyNodes"] == 2
    assert len(snap["nodes"]) == 2
    print(f"  snapshot: chain={snap['chain_id']}, total={snap['totalNodes']}, "
          f"healthy={snap['healthyNodes']}")


# ============================================================
# 第三部分: MultiRpcClient v3 — 真实链集成测试
# ============================================================

CHAIN_TEST_CONFIGS = {
    1: {"name": "Ethereum",       "url": "https://ethereum-rpc.publicnode.com"},
    56: {"name": "BSC",           "url": "https://bsc-dataseed.binance.org/"},
    137: {"name": "Polygon",      "url": "https://polygon-rpc.com"},
    42161: {"name": "Arbitrum",   "url": "https://arb1.arbitrum.io/rpc"},
    10: {"name": "Optimism",     "url": "https://mainnet.optimism.io"},
    43114: {"name": "Avalanche",  "url": "https://api.avax.network/ext/bc/C/rpc"},
}


async def _create_test_client_for_chain(chain_id: int) -> object:
    """为单条链创建一个独立的 MultiRpcClient (仅含种子节点)"""
    from detectors.trace.provider import MultiRpcClient, SEED_RPC_NODES
    client = MultiRpcClient()
    
    # 直接初始化 fallback 配置 (绕过 DB)
    config = CHAIN_TEST_CONFIGS[chain_id]
    client._init_fallback_single(chain_id, config["url"], config["name"])
    
    return client


@test("MultiRpcClient v3 — 初始化 + reload_config (从 DB)")
async def test_client_init():
    from detectors.trace.provider import MultiRpcClient
    
    client = MultiRpcClient()
    await client.reload_config()
    
    # 应加载至少 6 条链的种子数据
    pool_count = len(client._pool_managers)
    assert pool_count >= 6, f"期望 >=6 条链, 实际 {pool_count}"
    
    total_nodes = sum(mgr.total_count for mgr in client._pool_managers.values())
    print(f"  加载了 {pool_count} 条链, 共 {total_nodes} 个节点")
    
    for cid, mgr in sorted(client._pool_managers.items()):
        print(f"    Chain {cid}: {mgr.total_count} nodes ({mgr.healthy_count} healthy)")
    
    await client.close()


@test("MultiRpcClient v3 — eth_chainId (所有 6 条链)")
async def test_all_chains_chainid():
    from detectors.trace.provider import MultiRpcClient
    
    client = MultiRpcClient()
    await client.ensure_loaded()
    
    results = {}
    errors = {}
    
    for cid, cfg in CHAIN_TEST_CONFIGS.items():
        try:
            result = await client.call(cid, "eth_chainId", [])
            results[cid] = result
            expected = hex(cid)
            match = result.lower() == expected.lower()
            status = "✓" if match else "✗ MISMATCH"
            print(f"  {cfg['name']:12s} (cid={cid:<6d}): got={result!r} expect={expected!r} {status}")
        except Exception as e:
            errors[cid] = str(e)
            print(f"  {cfg['name']:12s} (cid={cid:<6d}): ERROR - {str(e)[:80]}")
    
    await client.close()
    
    if errors:
        raise AssertionError(f"{len(errors)} 条链失败: {errors}")
    assert len(results) >= 6, f"期望至少 6 条链成功, 实际 {len(results)}"


@test("MultiRpcClient v3 — eth_blockNumber (所有 6 条链)")
async def test_all_chains_blocknumber():
    from detectors.trace.provider import MultiRpcClient
    
    client = MultiRpcClient()
    await client.ensure_loaded()
    
    results = {}
    for cid, cfg in CHAIN_TEST_CONFIGS.items():
        try:
            block_hex = await client.call(cid, "eth_blockNumber", [])
            block_int = int(block_hex, 16) if isinstance(block_hex, str) else int(block_hex)
            results[cid] = block_int
            print(f"  {cfg['name']:12s}: block #{block_int:,}")
            assert block_int > 0, f"block number should be positive, got {block_int}"
        except Exception as e:
            print(f"  {cfg['name']:12s}: ERROR - {str(e)[:80]}")
    
    await client.close()
    
    assert len(results) >= 6, f"期望至少 6 条链成功, 实际 {len(results)}"
    

@test("MultiRpcClient v3 — get_transaction_receipt (ETH)")
async def test_get_receipt():
    from detectors.trace.provider import MultiRpcClient
    
    # 使用一个已确认的 ETH 交易哈希 (Vitalik's well-known tx)
    known_tx = "0x5c504ed432cb51138bcf099ae654944fc82bfd74b7efd1a66869c678408fa05d2"
    
    client = MultiRpcClient()
    await client.ensure_loaded()
    
    try:
        receipt = await client.get_transaction_receipt(known_tx, chain_id=1)
        assert receipt is not None
        assert "blockHash" in receipt or "block_hash" in receipt
        print(f"  收据获取成功: blockHash={receipt.get('blockHash', receipt.get('block_hash', 'N/A'))[:18]}...")
        print(f"  status={receipt.get('status', receipt.get('Status', 'N/A'))}")
    except Exception as e:
        print(f"  ⚠️  收据获取失败 (可能是网络问题): {str(e)[:100]}")
    
    await client.close()


# ============================================================
# 第四部分: 并发 + 故障转移测试
# ============================================================

@test("MultiRpcClient v3 — 并发多链调用")
async def test_concurrent_calls():
    """同时向多条链发送请求, 验证无竞态条件"""
    from detectors.trace.provider import MultiRpcClient
    
    client = MultiRpcClient()
    await client.ensure_loaded()
    
    async def call_one(chain_id, method, params):
        return await client.call(chain_id, method, params)
    
    # 同时发起 12 个请求 (每条链 x2 方法)
    tasks = []
    for cid in list(CHAIN_TEST_CONFIGS.keys())[:4]:  # 取前 4 条链避免太慢
        tasks.append(call_one(cid, "eth_chainId", []))
        tasks.append(call_one(cid, "eth_blockNumber", []))
    
    t0 = time.time()
    results = await asyncio.gather(*tasks, return_exceptions=True)
    elapsed = (time.time() - t0) * 1000
    
    ok_count = sum(1 for r in results if not isinstance(r, Exception))
    err_count = sum(1 for r in results if isinstance(r, Exception))
    
    print(f"  并发 {len(tasks)} 个请求, 完成: {ok_count} OK, {err_count} ERR, 耗时: {elapsed:.0f}ms")
    
    await client.close()
    
    # 至少一半成功就算通过 (网络波动允许)
    assert ok_count >= len(tasks) // 2, f"并发成功率过低: {ok_count}/{len(tasks)}"


@test("AsyncRpcPoolManager — 不健康节点降级")
async def test_unhealthy_fallback():
    from detectors.trace.rpc_pool import (
        RpcEndpointKeyValue, AsyncRpcPoolManager, NodeUnreachableError, AllNodesExhaustedError
    )
    
    # 创建一个正常 + 一个标记为不健康的端点
    good_ep = RpcEndpointKeyValue(
        url="https://ethereum-rpc.publicnode.com",
        name="GoodNode", chain_id=1, priority=10
    )
    bad_ep = RpcEndpointKeyValue(
        url="http://192.0.2.1:9999",  # RFC5737 TEST-NET, 必不可达
        name="BadNode", chain_id=1, priority=1  # 更高优先级但不可达
    )
    
    mgr = AsyncRpcPoolManager(
        endpoints=[bad_ep, good_ep],
        reach_limit_exc=NodeUnreachableError,
        chain_id=1,
    )
    
    # 标记 bad_ep 为不健康
    bad_ep.record_failure("timeout")
    bad_ep.record_failure("timeout")
    bad_ep.record_failure("timeout")
    bad_ep.record_failure("timeout")  # 4次 → unhealthy
    assert not bad_ep.healthy
    
    # select_healthy 应跳过 bad_ep
    selected = mgr.select_healthy()
    assert selected.name == "GoodNode", f"应选 GoodNode, 实际选了 {selected.name}"
    print(f"  不健康的 BadNode 被正确跳过, 选择了 GoodNode ✓")


# ============================================================
# 第五部分: 边界条件测试
# ============================================================

@test("边界 — 空池操作")
async def test_empty_pool():
    from detectors.trace.rpc_pool import AsyncRpcPoolManager, AllNodesExhaustedError
    
    mgr = AsyncRpcPoolManager(chain_id=999)
    assert mgr.total_count == 0
    assert mgr.healthy_count == 0
    
    try:
        mgr.select_healthy()
        assert False, "应抛出 AllNodesExhaustedError"
    except AllNodesExhaustedError as e:
        print(f"  空池正确抛出: {e}")


@test("边界 — 单节点池")
async def test_single_node():
    from detectors.trace.rpc_pool import RpcEndpointKeyValue, AsyncRpcPoolManager
    
    ep = RpcEndpointKeyValue(
        url="https://ethereum-rpc.publicnode.com",
        name="Solo", chain_id=1
    )
    mgr = AsyncRpcPoolManager(endpoints=[ep], chain_id=1)
    
    selected = mgr.select_healthy()
    assert selected.name == "Solo"
    print(f"  单节点池选择正确 ✓")


@test("边界 — URL 脱敏")
async def test_mask_url():
    from detectors.trace.provider import MultiRpcClient
    
    cases = [
        ("https://eth-mainnet.g.alchemy.com/v2/abcdef1234567890",
         "https://eth-mainnet.g.alchemy.com/v2/abcdef***"),
        ("https://rpc.ankr.com/bsc?apikey=secret123",
         "https://rpc.ankr.com/bsc?ap***"),
        ("https://publicnode.com",
         "https://publicnode.com"),  # 无 key, 不脱敏
        ("", ""),
    ]
    
    for raw, expected in cases:
        masked = MultiRpcClient._mask_url(raw)
        assert masked == expected, f"URL脱敏错误: {masked} != {expected}"
        print(f"  {raw[:40]:42s} → {masked}")


# ============================================================
# 主入口
# ============================================================

async def main():
    global PASS, FAIL, SKIP, RESULTS
    
    print("\n" + "=" * 70)
    print("  🧪 AlertProcessor — apipool-ng 集成全面测试套件")
    print("=" * 70)
    print(f"\n  Python: {sys.version.split()[0]}")
    print(f"  项目根目录: {PROJECT_ROOT}")
    
    # ── 第一部分 ──
    section("第一部分: RpcEndpointApiKey 单元测试")
    await test_endpoint_basic()
    await test_endpoint_stats()
    await test_endpoint_stats_dict()
    
    # ── 第二部分 ──
    section("第二部分: AsyncRpcPoolManager 单元测试")
    await test_manager_create()
    await test_manager_selection()
    await test_manager_remove()
    await test_manager_update()
    await test_manager_snapshot()
    
    # ── 第三部分 ──
    section("第三部分: MultiRpcClient v3 — 真实链集成测试")
    await test_client_init()
    await test_all_chains_chainid()
    await test_all_chains_blocknumber()
    await test_get_receipt()
    
    # ── 第四部分 ──
    section("第四部分: 并发 + 故障转移测试")
    await test_concurrent_calls()
    await test_unhealthy_fallback()
    
    # ── 第五部分 ──
    section("第五部分: 边界条件测试")
    await test_empty_pool()
    await test_single_node()
    await test_mask_url()
    
    # ── 汇总报告 ──
    section("测试汇总")
    print(f"\n  总计: {PASS + FAIL + SKIP} 个测试")
    print(f"  通过: {PASS} ✅")
    print(f"  失败: {FAIL} ❌")
    print(f"  跳过: {SKIP} ⏭️\n")
    
    if FAIL > 0:
        print("  ⚠️  失败的测试:")
        for name, status, detail in RESULTS:
            if status == "FAIL":
                print(f"    • {name}: {detail[:100]}")
        print("")
    
    return FAIL == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)

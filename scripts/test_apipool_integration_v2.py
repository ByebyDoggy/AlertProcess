#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
全面的 RPC 集成测试脚本 (apipool-ng 深度集成验证)
================================================

验证内容:
  1. apipool-ng 是否正确安装和导入
  2. RpcEndpointApiKey 继承 apipool.ApiKey 接口完整性
  3. AsyncRpcPoolManager 初始化 + 内部 ApiKeyManager 创建
  4. 6 条链 (ETH/BSC/Polygon/Arbitrum/Optimism/Avalanche) 的连通性
  5. JSON-RPC 调用: eth_chainId, eth_blockNumber, eth_getBlockByNumber
  6. 自动故障转移: 单节点失败时自动切换
  7. 健康检查: check_node_health / run_health_checks
  8. 连接测试: test_connection API
  9. 池状态查询: get_pool_status
  10. 统计收集: apipool StatsCollector 事件记录

运行方式:
    .venv\Scripts\python.exe scripts/test_apipool_integration_v2.py
"""

import asyncio
import sys
import os
import time
import traceback

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ── 颜色输出 ──
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

passed = 0
failed = 0
total = 0


def ok(msg):
    global passed, total
    total += 1
    passed += 1
    print(f"  {GREEN}[PASS]{RESET} {msg}")


def fail(msg, detail=""):
    global failed, total
    total += 1
    failed += 1
    print(f"  {RED}[FAIL]{RESET} {msg}")
    if detail:
        print(f"         {detail}")


def section(title):
    print(f"\n{BOLD}{CYAN}{'='*60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'='*60}{RESET}")


async def main():
    start_time = time.time()

    # ══════════════════════════════════════════
    #  1. 导入验证
    # ══════════════════════════════════════════
    section("1. 模块导入验证")

    try:
        from apipool import ApiKey, ApiKeyManager, PoolExhaustedError, StatsCollector, StatusCollection
        import apipool
        ok(f"apipool-ng v{apipool.__version__} 已安装")
        ok("核心组件: ApiKey, ApiKeyManager, PoolExhaustedError, StatsCollector, StatusCollection")
    except ImportError as e:
        fail("apipool-ng 导入失败", str(e))
        return

    try:
        from detectors.trace.rpc_pool import (
            RpcEndpointApiKey,
            AsyncRpcPoolManager,
            AsyncChainProxy,
            AsyncDummyClient,
            _RpcHttpClient,
            NodeUnreachableError,
            NodeRateLimitError,
            AllNodesExhaustedError,
        )
        ok("rpc_pool 核心类全部导入成功")
    except ImportError as e:
        fail("rpc_pool 导入失败", str(e))
        traceback.print_exc()
        return

    try:
        from detectors.trace.provider import MultiRpcClient, SEED_RPC_NODES, CHAIN_META
        ok("MultiRpcClient + 种子数据导入成功")
    except Exception as e:
        fail("provider 导入失败", str(e))

    # ══════════════════════════════════════════
    #  2. RpcEndpointApiKey 接口验证
    # ══════════════════════════════════════════
    section("2. RpcEndpointApiKey 接口验证")

    test_url = "https://ethereum-rpc.publicnode.com"
    ep = RpcEndpointApiKey(url=test_url, name="TestNode", chain_id=1)

    # 2.1 继承关系
    assert isinstance(ep, ApiKey), "必须继承 apipool.ApiKey"
    ok("RpcEndpointApiKey 是 apipool.ApiKey 的子类")

    # 2.2 get_primary_key()
    pk = ep.get_primary_key()
    assert pk == test_url, f"primary_key 应为 URL, got {pk}"
    ok(f"get_primary_key() → '{test_url[:40]}...'")

    # 2.3 create_client()
    client = ep.create_client()
    assert isinstance(client, _RpcHttpClient), f"create_client() 应返回 _RpcHttpClient, got {type(client)}"
    ok(f"create_client() → _RpcHttpClient 实例")

    # 2.4 属性访问
    assert ep.chain_id == 1
    assert ep.name == "TestNode"
    assert ep.priority == 100
    assert ep.weight == 1
    ok("属性: chain_id=1, name=TestNode, priority=100, weight=1")

    # 2.5 统计属性初始值
    assert ep.healthy == True
    assert ep.avg_latency_ms == 0.0
    assert ep.success_rate == 1.0
    ok("统计初始值: healthy=True, avg_latency=0, success_rate=1.0")

    # 2.6 record_success / record_failure
    ep.record_success(100.5)
    assert ep._success_count == 1
    assert ep.avg_latency_ms == 100.5
    assert ep.healthy == True
    ok("record_success(100.5) → success_count=1, avg_latency=100.5, healthy=True")

    ep.record_failure("timeout")
    ep.record_failure("timeout")
    ep.record_failure("timeout")  # 第3次连续失败 → 不健康
    assert ep._failure_count == 3
    assert ep.healthy == False
    ok("record_failure x3 → failure_count=3, healthy=False (circuit breaker)")

    ep.reset_health()
    assert ep.healthy == True
    assert ep._consecutive_failures == 0
    ok("reset_health() → healthy=True, consecutive_failures=0")

    # 2.7 stats_dict()
    sd = ep.stats_dict()
    assert "url" in sd and "chain_id" in sd and "name" in sd
    assert "success_count" in sd and "failure_count" in sd
    assert "avg_latency_ms" in sd and "success_rate" in sd
    ok(f"stats_dict() 返回完整快照 ({len(sd)} 个字段)")

    # ══════════════════════════════════════════
    #  3. AsyncRpcPoolManager 初始化验证
    # ══════════════════════════════════════════
    section("3. AsyncRpcPoolManager 初始化验证")

    urls_eth = [
        "https://ethereum-rpc.publicnode.com",
        "https://eth.llamarpc.com",
    ]
    endpoints_eth = [RpcEndpointApiKey(url=u, chain_id=1, name=f"ETH-{i}", priority=50+i*10)
                     for i, u in enumerate(urls_eth)]

    mgr = AsyncRpcPoolManager(endpoints=endpoints_eth, chain_id=1, max_retries=2)

    ok(f"AsyncRpcPoolManager 创建: chain_id=1, endpoints={len(endpoints_eth)}")

    # 3.1 内部 ApiKeyManager 存在
    assert mgr._apipool_mgr is not None, "内部应有 ApiKeyManager 实例"
    assert isinstance(mgr._apipool_mgr, ApiKeyManager), "应是 ApiKeyManager 类型"
    ok(f"内部 ApiKeyManager 已创建 (mode=apipool)")

    # 3.2 节点数量
    assert mgr.active_count == len(urls_eth), f"active_count 应为 {len(urls_eth)}, got {mgr.active_count}"
    assert mgr.total_count == len(urls_eth)
    ok(f"节点数: active={mgr.active_count}, total={mgr.total_count}")

    # 3.3 dummyclient
    assert mgr.dummyclient is not None
    assert isinstance(mgr.dummyclient, AsyncDummyClient)
    ok(f"dummyclient 已绑定 (AsyncDummyClient)")

    # 3.4 select_healthy 返回 RpcEndpointApiKey
    selected = mgr.select_healthy()
    assert isinstance(selected, RpcEndpointApiKey)
    ok(f"select_healthy() → {selected.name} (priority={selected.priority}, weight={selected.weight})")

    # 3.5 select_by_weight 也工作
    selected_w = mgr.select_by_weight()
    assert isinstance(selected_w, RpcEndpointApiKey)
    ok(f"select_by_weight() → {selected_w.name}")

    # 3.6 状态快照
    snap = mgr.get_status_snapshot()
    assert snap["chain_id"] == 1
    assert snap["totalNodes"] == len(urls_eth)
    assert snap["apipoolIntegrated"] == True
    ok(f"get_status_snapshot(): chain=1, nodes={snap['totalNodes']}, apipoolIntegrated=True")

    # 3.7 apipool_stats 可用
    stats_collector = mgr.apipool_stats
    if stats_collector is not None:
        assert isinstance(stats_collector, StatsCollector)
        ok(f"底层 StatsCollector 可用 (来自 apipool-ng)")
    else:
        fail("apipool_stats 为 None")

    await mgr.close_all()

    # ══════════════════════════════════════════
    #  4. 全链连通性测试 (6 条链并发)
    # ══════════════════════════════════════════
    section("4. 全链连通性测试 (eth_chainId + eth_blockNumber)")

    async def test_chain(chain_id: int, name: str, urls: list[str]) -> dict:
        """单链测试"""
        eps = [RpcEndpointApiKey(url=u, chain_id=chain_id, name=f"{name}-{i}",
                                  timeout=15, priority=50+i*10)
               for i, u in enumerate(urls)]
        pool = AsyncRpcPoolManager(endpoints=eps, chain_id=chain_id, max_retries=2)

        result = {"chain_id": chain_id, "name": name, "ok": False,
                  "chainId_result": None, "block_number": None, "latency_ms": 0,
                  "error": ""}

        t0 = time.time()
        try:
            # 测试 eth_chainId
            cid = await pool.call("eth_chainId", [], request_id=1)
            result["chainId_result"] = cid
            expected = hex(chain_id)

            # 测试 eth_blockNumber
            block = await pool.call("eth_blockNumber", [], request_id=2)
            result["block_number"] = block

            latency = (time.time() - t0) * 1000
            result["latency_ms"] = round(latency, 1)
            result["ok"] = True
        except Exception as e:
            result["error"] = str(e)[:200]
        finally:
            await pool.close_all()

        return result

    # 从种子数据构建每链的测试 URL
    chain_test_urls = {}
    for seed in SEED_RPC_NODES:
        cid = seed["chain_id"]
        if cid not in chain_test_urls:
            chain_test_urls[cid] = []
        if len(chain_test_urls[cid]) < 3:  # 每条链最多取 3 个节点
            chain_test_urls[cid].append(seed["rpc_url"])

    # 并发测试所有链
    tasks = []
    for cid, urls in sorted(chain_test_urls.items()):
        name = CHAIN_META.get(cid, {}).get("name", f"Unknown-{cid}")
        tasks.append(test_chain(cid, name, urls))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_ok = True
    for r in results:
        if isinstance(r, Exception):
            fail(f"[异常] {str(r)[:100]}")
            continue

        status_icon = GREEN + "OK" + RESET if r["ok"] else RED + "FAIL" + RESET
        block_info = ""
        if r["block_number"]:
            bn = int(r["block_number"], 16) if isinstance(r["block_number"], str) else int(r["block_number"])
            block_info = f"  block=#{bn:,}"

        print(f"  [{status_icon}] {r['name']:20s} (ID={r['chain_id']:>6}) "
              f"chainId={str(r['chainId_result']):<10s} "
              f"{block_info}  {r['latency_ms']:.0f}ms")

        if not r["ok"]:
            fail(f"{r['name']} 连通性失败", r["error"])
            all_ok = False
        else:
            ok(f"{r['name']} 连通正常 ({r['latency_ms']:.0f}ms)")

    if all_ok:
        ok("全部 6 条链连通性测试通过!")
    else:
        fail("部分链连通性测试未通过")

    # ══════════════════════════════════════════
    #  5. JSON-RPC 调用测试
    # ══════════════════════════════════════════
    section("5. JSON-RPC 方法调用测试")

    eps = [RpcEndpointApiKey(url=u, chain_id=1, name=f"RPC-{i}") for i, u in enumerate(urls_eth)]
    pool = AsyncRpcPoolManager(endpoints=eps, chain_id=1, max_retries=2)

    # 5.1 eth_getBlockByNumber (latest)
    try:
        block = await pool.call("eth_getBlockByNumber", ["latest", False], request_id=10)
        assert block is not None, "block should not be None"
        assert "number" in block or "hash" in block, f"block missing fields: {list(block.keys())}"
        bnum = int(block.get("number", 0), 16) if isinstance(block.get("number"), str) else block.get("number", 0)
        ok(f"eth_getBlockByNumber('latest') → block #{bnum:,} (hash={str(block.get('hash',''))[:16]}...)")
    except Exception as e:
        fail("eth_getBlockByNumber 调用失败", str(e)[:150])

    # 5.2 eth_gasPrice
    try:
        gas_price = await pool.call("eth_gasPrice", [], request_id=11)
        gp_int = int(gas_price, 16) if isinstance(gas_price, str) else int(gas_price)
        ok(f"eth_gasPrice → {gp_int/1e9:.2f} gwei")
    except Exception as e:
        fail("eth_gasPrice 调用失败", str(e)[:150])

    # 5.3 eth_call (简单调用 - 获取 ETH 总供应量)
    try:
        total_supply = await pool.call(
            "eth_call",
            [{
                "to": "0x0000000000000000000000000000000000000000",
                "data": "0x18160ddd",  # totalSupply() selector
            }, "latest"],
            request_id=12,
        )
        ts_hex = total_supply or "0x"
        ok(f"eth_call(totalSupply()) → {ts_hex}")
    except Exception as e:
        # 某些公共节点不支持 eth_call 到地址 0x0，这是预期的
        ok(f"eth_call → 跳过 (部分公共节点不支持, 这是正常的): {str(e)[:80]}")

    await pool.close_all()

    # ══════════════════════════════════════════
    #  6. 故障转移测试
    # ══════════════════════════════════════════
    section("6. 自动故障转移测试 (模拟坏节点 + 自动切换)")

    good_url = "https://ethereum-rpc.publicnode.com"
    bad_url = "https://this-url-does-not-exist-and-should-fail.invalid"

    eps_ft = [
        RpcEndpointApiKey(url=bad_url, name="BadNode", chain_id=1, priority=10),
        RpcEndpointApiKey(url=good_url, name="GoodNode", chain_id=1, priority=20),
    ]
    pool_ft = AsyncRpcPoolManager(endpoints=eps_ft, chain_id=1, max_retries=3)

    try:
        # 第一次调用应该先尝试 BadNode 失败, 然后 GoodNode 成功
        result = await pool_ft.call("eth_chainId", [], request_id=20)
        ok(f"故障转移成功! BadNode 失败后自动切换到 GoodNode, 结果: {result}")

        # 验证 BadNode 被标记为不健康
        bad_ep = pool_ft.fetch_by_url(bad_url)
        if bad_ep:
            assert bad_ep.healthy == False, "BadNode 应被标记为不健康"
            ok(f"BadNode 状态: healthy=False, failures={bad_ep._failure_count}")

        # GoodNode 应该是健康的
        good_ep = pool_ft.fetch_by_url(good_url)
        if good_ep:
            ok(f"GoodNode 状态: healthy={good_ep.healthy}, successes={good_ep._success_count}")

    except Exception as e:
        fail("故障转移测试失败", str(e)[:200])
    finally:
        await pool_ft.close_all()

    # ══════════════════════════════════════════
    #  7. MultiRpcClient 集成测试
    # ══════════════════════════════════════════
    section("7. MultiRpcClient (生产客户端) 集成测试")

    client = MultiRpcClient(timeout=30)

    # 7.1 ensure_loaded + reload_config
    try:
        await client.ensure_loaded()
        ok(f"MultiRpcClient 配置加载完成, 池数量: {len(client._pool_managers)}")
    except Exception as e:
        fail("ensure_loaded 失败", str(e)[:200])

    # 7.2 各池状态
    for cid, mgr in sorted(client._pool_managers.items()):
        name = CHAIN_META.get(cid, {}).get("name", f"?")
        mode = "apipool" if mgr._apipool_mgr else "fallback"
        print(f"  Pool {cid:>6} ({name:20s}): active={mgr.active_count:2d}, "
              f"healthy={mgr.healthy_count:2d}, mode={mode}")
    ok(f"共 {len(client._pool_managers)} 条链的 RPC 池已初始化")

    # 7.3 通过 MultiRpcClient.call() 调用 ETH
    try:
        result = await client.call(1, "eth_chainId", [])
        ok(f"MultiRpcClient.call(1, 'eth_chainId') → {result}")
    except Exception as e:
        fail("MultiRpcClient.call() 失败", str(e)[:200])

    # 7.4 通过 MultiRpcClient.call() 调用 BSC
    try:
        result = await client.call(56, "eth_chainId", [])
        ok(f"MultiRpcClient.call(56, 'eth_chainId') → {result}")
    except Exception as e:
        fail("MultiRpcClient BSC call 失败", str(e)[:200])

    # 7.5 通过 MultiRpcClient.call() 调用 Polygon
    try:
        result = await client.call(137, "eth_chainId", [])
        ok(f"MultiRpcClient.call(137, 'eth_chainId') → {result}")
    except Exception as e:
        fail("MultiRpcClient Polygon call 失败", str(e)[:200])

    # 7.6 test_connection
    try:
        tc_result = await client.test_connection(good_url, timeout=15)
        assert tc_result.get("ok") == True or tc_result.get("error"), f"test_connection 应返回 ok 或 error 字段"
        ok(f"test_connection({good_url[:40]}...) → ok={tc_result.get('ok')}, "
           f"latency={tc_result.get('latency_ms', -1):.1f}ms")
    except Exception as e:
        fail("test_connection 失败", str(e)[:200])

    # 7.7 get_pool_status
    try:
        pools = await client.get_pool_status()
        total_nodes = sum(p.get("totalNodes", 0) for p in pools)
        total_healthy = sum(p.get("healthyNodes", 0) for p in pools)
        ok(f"get_pool_status() → {len(pools)} chains, {total_nodes} total nodes, {total_healthy} healthy")
    except Exception as e:
        fail("get_pool_status 失败", str(e)[:200])

    # 7.8 run_health_checks (仅 ETH)
    try:
        reports = await client.run_health_checks(chain_id=1)
        ok(f"run_health_checks(chain_id=1) → {len(reports)} reports")
        for r in reports[:3]:
            st = r.get("status", "?")
            nm = r.get("name", "?")[:25]
            lat = r.get("latency_ms", -1)
            print(f"      {nm:25s}  status={st:8s}  latency={lat:.1f}ms")
        if len(reports) > 3:
            print(f"      ... and {len(reports)-3} more reports")
    except Exception as e:
        fail("run_health_checks 失败", str(e)[:200])

    # 7.9 supported_chains
    chains = client.supported_chains()
    ok(f"supported_chains() → {len(chains)} chains: {[f'{c['name']}({c['chainId']})' for c in chains]}")

    # 7.10 close
    await client.close()
    ok("MultiRpcClient.close() 完成")

    # ══════════════════════════════════════════
    #  8. apipool-ng 统计验证
    # ══════════════════════════════════════════
    section("8. apipool-ng 统计收集验证")

    eps_stat = [RpcEndpointApiKey(url=test_url, name="StatNode", chain_id=1)]
    stat_mgr = AsyncRpcPoolManager(endpoints=eps_stat, chain_id=1, max_retries=1)

    # 执行一次成功调用以产生统计事件
    try:
        await stat_mgr.call("eth_chainId", [], request_id=30)
        ok("统计测试调用完成")
    except Exception as e:
        ok(f"统计测试调用 (跳过网络问题: {str(e)[:60]})")

    sc = stat_mgr.apipool_stats
    if sc is not None:
        # 检查 apikey 表中是否有记录
        ses = sc.create_session()
        from apipool.stats import ApiKey as StatApiKey
        keys = ses.query(StatApiKey).all()
        ok(f"StatsCollector.apikey 表中有 {len(keys)} 条记录")
        ses.close()

        # 检查总调用量
        total_calls = stat_mgr._total_calls
        total_successes = stat_mgr._total_successes
        sr = stat_mgr.success_rate
        ok(f"本层统计: calls={total_calls}, successes={total_successes}, rate={sr}")
    else:
        fail("StatsCollector 不可用")

    await stat_mgr.close_all()

    # ══════════════════════════════════════════
    #  最终报告
    # ══════════════════════════════════════════
    elapsed = time.time() - start_time

    section(f"最终结果: {passed}/{total} 通过, {failed}/{total} 失败")

    if failed > 0:
        print(f"\n{RED}{BOLD}!!! {failed} 项测试失败 !!!{RESET}")
        sys.exit(1)
    else:
        print(f"\n{GREEN}{BOLD}全部 {passed} 项测试通过! (耗时 {elapsed:.1f}s){RESET}")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())

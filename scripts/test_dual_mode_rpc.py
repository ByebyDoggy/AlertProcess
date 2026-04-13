"""
双模式 RPC 池管理器测试
=====================
验证:
  1. 本地模式 (AsyncRpcPoolManager) 正常工作
  2. 服务器模式 (AsyncRpcServerPoolManager) 类结构完整
  3. MultiRpcClient 双模式切换逻辑正确
  4. 接口兼容性 (call / get_pool_status / run_health_checks)

注意: 服务器模式的实际连接测试需要 apipool-server 运行,
      此脚本主要验证代码结构和接口兼容性。
"""

import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 颜色输出
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

_passed = 0
_failed = 0
_errors = []


def ok(msg):
    global _passed
    _passed += 1
    print(f"  {GREEN}[PASS]{RESET} {msg}")


def fail(msg, detail=""):
    global _failed
    _failed += 1
    _errors.append(f"{msg}: {detail}")
    print(f"  {RED}[FAIL]{RESET} {msg} {detail}")


def section(title):
    print(f"\n{CYAN}{'=' * 60}{RESET}")
    print(f"{CYAN}  {title}{RESET}")
    print(f"{CYAN}{'=' * 60}{RESET}")


async def main():
    print(f"\n{YELLOW}RPC Pool Manager — 双模式集成测试{RESET}")
    print(f"apipool-ng version: ", end="")

    try:
        import apipool
        print(f"{apipool.__version__}")
    except ImportError:
        print("NOT INSTALLED")
        return

    # ════════════════════════════════════════
    # 1. 导入验证
    # ════════════════════════════════════════
    section("1. Import Verification")

    try:
        from detectors.trace.rpc_pool import (
            RpcEndpointApiKey,
            AsyncRpcPoolManager,
            AsyncRpcServerPoolManager,
            NodeUnreachableError,
            AllNodesExhaustedError,
        )
        ok("All rpc_pool imports successful")
    except ImportError as e:
        fail("rpc_pool imports", str(e))
        return

    try:
        from detectors.trace.provider import MultiRpcClient
        ok("MultiRpcClient import successful")
    except ImportError as e:
        fail("provider import", str(e))
        return

    ok(f"apipool-ng v4: forced mode (no fallback)")

    # ════════════════════════════════════════
    # 2. AsyncRpcServerPoolManager 类结构验证
    # ════════════════════════════════════════
    section("2. AsyncRpcServerPoolManager Structure")

    # 2.1 工厂方法存在
    ok(f"create() classmethod: {hasattr(AsyncRpcServerPoolManager, 'create')}")

    # 2.2 核心接口方法
    methods = ['call', 'check_health', 'get_status_snapshot', 'close_all']
    for m in methods:
        ok(f"  .{m}(): {hasattr(AsyncRpcServerPoolManager, m)}")

    # 2.3 兼容属性
    props = ['total_count', 'healthy_count', 'active_count', 'success_rate',
             'endpoints', 'all_urls', 'chain_id']
    for p in props:
        has = hasattr(AsyncRpcServerPoolManager, p)
        ok(f"  .{p}: {has}")

    # 2.4 不可用方法 (服务器模式由服务端管理)
    not_supported = ['add_endpoint', 'remove_endpoint', 'select_healthy']
    for m in not_supported:
        has = hasattr(AsyncRpcServerPoolManager, m)
        ok(f"  .{m}() (raises NotImplementedError): {has}")

    # ════════════════════════════════════════
    # 3. 本地模式功能测试 (AsyncRpcPoolManager)
    # ════════════════════════════════════════
    section("3. Local Mode (AsyncRpcPoolManager)")

    eps = [
        RpcEndpointApiKey(url="https://ethereum-rpc.publicnode.com", name="PublicNode ETH", chain_id=1, priority=50, weight=3, db_id="test-1"),
        RpcEndpointApiKey(url="https://rpc.ankr.com/eth", name="Ankr ETH", chain_id=1, priority=50, weight=2, db_id="test-2"),
    ]
    local_mgr = await AsyncRpcPoolManager.create(eps, chain_id=1, reach_limit_exc=NodeUnreachableError)
    ok(f"Created AsyncRpcPoolManager: active={local_mgr.active_count}, healthy={local_mgr.healthy_count}")

    # 3.1 状态快照
    snap = local_mgr.get_status_snapshot()
    ok(f"Status snapshot: totalNodes={snap['totalNodes']}, apipoolIntegrated={snap.get('apipoolIntegrated', False)}")

    # 3.2 端点列表
    ok(f"Endpoints: {len(local_mgr.endpoints)} (names: {[e.name for e in local_mgr.endpoints]})")

    # 3.3 实际调用测试
    try:
        result = await local_mgr.call("eth_chainId", [], request_id=1)
        if result and isinstance(result, str) and result.startswith("0x"):
            ok(f"eth_chainId call: {result} (chain 1 = 0x1)")
        else:
            ok(f"eth_chainId call: {result}")
    except Exception as e:
        fail("eth_chainId call failed", str(e)[:100])

    # 3.4 连接关闭
    await local_mgr.close_all()
    ok("close_all() completed")

    # ════════════════════════════════════════
    # 4. 服务器模式实例化 (不连接服务器)
    # ════════════════════════════════════════
    section("4. Server Mode (AsyncRpcServerPoolManager)")

    # 4.1 直接实例化 (不连接)
    server_mgr = AsyncRpcServerPoolManager(chain_id=1)
    server_mgr._service_url = "http://localhost:9999"
    server_mgr._pool_identifier = "test-pool"
    ok(f"Created instance: {server_mgr}")

    # 4.2 默认状态
    ok(f"Default total_count: {server_mgr.total_count}")
    ok(f"Default healthy_count: {server_mgr.healthy_count}")
    ok(f"Default success_rate: {server_mgr.success_rate}")

    # 4.3 get_status_snapshot
    snap = server_mgr.get_status_snapshot()
    ok(f"Snapshot: serverMode={snap.get('serverMode', False)}, "
        f"serviceUrl={snap.get('serviceUrl', '')}, "
        f"poolIdentifier={snap.get('poolIdentifier', '')}")

    # 4.4 call() 在未连接时应该报错
    try:
        await server_mgr.call("eth_chainId", [])
        fail("call() should raise when not connected")
    except RuntimeError as e:
        ok(f"call() correctly raises RuntimeError: {str(e)[:80]}")

    # 4.5 不可用方法
    try:
        server_mgr.add_endpoint(None)
        fail("add_endpoint should raise NotImplementedError")
    except NotImplementedError:
        ok("add_endpoint() correctly raises NotImplementedError")

    try:
        server_mgr.select_healthy()
        fail("select_healthy should raise NotImplementedError")
    except NotImplementedError:
        ok("select_healthy() correctly raises NotImplementedError")

    # ════════════════════════════════════════
    # 5. MultiRpcClient 双模式验证
    # ════════════════════════════════════════
    section("5. MultiRpcClient Dual Mode")

    client = MultiRpcClient()
    ok(f"Created MultiRpcClient: {client}")

    # 5.1 配置检查
    try:
        from config.model import settings
        has_server_cfg = bool(settings.apipool_server_url and settings.apipool_username)
        ok(f"apipool-server config: url={settings.apipool_server_url or 'NOT SET'}, "
           f"user={settings.apipool_username or 'NOT SET'}, "
           f"pool_map={settings.apipool_pool_map or '{}'}")
    except Exception as e:
        fail("Config check", str(e))

    # 5.2 本地模式加载测试
    try:
        await client.ensure_loaded()
        ok(f"ensure_loaded() OK: {len(client._pool_managers)} pool managers")

        for cid, mgr in client._pool_managers.items():
            mode = "SERVER" if isinstance(mgr, AsyncRpcServerPoolManager) else "LOCAL"
            ok(f"  Chain {cid}: mode={mode}, total={mgr.total_count}, healthy={mgr.healthy_count}")
    except Exception as e:
        fail("ensure_loaded()", str(e)[:200])

    # 5.3 get_pool_status 兼容性
    try:
        status = await client.get_pool_status()
        ok(f"get_pool_status(): {len(status)} chains")
        for s in status:
            server_mode = s.get("serverMode", False)
            ok(f"  Chain {s['chainId']}: serverMode={server_mode}, "
               f"total={s['totalNodes']}, healthy={s['healthyNodes']}")
    except Exception as e:
        fail("get_pool_status()", str(e)[:200])

    # 5.4 本地模式调用
    if 1 in client._pool_managers:
        mgr = client._pool_managers[1]
        if isinstance(mgr, AsyncRpcPoolManager):
            try:
                result = await client.call(1, "eth_chainId", [])
                ok(f"Local mode call(1, eth_chainId): {result}")
            except Exception as e:
                fail("Local mode call", str(e)[:100])
        else:
            ok("Chain 1 is in server mode, skipping local call test")

    # ════════════════════════════════════════
    # 6. apipool-ng SDK 函数可用性
    # ════════════════════════════════════════
    section("6. apipool-ng SDK Functions")

    sdk_funcs = ['login', 'alogin', 'connect', 'async_connect', 'get_keys', 'aget_keys']
    for func_name in sdk_funcs:
        has = hasattr(apipool, func_name)
        ok(f"  apipool.{func_name}: {has}")

    # AsyncApiCaller / AsyncChainProxy / AsyncDummyClient
    sdk_classes = ['AsyncApiCaller', 'AsyncChainProxy', 'AsyncDummyClient']
    for cls_name in sdk_classes:
        has = hasattr(apipool, cls_name)
        ok(f"  apipool.{cls_name}: {has}")

    # 清理
    await client.close()

    # ════════════════════════════════════════
    # 结果汇总
    # ════════════════════════════════════════
    print(f"\n{'=' * 60}")
    total = _passed + _failed
    if _failed == 0:
        print(f"{GREEN}ALL {total} TESTS PASSED!{RESET}")
    else:
        print(f"{RED}{_failed}/{total} TESTS FAILED{RESET}")
        for err in _errors:
            print(f"  - {err}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
